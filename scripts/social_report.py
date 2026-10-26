"""Contexto cadastral por seção; associação descritiva, sem inferência individual."""
import json
import pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
def render(con,table,fmt):
    path=ROOT/'data/context/locations.parquet'
    if not path.exists():return ''
    con.execute("CREATE OR REPLACE TEMP VIEW location_context AS SELECT * FROM read_parquet('"+str(path).replace("'","''")+"')")
    duplicates=con.execute('SELECT count(*) FROM (SELECT turn,id,count(*) n FROM location_context GROUP BY turn,id HAVING n>1)').fetchone()[0]
    if duplicates:raise ValueError('Duplicate location context keys')
    con.execute('''CREATE OR REPLACE TEMP VIEW social_sections AS SELECT s.*,l.local_type,l.accessibility_status,
        l.id IS NOT NULL AS context_found,try_cast(l.local_code AS INTEGER)=try_cast(s.local AS INTEGER) AS local_matches
        FROM sections s LEFT JOIN location_context l ON l.turn=2 AND s.id=l.id
        WHERE s.time_eligible AND s.uf<>'zz' ''')
    def rec(sql):
        c=con.execute(sql);return [dict(zip([x[0] for x in c.description],r)) for r in c.fetchall()]
    coverage=rec('SELECT count(*) n,count(*) FILTER(WHERE context_found) AS matched_count,count(*) FILTER(WHERE local_matches) same_local FROM social_sections')[0]
    coverage['matched']=coverage.pop('matched_count')
    groups={}
    for dim in ['local_type','accessibility_status']:
        groups[dim]=rec(f'''SELECT coalesce({dim},'Não informado') category,count(*) n,sum(total) ballots,
          sum(post) post17,sum(post1705) post1705,count(*) FILTER(WHERE post>0) sections_post17,
          count(*) FILTER(WHERE post1705>0) sections_post1705,
          10000.0*sum(post)/nullif(sum(total),0) rate17,10000.0*sum(post1705)/nullif(sum(total),0) rate1705
          FROM social_sections WHERE local_matches GROUP BY {dim} ORDER BY n DESC''')
    data=dict(coverage=coverage,groups=groups,duplicate_keys=duplicates)
    (ROOT/'output/social-context.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    out=['<section id="contexto-social"><h2>Contexto dos locais e acesso</h2>',f'<p>Cadastro oficial ligado por UF, município, zona e seção: {fmt(coverage["matched"])} de {fmt(coverage["n"])} seções temporais; {fmt(coverage["same_local"])} também coincidem no código do local. As tabelas usam apenas essas coincidências.</p>']
    for dim,title in [('local_type','Tipo de local cadastrado'),('accessibility_status','Situação cadastral de acessibilidade da seção')]:
        rows=groups[dim];out.append('<h3>'+title+'</h3>')
        maxrate=max([r['rate17'] or 0 for r in rows]+[1]);svg=['<svg viewBox="0 0 1060 '+str(65+len(rows)*40)+'" role="img" aria-label="Votos tardios por dez mil votos, por categoria cadastral">']
        for i,r in enumerate(rows):
            y=25+i*40;label=r['category'];svg.append(f'<text x="5" y="{y+12}" style="font-size:11px">{label}</text>')
            for j,k in enumerate(['rate17','rate1705']):
                width=440*(r[k] or 0)/maxrate;svg.append(f'<rect x="440" y="{y+j*12}" width="{width:.2f}" height="10" fill="'+('#177e89' if j==0 else '#bd801c')+f'"/><text x="{445+width:.2f}" y="{y+j*12+9}" style="font-size:10px">{r[k]:.2f}</text>')
        out.append(''.join(svg)+'</svg><p>Azul: após 17h. Ocre: após 17h05. Unidade: eventos por 10 mil votos no mesmo corpus.</p>')
        out.append(table(['Categoria','Seções','Votos','Após 17h','Após 17h05','Pós 17h / 10 mil','Pós 17h05 / 10 mil'],[(r['category'],fmt(r['n']),fmt(r['ballots']),fmt(r['post17']),fmt(r['post1705']),f'{r["rate17"]:.2f}',f'{r["rate1705"]:.2f}') for r in rows]))
    out.append('<p>“Acessibilidade” é uma situação administrativa da seção, não uma observação da deficiência ou mobilidade de cada eleitor. O tipo do prédio não mede renda, distância percorrida nem qualidade do transporte. Diferenças podem refletir composição regional e tamanho das seções; estas comparações brutas não identificam barreiras causais.</p><p>Consequências possíveis, a investigar com fontes adicionais: custos de deslocamento, dificuldade de retorno ao local e desigualdade de informação podem alterar a oportunidade de comparecer. Os logs só observam quem entrou no fluxo da urna, não quem desistiu ou não chegou. A análise não quantifica esses grupos ausentes.</p><a href="social-context.json">Dados e cobertura do vínculo cadastral</a></section>')
    return ''.join(out)
