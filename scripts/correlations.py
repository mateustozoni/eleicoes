"""Associação descritiva entre horário e identificação, sem atribuição causal."""
import collections
import html
import json
import math
import pathlib
import numpy as np
from scipy.stats import pearsonr, spearmanr

ROOT=pathlib.Path(__file__).resolve().parents[1]
BIO='elector_biometric'
NONBIO={'no_elector_biometric','pollworker_biometric','pollworker_unassigned_fingerprint','pollworker_captured_fingerprint','biographic'}

def coefficient(rows):
    if len(rows)<3:return dict(n=len(rows),pearson=None,spearman=None)
    x=np.array([r['late_rate'] for r in rows],dtype=float)
    y=np.array([r['nonbio_rate'] for r in rows],dtype=float)
    if np.ptp(x)==0 or np.ptp(y)==0:return dict(n=len(rows),pearson=None,spearman=None)
    return dict(n=len(rows),pearson=float(pearsonr(x,y).statistic),spearman=float(spearmanr(x,y).statistic))

def phi(a,b,c,d):
    # a=late/nonbio, b=late/bio, c=pre/nonbio, d=pre/bio.
    denominator=(a+b)*(c+d)*(a+c)*(b+d)
    return (a*d-b*c)/math.sqrt(denominator) if denominator else None

def axes(title,xmax=1,ymax=1):
    ylabel=lambda i:format(ymax*i*20,'.2f').rstrip('0').rstrip('.')+'%'
    return ['<svg viewBox="0 0 560 420" role="img" aria-label="'+html.escape(title)+'">',
      '<rect x="65" y="25" width="450" height="330" fill="#f8fafc"/>',
      *[f'<path d="M65 {355-i*66}H515 M{65+i*90} 25V355" stroke="#dfe7ee"/><text x="55" y="{359-i*66}" text-anchor="end">{ylabel(i)}</text><text x="{65+i*90}" y="375" text-anchor="middle">{xmax*i*20:.3f}%</text>' for i in range(6)],
      '<text x="285" y="407" text-anchor="middle">Proporção de votos após 17h</text><text transform="translate(15,190) rotate(-90)" text-anchor="middle">Sem reconhecimento biométrico do eleitor</text>']

def scatter(rows):
    xmax=max([r['late_rate'] for r in rows]+[.0001])*1.18
    ymax=max([r['nonbio_rate'] for r in rows]+[.05])*1.18
    out=axes('Estados: proporção tardia e proporção sem reconhecimento biométrico',xmax,ymax)
    occupied=[]
    for r in rows:
        x=65+450*r['late_rate']/xmax;y=355-330*r['nonbio_rate']/ymax
        tx,ty=x+6,y-5
        while any(abs(tx-px)<24 and abs(ty-py)<13 for px,py in occupied):ty+=13
        occupied.append((tx,ty))
        tip=f"{r['uf'].upper()}: {r['late_rate']*100:.2f}% tardios; {r['nonbio_rate']*100:.2f}% sem reconhecimento; {r['n']} votos classificados"
        out.append(f'<g><title>{html.escape(tip)}</title><circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="#087e8b" fill-opacity=".65"/><path d="M{x:.2f} {y:.2f}L{tx:.2f} {ty:.2f}" stroke="#9aafbf" stroke-width=".6"/><text x="{tx:.2f}" y="{ty:.2f}">{r["uf"].upper()}</text></g>')
    return ''.join(out)+'</svg>'

def density_bins(rows,field):
    return collections.Counter((min(39,int(r['late_rate']*40)),min(39,int(r[field]*40))) for r in rows if r.get(field) is not None)

def density(rows,field='nonbio_rate',maxn=None,label='todo o dia'):
    selected=[r for r in rows if r.get(field) is not None]
    out=axes('Seções: densidade de identificação sem reconhecimento biométrico '+label)
    bins=density_bins(rows,field)
    maxn=maxn or max(bins.values(),default=1)
    for (x,y),n in bins.items():
        ratio=math.log1p(n)/math.log1p(maxn)
        col=tuple(round(a+(b-a)*ratio) for a,b in zip((222,242,244),(5,83,107)))
        tip=f'{x*2.5:.1f}–{(x+1)*2.5:.1f}% tardios / {y*2.5:.1f}–{(y+1)*2.5:.1f}% sem reconhecimento {label}: {n} seções'
        out.append(f'<rect x="{65+x*11.25:.2f}" y="{355-(y+1)*8.25:.2f}" width="11.25" height="8.25" fill="rgb{col}"><title>{tip}</title></rect>')
    return ''.join(out)+f'</svg><p class="muted">{len(selected):,} seções com votos classificados {label}. Cada célula: 2,5 pontos percentuais por eixo. Cores em escala logarítmica compartilhada: de 1 até {maxn:,} seções por célula. Mais escuro indica mais seções.</p>'

def compare(rows):
    height=80+len(rows)*26
    out=[f'<svg viewBox="0 0 1000 {height}" role="img" aria-label="Proporção sem reconhecimento biométrico antes e depois das 17h por estado">']
    for i in range(6):
        x=65+i*140
        out.append(f'<path d="M{x} 35V{height-30}" stroke="#e3eaf0"/><text x="{x}" y="22" text-anchor="middle">{i*20}%</text>')
    for i,r in enumerate(rows):
        y=50+i*26;pre=r['pre_nonbio']/max(1,r['pre_nonbio']+r['pre_bio']);post=r['post_nonbio']/max(1,r['post_nonbio']+r['post_bio'])
        out.append(f'<text x="40" y="{y+4}" text-anchor="end">{r["uf"].upper()}</text>')
        if r['pre_nonbio']+r['pre_bio'] and r['post_nonbio']+r['post_bio']:
            out.append(f'<path d="M{65+pre*700:.2f} {y}H{65+post*700:.2f}" stroke="#93a9b9" stroke-width="2"/>')
        if r['pre_nonbio']+r['pre_bio']:
            out.append(f'<circle cx="{65+pre*700:.2f}" cy="{y}" r="4" fill="#087e8b"><title>Antes: {pre*100:.2f}%</title></circle>')
        if r['post_nonbio']+r['post_bio']:
            out.append(f'<circle cx="{65+post*700:.2f}" cy="{y}" r="4" fill="#c17d11"><title>Após: {post*100:.2f}%</title></circle>')
        out.append(f'<text x="800" y="{y+4}">n pós = {r["post_nonbio"]+r["post_bio"]:,}</text>')
    return ''.join(out)+'</svg><p><span style="color:#087e8b">● Antes das 17h</span> · <span style="color:#c17d11">● Após as 17h</span>. Ponto ausente indica denominador zero; não é 0%.</p>'

def render(con,table,fmt,prefix=''):
    cols={r[0] for r in con.execute('DESCRIBE good').fetchall()}
    if 'auth_cuts' not in cols:return '<section><h2>Correlação · em processamento</h2><p>Reprocessando os logs para cruzar o corte exato das 17h com as formas de habilitação.</p></section>'
    def rec(sql):
        c=con.execute(sql);return [dict(zip([x[0] for x in c.description],r)) for r in c.fetchall()]
    con.execute('''CREATE TEMP TABLE crosstab AS SELECT id,uf,municipality,zone,section,name,total,pre,post,
       sum(c.n) FILTER(WHERE c.period='pre' AND c.kind='elector_biometric')::BIGINT pre_bio,
       sum(c.n) FILTER(WHERE c.period='post' AND c.kind='elector_biometric')::BIGINT post_bio,
       sum(c.n) FILTER(WHERE c.period='pre' AND c.kind IN ('no_elector_biometric','pollworker_biometric','pollworker_unassigned_fingerprint','pollworker_captured_fingerprint','biographic'))::BIGINT pre_nonbio,
       sum(c.n) FILTER(WHERE c.period='post' AND c.kind IN ('no_elector_biometric','pollworker_biometric','pollworker_unassigned_fingerprint','pollworker_captured_fingerprint','biographic'))::BIGINT post_nonbio,
       sum(c.n) FILTER(WHERE c.period IN ('pre','post') AND c.kind IN ('unknown','manual_pending'))::BIGINT unclassified
       FROM timed,unnest(auth_cuts) AS u(c) GROUP BY id,uf,municipality,zone,section,name,total,pre,post''')
    con.execute('''CREATE TEMP TABLE section_correlations AS SELECT * EXCLUDE(pre_bio,post_bio,pre_nonbio,post_nonbio,unclassified),
       coalesce(pre_bio,0) pre_bio,coalesce(post_bio,0) post_bio,coalesce(pre_nonbio,0) pre_nonbio,
       coalesce(post_nonbio,0) post_nonbio,coalesce(unclassified,0) unclassified FROM crosstab''')
    def metrics(r):
        a,b,c,d=[r[k] for k in ('post_nonbio','post_bio','pre_nonbio','pre_bio')]
        n=a+b+c+d;r['n']=n
        r['late_rate']=(a+b)/n if n else None;r['nonbio_rate']=(a+c)/n if n else None
        r['phi']=phi(a,b,c,d)
        r['nonbio_share_pre']=c/(c+d) if c+d else None
        r['nonbio_share_post']=a/(a+b) if a+b else None
        return r
    sections=[metrics(r) for r in rec('SELECT * FROM section_correlations')]
    states=[metrics(r) for r in rec('''SELECT uf,count(*) sections,sum(pre_bio)::BIGINT pre_bio,sum(post_bio)::BIGINT post_bio,
       sum(pre_nonbio)::BIGINT pre_nonbio,sum(post_nonbio)::BIGINT post_nonbio,sum(unclassified)::BIGINT unclassified
       FROM section_correlations GROUP BY uf ORDER BY uf''')]
    sr=[r for r in sections if r['n']];ur=[r for r in states if r['n']]
    c_section=coefficient(sr);c_state=coefficient(ur)
    pooled=metrics({key:sum(r[key] for r in states) for key in ('pre_bio','post_bio','pre_nonbio','post_nonbio','unclassified')})
    shared_density_max=max([*density_bins(sr,'nonbio_share_pre').values(),*density_bins(sr,'nonbio_share_post').values(),1])
    within={r['uf']:coefficient([s for s in sr if s['uf']==r['uf']]) for r in ur}
    con.execute('''CREATE TEMP TABLE section_metrics AS SELECT *,
       (post_bio+post_nonbio)*1.0/nullif(pre_bio+post_bio+pre_nonbio+post_nonbio,0) AS late_rate,
       (pre_nonbio+post_nonbio)*1.0/nullif(pre_bio+post_bio+pre_nonbio+post_nonbio,0) AS nonbio_rate,
       pre_nonbio*1.0/nullif(pre_nonbio+pre_bio,0) AS nonbio_share_pre,
       post_nonbio*1.0/nullif(post_nonbio+post_bio,0) AS nonbio_share_post,
       (post_nonbio*1.0*pre_bio-post_bio*1.0*pre_nonbio)/sqrt(nullif((post_nonbio+post_bio)*1.0*(pre_nonbio+pre_bio)*(post_nonbio+pre_nonbio)*(post_bio+pre_bio),0)) AS phi
       FROM section_correlations''')
    con.execute('COPY section_metrics TO ? (FORMAT PARQUET,COMPRESSION ZSTD)',[str(ROOT/'output'/(prefix+'section-correlations.parquet'))])
    con.execute("COPY section_metrics TO ? (HEADER,DELIMITER ';')",[str(ROOT/'output'/(prefix+'section-correlations.csv'))])
    (ROOT/'output'/(prefix+'correlations.json')).write_text(json.dumps(dict(states=states,state_correlation=c_state,section_correlation=c_section,within_states=within,pooled=pooled),ensure_ascii=False,indent=2))
    nf=lambda v:'Indefinido' if v is None else f'{v:.3f}'
    pct=lambda v:'—' if v is None else f'{v*100:.2f}%'
    pre_n=pooled['pre_bio']+pooled['pre_nonbio'];post_n=pooled['post_bio']+pooled['post_nonbio']
    difference=(pooled['nonbio_share_post']-pooled['nonbio_share_pre'])*100 if pre_n and post_n else None
    comparison=(f'Entre os votos classificados, a proporção sem reconhecimento biométrico do eleitor é <strong>{pct(pooled["nonbio_share_pre"])} antes das 17h</strong> '
       f'({fmt(pre_n)} votos) e <strong>{pct(pooled["nonbio_share_post"])} após as 17h</strong> ({fmt(post_n)} votos). '
       f'Diferença observada: <strong>{difference:+.2f} pontos percentuais</strong>.') if difference is not None else 'Ainda não há votos classificados suficientes nos dois períodos para comparar as proporções.'
    out=['<section id="correlacoes"><h2>Correlação · horário × reconhecimento biométrico</h2>',
       '<p>“Com biometria” significa <strong>digital do eleitor reconhecida</strong>. “Sem reconhecimento” reúne identificação biográfica e procedimentos com digital de mesário; não significa ausência de cadastro. Casos sem classificação ficam fora dos denominadores. O instante exato 17:00:00 fica separado.</p>',
       '<p>A divisão pré/pós destes gráficos usa o <strong>horário da confirmação presidencial</strong>. O horário da própria habilitação aparece em uma série separada, para que liberação e confirmação não sejam confundidas.</p>',
       '<div class="notice">Associação descritiva do corpus já conciliado. A coleta parcial não é uma amostra aleatória. Estes coeficientes não demonstram causa, irregularidade nem preferência por candidato. Diferenças de tamanho, região, filas e cobertura podem influenciar os resultados.</div>',
       f'<p>Este cruzamento já foi processado para <strong>{fmt(len(sections))} seções</strong> em {fmt(len(states))} UFs; pode estar atrás da curva temporal enquanto os logs são reprocessados. No gráfico dos estados, os eixos se ajustam aos valores observados; no das seções, a escala vai de 0 a 100%.</p>',
       '<p>'+comparison+' Os denominadores são os votos com procedimento identificável em cada período; não se trata da proporção sobre todo o eleitorado. A associação agrupada pode diferir da associação dentro de cada estado.</p>',
       table(['Comparação de proporções','Unidades','Pearson r','Spearman ρ'],[('Entre estados',fmt(c_state['n']),nf(c_state['pearson']),nf(c_state['spearman'])),('Entre seções',fmt(c_section['n']),nf(c_section['pearson']),nf(c_section['spearman']))]),
       '<p>Em cada unidade: x = votos tardios classificados / todos os votos classificados; y = votos sem reconhecimento biométrico do eleitor / todos os votos classificados. Cada estado ou seção tem peso igual no seu coeficiente. Sem variabilidade, o resultado é indefinido.</p>',
       '<h3>Estados</h3><div style="max-width:760px;margin:auto">',scatter(ur),'</div>',
       '<h3>Seções · densidade de biometria antes e depois das 17h</h3><p>Os dois gráficos usam os mesmos eixos e escala de cores. Em ambos, x é a proporção de votos tardios da seção; y é a proporção sem reconhecimento biométrico do eleitor <strong>no período indicado</strong>. Isso permite comparar como o perfil de identificação muda antes e depois, mantendo a mesma referência de horário.</p>',
       '<h3>Pré-17h · identificação antes das 17:00:00</h3><div style="max-width:760px;margin:auto">',density(sr,'nonbio_share_pre',shared_density_max,'antes das 17h'),'</div>',
       '<h3>Pós-17h · identificação após as 17:00:00</h3><div style="max-width:760px;margin:auto">',density(sr,'nonbio_share_post',shared_density_max,'após as 17h'),'</div>',
       '<p>Seções sem votos classificados no período ficam fora daquele painel. A quantidade de seções nos dois painéis é diferente; maior densidade também reflete esse denominador. “Sem reconhecimento” é o complemento de “digital do eleitor reconhecida” entre os casos classificados.</p>',
       '<h3>Antes e depois das 17h em cada estado</h3>',compare(ur),
       table(['UF','Antes: digital eleitor','Antes: sem reconhecimento','Após: digital eleitor','Após: sem reconhecimento','Sem classificação','φ horário × identificação','r entre seções da UF'],[(r['uf'].upper(),fmt(r['pre_bio']),fmt(r['pre_nonbio']),fmt(r['post_bio']),fmt(r['post_nonbio']),fmt(r['unclassified']),nf(r['phi']),nf(within[r['uf']]['pearson'])) for r in ur]),
       '<p>φ é a correlação entre dois indicadores na tabela 2×2: voto após 17h e ausência de reconhecimento biométrico do eleitor. Positivo: maior frequência relativa de identificação sem reconhecimento nos votos tardios. Negativo: menor frequência relativa. Se uma margem é zero, φ é indefinido. Não se substitui indefinido por zero.</p>',
       '<details><summary>Seções com maior quantidade de eventos após as 17h — até 50 nesta visualização</summary>',
       table(['UF · Município','Zona / Seção','Votos pós 17h','% tardios classificados','% sem reconhecimento','φ'],[(html.escape(r['uf'].upper()+' · '+r['name']),f'{r["zone"]} / {r["section"]}',fmt(r['post']),pct(r['late_rate']),pct(r['nonbio_rate']),nf(r['phi'])) for r in sorted(sr,key=lambda r:r['post'],reverse=True)[:50]]),'</details>',
       '<p>A análise de todas as seções, com as quatro células e coeficiente individual, está nos arquivos <a href="section-correlations.csv">CSV</a> e <a href="section-correlations.parquet">Parquet</a>. <a href="correlations.json">Coeficientes e cruzamentos por estado</a>. Os gráficos são SVGs agregados, sem consultas aos brutos no navegador.</p>',
       '<p class="muted">Cálculos: <a href="https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.pearsonr.html">Pearson</a> e <a href="https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html">Spearman</a>, SciPy. Não se apresentam p-valores de amostra independente para este corpus espacial e ainda incompleto.</p></section>']
    return ''.join(out)
