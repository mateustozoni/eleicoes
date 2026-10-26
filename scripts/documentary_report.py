"""Apresentação dos marcos documentais e comparações já calculadas."""
import json,pathlib,html,collections,math
from datetime import datetime,timezone
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
from documentary_sources import sources
from timing_report import AUTH_LABELS,LABELS
ROOT=pathlib.Path(__file__).resolve().parents[1];OUT=ROOT/'output'
COLORS={'recebimento':'#3974a4','criacao_pdf':'#b67b17','juizes_sp':'#825293'}
def load():return json.loads((OUT/'documentary-analysis.json').read_text())
def fmt(v):return '—' if v is None else f'{int(v):,}'.replace(',','.')
def nf(v):return '—' if v is None else f'{v:.1f}'
def hh(v):return f'{int(v)//3600:02}:{int(v)%3600//60:02}:{int(v)%60:02}'
def table(headers,rows):
 return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def overview(d=None):
 d=d or load();rows=[]
 for a in d['sources']['anchors']:
  n=next(r for r in d['national'] if r['anchor']==a['id'] and r['turn']==2)
  rows.append((html.escape(a['label']),fmt(n['post_n']),fmt(n['at_n'])))
 return ('<section id="marcos-documentais"><h2>Extra · recebimento, criação e comunicação aos juízes</h2>'
  '<p>Comparação adicional com 16h32min49s (fatos recebidos no STF), 17h01min47s (criação do PDF) e 17h18 (comunicação aos juízes de SP, menor horário explícito localizado). Nenhum desses marcos foi identificado como hora de assinatura. O corte principal de 17h05 permanece disponível.</p>'
  +table(['Marco','Confirmações posteriores no Brasil¹','No segundo nominal exato'],rows)
  +'<p>¹ Corpus de sessões conciliadas, 497.834 seções domésticas. O horário de SP aplicado ao Brasil é uma referência comum de relógio, não uma comunicação nacional. Votos depois das 16h32 incluem votação ordinária antes das 17h.</p>'
  '<p><a href="documentary-comparison.html"><strong>Abrir o extra completo: gráficos, UFs, biometria, tempos e fontes</strong></a> · <a href="documentary-analysis.json">Agregados</a> · <a href="documentary-sections.parquet">Dados por seção e marco</a></p></section>')
def figures(d):
 folder=OUT/'figures';folder.mkdir(exist_ok=True)
 plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'white','savefig.facecolor':'white'})
 def save(n,fig):fig.savefig(folder/(n+'.png'),dpi=180,bbox_inches='tight');plt.close(fig)
 anchors=d['sources']['anchors'];short={a['id']:hh(a['second']) for a in anchors}
 fig,axs=plt.subplots(2,1,figsize=(10,7))
 for ax,turn in zip(axs,[1,2]):
  sums=collections.Counter()
  for r in d['bins']:
   if r['turn']==turn:sums[r['second']]+=r['n']
  xs=list(range(57600,69600,300));ax.step([x/3600 for x in xs],[sums[x] for x in xs],where='post',color='#176e78');ax.set_title(str(turn)+'º turno - confirmações por cinco minutos');ax.set_ylabel('Confirmações');ax.set_xlabel('Horário de Brasília');ax.set_xlim(16,19.3)
  for a in anchors:ax.axvline(a['second']/3600,c=COLORS[a['id']],ls='--',label=short[a['id']])
  ax.legend(fontsize=8);ax.grid(alpha=.15);ax.xaxis.set_major_formatter(FuncFormatter(lambda value,pos:f'{int(value):02}:{round((value-int(value))*60):02}'))
 fig.tight_layout();save('16-documentary-activity',fig)
 fig,ax=plt.subplots(figsize=(10,5));rows=[r for r in d['bands'] if r['turn']==2];labels=[];bottom=np.zeros(3)
 for key,color,label in [('post_before17','#809cad','Entre marco e 17h'),('post_17_to_1705','#c79e52','17h a 17h05, inclusive'),('post_after1705','#835393','Após 17h05')]:
  vals=[next(r[key] for r in rows if r['anchor']==a['id']) for a in anchors];ax.bar(range(3),vals,bottom=bottom,color=color,label=label);bottom+=vals
 ax.set_xticks(range(3));ax.set_xticklabels([hh(a['second']) for a in anchors]);ax.set_yscale('symlog',linthresh=100);ax.set_ylabel('Confirmações posteriores - escala simétrica log');ax.set_title('Votos após cada marco não são todos votos após 17h');ax.legend(fontsize=8);save('17-documentary-bands',fig)
 fig,axs=plt.subplots(1,2,figsize=(10,7));ufs=sorted({r['uf'] for r in d['by_state']});ix=np.arange(len(ufs))
 for ax,rate in zip(axs,[False,True]):
  for j,a in enumerate(anchors):
   r={x['uf']:x for x in d['by_state'] if x['turn']==2 and x['anchor']==a['id']};vals=[r[u]['post_n']*(10000/r[u]['ballots'] if rate else 1) for u in ufs]
   ax.barh(ix+(j-1)*.24,vals,.24,color=COLORS[a['id']],label=short[a['id']])
  ax.set_yticks(ix);ax.set_yticklabels([u.upper() for u in ufs],fontsize=8);ax.invert_yaxis();ax.legend(fontsize=8);ax.set_title('Por 10 mil votos' if rate else 'Quantidade de confirmações');ax.grid(axis='x',alpha=.15)
 fig.tight_layout();save('18-documentary-states',fig)
 kinds=['elector_biometric','no_elector_biometric','pollworker_biometric','pollworker_captured_fingerprint','pollworker_unassigned_fingerprint']
 fig,ax=plt.subplots(figsize=(10,5))
 for j,a in enumerate(anchors):
  stats={r['auth_kind']:r for r in d['method_metrics'] if r['turn']==2 and r['anchor']==a['id'] and r['metric']=='identification_seconds'}
  vals=[stats.get(k,{}).get('mean',np.nan) for k in kinds];ax.bar(np.arange(5)+(j-1)*.24,vals,.24,color=COLORS[a['id']],label='Após '+short[a['id']])
 ax.set_xticks(range(5));ax.set_xticklabels(['Eleitor\nreconhecido','Biográfico /\nsem biometria','Mesário\nidentificado','Mesário\ncaptura','Mesário sem\nvínculo inicial']);ax.set_ylabel('Identificação média (s)');ax.set_title('Segundo turno - métodos nas sessões posteriores');ax.legend(fontsize=8);save('19-documentary-methods',fig)
 fig,axs=plt.subplots(1,3,figsize=(11,4.7),sharey=True)
 for ax,a in zip(axs,anchors):
  for turn,color in [(1,'#3974a4'),(2,'#b67b17')]:
   rows={r['period']:r for r in d['equal_windows'] if r['anchor']==a['id'] and r['turn']==turn and r['width_seconds']==900 and r['metric']=='identification_seconds'}
   ax.plot([0,1],[rows.get(p,{}).get('mean',np.nan) for p in ['pre','post']],marker='o',label=str(turn)+'º turno',c=color)
  ax.set_xticks([0,1]);ax.set_xticklabels(['15 min antes','15 min depois'],rotation=20);ax.set_title(short[a['id']]);ax.grid(alpha=.15);ax.legend(fontsize=8)
 axs[0].set_ylabel('Identificação média (s)');fig.suptitle('Janelas de igual duração - comparação descritiva');fig.tight_layout();save('20-documentary-windows',fig)
 fig,ax=plt.subplots(figsize=(10,4.5));rows={r['anchor']:r for r in d['same_universe_status'] if r['turn']==2}
 for j,(field,label,color) in enumerate([('bu_after','BU ainda não encerrado','#537c9a'),('activity_after','Com confirmação posterior','#c28a31')]):
  ax.bar(np.arange(3)+(j-.5)*.3,[rows[a['id']][field] for a in anchors],.3,label=label,color=color)
 ax.set_xticks(range(3));ax.set_xticklabels([hh(a['second']) for a in anchors]);ax.set_ylabel('Seções no mesmo universo de sessões');ax.set_title('Encerramento administrativo e atividade posterior');ax.legend(fontsize=8);save('21-documentary-status',fig)
 fig,ax=plt.subplots(figsize=(10,4.3));r=d['regional_communications'];x=np.arange(len(r));ax.bar(x,[z['closed_percent'] for z in r],color=['#537c9a','#c28a31','#825293']);ax.set_xticks(x);ax.set_xticklabels([z['uf'].upper()+' · '+z['label'] for z in r]);ax.set_ylim(0,105);ax.set_ylabel('BUs com encerramento declarado até o marco (%)');ax.set_title('Reconstrução por relógio dos BUs - horários regionais');
 for i,z in enumerate(r):ax.text(i,z['closed_percent']+1,f'{z["closed_percent"]:.2f}%',ha='center')
 save('22-documentary-regional',fig)
def render(d):
 anchors=d['sources']['anchors'];src=d['sources'];names={a['id']:a['label'] for a in anchors}
 css='body{max-width:1240px;margin:auto;padding:34px 26px;background:#f3f6fa;color:#18354a;font:15px/1.6 system-ui}section{background:white;border:1px solid #dae3eb;border-radius:12px;padding:26px;margin:24px 0}h1{font-size:34px;line-height:1.2}h2{font-size:24px}h3{font-size:18px}.notice{background:#fff2d8;border-left:5px solid #ad801e;padding:18px}.muted{color:#506c7f}.grid{display:grid;grid-template-columns:1fr 1fr;gap:22px}img{max-width:100%;height:auto}.scroll{overflow:auto;max-height:660px}table{border-collapse:collapse;width:100%;font-size:12px}th,td{padding:10px;text-align:left;border-bottom:1px solid #dde5eb}th{background:#eaf1f6;position:sticky;top:0}a{color:#08798a}@media(max-width:750px){.grid{grid-template-columns:1fr}}'
 page=['<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Extra · marcos documentais da prorrogação</title><style>'+css+'</style><main>',
 '<a href="report.html#marcos-documentais">Voltar ao relatório principal</a> · <a href="pdf/relatorio-presidencial-2026.pdf">PDF completo atualizado</a><h1>Extra · três marcos documentais e a votação</h1><p>Presidente, segundo turno de 2026, com comparação ao primeiro turno. Horário de Brasília. O corte principal de 17h05 permanece no relatório principal.</p>',
 '<div class="notice"><strong>Hora da assinatura não verificada.</strong> Comparamos o recebimento dos fatos no STF, a criação da cópia PDF e o menor horário explícito de comunicação aos juízes localizado (SP). Comunicação ao juiz não demonstra o instante em que cada mesa recebeu a orientação. Não usamos média entre os locais.</div>',
 '<section id="fontes"><h2>O que cada horário significa</h2>',table(['Horário nominal','Etapa','Precisão e alcance','Fonte'],[(hh(a['second']),html.escape(a['label']),html.escape(a['precision']+' · '+a['note']),'<a href="'+a['source']+'">Ver fonte</a>') for a in anchors]),
 '<h3>Horários de comunicação encontrados</h3>',table(['UF','Horário','Qualidade do registro','Fonte'],[(r['uf'].upper(),r['label'],html.escape(r['source_type']+' · '+r['precision']),'<a href="'+r['source']+'">Fonte</a>') for r in src['regional']]),
 '<p>SP é o menor horário explícito entre as fontes localizadas. MG é aproximado; TO é reprodução de nota pela imprensa. SC confirma comunicação sem hora publicada. Isso não é censo nacional, nem comprovação do primeiro aviso de todo o Brasil. Não se preenchem UFs sem horário usando SP.</p>',
 '<p>Em SP, o comunicado também distingue confirmação telefônica às 17h16 e e-mail do TSE às 18h16. Em MG, o ofício regional tem assinaturas às 18h26 e 18h28; esses horários não equivalem à ciência dos juízes. <a href="https://www.tre-mg.jus.br/comunicacao/noticias/arquivos/oficio-circular-no-59-2026-pre">Ofício de MG</a>.</p></section>',
 '<section><h2>Cobertura e contagens após os marcos</h2>',table(['Turno','Seções domésticas de sessões conciliadas','Votos / sessões utilizáveis'],[(r['turn'],fmt(r['sections']),fmt(r['ballots'])) for r in d['coverage']]),
 '<p>O universo de duração exige sessões computadas conciliadas: 497.834 seções no segundo turno, três a menos que a série central de confirmações do relatório principal. Essas três seções não têm eventos depois das 16h no corpus central. As contagens posteriores são conferidas; os denominadores continuam separados.</p>',
 table(['Marco','Turno','Antes','No segundo nominal','Depois','Seções com evento posterior'],[(names[r['anchor']],r['turn'],fmt(r['pre_n']),fmt(r['at_n']),fmt(r['post_n']),fmt(r['sections_with_post'])) for r in d['national']]),
 '<p>“Depois” usa > marco, com o segundo exato separado. Para SP, 17h18 tem precisão de minuto: 17:18:00 é uma referência nominal, não o segundo certificado da comunicação. A sensibilidade ao final do minuto está abaixo. Aplicar 17h18 ao Brasil compara o relógio; não supõe comunicação simultânea nacional.</p>',
 '<img src="figures/16-documentary-activity.png" alt="Confirmações por cinco minutos nos dois turnos com os três marcos">',
 '<h3>Parte da votação posterior ainda ocorreu antes de 17h</h3>',table(['Marco','Depois do marco e antes de 17h','Depois do marco, entre 17h e 17h05 inclusive','Depois de ambos: marco e 17h05'],[(names[r['anchor']],fmt(r['post_before17']),fmt(r['post_17_to_1705']),fmt(r['post_after1705'])) for r in d['bands'] if r['turn']==2]),
 '<p><strong>Votos depois do recebimento dos fatos no STF não são automaticamente votos adicionais da prorrogação.</strong> A maior parte ocorre durante o horário ordinário; não se observa a preferência individual ou o efeito de receber uma ordem.</p><img src="figures/17-documentary-bands.png" alt="Decomposição dos votos posteriores em faixas de horário"></section>',
 '<section><h2>Estado: quantidade e intensidade relativa</h2><img src="figures/18-documentary-states.png" alt="Contagem e taxa por UF após cada marco">',
 table(['Marco','UF','Votos depois','Por 10 mil votos do corpus','Seções com evento depois','Sem reconhecimento entre posteriores'],[(names[r['anchor']],r['uf'].upper(),fmt(r['post_n']),nf(r['post_fraction']*10000),fmt(r['sections_with_post']),nf(100*r['nonbio_share_post'])+'%' if r['nonbio_share_post'] is not None else 'Sem denominador') for r in d['by_state'] if r['turn']==2]),
 '<p>Quantidade depende do tamanho da UF. A composição dos métodos depois do marco pode refletir seleção de seções ainda em atividade; não é efeito causal identificado.</p></section>',
 '<section><h2>As mesmas seções nos dois turnos</h2><p>Esta comparação usa somente pares com ao menos 30 sessões utilizáveis em cada turno. Mantém a seção, mas não torna os turnos equivalentes em demanda ou número de cargos.</p>',
 table(['Marco','UF','Seções pareadas','Posteriores no 1º','Posteriores no 2º','Diferença 2º − 1º'],[(names[r['anchor']],r['uf'].upper(),fmt(r['section_pairs']),fmt(r['first_post']),fmt(r['second_post']),fmt(r['second_post']-r['first_post'])) for r in d['matched_states']]),'</section>',
 '<section><h2>Identificação, votação e cadência após cada marco</h2><img src="figures/19-documentary-methods.png" alt="Tempo de identificação por método após cada marco">',
 '<p>Todos os tempos deste extra são selecionados pelo horário da confirmação presidencial. A identificação pode começar antes do marco. Intervalo entre confirmações inclui pausas e inatividade; não mede fila.</p>']
 for metric in ['identification_seconds','voting_seconds','pres_stage_seconds','confirmation_gap_seconds']:
  page+=['<details><summary>'+html.escape(LABELS[metric])+' · dados por método e turno</summary>',table(['Marco','Turno','Método','Registros da medida','Média (s)','Mediana (s)','P90 (s)'],[(names[r['anchor']],r['turn'],html.escape(AUTH_LABELS.get(r['auth_kind'],r['auth_kind'])),fmt(r['n']),nf(r['mean']),nf(r['median']),nf(r['p90'])) for r in d['method_metrics'] if r['metric']==metric]),'</details>']
 page+=['</section><section><h2>Janelas de igual duração antes e depois</h2><img src="figures/20-documentary-windows.png" alt="Identificação em janelas de quinze minutos antes e depois dos marcos">',
 table(['Marco','Turno','Janela em cada lado','Lado','Confirmações','Confirmações/minuto','Seções com registro'],[(names[r['anchor']],r['turn'],str(r['width_seconds']//60)+' min','Antes' if r['period']=='pre' else 'Depois',fmt(r['n']),nf(r['per_minute']),fmt(r['sections'])) for r in d['window_activity']]),
 '<p>Janelas de 15 e 30 minutos têm duração igual; o segundo do marco fica separado. São comparações descritivas. O esvaziamento das seções ao final do dia, o número de cargos e a composição dos eleitores variam. A coincidência temporal não mede o efeito da decisão.</p>',
 '<details><summary>Tempos nas janelas de igual duração</summary>',table(['Marco','Turno','Janela','Lado','Medida','n','Média','Mediana','P90'],[(names[r['anchor']],r['turn'],str(r['width_seconds']//60)+' min',r['period'],html.escape(LABELS[r['metric']]),fmt(r['n']),nf(r['mean']),nf(r['median']),nf(r['p90'])) for r in d['equal_windows']]),'</details></section>',
 '<section><h2>Fechamento e atividade no mesmo universo</h2><img src="figures/21-documentary-status.png" alt="Seções administrativamente não encerradas e com confirmação posterior">',
 table(['Marco','Turno','Seções','BU encerrado até o marco','BU encerrado depois','Com confirmação depois','Sem hora de BU'],[(names[r['anchor']],r['turn'],fmt(r['sections']),fmt(r['bu_closed']),fmt(r['bu_after']),fmt(r['activity_after']),fmt(r['missing_close'])) for r in d['same_universe_status']]),
 '<p>BU ainda não encerrado é estado administrativo reconstruído pelo relógio registrado; não prova portão aberto, fila ou admissão de novo eleitor. Seções sem voto posterior podem estar aguardando apenas a etapa final.</p></section>',
 '<section><h2>Comunicação regional e disponibilidade administrativa</h2><img src="figures/22-documentary-regional.png" alt="BUs encerrados até os horários regionais de comunicação">',
 table(['UF','Marco regional','BUs publicados','BU encerrado até o marco','%','Confirmações posteriores no corpus de sessões','Seções com confirmação posterior'],[(r['uf'].upper(),r['label'],fmt(r['sections']),fmt(r['closed_at_or_before']),nf(r['closed_percent'])+'%',fmt(r['post_n']),fmt(r['sections_with_post'])) for r in d['regional_communications']]),
 '<p>Os denominadores de BU e de sessões são distintos nesta tabela. MG usa 18h como referência nominal aproximada; TO tem fonte reproduzida. Nenhuma tabela mede quando cada eleitor soube da notícia.</p>']
 sp=next(r for r in d['regional_communications'] if r['uf']=='sp')
 page+=['<h3>SP: reconstrução dos BUs e estimativa publicada não coincidem</h3>',f'<p>O TRE-SP menciona cerca de 80% de seções encerradas às 17h18. A reconstrução desta captura encontra {fmt(sp["closed_at_or_before"])} de {fmt(sp["sections"])} BUs com encerramento até 17:18:00: {sp["closed_percent"]:.2f}%, diferença de aproximadamente {sp["closed_percent"]-80:.2f} pontos percentuais. Há {fmt(sp["protocol_confirmed_at_or_before"])} protocolos com confirmação de encerramento até esse horário.</p>',
 '<p>A diferença fica registrada sem atribuição de causa: estimativa operacional publicada e reconstrução posterior por relógios podem usar informações ou critérios diferentes. O comunicado não fornece sua base de cálculo. Não é evidência suficiente de irregularidade ou de comunicação a todas as mesas. <a href="'+src['anchors'][2]['source']+'">Fonte do TRE-SP</a>.</p>',
 '<h3>Sensibilidade à precisão de minuto</h3>',table(['Âmbito no 2º turno','Depois de 17:18:00','Depois de 17:18:59'],[(label,fmt(sum(r['after_minute_start'] for r in d['communication_minute_sensitivity'] if r['turn']==2 and (uf is None or r['uf']==uf))),fmt(sum(r['after_minute_end'] for r in d['communication_minute_sensitivity'] if r['turn']==2 and (uf is None or r['uf']==uf)))) for uf,label in [(None,'Brasil (referência de relógio)'),('sp','Somente SP')]]),
 '<p>Essa faixa varia apenas o segundo nominal dentro de 17h18; não representa intervalo de confiança nem corrige imprecisão dos relógios das urnas.</p></section>',
 '<section><h2>Correlações e limites por candidato</h2>',table(['Marco','Unidade','Observações','Pearson','Spearman'],[(names[r['anchor']],'UF' if r['unit']=='uf' else 'Seção',fmt(r['n']),('—' if r['pearson'] is None else f'{r["pearson"]:.4f}'),('—' if r['spearman'] is None else f'{r["spearman"]:.4f}')) for r in d['correlations']]),
 '<p>Correlação: proporção diária sem reconhecimento do eleitor versus fração posterior ao marco, no segundo turno. Estados e seções são unidades diferentes; não se traduz uma associação agregada em efeito individual.</p>',
 table(['Marco','Candidato','Mínimo compatível depois','Máximo compatível depois','Votos do candidato fora do conjunto temporal Totalizado'],[(names[r['anchor']],r['candidate'],fmt(r['minimum']),fmt(r['maximum']),fmt(r['unresolved_candidate'])) for r in d['candidate_post_bounds']]),
 '<p>Limites determinísticos do BU, sem vincular a escolha ao horário. Só o conjunto temporal com status Totalizado restringe os intervalos; os demais votos ficam livres. Não se distribuem candidatos proporcionalmente aos horários.</p></section>',
 '<section><h2>Consultar a seção e reproduzir as contas</h2><form action="/section" method="get" target="_blank"><label>UF/município TSE/zona/seção <input name="id" value="sp/71072/0001/0001" required></label> <button>Abrir seção</button></form>',
 '<p><a href="documentary-sections.parquet">Comparação integral por seção, turno e marco</a> · <a href="documentary-window-sections.parquet">Janelas ±15 minutos por seção</a> · <a href="documentary-analysis.json">Agregados e fontes</a></p>',
 '</section></main></html>']
 return ''.join(page)
def publish():
 d=load();assert d['sources']['average_used'] is False
 figures(d);(OUT/'documentary-comparison.html').write_text(render(d))
 for name in ['report.html','report-1700.html']:
  p=OUT/name;s=p.read_text();start=s.find('<section id="marcos-documentais">')
  if start>=0:end=s.index('</section>',start)+len('</section>');s=s[:start]+s[end:]
  insert=s.index('<section id="auditoria-final">');s=s[:insert]+overview(d)+s[insert:];p.with_suffix('.tmp').write_text(s);p.with_suffix('.tmp').replace(p)
 print(json.dumps(dict(published='documentary-comparison.html',anchors=[a['second'] for a in d['sources']['anchors']],average_used=False)))
if __name__=='__main__':publish()
