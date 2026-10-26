"""Servidor local do relatório e consulta de tempos por seção, sem cálculos brutos no navegador."""
import argparse
import html
import json
import pathlib
import re
import sqlite3
import urllib.parse
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from datetime import datetime,timezone,timedelta
import duckdb
from timing_report import line_chart,LABELS
from report import table,fmt
from profile_store import BASE

ROOT=pathlib.Path(__file__).resolve().parents[1]
UFSET=set('ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to zz'.split())

def normalized_key(value):
    parts=value.lower().strip().split('/')
    if len(parts)!=4 or parts[0] not in UFSET or any(not re.fullmatch(r'\d{1,'+str(n)+'}',p) for p,n in zip(parts[1:],[5,4,4])):raise ValueError('Use UF/município TSE/zona/seção; exemplo ac/01074/0004/0001')
    return '/'.join([parts[0],parts[1].zfill(5),parts[2].zfill(4),parts[3].zfill(4)])

def lookup(turn,key):
    path=ROOT/'data/timing/profile-lookup.sqlite'
    if not path.exists():return None
    c=sqlite3.connect(str(path));row=c.execute('SELECT batch FROM lookup WHERE turn=? AND id=?',(turn,key)).fetchone();c.close()
    if not row:
        # Read immutable manifests if the incremental lookup has not caught up.
        for manifest in (BASE/(str(turn)+'t')/key.split('/')[0]).glob('*/manifest.json'):
            if key in json.loads(manifest.read_text()).get('ids',[]):return manifest.parent
        return None
    folder=(BASE/row[0]).resolve()
    if BASE.resolve() not in folder.parents:raise ValueError('Invalid managed batch')
    return folder

def rec(con,sql,args=None):
    cur=con.execute(sql,args or []);return [dict(zip([x[0] for x in cur.description],r)) for r in cur.fetchall()]

def documentary_section(key):
    path=ROOT/'output/documentary-sections.parquet'
    if not path.exists():return ''
    c=duckdb.connect();c.execute('SET threads=2');rows=rec(c,'SELECT * FROM read_parquet(?) WHERE id=? ORDER BY cutoff,turn',[str(path),key]);c.close()
    if not rows:return '<section><h2>Marcos documentais</h2><p>Esta seção não tem sessão conciliada nos universos qualificados deste extra. Consulte o BU e os sinalizadores acima.</p></section>'
    names={'recebimento':'Recebimento dos fatos no STF','criacao_pdf':'Criação do PDF','juizes_sp':'Comunicação aos juízes de SP (referência de relógio)'}
    nf=lambda v:'—' if v is None else f'{v:.1f}s'
    return ('<section><h2>Comparação pelos marcos documentais</h2><p>Horário de Brasília. Para UFs diferentes de SP, 17h18 é somente referência comum de relógio. Os marcos não certificam o recebimento da ordem por esta mesa.</p>'
      +table(['Marco','Horário nominal','Turno','Antes','Exato','Depois','Identificação média dos posteriores','Votação média dos posteriores','Mediana entre confirmações posteriores'],[(names[r['anchor']],f'{int(r["cutoff"])//3600:02}:{int(r["cutoff"])%3600//60:02}:{int(r["cutoff"])%60:02}',r['turn'],fmt(r['pre_n']),fmt(r['at_n']),fmt(r['post_n']),nf(r['identification_mean']),nf(r['voting_mean']),nf(r['gap_median'])) for r in rows])
      +'<p><a href="/documentary-comparison.html">Fontes, precisão dos horários e comparação completa</a>. Esses períodos não revelam candidato por horário nem medem diretamente fila.</p></section>')

def section_page(key):
    con=duckdb.connect();con.execute("SET memory_limit='2GB'");con.execute('SET threads=2')
    metadata=[];series=[];methods=[];longest=[];source_rows=[]
    for turn in [1,2]:
        folder=lookup(turn,key)
        if not folder:continue
        data=rec(con,'SELECT * FROM read_parquet(?) WHERE id=?',[str(folder/'sections.parquet'),key])
        if not data:continue
        meta=data[0];metadata.append(meta);source_rows.append((turn,html.escape(meta['source'])))
        con.execute('CREATE OR REPLACE TEMP VIEW current_events AS SELECT * FROM read_parquet(\''+str(folder/'events.parquet').replace("'","''")+'\')')
        when='presidential_local' if key.startswith('zz/') else 'presidential_bsb'
        for metric in ['identification_seconds','voting_seconds','pres_stage_seconds','confirmation_gap_seconds','activation_gap_seconds']:
            values=rec(con,f'''SELECT turn,(floor({when}/300)*300)::INTEGER AS "second",count({metric})::BIGINT n,
                avg({metric}) mean,median({metric}) median,quantile_cont({metric},.9) p90
                FROM current_events WHERE id=? AND valid_timing AND {when} IS NOT NULL AND {metric} IS NOT NULL
                GROUP BY turn,"second" ORDER BY "second"''',[key])
            for row in values:row['metric']=metric
            series.extend(values)
        methods.extend(rec(con,'''SELECT turn,auth_kind,count(*)::BIGINT n,avg(identification_seconds) identification_mean,
            median(identification_seconds) identification_median,avg(voting_seconds) voting_mean,
            avg(cargo_confirmations) mean_stages FROM current_events WHERE id=? AND valid_timing GROUP BY turn,auth_kind''',[key]))
        longest.extend(rec(con,'''SELECT turn,ordinal,identifier_local,enabled_local,presidential_local,computed_local,
            auth_kind,identification_seconds,voting_seconds,pres_stage_seconds,confirmation_gap_seconds,
            was_suspended,gap_crosses_restart,completed,flags,archive_entry FROM current_events
            WHERE id=? ORDER BY coalesce(voting_seconds,0)+coalesce(identification_seconds,0) DESC LIMIT 8''',[key]))
    con.close()
    esc=html.escape
    name=metadata[-1]['name'] if metadata else key
    time_basis='relógio local; sem aplicação da prorrogação no Brasil' if key.startswith('zz/') else 'horário de Brasília'
    content=['<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Tempos · '+esc(key)+'</title><style>body{max-width:1200px;margin:32px auto;padding:0 22px;background:#f5f7fa;color:#18324a;font:15px/1.6 system-ui}section{background:white;border:1px solid #dce5ed;padding:24px;border-radius:12px;margin:24px 0}svg{width:100%;height:auto}svg text{font:12px system-ui;fill:#405a71}.scroll{overflow:auto;max-height:650px}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:10px;border-bottom:1px solid #dfe6ec;text-align:left;white-space:nowrap}th{background:#ebf1f7}.muted{color:#526c80}.notice{background:#fff1d4;padding:18px}a{color:#08718a}</style>',
        '<a href="/report.html">Voltar ao relatório</a><h1>'+esc(name)+' · '+esc(key)+'</h1>',
        '<p>Consulta calculada no servidor local. Base de horário: '+time_basis+'. Registros anônimos de sessão, sem identificação do eleitor nem vínculo com candidato.</p>']
    if not metadata:
        message='Não foi encontrado BU/log publicado para este identificador no corpus consultado. Confira município TSE, zona e seção.'
        uf,mun,zone,sec=key.split('/')
        db=sqlite3.connect(str(ROOT/'data/raw'/(uf+'.sqlite')))
        cfgrow=db.execute("SELECT payload FROM files WHERE url LIKE '%-cs.json'").fetchone();db.close()
        if cfgrow:
            cfg=json.loads(cfgrow[0])
            for abr in cfg['abr']:
                for m in abr.get('mu',[]):
                    if int(m['cd'])!=int(mun):continue
                    for z in m['zon']:
                        if int(z['cd'])!=int(zone):continue
                        for section in z['sec']:
                            if int(section['ns'])!=int(sec):continue
                            principal=section.get('nsp')
                            if principal:
                                dest='/'.join([uf,mun,zone,str(principal).zfill(4)])
                                message=f'Seção agregada: seus registros são publicados com a seção principal <a href="/section?id={dest}">{dest}</a>. Não há uma segunda urna independente.'
                            elif not section.get('da'):message='Seção principal sem arquivo auxiliar publicado no índice capturado do TSE.'
                            else:message='O índice declara arquivo publicado, mas não foi localizado perfil para este identificador. Consulte a cobertura e os erros de processamento.'
        content.append('<div class="notice">'+message+'</div>')
    else:
        content.append(table(['Turno','Aptos','Votos no BU','Confirmações','Sessões presidenciais computadas','Tempos utilizáveis','Conciliação para tempos'],[(m['turn'],fmt(m.get('aptos')),fmt(m.get('total')),fmt(m.get('presidential_markers')),fmt(m.get('completed_presidential_sessions')),fmt(m.get('valid_sessions')),'Sim' if m.get('section_eligible') else 'Não / revisão') for m in metadata]))
        if any(not m.get('section_eligible') for m in metadata):content.append('<p class="notice">Ao menos um turno está fora do corpus temporal estrito. A consulta preserva os tempos observáveis das sessões, para revisão; não os apresenta como uma seção plenamente conciliada.</p>')
        for metric in ['identification_seconds','voting_seconds','pres_stage_seconds','confirmation_gap_seconds','activation_gap_seconds']:
            content.extend(['<section><h2>'+esc(LABELS[metric])+'</h2>',line_chart(series,metric,LABELS[metric],1,not key.startswith('zz/')),'</section>'])
        nf=lambda x:'—' if x is None else f'{x:.1f}s'
        content.append('<section><h2>Método e etapas observadas</h2>'+table(['Turno','Método','Sessões','Identificação média','Identificação mediana','Votação média','Etapas médias'],[(r['turn'],esc(r['auth_kind']),fmt(r['n']),nf(r['identification_mean']),nf(r['identification_median']),nf(r['voting_mean']),f'{r["mean_stages"]:.2f}') for r in methods])+'</section>')
        def tm(v):return '—' if v is None else f'{int(v)//3600:02}:{int(v)%3600//60:02}:{int(v)%60:02}'
        content.append('<section><h2>Sessões com maiores durações registradas</h2><p>Os horários desta tabela são locais da urna. Uma duração extrema pode incluir suspensão, inatividade ou interrupção; os sinalizadores mostram apenas o que foi registrado.</p>'+table(['Turno','Sessão anônima','Habilitação local','Presidente local','Identificação','Votação','Suspensão','Retomada no intervalo','Computada','Sinalizadores'],[(r['turn'],r['ordinal'],tm(r['enabled_local']),tm(r['presidential_local']),nf(r['identification_seconds']),nf(r['voting_seconds']),'Sim' if r['was_suspended'] else 'Não','Sim' if r['gap_crosses_restart'] else 'Não','Sim' if r['completed'] else 'Não',esc(r['flags'] or '—')) for r in longest])+'</section>')
        content.append('<section><h2>Resultados presidenciais do BU, sem associação a horário</h2>'+table(['Turno','13','22','Demais votos','Brancos','Nulos'],[(m['turn'],fmt(m.get('v13')),fmt(m.get('v22')),fmt(m.get('other_votes')),fmt(m.get('blank')),fmt(m.get('null'))) for m in metadata])+'</section>')
        content.append('<section><h2>Origem dos dados</h2>'+table(['Turno','Arquivo ou auxiliar oficial'],source_rows)+'<p>Em ZIPs, o trecho após # identifica o membro do pacote, não uma nova API. BUs e logs originais e seus hashes ficam preservados nos diretórios de dados do projeto.</p></section>')
    content.append(documentary_section(key))
    content.append('<p>Identificação e tempo de votação são medidas distintas. Intervalos entre sessões incluem possíveis pausas e não são uma medição direta de espera em fila.</p></html>')
    return ''.join(content)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT/'output'),**kwargs)
    def do_GET(self):
        parsed=urllib.parse.urlparse(self.path)
        if parsed.path not in ('/section','/api/section'):return super().do_GET()
        query=urllib.parse.parse_qs(parsed.query)
        try:
            key=normalized_key(query.get('id',[''])[0]);page=section_page(key)
            payload=(json.dumps(dict(id=key,html=page),ensure_ascii=False).encode() if parsed.path=='/api/section' else page.encode())
            self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8' if parsed.path=='/api/section' else 'text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        except ValueError as e:self.send_error(400,str(e))
        except Exception as e:self.send_error(503,'Consulta temporariamente indisponível: '+str(e))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);args=parser.parse_args()
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
