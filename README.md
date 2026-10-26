# Eleições 2026 — análise dos horários de votação para presidente

Código de coleta e processamento de BUs/logs oficiais do TSE, aplicativo local e relatório já calculado do segundo turno presidencial, com comparação ao primeiro turno.

- [PDF completo](public/pdf/relatorio-presidencial-2026.pdf)
- [HTML principal](public/report.html) — corte de **17h05**, com referência alternativa de 17h
- [Extra documental](public/documentary-comparison.html) — recebimento dos fatos no STF, criação do PDF e comunicação aos juízes
- [Como reproduzir a análise](docs/RUNNING.md)
- [Método, fontes e limitações](docs/METHODOLOGY.md)

## Abrir o relatório sem baixar as urnas

Requer apenas Python 3.9 ou superior; não precisa instalar dependências nem baixar dados eleitorais:

```sh
git clone https://github.com/mateustozoni/eleicoes.git
cd eleicoes
python3 serve.py
```

Abra **http://127.0.0.1:8765/report.html**. Para outra porta:

```sh
python3 serve.py --port 8000
```

O diretório `public/` é uma **cópia compacta e estática** da análise final. Seus contadores são da captura publicada, sem iniciar coleta em segundo plano. Os arquivos HTML são exibidos como código na interface do GitHub; use o servidor acima ou habilite opcionalmente GitHub Pages.

As consultas individuais por seção e os downloads grandes apontam para uma explicação quando os dados necessários não estão presentes. Para habilitar o aplicativo completo, reproduza o processamento e execute `python3 serve.py --mode full` no ambiente com as dependências.

## O que foi publicado

| Conteúdo | Local |
|---|---|
| HTML, PDF, gráficos e agregados pequenos | `public/` |
| Coleta, parsers, cálculos, verificações e geradores | `scripts/` |
| Metadados pequenos da captura e malha simplificada | `assets/` |
| Leiautes ASN.1, documentação e procedência | `docs/` |
| Dependências da análise completa | `requirements.txt` |
| Testes com dados sintéticos, sem logs brutos | `scripts/test_*.py` |

**Não estão no Git:** SQLite, DuckDB, arquivos de urna brutos, ZIPs eleitorais, logs de execução, sessões Parquet, exportações grandes CSV/Parquet, ambientes virtuais, temporários ou históricos de saída. O `.gitignore` bloqueia esses conteúdos. O pequeno ZIP em `docs/official-schema.zip` contém somente a especificação oficial dos formatos, não arquivos eleitorais.

`public/snapshot-manifest.json` lista os arquivos publicados, tamanhos e SHA-256. Os dossiês do relatório contêm trechos selecionados com identificadores pessoais omitidos, não os pacotes completos de logs.

## Instalar o ambiente completo

Para processamento, recomendamos **Python 3.11 em Linux ou macOS**. Em Windows, use WSL para o pipeline; o visualizador estático funciona com Python padrão.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/bootstrap.py
.venv/bin/python -m unittest discover -s scripts -p 'test_*.py'
```

O bootstrap copia apenas metadados pequenos congelados e cria diretórios. **Não baixa BUs nem logs.** A análise completa trabalha com centenas de GB; veja as etapas e os recursos observados em [RUNNING.md](docs/RUNNING.md).

## Reproduzir os cálculos

Os downloads grandes só começam quando solicitados explicitamente:

```sh
.venv/bin/python scripts/reproduce.py --stage download
.venv/bin/python scripts/reproduce.py --stage process
.venv/bin/python scripts/reproduce.py --stage report
.venv/bin/python serve.py --mode full
```

Cada etapa e suas dependências estão detalhadas em [RUNNING.md](docs/RUNNING.md). Os scripts preservam originais, hashes e checkpoints. Não execute duas instâncias do mesmo estágio sobre os mesmos diretórios. O ambiente de processamento e as bases locais não são necessários para apenas consultar o PDF ou o snapshot.

## Interpretação dos resultados

A publicação corresponde à captura analisada: **499.207 BUs principais publicados**, com recontagem nacional conciliada. Nem todas as seções entram nos mesmos subconjuntos temporais; exclusões, exterior e metadados ainda provisórios aparecem no relatório.

O BU informa totais por candidato; o log informa eventos e horários, **sem vincular a escolha de candidato ao minuto do voto**. São apresentados limites matemáticos, não rateio proporcional de candidatos por horário. As correlações e os cenários são descritivos e condicionais; não identificam sozinhos efeito causal, fraude, espera em fila ou preferência de abstentes.

A coorte “2º turno · 17h05+” usa confirmação presidencial estritamente depois de 17:05:00 de Brasília. A identificação pode começar antes desse instante. O extra usa 16:32:49, 17:01:47 e 17h18 como marcos distintos; o último é o menor horário explícito de comunicação aos juízes encontrado nas fontes, sem afirmar ser o primeiro de todo o país.

Não foi implementada validação criptográfica das assinaturas oficiais. SHA-256 permite identificar os arquivos recebidos, mas não substitui essa validação.

## Publicação opcional no GitHub Pages

Há um workflow manual em `.github/workflows/pages.yml`, que publica **somente `public/`**, sem executar coleta. Para habilitar:

1. No GitHub, abra **Settings → Pages → Source → GitHub Actions**.
2. Em **Actions → Publicar relatório no Pages**, execute **Run workflow**.

Isso é opcional; o clone e o servidor local já funcionam sem configurar Pages. [Documentação oficial](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

## Fontes e procedência

Os endpoints e a documentação do TSE, a malha do IBGE e os documentos citados estão registrados em `docs/`, nos agregados e no PDF. Os metadados em `assets/bootstrap/` são uma referência congelada para reprodução; a etapa de relatório consulta novamente os totais nacionais e interrompe a auditoria se a referência tiver mudado. Consulte [NOTICE.md](NOTICE.md) para a distinção entre código, documentos de terceiros e artefatos gerados.
