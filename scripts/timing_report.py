"""Gráficos de tempos e comparações pareadas; cálculo inteiro no DuckDB/Python local."""
import collections
import html
import json
import math
import hashlib
import pathlib
import numpy as np
from scipy.stats import pearsonr,spearmanr
from profile_store import exists,KNOWN_NONBIO

ROOT=pathlib.Path(__file__).resolve().parents[1]
PRODUCER_SHA=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
LABELS={'identification_seconds':'Entrada do identificador até habilitação','voting_seconds':'Habilitação até confirmação de Presidente',
    'pres_stage_seconds':'Etapa aproximada de Presidente','session_seconds':'Habilitação até sessão computada',
    'confirmation_gap_seconds':'Intervalo entre confirmações sucessivas','activation_gap_seconds':'Computação anterior até próxima habilitação',
    'active_confirmation_gap_seconds':'Intervalo entre confirmações, sem retomada registrada'}
COLORS={1:'#3a6793',2:'#b87510'}

AUTH_LABELS={'elector_biometric':'Digital do eleitor reconhecida','no_elector_biometric':'Biografia / sem biometria do eleitor','pollworker_biometric':'Digital de mesário identificado','pollworker_unassigned_fingerprint':'Digital de mesário sem associação inicial','pollworker_captured_fingerprint':'Digital de mesário capturada','biographic':'Habilitação biográfica explícita','unknown':'Método não classificado'}
def method_chart(rows):
    kinds=sorted({r['auth_kind'] for r in rows});maximum=max([r['mean'] for r in rows if r['mean'] is not None]+[1])*1.12
    x=lambda n:440+480*n/maximum;out=[f'<svg viewBox="0 0 1060 {90+len(kinds)*67}" role="img" aria-label="Tempo médio de identificação por método: primeiro turno, segundo turno e segundo turno após 17h05">']
    groups=[('1º turno','#3a6793'),('2º turno','#b87510'),('2º turno · 17h05+','#804b95')]
    for i,kind in enumerate(kinds):
        y=20+i*67;out.append(f'<text x="5" y="{y+24}" style="font-size:11px">{html.escape(AUTH_LABELS.get(kind,kind))}</text>')
        for j,(group,color) in enumerate(groups):
            r=next((r for r in rows if r['auth_kind']==kind and r.get('cohort',str(r['turn'])+'º turno')==group),None)
            if not r or r['mean'] is None:continue
            width=x(r['mean'])-440;out.append(f'<rect x="440" y="{y+j*15}" width="{width:.2f}" height="12" fill="{color}"><title>{html.escape(group)}: {r["mean"]:.2f}s; n={r["n"]}</title></rect><text x="{445+width:.2f}" y="{y+j*15+10}" style="font-size:11px">{r["mean"]:.1f}s</text>')
    out.append('</svg><p class="muted">Azul: 1º turno · ocre: 2º turno · roxo: 2º turno, confirmação após 17h05. Médias ponderadas pelo número de registros, sem atribuição causal.</p>')
    return ''.join(out)



def recognition_summary(rows):
    groups=collections.defaultdict(list)
    for r in rows:
        if r['auth_kind']=='elector_biometric':kind='Digital do eleitor reconhecida'
        elif r['auth_kind'] in {'no_elector_biometric','pollworker_biometric','pollworker_unassigned_fingerprint','pollworker_captured_fingerprint','biographic'}:kind='Sem reconhecimento biométrico do eleitor'
        else:continue
        groups[(r.get('cohort',str(r['turn'])+'º turno'),kind)].append(r)
    result=[]
    for (cohort,kind),cells in groups.items():
        n=sum(r['n'] for r in cells);result.append(dict(cohort=cohort,recognition=kind,n=n,mean=sum(r['mean']*r['n'] for r in cells)/n if n else None))
    return result

def methods_html(rows,table,fmt):
    summary=recognition_summary(rows)
    return ('<h3 id="identificacao-metodos">Identificação por método observado</h3><p>O grupo <strong>2º turno · 17h05+</strong> reúne sessões com confirmação presidencial estritamente depois de 17:05:00 de Brasília, com os mesmos filtros de conciliação e duração utilizável dos perfis. O tempo de identificação dessas sessões pode ter começado antes do corte. Não é um terceiro turno eleitoral; o segundo exato 17:05:00 fica fora do grupo. Métodos sem registros no grupo não recebem média.</p>'
      +method_chart(rows)+table(['Turno / grupo','Método','Registros','Média','Mediana','P90'],[(html.escape(r.get('cohort',str(r['turn'])+'º turno')),html.escape(AUTH_LABELS.get(r['auth_kind'],r['auth_kind'])),fmt(r['n']),f'{r["mean"]:.1f}s',f'{r["median"]:.1f}s',f'{r["p90"]:.1f}s') for r in rows])
      +'<h4>Resumo com e sem reconhecimento da digital do eleitor</h4>'+table(['Turno / grupo','Reconhecimento do eleitor','Registros','Média'],[(html.escape(r['cohort']),r['recognition'],fmt(r['n']),f'{r["mean"]:.1f}s') for r in summary])
      +'<p class="muted">O resumo agrega métodos conhecidos, com média ponderada pelo número de registros; não deve ser somado às linhas detalhadas. Sem reconhecimento da digital do eleitor pode incluir a digital do mesário. Métodos desconhecidos ficam na tabela detalhada e fora dessa comparação binária.</p>')

def records(con,sql,params=None):
    c=con.execute(sql,params or []);return [dict(zip([x[0] for x in c.description],r)) for r in c.fetchall()]

def weighted(con,dimensions,where='true'):
    dims=','.join('"'+x+'"' for x in dimensions)
    quant=[]
    for q,label in [(.5,'median'),(.9,'p90'),(.95,'p95')]:
        lower=f'min(value) FILTER(WHERE cumulative_n>=floor(1+{q}*(n_total-1)))'
        upper=f'min(value) FILTER(WHERE cumulative_n>=ceil(1+{q}*(n_total-1)))'
        weight=f'(1+{q}*(max(n_total)-1)-floor(1+{q}*(max(n_total)-1)))'
        quant.append(f'(({lower})+{weight}*(({upper})-({lower})))::DOUBLE AS {label}')
    return records(con,f'''WITH h AS (SELECT {dims},value,sum(n)::BIGINT n FROM timing_hist WHERE {where} GROUP BY {dims},value),
        ranked AS (SELECT *,sum(n) OVER(PARTITION BY {dims} ORDER BY value ROWS UNBOUNDED PRECEDING) cumulative_n,
        sum(n) OVER(PARTITION BY {dims}) n_total FROM h)
        SELECT {dims},max(n_total)::BIGINT n,sum(value*1.0*n)/sum(n) mean,{','.join(quant)},max(value) maximum
        FROM ranked GROUP BY {dims} ORDER BY {dims}''')

def clock(second):return f'{int(second)//3600:02}:{int(second)%3600//60:02}'

def line_chart(rows,metric,title,min_n=30,show_cutoffs=True):
    selected=[r for r in rows if r['metric']==metric]
    lo=min([28800]+[r['second'] for r in selected]);hi=max([68400]+[r['second']+300 for r in selected])
    maximum=max([r['mean'] for r in selected if r['n']>=min_n]+[10])*1.15
    x=lambda v:65+(v-lo)/(hi-lo)*920;y=lambda v:270-min(maximum,v)/maximum*230
    out=[f'<svg viewBox="0 0 1060 325" role="img" aria-label="{html.escape(title,quote=True)}">']
    for i in range(5):
        yy=y(maximum*i/4);out.append(f'<path d="M65 {yy:.2f}H985" stroke="#e2e9f0"/><text x="55" y="{yy+4:.2f}" text-anchor="end">{maximum*i/4:.0f}s</text>')
    for t in range(math.ceil(lo/3600)*3600,int(hi)+1,3600):out.append(f'<text x="{x(t):.2f}" y="292" text-anchor="middle">{clock(t)}</text>')
    if show_cutoffs:
        for cutoff,color in [(61200,'#9aafbd'),(61500,'#c59647')]:out.append(f'<path d="M{x(cutoff):.2f} 30V270" stroke="{color}" stroke-dasharray="4 4"/>')
    for turn in [1,2]:
        points=sorted([r for r in selected if r['turn']==turn],key=lambda r:r['second']);path=[];previous=None
        for r in points:
            xx=x(r['second']);yy=y(r['mean'])
            tip=f"{turn}º turno · {clock(r['second'])}: média {r['mean']:.1f}s; mediana {r['median']:.1f}s; P90 {r['p90']:.1f}s; n={r['n']}"
            if r['n']>=min_n:
                path.append(f'{"L" if previous is not None and r["second"]-previous==300 else "M"}{xx:.2f},{yy:.2f}');previous=r['second']
            else:previous=None
            out.append(f'<circle cx="{xx:.2f}" cy="{yy:.2f}" r="{2.5 if r["n"]>=min_n else 2}" fill="{COLORS[turn]}" fill-opacity="{.9 if r["n"]>=min_n else .25}"><title>{html.escape(tip)}</title></circle>')
        out.append('<path d="'+' '.join(path)+f'" stroke="{COLORS[turn]}" fill="none" stroke-width="2"/>')
    return ''.join(out)+f'</svg><p class="muted"><span style="color:#3a6793">● 1º turno</span> · <span style="color:#b87510">● 2º turno</span>. Médias ponderadas pelo número de registros; pontos com menos de {min_n} observações ficam tênues e não são conectados. Valores acima da escala principal são mostrados na borda e permanecem nas tabelas de dados.</p>'

def heatmap(rows,metric,turn,limit):
    ufs='ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to'.split()
    values={(r['uf'],r['second']):r for r in rows if r['metric']==metric and r['turn']==turn}
    start,end=28800,72000;width=900;cell=width/((end-start)//300)
    out=[f'<svg viewBox="0 0 1060 515" role="img" aria-label="{turn}º turno por UF e horário: {html.escape(LABELS[metric])}">']
    for i,uf in enumerate(ufs):
        yy=35+i*16;out.append(f'<text x="42" y="{yy+12}" text-anchor="end">{uf.upper()}</text>')
        for j,t in enumerate(range(start,end,300)):
            r=values.get((uf,t));color='#e8edf1';title=f'{uf.upper()} {clock(t)}: sem dados processados suficientes'
            if r and r['n']>=20:
                ratio=min(1,r['mean']/max(1,limit));rgb=tuple(round(a+(b-a)*ratio) for a,b in zip((234,246,247),(5,88,112)));color='#%02x%02x%02x'%rgb
                title=f"{uf.upper()} {clock(t)}: média {r['mean']:.1f}s; P90 {r['p90']:.1f}s; n={r['n']}"
            out.append(f'<rect x="{65+j*cell:.2f}" y="{yy}" width="{cell+.1:.2f}" height="15" fill="{color}"><title>{html.escape(title)}</title></rect>')
    for t in range(start,end+1,3600):out.append(f'<text x="{65+(t-start)/300*cell:.2f}" y="486" text-anchor="middle">{clock(t)}</text>')
    return ''.join(out)+f'</svg><p class="muted">Escala compartilhada entre turnos: branco até azul escuro, 0 a {limit:.0f}s ou mais. Cinza: menos de 20 observações ou dados ainda não processados. Cada célula representa cinco minutos.</p>'

def density(points,x_label,y_label):
    if not points:return '<p>Comparação pareada ainda sem observações suficientes.</p>'
    a=np.array(points,dtype=float);lo=np.quantile(a,.005,axis=0);hi=np.quantile(a,.995,axis=0)
    for i in [0,1]:
        if hi[i]<=lo[i]:hi[i]=lo[i]+1
    bins=collections.Counter();clipped=0
    for x,y in points:
        if x<lo[0] or x>hi[0] or y<lo[1] or y>hi[1]:clipped+=1
        bx=max(0,min(39,int((x-lo[0])/(hi[0]-lo[0])*40)));by=max(0,min(39,int((y-lo[1])/(hi[1]-lo[1])*40)));bins[bx,by]+=1
    maximum=max(bins.values(),default=1);out=['<svg viewBox="0 0 560 420" role="img" aria-label="Comparação pareada por seção">']
    for (x,y),n in bins.items():
        ratio=math.log1p(n)/math.log1p(maximum);rgb=tuple(round(u+(v-u)*ratio) for u,v in zip((226,244,245),(5,82,111)))
        out.append(f'<rect x="{65+x*11.25}" y="{355-(y+1)*8.25}" width="11.25" height="8.25" fill="rgb{rgb}"><title>{n} seções</title></rect>')
    for i in range(5):
        out.append(f'<text x="{65+i*112.5}" y="377" text-anchor="middle">{lo[0]+(hi[0]-lo[0])*i/4:.2f}</text><text x="55" y="{359-i*82.5}" text-anchor="end">{lo[1]+(hi[1]-lo[1])*i/4:.2f}</text>')
    out.append(f'<text x="280" y="408" text-anchor="middle">{html.escape(x_label)}</text><text transform="translate(13,190) rotate(-90)" text-anchor="middle">{html.escape(y_label)}</text>')
    return ''.join(out)+f'</svg><p class="muted">Densidade de {len(points):,} seções. Eixos focalizam P0,5 a P99,5; {clipped:,} pontos fora da faixa permanecem nas células de borda. Os dados completos ficam disponíveis em Parquet.</p>'

def correlation(rows,x,y):
    values=[(r[x],r[y],r['uf']) for r in rows if r.get(x) is not None and r.get(y) is not None and math.isfinite(r[x]) and math.isfinite(r[y])]
    if len(values)<3:return dict(n=len(values),pearson=None,spearman=None,within_uf_pearson=None)
    a=np.array([[r[0],r[1]] for r in values]);groups=collections.defaultdict(list)
    for i,r in enumerate(values):groups[r[2]].append(i)
    residual=a.copy()
    for indexes in groups.values():residual[indexes]-=a[indexes].mean(axis=0)
    f=lambda v:float(pearsonr(v[:,0],v[:,1]).statistic) if np.ptp(v[:,0]) and np.ptp(v[:,1]) else None
    return dict(n=len(values),pearson=f(a),spearman=float(spearmanr(a[:,0],a[:,1]).statistic) if np.ptp(a[:,0]) and np.ptp(a[:,1]) else None,within_uf_pearson=f(residual))

def render(con,table,fmt):
    if not exists(con):return '<section id="tempos"><h2>Tempos de identificação e votação</h2><p>Os perfis dos dois turnos estão sendo processados em Parquet.</p></section>'
    fingerprint=dict(profile=list(con.execute('SELECT count(*),sum(sections),sum(events) FROM profile_batches').fetchone()),
        core=list(con.execute('SELECT count(*),sum(size) FROM ingested_files').fetchone()),code=PRODUCER_SHA,render_abi=2)
    cache=ROOT/'output/timing-fragment.html';cache_meta=ROOT/'output/timing-fragment-meta.json'
    if cache.exists() and cache_meta.exists() and json.loads(cache_meta.read_text())==fingerprint:return cache.read_text()
    coverage=records(con,'''SELECT turn,count(*) sections,count(*) FILTER(WHERE section_eligible AND uf<>'zz') eligible,
        sum(total) ballots,sum(valid_sessions) FILTER(WHERE section_eligible AND uf<>'zz') valid_sessions,count(*) FILTER(WHERE error IS NOT NULL) errors
        FROM timing_sections GROUP BY turn ORDER BY turn''')
    by_time=weighted(con,['turn','second','metric'])
    by_state=weighted(con,['turn','uf','metric'])
    state_time=weighted(con,['turn','uf','second','metric'],"metric IN ('identification_seconds','voting_seconds')")
    methods=weighted(con,['turn','auth_kind','metric'],"metric='identification_seconds'")
    late_cohort=json.loads((ROOT/'output/cutoff-1705-verification.json').read_text())
    methods.extend(late_cohort['methods_late'])
    con.execute('''CREATE TEMP TABLE timing_pairs AS SELECT a.id,a.uf,a.name,a.aptos aptos_first,b.aptos aptos_second,
        a.total total_first,b.total total_second,100.0*a.total/nullif(a.aptos,0) turnout_first,
        100.0*b.total/nullif(b.aptos,0) turnout_second,
        100.0*b.total/nullif(b.aptos,0)-100.0*a.total/nullif(a.aptos,0) turnout_change_pp,
        a.identification_seconds_mean identification_first,b.identification_seconds_mean identification_second,
        a.voting_seconds_mean voting_first,b.voting_seconds_mean voting_second,
        a.pres_stage_seconds_mean stage_first,b.pres_stage_seconds_mean stage_second,
        a.confirmation_gap_seconds_median gap_first,b.confirmation_gap_seconds_median gap_second,
        b.identification_seconds_mean-a.identification_seconds_mean identification_change,
        b.voting_seconds_mean-a.voting_seconds_mean voting_change,
        f.nonbiometric_sessions*1.0/nullif(f.biometric_sessions+f.nonbiometric_sessions,0) nonbio_share,
        f.mean_cargo_confirmations,c.post*1.0/nullif(c.total,0) late17_share,c.post1705*1.0/nullif(c.total,0) late1705_share
        FROM timing_sections a JOIN timing_sections b ON a.id=b.id AND a.turn=1 AND b.turn=2
        JOIN timing_flows f ON f.id=b.id AND f.turn=2 LEFT JOIN sections c ON c.id=b.id
        WHERE a.section_eligible AND b.section_eligible AND a.valid_sessions>=30 AND b.valid_sessions>=30
        AND a.aptos>0 AND b.aptos>0 AND a.uf<>'zz' ''')
    pairs=records(con,'SELECT * FROM timing_pairs')
    con.execute('''CREATE TEMP TABLE timing_identification_adjusted AS WITH method_rows AS (
        SELECT m.turn,m.id,s.uf,m.auth_kind,m.identification_seconds_n n,m.identification_seconds_mean mean,
            m.identification_seconds_n*m.identification_seconds_mean total
        FROM timing_methods m JOIN timing_sections s USING(turn,id)
        WHERE s.section_eligible AND s.uf<>'zz' AND m.identification_seconds_n>0),
        regional AS (SELECT turn,uf,auth_kind,sum(n) n,sum(total) total FROM method_rows GROUP BY turn,uf,auth_kind)
        SELECT m.turn,m.id,sum(m.n)::BIGINT n,sum(m.total)/sum(m.n) actual_mean,
            sum(m.n*(r.total-m.total)/(r.n-m.n))/sum(m.n) expected_mean,
            sum(m.total)/sum(m.n)-sum(m.n*(r.total-m.total)/(r.n-m.n))/sum(m.n) residual
        FROM method_rows m JOIN regional r USING(turn,uf,auth_kind) WHERE r.n-m.n>=100 GROUP BY m.turn,m.id''')
    adjusted=records(con,'SELECT * FROM timing_identification_adjusted WHERE turn=2')
    adjusted_map={r['id']:r for r in adjusted}
    for r in pairs:
        a=adjusted_map.get(r['id']);r['identification_expected_mix']=a['expected_mean'] if a else None;r['identification_residual_mix']=a['residual'] if a else None
    definitions=[('Entrada do identificador → habilitação','Tempo observado de conferência após a digitação do identificador; não inclui toda a chegada ou fila.'),
        ('Habilitação → confirmação de Presidente','Inclui as demais etapas de votação anteriores à escolha de Presidente.'),
        ('Última etapa anterior → Presidente','Aproxima a etapa presidencial; inclui transição entre telas. Se há somente Presidente, começa na habilitação.'),
        ('Confirmação anterior → próxima confirmação','Mede cadência entre sessões sucessivas na mesma urna/arquivo, incluindo possíveis pausas.'),
        ('Computação anterior → próxima habilitação','Mede o intervalo entre registros do fluxo. Não identifica sozinho fila ou ociosidade.')]
    contrasts=[('Não reconhecimento biométrico × tempo de identificação','nonbio_share','identification_second'),
        ('Não reconhecimento biométrico × resíduo após referência por método/UF','nonbio_share','identification_residual_mix'),
        ('Não reconhecimento biométrico × tempo total de votação','nonbio_share','voting_second'),
        ('Votos após 17h × mudança no comparecimento','late17_share','turnout_change_pp'),
        ('Votos após 17h05 × mudança no comparecimento','late1705_share','turnout_change_pp'),
        ('Mudança no tempo de votação × mudança no comparecimento','voting_change','turnout_change_pp')]
    correlations=[dict(label=label,x=x,y=y,**correlation(pairs,x,y)) for label,x,y in contrasts]
    outliers=[];groups=collections.defaultdict(list)
    for r in pairs:groups[(r['uf'],round(r['mean_cargo_confirmations'] or 0))].append(r)
    for group,members in groups.items():
        if len(members)<100:continue
        for field in ['identification_second','voting_second','gap_second']:
            values=[r[field] for r in members if r.get(field) is not None and r[field]>=0]
            if len(values)<100:continue
            a=np.array(values);q01=float(np.quantile(a,.01));q99=float(np.quantile(a,.99));log=np.log1p(a);median=float(np.median(log));mad=float(np.median(np.abs(log-median)))
            for r in members:
                value=r.get(field)
                if value is None or (q01<=value<=q99) or mad<=0:continue
                score=.67448975*(math.log1p(value)-median)/mad
                if abs(score)>3.5:outliers.append(dict(id=r['id'],uf=r['uf'],name=r['name'],metric=field,value=value,peer_p01=q01,peer_p99=q99,direction='longo' if score>0 else 'curto',robust_score=score,nonbio_share=r['nonbio_share'],identification_expected_mix=r['identification_expected_mix'],identification_residual_mix=r['identification_residual_mix']))
    outliers.sort(key=lambda r:abs(r['robust_score']),reverse=True)
    (ROOT/'output/timing-outliers.json').write_text(json.dumps(dict(criteria='Outside UF/workload P1-P99 and absolute robust log-MAD score >3.5; at least 100 peer sections',rows=outliers),ensure_ascii=False,indent=2))
    summary=dict(method_recognition_summary=recognition_summary(methods),coverage=coverage,by_time=by_time,by_state=by_state,by_state_time=state_time,methods=methods,paired_sections=len(pairs),correlations=correlations,outliers_count=len(outliers))
    (ROOT/'output/timing-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    con.execute('COPY timing_pairs TO ? (FORMAT PARQUET,COMPRESSION ZSTD)',[str(ROOT/'output/timing-paired-sections.parquet')])
    con.execute('COPY timing_identification_adjusted TO ? (FORMAT PARQUET,COMPRESSION ZSTD)',[str(ROOT/'output/timing-identification-adjusted.parquet')])
    nf=lambda v:'Indefinido' if v is None else f'{v:.3f}'
    out=['<section id="tempos"><h2>Tempos de identificação, votação e cadência</h2><div class="notice">Perfis do corpus publicado, com cobertura e exclusões abaixo. Comparações são descritivas; chegada, espera na fila e preferência de quem não votou não aparecem nos logs.</div>',
        table(['Turno','Seções processadas (incl. exterior)','Brasil aptas para tempos','Sessões utilizáveis no Brasil','Erros de processamento'],[(r['turn'],fmt(r['sections']),fmt(r['eligible']),fmt(r['valid_sessions']),fmt(r['errors'])) for r in coverage]),
        '<p class="muted">As curvas por horário e mapas desta seção usam o relógio de Brasília nas seções domésticas. Durações do exterior continuam disponíveis na consulta individual, pelo relógio local. Registros de sessão incluem tentativas e interrupções; somente o subconjunto explicitamente conciliado entra nas distribuições de referência.</p>',
        table(['Medida','Interpretação'],definitions),
        '<h3>Conferência de identificação por horário</h3>',line_chart(by_time,'identification_seconds','Identificação: média por cinco minutos nos dois turnos'),
        '<h3>Tempo até a confirmação de Presidente</h3>',line_chart(by_time,'voting_seconds','Habilitação até confirmação de Presidente por horário'),
        '<h3>Etapa aproximada de Presidente</h3>',line_chart(by_time,'pres_stage_seconds','Etapa presidencial por horário'),
        '<p>O primeiro turno tem mais etapas. A diferença do tempo total não pode ser atribuída automaticamente à identificação. A etapa aproximada de Presidente ajuda a criticar essa hipótese, mas a transição de telas e o número de cargos continuam relevantes.</p>',
        '<h3>Intervalo entre confirmações sucessivas</h3>',line_chart(by_time,'confirmation_gap_seconds','Cadência entre confirmações presidenciais sucessivas'),
        '<p>Gaps longos podem incluir ausência de demanda, procedimentos, interrupções ou outros fatores. A distribuição não é uma medida direta de tamanho ou tempo de fila.</p>']
    for metric in ['identification_seconds','voting_seconds']:
        limit=max([r['mean'] for r in state_time if r['metric']==metric and r['n']>=100]+[1])
        out.extend(['<h3>'+LABELS[metric]+' · UF × horário</h3><h4>Primeiro turno</h4>',heatmap(state_time,metric,1,limit),'<h4>Segundo turno</h4>',heatmap(state_time,metric,2,limit)])
    out.extend([methods_html(methods,table,fmt),
        '<h3>Comparação das mesmas seções entre turnos</h3>',f'<p>{fmt(len(pairs))} seções com pelo menos 30 registros utilizáveis em cada turno. Cada seção tem peso igual nas correlações abaixo. O coeficiente dentro da UF remove apenas a média estadual; não elimina todos os fatores de confusão e não estima efeito causal.</p>',
        table(['Relação','Seções','Pearson','Spearman','Pearson após remover médias de UF'],[(r['label'],fmt(r['n']),nf(r['pearson']),nf(r['spearman']),nf(r['within_uf_pearson'])) for r in correlations]),
        '<div class="grid"><div><h4>Método de identificação e duração</h4>',density([(r['nonbio_share']*100,r['identification_second']) for r in pairs if r['nonbio_share'] is not None and r['identification_second'] is not None],'% sem reconhecimento biométrico','Identificação média (s)'),
        '</div><div><h4>Horário tardio e comparecimento</h4>',density([(r['late1705_share']*100,r['turnout_change_pp']) for r in pairs if r['late1705_share'] is not None and r['turnout_change_pp'] is not None],'% de votos após 17h05','Mudança de comparecimento (pp)'),'</div></div>',
        '<h3>O mix de identificação explica parte da diferença?</h3><p>A referência abaixo usa a duração média de cada método dentro da própria UF, excluindo a seção avaliada da média regional. O valor esperado recompõe o mix observado na seção; exige pelo menos 100 observações de comparação por método. Isso é uma padronização descritiva, não um teste causal. Um resíduo pequeno não prova ausência de barreira: o próprio uso de um método mais demorado pode fazer parte do mecanismo investigado.</p>',
        density([(r['identification_expected_mix'],r['identification_second']) for r in pairs if r['identification_expected_mix'] is not None and r['identification_second'] is not None],'Referência pelo mix/UF (s)','Identificação observada (s)'),
        '<p><a href="timing-identification-adjusted.parquet">Referências e resíduos por seção e turno</a>.</p>',
        '<h3>Seções pareadas que se afastam dos pares</h3><p>Critério exploratório: fora de P1-P99 e valor absoluto do escore robusto de log-MAD maior que 3,5, dentro da mesma UF e carga de votação aproximada. Isso identifica caudas curtas e longas; não é classificação automática de irregularidade. Seções pequenas permanecem nas contagens, mas não recebem este escore quando falta quantidade suficiente para comparação. A lista completa preserva valores e referências.</p>',
        table(['Seção','Município','Medida','Valor','P1-P99 dos pares','Escore robusto'],[('<a href="/section?id='+r['id']+'" target="_blank">'+r['id']+'</a>',html.escape(r['name']),r['metric'],f'{r["value"]:.1f}s',f'{r["peer_p01"]:.1f}–{r["peer_p99"]:.1f}s',f'{r["robust_score"]:.2f}') for r in outliers[:60]]),
        '<h3>Consultar qualquer seção processada</h3><form action="/section" method="get" target="_blank"><label>UF / município TSE / zona / seção <input name="id" value="ac/01074/0004/0001" pattern="[A-Za-z]{2}/[0-9]{1,5}/[0-9]{1,4}/[0-9]{1,4}" style="padding:10px;width:260px;max-width:100%" required></label> <button type="submit" style="padding:10px">Abrir comparação da seção</button></form><p class="muted">A consulta usa os lotes Parquet no servidor local e mostra gráficos de cada turno, métodos, sessões longas e sinalizadores. Também é possível abrir uma seção pelos identificadores nas tabelas.</p>',
        '<p><a href="timing-summary.json">Agregados completos de tempos</a> · <a href="timing-paired-sections.parquet">Seções pareadas</a> · <a href="timing-outliers.json">Todas as sinalizações exploratórias</a>.</p></section>'])
    content=''.join(out);cache.with_suffix('.tmp').write_text(content);cache.with_suffix('.tmp').replace(cache)
    cache_meta.write_text(json.dumps(fingerprint));return content
