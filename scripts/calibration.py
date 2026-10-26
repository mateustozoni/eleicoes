"""Aplica a referência de 1º turno à cauda de encerramento, sem mudar horário de voto."""
import html
import json
import pathlib
import shutil
import math

ROOT=pathlib.Path(__file__).resolve().parents[1]

def duration(seconds):
    if seconds is None:return '—'
    minutes,sec=divmod(round(seconds),60)
    return f'{minutes}min {sec:02}s'

def plot(states):
    valid=[s for s in states if s.get('p95_seconds') is not None]
    upper=max([2100]+[(s.get('p95_interval') or [s['p95_seconds'],s['p95_seconds']])[1] for s in valid])*1.1
    height=80+len(valid)*25;x=lambda v:65+800*v/upper
    out=[f'<svg viewBox="0 0 1000 {height}" role="img" aria-label="Percentil 95 do atraso de encerramento no primeiro turno por estado, com intervalo bootstrap">']
    for minute in range(0,int(upper/60)+1,5):
        xx=x(minute*60);out.append(f'<path d="M{xx:.2f} 30V{height-30}" stroke="#e2e9f0"/><text x="{xx:.2f}" y="22" text-anchor="middle">{minute} min</text>')
    out.append(f'<path d="M{x(300):.2f} 30V{height-30}" stroke="#b77e14" stroke-width="1.5" stroke-dasharray="5 4"/>')
    for i,s in enumerate(valid):
        y=48+i*25;lo,hi=s.get('p95_interval') or [s['p95_seconds'],s['p95_seconds']];point=s['p95_seconds']
        out.append(f'<text x="42" y="{y+4}" text-anchor="end">{s["uf"].upper()}</text><path d="M{x(lo):.2f} {y}H{x(hi):.2f}" stroke="#9ab5c4" stroke-width="4"/><circle cx="{x(point):.2f}" cy="{y}" r="4" fill="#087e8b"><title>{s["uf"].upper()}: P95 {duration(point)}; intervalo {duration(lo)} a {duration(hi)}</title></circle><text x="900" y="{y+4}">{duration(point)}</text>')
    caption='Ponto: P95 da amostra; traço: intervalo bootstrap.' if any(s.get('p95_interval') for s in valid) else 'Ponto: P95 da base qualificada completa; não é uma estimativa amostral.'
    return ''.join(out)+'</svg><p class="muted">'+caption+' A linha tracejada dourada indica a janela fixa de 5 minutos, para comparação.</p>'

def render(con,table,fmt):
    source=ROOT/'output/reference-calibration.json'
    data=json.loads(source.read_text()) if source.exists() else {'states':[]}
    states=sorted(data.get('states',[]),key=lambda r:r['uf'])
    full=False;sample_states=states
    op_exists=con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name='operation_sections'").fetchone()[0]
    first_reference=ROOT/'data/raw/first-turn-national.json'
    if op_exists and first_reference.exists():
        expected=int(json.loads(first_reference.read_text())['s']['si'])
        available=con.execute('SELECT count(*) FROM operation_sections WHERE turn=1').fetchone()[0]
        if available==expected:
            cur=con.execute('''SELECT uf,count(*) sampled,count(*) FILTER(WHERE timing_eligible AND deadline_tail_seconds>=0) eligible,
                avg(deadline_tail_seconds) FILTER(WHERE timing_eligible AND deadline_tail_seconds>=0) mean_seconds,
                median(deadline_tail_seconds) FILTER(WHERE timing_eligible AND deadline_tail_seconds>=0) median_seconds,
                quantile_cont(deadline_tail_seconds,.95) FILTER(WHERE timing_eligible AND deadline_tail_seconds>=0) p95_seconds,
                min(deadline_tail_seconds) FILTER(WHERE timing_eligible AND deadline_tail_seconds>=0) min_seconds,
                max(deadline_tail_seconds) FILTER(WHERE timing_eligible AND deadline_tail_seconds>=0) max_seconds
                FROM operation_sections WHERE turn=1 AND uf<>'zz' GROUP BY uf ORDER BY uf''')
            cols=[x[0] for x in cur.description];states=[dict(zip(cols,row)) for row in cur.fetchall()]
            archives=json.loads((ROOT/'output/first-turn-download-status.json').read_text())['files']
            for s in states:
                s['sufficient']=s['eligible']>=100 and s['eligible']>=.8*s['sampled'];s['p95_interval']=None
                s['archive']=archives[s['uf']]['url'];s['indicative_closing_cutoff_seconds']=61200+math.ceil(s['p95_seconds']/60)*60 if s['sufficient'] else None
            full=len(states)==27
            (ROOT/'output/reference-calibration-full.json').write_text(json.dumps(dict(method='closure - max(17h,last presidential marker)',states=states),ensure_ascii=False,indent=2))
    if not states:return '<section id="primeiro-turno"><h2>Primeiro turno · referência operacional</h2><p>Execute os perfis de operação do primeiro turno para calcular a referência integral.</p></section>'
    rows=[];applied=[]
    for s in states:
        p95=s.get('p95_seconds');cut=s.get('indicative_closing_cutoff_seconds')
        if s.get('sufficient') and p95 is not None:
            n,above,raw_late=con.execute('''SELECT count(*),count(*) FILTER(WHERE closing_bsb-greatest(61200,"last")>?),
                count(*) FILTER(WHERE closing_bsb>?) FROM bu_hours
                WHERE uf=? AND time_eligible AND "last" IS NOT NULL AND closing_bsb>=greatest(61200,"last")''',
                [p95,cut,s['uf']]).fetchone()
            cutoff=f'{int(cut)//3600:02}:{int(cut)%3600//60:02}'
            applied.append(dict(uf=s['uf'],reference_p95_seconds=p95,indicative_closing_cutoff_seconds=cut,
                second_turn_eligible=n,second_turn_residual_above_p95=above,second_turn_closing_after_indicative_cut=raw_late))
            above_text=f'{fmt(above)} / {fmt(n)}'
        else:cutoff='Amostra insuficiente';above_text='—'
        ci=s.get('p95_interval')
        rows.append((s['uf'].upper(),f'{fmt(s["eligible"])} / {fmt(s["sampled"])}',duration(s.get('mean_seconds')),
            duration(s.get('median_seconds')),duration(p95),(' a '.join(duration(v) for v in ci) if ci else '—'),cutoff,above_text))
        p=ROOT/'data/reference-first-turn'/(s['uf']+'-metrics.json');target=ROOT/'output/reference-samples'/(s['uf']+'.json')
        if p.exists():
            target.parent.mkdir(exist_ok=True)
            if not target.exists() or target.stat().st_mtime<p.stat().st_mtime:shutil.copyfile(p,target)
    (ROOT/'output/reference-applied.json').write_text(json.dumps(dict(method='BU closing minus max(17h,last presidential event)',states=applied),ensure_ascii=False,indent=2))
    links=' · '.join('<a href="reference-samples/'+s['uf']+'.json">'+s['uf'].upper()+'</a>' for s in states if (ROOT/'output/reference-samples'/(s['uf']+'.json')).exists())
    sources=' · '.join('<a href="'+html.escape(s['archive'],quote=True)+'">'+s['uf'].upper()+'</a>' for s in states)
    data_link='reference-calibration-full.json' if full else 'reference-calibration.json'
    introduction=('<p>Referência calculada na <strong>base integral qualificada do primeiro turno</strong> (04/10/2026), com cobertura e exclusões mostradas por UF. A amostra inicial de 200 seções por UF é preservada para comparação, mas não é a base do P95 final.</p>' if full else '<p>Amostra aleatória reproduzível de até <strong>200 seções por UF</strong>, proveniente dos ZIPs oficiais do primeiro turno (04/10/2026).</p>')
    inference=('<p>Na base integral, a distribuição é descrita diretamente, sem intervalo de erro amostral. Isso não elimina imprecisão do relógio nem ausência de registros. A média, mediana e P95 são referências observadas; não alteram o horário dos votos.</p>' if full else '<p>A média aparece ao lado da mediana e do percentil 95. O intervalo exibido é obtido por 1.000 reamostragens bootstrap. Uma UF só recebe referência aplicável com pelo menos 100 casos válidos e 80% de aproveitamento da amostra.</p>')
    return ('<section id="primeiro-turno"><h2>Primeiro turno · referência operacional por estado</h2>'+introduction+
       '<p>'
       'Somente entram casos com BU/log presidencial conciliados, identificação de seção confirmada, relógio sem regressão detectada e intervalo não negativo.</p>'
       '<p><strong>Cauda de encerramento = horário de encerramento do BU − máx(17h, último voto presidencial).</strong> '
       'Assim, a espera até o horário oficial e os votos posteriores em fila ficam fora desse intervalo. Ele é uma referência observada, não uma prova da causa de cada atraso.</p>'
       +inference+plot(states)+table(['UF','Válidas / base','Média','Mediana','P95','Intervalo amostral (se aplicável)','17h + P95 (arred. minuto)','2º turno: cauda acima do P95 / avaliadas'],rows)+
       '<p><strong>Aplicação:</strong> a última coluna compara a cauda de encerramento do segundo turno à referência da própria UF. '
       '“17h + P95” é apenas uma referência de fechamento para uma seção sem votos posteriores às 17h. Quando há voto tardio, a comparação usa o último voto como base. '
       '<strong>O horário real dos votos não é deslocado nem reclassificado pela demora de encerramento.</strong> As visões de 17h e 17h05 continuam disponíveis como análises de sensibilidade.</p>'
       '<p>A eleição do primeiro turno tem mais cargos e pode ter rotina diferente do segundo. Diferenças entre turnos não demonstram, sozinhas, irregularidade. '
       'O relatório distingue a referência integral qualificada da amostra inicial e mostra cobertura e exclusões, sem aplicar uma média estadual como verdade exata.</p>'
       '<p>Amostras iniciais e horários por UF: '+links+'. <a href="'+data_link+'">Referência agregada utilizada</a> · <a href="reference-applied.json">Aplicação ao segundo turno</a> · <a href="operations-sections.parquet">Protocolo completo por seção</a>.</p>'
       '<p class="muted">Pacotes oficiais TSE de origem: '+sources+'.</p></section>')
