# Procedência e conteúdo publicado

Este repositório reúne código de análise, documentos de referência e uma captura dos relatórios gerados. Não é um produto oficial da Justiça Eleitoral.

- BUs, logs e índices eleitorais utilizados na execução foram obtidos dos endpoints oficiais do TSE. Os arquivos brutos não fazem parte do repositório.
- `docs/bu.asn1`, `docs/rdv.asn1`, `docs/official-asn1/`, `docs/official-schema.zip` e a documentação de logs são especificações de terceiros. As URLs e os SHA-256 originais estão nos arquivos de procedência.
- `docs/stf-20261025/` contém cópias de documentos e referências documentais identificadas por origem. A cópia de uma liminar ou seus metadados de criação não são prova da hora de assinatura.
- `assets/` contém pequenos metadados públicos da captura e uma malha simplificada do IBGE, usados para inicializar a reprodução. Não contém logs de votação.
- `public/` contém HTML/PDF, imagens e agregados calculados. Dossiês incluem apenas trechos selecionados com identificadores pessoais omitidos.
- `scripts/synthetic_fixtures.py` gera exemplos artificiais para testes, com assinaturas/hash fictícios. Eles não representam uma urna oficial nem evidenciam validade criptográfica.

Direitos, condições de uso e atribuição dos documentos e dados de terceiros devem ser consultados nas fontes. Sua presença no projeto não altera sua titularidade.
