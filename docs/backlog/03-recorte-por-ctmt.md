---
title: "ingest: recorte de todas as camadas por alimentador (CTMT)"
labels: area:ingest, phase:F1, copilot
milestone: F1 Dados + mapa
---
## Tarefa
`bdgd-light recortar --parquet data/parquet --ctmt <COD_ID>[,<COD_ID>...] --out data/feeders/<COD_ID>.gpkg`:
filtra cada camada pela coluna `CTMT` (ou pela ligação via `UNI_TR_MT`/`PAC` quando a camada não tem
`CTMT`, ex.: SSDBT/UCBT ligam ao transformador UNTRMT, que tem CTMT). Gera um GeoPackage por alimentador
com todas as camadas relevantes, mais um `meta.json` com contagens. Este arquivo é a unidade de trabalho
de todo o resto do projeto (grafo, OpenDSS, tiles).

Depende de #1.

## Critérios de aceite
- [ ] GeoPackage por alimentador com CTMT, SSDMT, SSDBT, UNTRMT, UNSEMT, UNSEBT, UNREMT, UNCRMT, UCMT, UCBT, UGMT, UGBT, PONNOT, RAMLIG, SUB.
- [ ] Regras de junção documentadas em `docs/bdgd-relacoes.md` (quais colunas ligam cada camada).
- [ ] Testes com fixture sintética verificam que nada de outro CTMT vaza para o recorte.
