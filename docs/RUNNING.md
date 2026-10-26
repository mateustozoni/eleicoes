# Como executar e reproduzir

## 1. Apenas consultar a publicação

```sh
git clone https://github.com/mateustozoni/eleicoes.git
cd eleicoes
python3 serve.py
```

Acesse `http://127.0.0.1:8765/report.html` e `http://127.0.0.1:8765/documentary-comparison.html`. O PDF está em `public/pdf/relatorio-presidencial-2026.pdf`. O servidor usa somente a biblioteca padrão e escuta apenas em `127.0.0.1`.

Esse modo **não consulta o TSE**, não inicia downloads e não executa análise no navegador. Os sinais mostrados são os da captura final. Downloads CSV/Parquet omitidos e consultas por seção mostram uma página explicativa.

## 2. Preparar o processamento completo

Use Python 3.11, Linux/macOS ou WSL. A execução original ocorreu em um computador com 10 processadores lógicos e 24 GB de RAM; os arquivos locais ocuparam mais de 200 GB. Reserve pelo menos 250 GB livres para reproduzir o conjunto e permitir temporários. O volume e o tempo variam conforme os arquivos publicados e a conexão.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/bootstrap.py
.venv/bin/python -m unittest discover -s scripts -p 'test_*.py'
```

O bootstrap cria `data/`, `output/` e `tmp/`, copiando os pequenos metadados e a malha incluídos em `assets/`. Não sobrescreve arquivos locais existentes. Não contém BUs, logs ou bancos eleitorais. Os testes constroem BU e log sintéticos em memória, com hashes/assinaturas fictícios; não dependem de bases externas nem validam assinaturas oficiais.

Para renderizar o PDF, instale também Poppler (`pdftoppm` e `pdfinfo`): `brew install poppler` no macOS ou `sudo apt-get install poppler-utils` em Debian/Ubuntu. O gerador usa as fontes distribuídas pelo Matplotlib, sem caminhos de uma máquina específica.

## 3. Baixar os dados oficiais

```sh
.venv/bin/python scripts/reproduce.py --stage download
```

A etapa executa, sequencialmente:

1. `bootstrap.py`: metadados e diretórios.
2. `collect.py`: BUs/logs do segundo turno em SQLite por UF.
3. `download_first_turn.py`: ZIPs oficiais completos do primeiro turno por UF, incluindo exterior.
4. `context_locations.py`: cadastro oficial dos locais.

A coleta de urnas utiliza 64 conexões e até 95 requisições/s. Interrompe em 403/429; não tente contornar bloqueios ou aumentar o limite. Reexecute após resolver a condição: payloads confirmados são reutilizados. Erros, cobertura, bytes e datas ficam em `output/*status.json`.

Os comandos também podem ser executados individualmente. Não execute processos adicionais de coleta na mesma conexão sem compartilhar o orçamento de requisições. O pipeline acima é sequencial para evitar concorrência de rede entre os downloads.

## 4. Processar os arquivos

```sh
.venv/bin/python scripts/reproduce.py --stage process
```

Essa etapa pressupõe que os downloads terminaram sem pendências. Executa resumo central (`analyze.py`), perfis de sessões (`profile_jobs.py`), protocolos de encerramento (`operation_profiles.py --workers 6`), releitura dos tipos de voto do primeiro turno e comparação de leiautes.

Os perfis são publicados em lotes imutáveis por turno/UF. O DuckDB incorpora cada lote uma vez; Parquet armazena sessões e histogramas sem enviá-los ao navegador. Os comandos são retomáveis; preserve os diretórios e não modifique lotes já incorporados.

## 5. Gerar e verificar os relatórios

```sh
.venv/bin/python scripts/reproduce.py --stage report
```

A etapa revalida os totais nacionais e auxiliares provisórios, calcula o corte exato de 17h05, gera os dois HTMLs, calcula o extra documental, executa as auditorias e prepara figuras/PDF.

- `report.html`: corte analítico de 17h05.
- `report-1700.html`: referência de 17h.
- `documentary-comparison.html`: marcos documentais.
- `pdf/relatorio-presidencial-2026.pdf`: documento completo.

O primeiro turno integral substitui a amostra operacional inicial quando estiver qualificado. `reference_first_turn.py` é uma ferramenta opcional da execução histórica; não é necessário gerar a amostra para usar a referência integral.

O cadastro de locais e as fontes documentais são dependências dos capítulos correspondentes. A cópia PDF da liminar e seus metadados estão em `docs/stf-20261025/`. O instante de criação não é tratado como instante da assinatura.

A etapa não atesta sozinha a revisão visual do PDF. Depois da geração:

```sh
.venv/bin/python scripts/review_pdf.py --render
.venv/bin/python scripts/pdf_contact_sheets.py tmp/pdfs/review tmp/pdfs/contact
```

Confira todas as páginas, sobretudo quebras, cabeçalhos, tabelas e gráficos. Após essa inspeção, registre-a com `.venv/bin/python scripts/review_pdf.py --confirm-reviewed`. A confirmação confere se o PDF ainda corresponde ao arquivo renderizado. O pipeline completo pode levar horas. As referências nacionais congeladas não são sobrescritas silenciosamente: uma mudança detectada exige reconciliar as versões antes de aprovar a auditoria.

## 6. Executar o aplicativo com consultas por seção

```sh
.venv/bin/python serve.py --mode full
```

O modo completo serve `output/` e habilita `/section?id=UF/MUNICIPIO_TSE/ZONA/SECAO` usando os lotes Parquet e índices locais. Seções agregadas são encaminhadas à principal; exterior e registros não conciliados são identificados separadamente.

Para outra porta, acrescente `--port 8000`. Não exponha o servidor de desenvolvimento diretamente à internet.

## 7. Exportar uma nova cópia compacta

`scripts/export_public_snapshot.py` exige que `output/finalization-status.json` tenha a revisão final registrada e que o SHA-256 corresponda ao PDF. O sinal de revisão é uma atestação da inspeção realizada, não uma validação de assinaturas eleitorais.

```sh
.venv/bin/python scripts/export_public_snapshot.py
.venv/bin/python scripts/check_publication.py
```

A exportação segue os links dos HTMLs, inclui figuras/PDF/agregados pequenos e substitui downloads grandes por explicações. Não copia SQLite, DuckDB, CSV, Parquet, ZIPs eleitorais ou logs. Listas grandes de revalidação são reduzidas a contadores. `public/snapshot-manifest.json` registra os arquivos efetivamente exportados e seus hashes.

## Organização dos arquivos locais

| Diretório | Conteúdo | Vai para o Git? |
|---|---|---|
| `data/raw/` | Payloads oficiais em SQLite e metadados | Não |
| `data/first-turn-archives/` | ZIPs completos do primeiro turno | Não |
| `data/derived/` | Resumos centrais JSONL | Não |
| `data/timing/`, `data/operations/` | Perfis e protocolos por turno/UF | Não |
| `data/*.duckdb` | Caches locais de análise | Não |
| `output/` | Artefatos completos da execução | Não |
| `output-history/`, `tmp/` | Histórico e temporários | Não |
| `public/` | Snapshot compacto aprovado | Sim |
| `assets/`, `docs/`, `scripts/` | Metadados pequenos, especificações e código | Sim |

Não apague o conjunto local apenas para atualizar o HTML. Uma cópia do GitHub não contém os centenas de GB da execução original e não deve ser apresentada como contendo todos os microdados ou logs brutos.
