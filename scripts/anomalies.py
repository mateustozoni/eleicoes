"""Dossiês locais com evidência dos arquivos originais, sem presumir causa ou irregularidade."""
import collections
import hashlib
import html
import json
import pathlib
import re
import sqlite3
from datetime import datetime
import asn1tools
from analyze import BASE,logs,process,section_vota
from collect import select_hash

ROOT=pathlib.Path(__file__).resolve().parents[1]

def clean(s):
    return re.sub(r'(?<!\d)\d{11,12}(?!\d)','[identificador omitido]',s)

def load(key):
    uf,m,z,s=key.split('/');c=sqlite3.connect(str(ROOT/'data/raw'/(uf+'.sqlite')))
    base=f'{BASE}/dados/{uf}/{m}/{z}/{s}';url=f'{base}/p003221-{uf}-m{m}-z{z}-s{s}-aux.json'
    aux=json.loads(c.execute('SELECT payload FROM files WHERE url=?',(url,)).fetchone()[0]);h=select_hash(aux)
    name=c.execute('SELECT name FROM sections WHERE id=?',(key,)).fetchone()[0]
    bu=None;blobs=[];sources=[]
    for a in h['arq']:
        if a['tp'] not in ('bu','busa','log','logsa'):continue
        source=f"{base}/{h['hash']}/{a['nm']}"
        b,sha=c.execute('SELECT payload,sha256 FROM files WHERE url=?',(source,)).fetchone()
        sources.append(dict(url=source,name=a['nm'],sha256=sha,type=a['tp']))
        if a['tp'] in ('bu','busa'):bu=b
        else:blobs.append(b)
    c.close()
    return (key,name,bu,blobs,url,h['st']),sources,h['hash']

def inspect(key):
    item,sources,hash_=load(key)
    path=ROOT/'output/cases'/(key.replace('/','_')+'.json');path.parent.mkdir(exist_ok=True)
    if path.exists():
        old=json.loads(path.read_text())
        if old.get('hash')==hash_ and old.get('evidence_version')==2:return old
    r=process(item)
    schema=asn1tools.compile_files(str(ROOT/'docs/bu.asn1'),'ber')
    bu=schema.decode('EntidadeBoletimUrna',schema.decode('EntidadeEnvelopeGenerico',item[2])['conteudo'])
    files=[];evidence=[];clock=[];missing=[];archive_names=set();references=[]
    audit_seen=set();completed=0;unfinished=[];restarts=[]
    for blob in item[3]:
        for filename,text in logs(blob):
            archive_names.update(p for p in filename.split('/') if p.endswith('.jez'))
            rows=[];votes=[];prev=None;identities=[]
            for lineno,line in enumerate(text.splitlines(),1):
                p=line.split('\t')
                if len(p)<6 or not p[0].startswith('25/10/2026 '):continue
                event=dict(file=filename,line=lineno,time_local=p[0],device=p[2],app=p[3],severity=p[1],message=clean(p[4]),authenticator=p[-1])
                rows.append(event)
                if re.fullmatch(r'(Município|Zona Eleitoral|Seção Eleitoral):\s*\d+',p[4]):identities.append(event)
                if p[4]=='Voto confirmado para [Presidente]':votes.append(event)
                if p[1]=='EXTERNO':
                    m=re.search(r'Arquivo (\S+\.jez)',p[4])
                    if m:references.append((m.group(1),event))
                if p[3]=='VOTA':
                    dt=datetime.strptime(p[0],'%d/%m/%Y %H:%M:%S')
                    if prev and dt<prev[0]:clock.append(dict(before=prev[1],after=event,backwards_seconds=int((prev[0]-dt).total_seconds())))
                    prev=(dt,event)
            selected=[]
            for i,e in enumerate(rows):
                msg=e['message'].lower()
                if e['severity'] in ('ERRO','EXTERNO') or any(t in msg for t in ('reinício','reinicio','relógio','data/hora','corrompido','iniciando aplicação','retomada','encerramento confirmado')):
                    selected.extend(rows[max(0,i-1):min(len(rows),i+2)])
            selected=identities+votes[:1]+votes[-1:]+selected
            bound,_,_,_=section_vota(text,tuple(map(int,key.split('/')[1:])),audit_seen)
            bound_events={(p[0],p[2],p[3],clean(p[4]),p[-1]) for p in bound}
            scoped=[e for e in rows if (e['time_local'],e['device'],e['app'],e['message'],e['authenticator']) in bound_events]
            important=[e for e in scoped if e['message'] in ('Voto confirmado para [Presidente]','O voto do eleitor foi computado')]
            completed+=sum(e['message']=='O voto do eleitor foi computado' for e in scoped)
            restarts.extend(e for e in scoped if 'reinício da votação' in e['message'])
            for before,after in zip(important,important[1:]):
                if before['message']==after['message']=='Voto confirmado para [Presidente]':
                    markers=[e for e in rows if before['line']<e['line']<after['line'] and any(s in e['message'].lower() for s in ['desligad','iniciando aplicação','reinício da votação'])]
                    unfinished.append(dict(confirmation=before,next_confirmation=after,intervening_operational_events=markers))
                    selected.extend([before,*markers,after])
            uniq={ (e['file'],e['line']):e for e in selected }
            evidence.extend(list(uniq.values())[:45])
            files.append(dict(file=filename,sha256_text=hashlib.sha256(text.encode()).hexdigest(),presidential_confirmations=len(votes),
                devices=sorted({e['device'] for e in rows}),first_confirmation=votes[0]['time_local'] if votes else None,last_confirmation=votes[-1]['time_local'] if votes else None))
    missing=[dict(name=n,event=e) for n,e in references if n not in archive_names]
    explanations=[]
    if r['bu_kind']=='dadosSA':explanations.append(dict(status='Fato documentado',text='O BU foi produzido no Sistema de Apuração (dadosSA). A ausência de confirmações VOTA neste pacote não é uma comparação direta com a votação em urna; os votos do BU permanecem na soma geral.'))
    if r['foreign_section_events']:
        text=f"O pacote contém {r['foreign_section_events']} confirmações vinculadas explicitamente a outra seção, além da seção do BU. Após separar pelas identificações de município/zona/seção registradas nos logs, a contagem desta seção é {r['log_votes']} e o BU tem {r['total']}."
        explanations.append(dict(status='Conciliação explicada' if r['match'] else 'Separação comprovada; diferença residual pendente',text=text))
    if clock:explanations.append(dict(status='Regressão observada; causa ainda não comprovada',text='O horário diminui na ordem de gravação das linhas VOTA. A documentação oficial admite ajustes do relógio (PDF, p. 7), mas isso não identifica por si só a causa deste caso. Os pares de linhas e o tamanho de cada retrocesso estão abaixo.'))
    if not r['match'] and r['bu_kind']!='dadosSA':explanations.append(dict(status='Pendente de conciliação',text=f"BU: {r['total']}; eventos presidenciais vinculados à seção: {r['log_votes']}; diferença log − BU: {r['log_votes']-r['total']:+d}. Não foi atribuída causa sem confirmação nos arquivos. A seção fica fora da série temporal principal."))
    if r['log_votes']>r['total'] and completed==r['total']:
        explanations.append(dict(status='Diferença entre confirmação e sessão computada',text=f"O log tem {r['log_votes']} confirmações presidenciais, mas {completed} mensagens de sessão computada, coincidindo com o total do BU. Há {len(unfinished)} sequência(s) de confirmação sem mensagem de computação entre duas confirmações sucessivas e {len(restarts)} registro(s) de retomada da votação. Isso documenta uma diferença entre tipos de evento; o efeito da interrupção não é presumido. Os trechos estão preservados abaixo."))
    if missing:explanations.append(dict(status='Arquivo referenciado ausente deste pacote',text=f'{len(missing)} referência(s) EXTERNO do dia apontam para arquivos .jez não encontrados na árvore deste pacote. Isso documenta uma lacuna do pacote consultado; não prova perda de votos.'))
    if r['binding_unknown_votes']:explanations.append(dict(status='Vínculo incompleto',text=f"Em {r['binding_unknown_votes']} eventos não foi encontrada uma identificação completa da seção antes do voto dentro do respectivo arquivo. Não são usados como evidência temporal conciliada."))
    if r['total']==0:explanations.append(dict(status='Comparecimento zero declarado',text='O BU presidencial declara zero votos. Zero eventos é compatível com esse boletim; o caso não é tratado como ausência de arquivo nem como erro automático.'))
    for field,label in [('first','antes das 8h'),('last','após as 19h')]:
        v=r.get(field)
        if v is not None and ((field=='first' and v<28800) or (field=='last' and v>68400)):
            explanations.append(dict(status='Horário fora da faixa de referência',text=f'Há evento presidencial {label} de Brasília. Fila, prorrogação, operação e relógio precisam ser examinados com as evidências do caso; a causa não é presumida.'))
    if not explanations:explanations.append(dict(status='Revisão documental',text='Os campos que motivaram a seleção estão listados. Não foi encontrada uma causa adicional comprovada nos trechos selecionados.'))
    keys=['id','name','uf','total','log_votes','raw_log_votes','foreign_section_events','foreign_sections','match','clock_backwards',
          'binding_unknown_votes','unknown_auth','log_files','bu_kind','opening_local','closing_local','aptos_president','full_turnout','first','last','offset_hours']
    case=dict(evidence_version=2,hash=hash_,verified={k:r.get(k) for k in keys},sources=sources,files=files,
        clock_regressions=clock,missing_archived_references=missing,explanations=explanations,evidence=evidence,
        protocol_events=dict(completed_sessions=completed,unfinished_confirmation_sequences=unfinished,restarts=restarts),
        declared_sa_reason=bu.get('urna',{}).get('motivoUtilizacaoSA'))
    path.write_text(json.dumps(case,ensure_ascii=False,indent=2));return case

def render_case(case,table,fmt):
    r=case['verified'];key=r['id'];esc=html.escape
    events=[]
    for e in case['evidence']:
        events.append((esc(e['file']),fmt(e['line']),esc(e['time_local']),esc(e['device']),esc(e['app']),esc(e['severity']),esc(e['message'])))
    body=['<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ocorrência '+esc(key)+'</title><style>body{max-width:1200px;margin:30px auto;padding:0 22px;font:15px/1.6 system-ui;color:#173248}table{border-collapse:collapse;font-size:12px;width:100%}th,td{padding:9px;border:1px solid #dde5ec;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#edf3f8}.scroll{overflow:auto}section{margin:24px 0}a{color:#076c88}code{overflow-wrap:anywhere}</style>',
        '<a href="../report.html">Voltar ao relatório (17h05)</a> · <a href="../report-1700.html">Referência de 17h</a>',
        '<h1>'+esc(key)+' · '+esc(r['name'])+'</h1><p>Horários dos trechos abaixo são os <strong>horários locais registrados pela urna</strong>. Conversão para Brasília: '+(str(r['offset_hours'])+' hora(s)' if r['offset_hours'] is not None else 'não aplicada nesta versão (exterior)')+'. Os registros preservam a ordem de gravação; identificadores de eleitor/mesário foram omitidos dos trechos.</p>',
        table(['Medida','Valor'],[(esc(k),esc(str(r.get(k)))) for k in ['total','raw_log_votes','log_votes','foreign_section_events','clock_backwards','binding_unknown_votes','log_files','bu_kind','aptos_president','full_turnout']]),
        '<h2>Explicações e limites</h2>']
    body+=['<section><strong>'+esc(e['status'])+'</strong><p>'+esc(e['text'])+'</p></section>' for e in case['explanations']]
    if case['declared_sa_reason']:body.append('<p>Motivo declarado de utilização do SA: <code>'+esc(json.dumps(case['declared_sa_reason'],ensure_ascii=False))+'</code>.</p>')
    body.append('<h2>Arquivos internos do pacote</h2>'+table(['Caminho no ZIP','Confirmações presidenciais (antes do filtro por seção)','Urnas nos registros'],[(esc(f['file']),fmt(f['presidential_confirmations']),esc(', '.join(f['devices']))) for f in case['files']]))
    if case['clock_regressions']:
        body.append('<h2>Retrocesso na ordem das linhas VOTA</h2>'+table(['Antes (local)','Depois (local)','Retrocesso','Arquivo / linhas'],[(esc(p['before']['time_local']),esc(p['after']['time_local']),fmt(p['backwards_seconds'])+' s',esc(p['after']['file'])+' · '+str(p['before']['line'])+' → '+str(p['after']['line'])) for p in case['clock_regressions']]))
    protocol=case.get('protocol_events',{})
    if protocol.get('unfinished_confirmation_sequences'):
        body.append('<h2>Confirmação sem mensagem de computação entre confirmações sucessivas</h2>'+table(['Confirmação anterior','Confirmação seguinte','Eventos operacionais entre elas'],[(esc(p['confirmation']['time_local']),esc(p['next_confirmation']['time_local']),'<br>'.join(esc(e['time_local']+' · '+e['message']) for e in p['intervening_operational_events'])) for p in protocol['unfinished_confirmation_sequences']]))
    body.append('<h2>Trechos selecionados</h2>'+table(['Arquivo interno','Linha','Data/hora local','Urna','Aplicativo','Nível','Mensagem'],events))
    body.append('<h2>Fontes oficiais e identidade dos arquivos</h2>')
    for source in case['sources']:
        body.append('<p><a href="'+esc(source['url'],quote=True)+'">'+esc(source['name'])+'</a><br>SHA-256: <code>'+source['sha256']+'</code></p>')
    body.append('<p>As mensagens de ERRO, reinício ou contingência são evidências de eventos registrados, não uma conclusão automática sobre seu efeito na votação. Sem verificação criptográfica das assinaturas nesta análise.</p><p><a href="'+key.replace('/','_')+'.json">Evidências estruturadas em JSON</a>.</p></html>')
    (ROOT/'output/cases'/(key.replace('/','_')+'.html')).write_text(''.join(body))

def render(con,table,fmt):
    cols={r[0] for r in con.execute('DESCRIBE good').fetchall()}
    foreign='coalesce(foreign_section_events,0)>0' if 'foreign_section_events' in cols else 'false'
    unknown='coalesce(binding_unknown_votes,0)>0' if 'binding_unknown_votes' in cols else 'false'
    sql=f'''SELECT id,name,uf,total,log_votes,clock_backwards,unknown_auth,log_files,bu_kind FROM good
        WHERE NOT match OR clock_backwards>0 OR unknown_auth>0 OR {foreign} OR {unknown}
        OR total=0 OR "first"<28800 OR "last">68400
        ORDER BY (NOT match)::INTEGER DESC,clock_backwards DESC,id'''
    cur=con.execute(sql);rows=[dict(zip([x[0] for x in cur.description],row)) for row in cur.fetchall()]
    cases=[]
    for row in rows:
        try:
            case=inspect(row['id']);render_case(case,table,fmt);cases.append(case)
        except Exception as e:
            cases.append(dict(verified=row,error=repr(e),explanations=[dict(status='Falha na revisão documental',text=repr(e))]))
    stats=collections.Counter()
    for c in cases:
        for e in c['explanations']:stats[e['status']]+=1
    (ROOT/'output/anomalies.json').write_text(json.dumps(dict(selected=len(rows),categories=stats,cases=cases),ensure_ascii=False,indent=2))
    summary=table(['Categoria observada na revisão','Seções'],[(html.escape(k),fmt(v)) for k,v in stats.items()])
    listing=table(['Seção','Município','BU','Eventos vinculados','Diferença','Revisão'],[
        ('<a href="cases/'+c['verified']['id'].replace('/','_')+'.html">'+c['verified']['id']+'</a>',html.escape(c['verified']['name']),fmt(c['verified']['total']),fmt(c['verified']['log_votes']),fmt(c['verified']['log_votes']-c['verified']['total']),html.escape('; '.join(e['status'] for e in c['explanations']))) for c in cases])
    return '<section id="ocorrencias"><h2>Ocorrências e conciliações — evidência por seção</h2><p>A revisão separa fatos observados, conciliações explicadas e causas ainda não comprovadas. Cada seção abre um dossiê com arquivos oficiais, SHA-256, identificação das urnas, horários e linhas relevantes. Uma seção pode aparecer em mais de uma categoria. Casos do Sistema de Apuração são identificados separadamente.</p>'+summary+listing+'<p><a href="anomalies.json">Todas as evidências estruturadas</a>. As conclusões são atualizadas com a cobertura. A leitura revisada pode corrigir uma divergência inicial causada pela inclusão de logs de outra seção no mesmo pacote.</p></section>'
