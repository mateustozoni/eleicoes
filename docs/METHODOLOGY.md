# Método e histórico da análise

Este documento descreve a execução analítica original. Para instalação e reprodução em um clone novo, use [RUNNING.md](RUNNING.md) e o [README](../README.md).

Processamento local de arquivos oficiais do TSE, pleito 3221, eleição 6258, cargo Presidente.
O HTML recebe apenas agregados e SVGs calculados em Python/DuckDB. Os brutos ficam em SQLite por UF.

## Executar e retomar

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/collect.py
```

Em outro terminal, para analisar enquanto baixa:

```sh
.venv/bin/python scripts/analyze.py
```

Para gerar o relatório ou atualizá-lo durante a coleta:

```sh
.venv/bin/python scripts/report.py
.venv/bin/python scripts/watch_report.py
```

Abra `output/report.html`. Os comandos são retomáveis. Execute uma instância de cada script por vez.
O coletor usa 64 conexões simultâneas e limita a 95 requisições/s, abaixo do limite oficial de 100/s por IP.
O processamento usa todos os processadores lógicos disponíveis em processos independentes; DuckDB também utiliza os núcleos disponíveis.
Com cerca de 499 mil seções e três requisições por seção, a coleta pode levar várias horas e dezenas de GB.
Downloads já confirmados são reutilizados. Erros de seleção, ausência ou ambiguidade ficam registrados.
Se houver HTTP 403/429 na CDN de resultados, o coletor interrompe a execução para não renovar um bloqueio.

## Auditoria dos artefatos

- `data/raw/<uf>.sqlite`: tabela `files` contém URL, instante UTC, SHA-256 e payload original; tabela `sections` registra cobertura.
- `data/derived/part-*.jsonl`: estatísticas por seção, incluindo conciliação e bins de cinco minutos.
- `output/sections.parquet` e `output/sections.csv`: extrações analíticas.
- `output/summary.json`: agregados usados pelo HTML.
- `output/collection-status.json`: cobertura da coleta, distinta da cobertura da análise.
- `output/analysis-errors.json`: falhas de decodificação/análise.

O índice contém seções agregadas (`nsp`): elas não equivalem a uma segunda urna com votos independentes.
O coletor baixa apenas o único hash Totalizado; quando não existe, preserva o único Recebido como provisório.
Versões rejeitadas e múltiplos hashes sem seleção inequívoca não são somados.

## O que os dados permitem

É possível contar confirmações presidenciais e formas de habilitação por horário, somar resultados gerais
por candidato e identificar locais com eventos após 17h. Não é possível vincular o candidato escolhido
ao horário de um voto. Não é feita interpolação proporcional nem inferência da escolha do eleitor.

O corte é `<17:00:00`, `=17:00:00` e `>17:00:00` em Brasília. Os bins usam `[início,fim)`.
A série principal inclui somente seções em que o total de confirmações de Presidente, incluindo nulos
atribuídos por suspensão, confere com o BU e sem regressão de relógio detectada. Isso não comprova
a exatidão do relógio. O exterior permanece fora do corte temporal de Brasília nesta versão.

O local administrativo é identificado por UF, município, zona e número do local no BU; não se afirma
que essa chave represente um prédio físico único. Durante coleta parcial, ausência de evento tardio
não permite afirmar que não houve voto tardio em todo o local.

Digital do eleitor reconhecida, digital do mesário identificado, digital capturada, digital não associada,
identificação biográfica e classificação insuficiente são preservadas separadamente. Não se conclui
“mesário sem digital” pela simples ausência de mensagem. Tentativas de habilitação não são votos.

## Fontes

- [TSE — documentação da distribuição, EA16, EA18 e EA20](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados)
- [TSE — formato de log 2026](https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/log-do-ecossistema)
- [TSE — prorrogação](https://www.tse.jus.br/comunicacao/noticias/2026/Outubro/esclarecimento-sobre-prorrogacao-da-votacao)
- [Justiça Eleitoral — fusos e onze municípios do Amazonas](https://www.justicaeleitoral.jus.br/fato-ou-boato/checagens/2026/e-falso-que-eleitores-devam-votar-em-dias-diferentes-dependendo-do-candidato-escolhido-entenda)
- [IBGE — malhas](https://servicodados.ibge.gov.br/api/docs/malhas?versao=3)

Os leiautes oficiais foram fornecidos pelo usuário no ZIP baixado do TSE, preservado em
`docs/official-schema.zip`. Os arquivos originais estão em `docs/official-asn1/`; os hashes e
URL de origem constam em `docs/provenance.json`. O PDF oficial de logs também está preservado.
A comparação entre o leiaute anterior e o oficial, em `output/layout-verification.json`, confirma
igualdade dos demais campos após normalizar três nomes de enumerações alterados na especificação.
Todos os payloads eleitorais são obtidos diretamente do TSE.
Não foi implementada verificação criptográfica das assinaturas oficiais; SHA-256 registra a identidade
do arquivo recebido e não substitui a validação da assinatura.

## Verificação

```sh
.venv/bin/python scripts/test_analysis.py
```

Os testes cobrem corte exato, conversão de fuso, digital do mesário, habilitação cancelada,
arquivos de contingência duplicados, regressão de relógio, seleção de hash e conciliação de um BU sintético.

## Correlações solicitadas

O relatório inclui dispersão por UF, densidade das seções e comparação da proporção sem reconhecimento
biométrico do eleitor antes/depois das 17h. Os gráficos usam as contagens da tabela 2×2 por seção,
com o corte exato, e excluem casos sem classificação. Estados e seções possuem Pearson e Spearman
entre proporções, com peso igual por unidade. Cada seção também tem coeficiente φ da sua tabela 2×2.
Margens nulas geram valor indefinido. Os resultados completos ficam em `output/section-correlations.csv`
e `.parquet`; os agregados em `output/correlations.json`. A coleta parcial não é amostra aleatória;
as associações são descritivas e não sustentam conclusões causais, de preferência eleitoral ou fraude.

## Dois cortes de horário

`output/report.html` usa 17h05 como corte analítico, e `output/report-1700.html` preserva a referência de 17h.
Os dois relatórios são calculados localmente, incluindo mapas, correlações, densidades e limites por candidato.
A janela de 17:00:00 a 17:05:00 é mostrada separadamente e não altera o horário oficial.
Os arquivos com prefixo `1700-` correspondem à visão de 17h; os sem prefixo, à visão de 17h05.
O campo `cutoff_seconds` registra o corte nos dados exportados. Os bins continuam sendo intervalos reais de cinco minutos.

## Atualização e primeiro turno

O relatório servido em `http://127.0.0.1:8765/report.html` consulta os estados locais a cada cinco segundos,
sem processar dados brutos no navegador. Novas gerações de HTML são incorporadas preservando a posição de leitura.
Coletor e analisador publicam seus próprios sinais e datas, separados da geração dos gráficos.
O banco `data/analytics.duckdb` incorpora cada lote derivado uma única vez e mantém a revisão mais
nova de cada seção. A migração foi comparada linha a linha aos JSONL em `output/cache-verification.json`.
As duas visões de corte usam o mesmo conjunto de lotes em cada geração, para evitar diferenças
de cobertura enquanto os downloads continuam.

`scripts/reference_first_turn.py` obtém uma amostra aleatória fixa de até 200 pares BU/log por UF
diretamente dos ZIPs oficiais do primeiro turno, por intervalos HTTP. Os originais amostrados ficam em
`data/reference-first-turn/<uf>.sqlite`, com ETag do pacote, nome do membro e SHA-256.
O compartilhamento de requisições reserva 85/s à coleta principal e 10/s à referência; ao terminar,
a referência devolve o orçamento de 95/s à principal.

A calibração usa `encerramento BU - máximo(17h, último voto presidencial)` e mostra média, mediana,
P95 e intervalo bootstrap por UF. Não desloca horários de votos; aplica a referência à cauda operacional
de encerramento do segundo turno. A amostra, sua semente, exclusões e incerteza permanecem explícitas.

`output/cases/` contém dossiês de ocorrências com contagens revisadas, trechos dos logs, horários locais,
linhas, urnas de origem, URLs e hashes. Logs arquivados de outra seção são separados por identificação
de município/zona/seção antes da soma; a contagem bruta fica preservada como referência.

## Revalidação dos auxiliares provisórios

`scripts/refresh_metadata.py` consulta novamente os auxiliares originalmente capturados como Recebido.
Uma confirmação Totalizado só é aplicada quando o hash de seleção e os nomes de BU/log são idênticos
aos da captura original. Mudanças de hash ficam separadas para revisão; os brutos iniciais não são alterados.
O histórico das respostas revalidadas fica em `data/metadata-refresh.sqlite`, com payload, URL, data e SHA-256.
`output/metadata-status.json` registra o andamento e as confirmações. Os arquivos analíticos distinguem
`captured_hash_status` de `hash_status`, com data e SHA-256 da revalidação aplicada.
Durante esta consulta, o orçamento de rede também é compartilhado: 85/s para a coleta principal e 10/s
para os metadados, retornando a 95/s na coleta principal ao término.

## Análise ampliada solicitada

O escopo inclui a coleta integral do primeiro turno, comparação das mesmas seções, tempos registrados
de identificação/habilitação/votação, etapa aproximada de Presidente, intervalos entre sessões e
sinalizações de caudas da distribuição por UF e carga de votação. Os dados não identificam espera
na fila, desistentes, chegada física ou preferência de abstentes.

`scripts/download_first_turn.py` preserva os ZIPs oficiais completos por UF com ETag, SHA-256 e retomada.
`scripts/profile_jobs.py` processa os dois turnos em oito processos e publica lotes atômicos sob
`data/timing/v1/<turno>/<uf>/<lote>/`, com sessões anônimas, estatísticas por seção e histogramas.
`scripts/profile_store.py` incorpora os lotes no DuckDB e cria o índice de consulta por seção.

As comparações e cenários de isonomia devem distinguir evidências observadas de hipóteses de demanda,
capacidade de atendimento e preferência. Nenhum cenário representa uma identificação causal do
resultado que teria ocorrido. Hipóteses são acompanhadas de gráficos que as apoiem ou critiquem.

**O PDF final completo só deve ser produzido após concluir as coletas, processamentos e verificações.**
Deve analisar os achados, ocorrências, explicações sustentadas, incertezas e possíveis consequências
sociais e eleitorais, com fontes, premissas e anexos. Tabelas integrais por seção permanecem em dados
separados; o PDF apresenta síntese e anexos legíveis, sem tentar imprimir centenas de milhares de linhas.

## Publicação final e reprodução

A auditoria integral está em `output/final-audit.json`: verifica igualdade de identificadores entre
brutos, resumos, perfis e protocolos dos dois turnos, partições de votos, monotonicidade dos cortes,
comparação independente dos totais e igualdade da recontagem com a referência nacional.
`output/national-reference-check.json` e `output/first-turn-national-reference-check.json` preservam
URL e SHA-256 de uma nova consulta às totalizações oficiais.

O relatório analítico final fica em `output/pdf/relatorio-presidencial-2026.pdf`. As figuras de publicação
são calculadas em Python/Matplotlib sob `output/figures/`; o PDF usa ReportLab com fontes incorporadas.
O PDF só recebe o estado de verificado após renderização e inspeção visual das páginas.

Com o ambiente Python do projeto e os dados preservados:

```sh
.venv/bin/python scripts/final_audit.py
.venv/bin/python scripts/report.py
.venv/bin/python scripts/publication_figures.py
```

`scripts/build_pdf.py` requer ReportLab e pypdf (instaláveis no ambiente Python pelo requirements.txt). `scripts/finalize_analysis.py` encadeia a auditoria, as duas versões HTML, figuras,
PDF e renderização. Ele aguarda a revalidação dos metadados e deixa a revisão visual como etapa final.
Não dispara uma segunda coleta dos arquivos originais.

Os 28 ZIPs completos do primeiro turno e os SQLite por UF do segundo turno ficam organizados em
`data/first-turn-archives/` e `data/raw/`. Sessões e protocolos usam diretórios próprios por turno,
UF e lote imutável. Não apagar esses diretórios para apenas atualizar a apresentação do relatório.
A consulta por seção é servida por:

```sh
.venv/bin/python scripts/local_report_server.py --port 8765
```

Seções agregadas são encaminhadas à principal, e identificadores sem arquivo publicado são
identificados como tal. O painel consulta sinais compactos a cada cinco segundos, sem enviar
sessões brutas nem listas integrais de hashes ao navegador.

### Ponte de categorias no primeiro turno

`scripts/recount_first_turn_types.py` relê diretamente todos os BUs presidenciais do primeiro turno,
sem reprocessar os logs. A conferência individual dos candidatos da lista nacional passou. Os BUs
registram 5.246 votos nominais no código 28, que não aparece nessa lista; a quantidade coincide com o
campo nacional `vnt`. O tipo bruto `nulo` dos BUs coincide com `vn`, e `vn + vnt = tvn`.
Por isso, o resumo imutável de perfis mantém esses votos em `other_votes`, preservando o conteúdo
recebido. `output/first-turn-vote-type-audit.json` documenta a ponte e
`output/first-turn-code28-sections.parquet` preserva seções, membro do ZIP e SHA-256.
Essa conciliação aritmética não atribui uma causa jurídica à classificação.


## Revisão do corte para 17h05

O corte ativo é 61.500 segundos de Brasília. `scripts/recut_1705.py` reutiliza os bins de cinco
minutos e relê os logs originais das 982 seções do corpus estrito com evento no bin limítrofe,
para separar exatamente 17:05:00 de depois de 17:05:00. O recálculo fica em
`data/cutoffs/1705/sections.parquet` e na tabela `cutoff_1705_sections` do DuckDB.
Os resumos históricos originais de 17h35 não são reinterpretados; o gerador cria uma visão
temporária com campos novos `pre1705`, `at1705`, `post1705` e `auth_cuts1705`. Fora do corpus
estrito esses campos são nulos nas exportações públicas. A versão anterior está preservada em
`output-history/corte-1735/`.

A coorte “2º turno · 17h05+” seleciona sessões com confirmação presidencial estritamente após
17:05:00, elegibilidade da seção e duração válida. O tempo de identificação pode ter começado
antes do corte. Não se usa apenas o bin das 17h05 para selecionar a coorte. As estatísticas são
calculadas nos eventos Parquet, com média ponderada por registros e quantis exatos. O resumo
com/sem reconhecimento do eleitor agrega apenas métodos conhecidos; sem reconhecimento do
eleitor pode incluir digital do mesário.

Reprodução da revisão: execute `recut_1705.py`, `report.py`, `verify_active_cutoff.py`,
`publication_figures.py` e `build_pdf.py` nos ambientes indicados acima.

## Extra: marcos documentais da prorrogação

O corte de 17h05 permanece ativo. `scripts/documentary_sources.py` registra os três marcos adicionais:
recebimento dos fatos no STF às 16:32:49 (texto da liminar), criação da cópia PDF às 17:01:47
(metadados, não assinatura) e comunicação aos juízes de SP às 17h18. O último é o menor horário
explícito encontrado, sem alegar ser o primeiro de todo o Brasil. Não se usa média de horários.
MG é aproximado; TO foi localizado em reprodução de nota; SC não informa hora. As origens e a
precisão permanecem nos agregados e em `docs/stf-20261025/`.

`scripts/documentary_analysis.py` usa um DuckDB separado e reaproveita um recorte anonimizado das
sessões após 16h dos dois turnos em `data/documentary.duckdb`. Contagens por seção são conciliadas
com os BUs; a comparação independente contra os bins centrais está em `documentary-verification.json`.
O extra inclui faixas antes/depois de 17h, métodos, durações, janelas iguais de 15/30 minutos,
mesmas seções entre turnos, fechamento administrativo, precisão de minuto e limites por candidato.
A discrepância entre estimativa publicada do TRE-SP e reconstrução pelo relógio dos BUs é exposta
sem atribuição causal ou conclusão automática de irregularidade.

Reprodução adicional: `documentary_analysis.py`, `verify_documentary.py`, `documentary_report.py` e
`build_pdf.py`. O gerador principal incorpora a visão resumida quando o extra existe. A página
completa fica em `output/documentary-comparison.html`; a consulta por seção inclui os três marcos.
Os cálculos não são realizados no navegador. Não foi confirmada a hora de assinatura da liminar,
nem se supõe que a comunicação ao tribunal ou ao juiz alcançou imediatamente cada mesa.
