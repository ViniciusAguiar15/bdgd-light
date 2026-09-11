---
title: "ingest: base de micro e minigeração distribuída (MMGD) da ANEEL cruzada com o recorte"
labels: area:ingest, area:grid, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
A BDGD traz as unidades geradoras (`UGBT_tab`, `UGMT_tab`), mas a ANEEL publica à parte a relação de
empreendimentos de MMGD, atualizada diariamente, com distribuidora, município, fonte, potência
instalada e data de conexão. Cruzar as duas dá o retrato de **quanta geração distribuída existe em
cada alimentador da Light** — informação que hoje não entra em nenhuma decisão do sistema.

Fonte: `https://dadosabertos.aneel.gov.br/dataset/relacao-de-empreendimentos-de-geracao-distribuida`
(recursos `empreendimento-geracao-distribuida.parquet` e `.zip`; há dicionário de dados em PDF no
próprio dataset — baixar e seguir o dicionário, não adivinhar nome de coluna).

## Tarefa
- `scripts/baixar_gd.py`: download parametrizado e resumível para `data/gd/` (nunca no git),
  preferindo o Parquet. Registrar a data de extração — a base muda todo dia.
- `src/bdgd_light/ingest/gd.py`: filtrar distribuidora Light e municípios do Rio; normalizar
  potência (kW), fonte, classe, data de conexão.
- **Chave de junção com a BDGD**: descobrir e **documentar** qual campo liga os dois lados
  (código do empreendimento, CEG, unidade consumidora que recebe os créditos, ou apenas
  município + classe). Se não existir chave direta, dizer isso explicitamente e usar a agregação
  possível (município/conjunto), sem fingir precisão que o dado não tem.
- Agregar por alimentador (via UC/trafo quando houver chave; via conjunto ou município quando não) e
  produzir `docs/gd-light.md`: potência instalada por alimentador e por conjunto, fonte predominante,
  evolução por ano de conexão, e **penetração** = kW de GD ÷ carga instalada do alimentador.
- Comparar a contagem com `UGBT_tab`/`UGMT_tab` da BDGD e reportar a divergência entre as duas
  fontes — ela é, por si, um resultado sobre defasagem de cadastro.

## Critérios de aceite
- [ ] Download reprodutível, `data/` fora do git, data de extração registrada no relatório.
- [ ] A chave de junção (ou a ausência dela) está documentada com evidência.
- [ ] `docs/gd-light.md` gerado por script, com penetração por alimentador e a comparação com a BDGD.
