"""Capítulos adicionais do PDF; consome só agregados e figuras já preparados."""
import json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
KNOWN={'no_elector_biometric','pollworker_biometric','pollworker_unassigned_fingerprint','pollworker_captured_fingerprint','biographic'}
def append_pdf(page,p,h,table,fig,fmt,dec):
 path=ROOT/'output/documentary-analysis.json'
 if not path.exists():return
 d=json.loads(path.read_text());assert not d['sources']['average_used'];anchors=d['sources']['anchors'];names={a['id']:a['label'].split(' · ')[0] for a in anchors}
 page('Extra 1. Recebimento, criação e comunicação')
 p('Este extra mantém o corte principal de 17h05 e compara três referências documentais. A hora da assinatura da liminar continua não verificada. O menor horário explícito de comunicação aos juízes encontrado é o de SP, 17h18; isso não certifica o primeiro aviso em todo o Brasil. Não foi usada média entre locais.')
 table(['Horário de Brasília','Etapa e natureza','O que não demonstra'],[
  ('16:32:49','Recebimento dos fatos no STF, informado no texto da liminar','Não é hora de assinatura ou publicação.'),
  ('17:01:47','Criação do PDF, conforme metadados da cópia publicada','Não certifica assinatura nem ciência dos juízes.'),
  ('17h18','Comunicação aos juízes de SP, conforme comunicado do TRE-SP','Não demonstra aviso simultâneo às mesas ou a todo o Brasil.')],[85,203,203])
 table(['UF','Comunicação encontrada','Qualidade da fonte'],[(r['uf'].upper(),r['label'],r['source_type']+'; '+r['precision']) for r in d['sources']['regional']],[35,115,341])
 p('MG tem referência aproximada; TO foi localizado em reprodução de nota pela imprensa. SC confirma comunicação sem publicar horário. UFs sem horário não recebem 17h18 por imputação. Em SP, confirmação telefônica às 17h16 e e-mail do TSE às 18h16 são etapas distintas. No ofício regional de MG, as assinaturas de 18h26 e 18h28 não equivalem à hora de ciência dos juízes.')
 for label,url in [('Liminar disponibilizada no servidor de notícias do STF',anchors[0]['source']),('Comunicado do TRE-SP',anchors[2]['source']),('Balanço oficial do TRE-MG',d['sources']['regional'][1]['source']),('Reprodução da nota atribuída ao TRE-TO',d['sources']['regional'][2]['source'])]:
  p(label+': <link href="'+url+'" color="#087e8b">'+url+'</link>','SmallNote')
 page('Extra 2. Votação após os marcos')
 fig('16-documentary-activity','Mesma posição do relógio nos dois turnos; degraus de cinco minutos. Linhas verticais: recebimento dos fatos, criação da cópia e comunicação aos juízes de SP. A posição no relógio não identifica exposição à ordem.',390)
 table(['Marco','Turno','Posteriores','No segundo nominal','Seções com confirmação posterior'],[(names[r['anchor']],r['turn'],fmt(r['post_n']),fmt(r['at_n']),fmt(r['sections_with_post'])) for r in d['national']],[81,45,110,110,145])
 p('Universos de sessão: 497.728 seções no primeiro turno e 497.834 no segundo. A comparação exige sessão computada e duração utilizável; difere em três seções da série central do segundo turno. As três não têm confirmações após 16h. Os denominadores de cada análise permanecem explícitos.')
 page('Extra 3. Recebimento dos fatos não é voto adicional')
 table(['Marco','Posteriores antes de 17h','Posteriores entre 17h e 17h05','Posteriores após 17h05'],[(names[r['anchor']],fmt(r['post_before17']),fmt(r['post_17_to_1705']),fmt(r['post_after1705'])) for r in d['bands'] if r['turn']==2],[95,132,132,132])
 fig('17-documentary-bands','Segundo turno. As faixas são disjuntas e somam os eventos posteriores a cada marco. O eixo usa escala simétrica logarítmica para mostrar ordens de grandeza distintas.',330)
 p('A maioria das confirmações posteriores às 16h32min49s ainda ocorre antes de 17h, no horário ordinário. Não é correto atribuir esse total à prorrogação ou chamá-lo de votos depois da assinatura. Chegada, comunicação à mesa e escolha individual por horário continuam não observadas.')
 page('Extra 4. Estado e referência de relógio')
 fig('18-documentary-states','Segundo turno. Quantidades absolutas e taxas por 10 mil votos do corpus. As cores correspondem aos três marcos. Aplicar 17h18 a uma UF diferente de SP é uma comparação no relógio, sem supor comunicação local nessa hora.',470)
 p('Seções e eleitores ainda em atividade no fim do dia são grupos selecionados. Volume tardio pode refletir tamanho, demanda, número de cargos, atendimento, interrupções e outras condições. O mapa temporal não identifica sozinho quem teria votado sob outra política.')
 page('Extra 4b. Contagens estaduais após cada marco')
 lookup={(r['anchor'],r['uf']):r for r in d['by_state'] if r['turn']==2};ufs=sorted({r['uf'] for r in d['by_state']})
 table(['UF','Seções de sessões','Após 16:32:49','Após 17:01:47','Após 17h18','17h18 / 10 mil'],[(u.upper(),fmt(lookup['recebimento',u]['sections']),fmt(lookup['recebimento',u]['post_n']),fmt(lookup['criacao_pdf',u]['post_n']),fmt(lookup['juizes_sp',u]['post_n']),dec(10000*lookup['juizes_sp',u]['post_fraction'],2)) for u in ufs],[35,90,95,95,90,86])
 p('A última taxa usa os votos do corpus da própria UF. O segundo exato de cada marco fica separado nos agregados. Para 17h18, os valores usam o início nominal do minuto; a variação até 17:18:59 está documentada adiante.')
 page('Extra 5. Identificação após os marcos')
 fig('19-documentary-methods','Métodos conhecidos no segundo turno. As sessões são selecionadas pela confirmação presidencial posterior ao marco; sua identificação pode ter começado antes. Métodos desconhecidos continuam nas tabelas, sem serem recodificados como ausência de biometria.',300)
 summary=[]
 for a in anchors:
  rows=[r for r in d['method_metrics'] if r['anchor']==a['id'] and r['turn']==2 and r['metric']=='identification_seconds']
  for group,label in [({'elector_biometric'},'Digital do eleitor reconhecida'),(KNOWN,'Sem reconhecimento do eleitor')]:
   cells=[r for r in rows if r['auth_kind'] in group];n=sum(r['n'] for r in cells);mean=sum(r['n']*r['mean'] for r in cells)/n if n else None
   summary.append((names[a['id']],label,fmt(n),dec(mean,1)+'s' if mean is not None else '-'))
 table(['Marco','Reconhecimento do eleitor','Registros','Média'],summary,[85,220,100,86])
 p('O resumo pondera pelo número de registros e não deve ser somado às linhas detalhadas. Sem reconhecimento do eleitor pode incluir digital do mesário. Composições e médias não isolam o efeito do método nem do horário.')
 page('Extra 5b. Métodos detalhados no segundo turno')
 labels={'elector_biometric':'Digital do eleitor reconhecida','no_elector_biometric':'Biografia / sem biometria do eleitor','pollworker_biometric':'Digital de mesário identificado','pollworker_captured_fingerprint':'Digital de mesário capturada','pollworker_unassigned_fingerprint':'Digital de mesário sem associação inicial','unknown':'Não classificado'}
 table(['Após o marco','Método','n','Média','Mediana','P90'],[(names[r['anchor']],labels.get(r['auth_kind'],r['auth_kind']),fmt(r['n']),dec(r['mean'],1),dec(r['median'],1),dec(r['p90'],1)) for r in d['method_metrics'] if r['turn']==2 and r['metric']=='identification_seconds'],[80,185,70,52,52,52])
 p('Unidade dos tempos: segundos. O HTML e o JSON acrescentam primeiro turno, habilitação até Presidente, etapa aproximada presidencial e intervalo entre confirmações. Intervalos incluem pausas e inatividade, sem medir diretamente espera em fila.')
 page('Extra 6. Antes e depois com janelas iguais')
 fig('20-documentary-windows','Identificação média em 15 minutos antes e 15 minutos depois do marco. Azul: primeiro turno; ocre: segundo. O segundo do marco é separado. A comparação não é um desenho causal.',265)
 table(['Marco','Turno','Lado','Confirmações','Por minuto','Seções com registros'],[(names[r['anchor']],r['turn'],'Antes' if r['period']=='pre' else 'Depois',fmt(r['n']),dec(r['per_minute'],1),fmt(r['sections'])) for r in d['window_activity'] if r['width_seconds']==900],[84,40,55,100,90,122])
 p('O extra digital também apresenta janelas de 30 minutos e tempos por medida. A comparação das mesmas seções exige ao menos 30 sessões em cada turno. Ela mantém a seção, mas não neutraliza diferenças de demanda e cargos entre turnos. Redução de movimento no fim do dia pode ocorrer sem relação causal com a ordem.')
 page('Extra 7. Fechamento não é atividade de voto')
 fig('21-documentary-status','Mesmo universo de seções conciliadas em cada turno. Encerramento administrativo é reconstruído pelo campo do BU; atividade significa existir confirmação presidencial posterior.',280)
 table(['Marco','Seções 2º turno','BU encerrado até','BU encerrado depois','Com confirmação depois'],[(names[r['anchor']],fmt(r['sections']),fmt(r['bu_closed']),fmt(r['bu_after']),fmt(r['activity_after'])) for r in d['same_universe_status'] if r['turn']==2],[85,101,101,102,102])
 table(['UF','Horário regional','BUs publicados','Encerrados até','%','Confirmações depois'],[(r['uf'].upper(),r['label'],fmt(r['sections']),fmt(r['closed_at_or_before']),dec(r['closed_percent'],2)+'%',fmt(r['post_n'])) for r in d['regional_communications']],[35,96,90,90,80,100])
 p('A tabela regional usa BUs publicados para encerramento e o corpus de sessões para confirmações; os denominadores são diferentes. Um BU ainda não encerrado não comprova portão aberto, admissão de novo eleitor ou fila. MG usa uma referência aproximada de 18h; TO tem nota reproduzida.')
 page('Extra 8. SP: divergência e precisão de minuto')
 sp=next(r for r in d['regional_communications'] if r['uf']=='sp')
 p('O comunicado do TRE-SP menciona cerca de 80% de seções encerradas às 17h18. Na reconstrução desta captura, '+fmt(sp['closed_at_or_before'])+' de '+fmt(sp['sections'])+' BUs têm encerramento declarado até 17:18:00: '+dec(sp['closed_percent'],2)+'%, aproximadamente '+dec(sp['closed_percent']-80,2)+' pontos percentuais acima daquela estimativa. Há '+fmt(sp['protocol_confirmed_at_or_before'])+' protocolos com confirmação de encerramento até esse horário.')
 p('A divergência é registrada sem atribuir causa: estimativa operacional publicada e reconstrução posterior pelos relógios podem usar informação e critérios distintos. O comunicado não fornece sua base de cálculo. A diferença não comprova irregularidade nem recebimento da orientação por cada mesa.')
 fig('22-documentary-regional','BUs com horário declarado de encerramento até o marco regional, em cada UF disponível. A precisão e a origem dos horários diferem, conforme a tabela de fontes.',260)
 sensitivity=d['communication_minute_sensitivity']
 table(['Âmbito no 2º turno','Depois de 17:18:00','Depois de 17:18:59'],[(label,fmt(sum(r['after_minute_start'] for r in sensitivity if r['turn']==2 and (uf is None or r['uf']==uf))),fmt(sum(r['after_minute_end'] for r in sensitivity if r['turn']==2 and (uf is None or r['uf']==uf)))) for uf,label in [(None,'Brasil: referência de relógio'),('sp','Somente SP')]], [211,140,140])
 p('A comparação acima representa a posição nominal dentro de um minuto informado pelo TRE. Não é intervalo de confiança, não autentica os relógios das urnas e não mede atraso de comunicação por mesa.')
 page('Extra 9. Correlações, candidatos e reprodução')
 table(['Marco','Unidade','n','Pearson','Spearman'],[(names[r['anchor']],'UF' if r['unit']=='uf' else 'Seção',fmt(r['n']),dec(r['pearson'],4),dec(r['spearman'],4)) for r in d['correlations']],[85,70,110,113,113])
 p('Relação entre proporção diária sem reconhecimento do eleitor e fração posterior ao marco, no segundo turno. Cada UF ou seção tem peso igual em seu coeficiente. A agregação e a seleção no fim do dia impedem a leitura do coeficiente como efeito causal individual.')
 table(['Marco','Candidato','Mínimo depois','Máximo depois','Votos fora do conjunto temporal Totalizado'],[(names[r['anchor']],r['candidate'],fmt(r['minimum']),fmt(r['maximum']),fmt(r['unresolved_candidate'])) for r in d['candidate_post_bounds']],[85,55,100,100,151])
 p('São limites compatíveis com os totais do BU, sem revelar escolha por horário. Votos fora do conjunto qualificado com metadado Totalizado ampliam os intervalos. Não se rateia candidato proporcionalmente ao horário.')
 p('O HTML adicional apresenta todas as UFs, métricas por método/turno, janelas de 15 e 30 minutos e pares de seções. A consulta individual da seção inclui os três marcos. Os arquivos documentary-analysis.json, documentary-sections.parquet e documentary-window-sections.parquet preservam os números e a procedência. A conferência independente contra os bins centrais está em documentary-verification.json.')
