---
title: "ingest: exportar camadas-chave da BDGD para Parquet/GeoPackage"
labels: area:ingest, phase:F1, copilot
milestone: F1 Dados + mapa
---
## Contexto
A BDGD da Light vem como File Geodatabase (~1,1 GB, dezenas de camadas). Precisamos de um formato
colunar rápido para as etapas seguintes (inventário, grafo, tiles).

## Tarefa
Criar `bdgd_light.ingest.export` e o comando `bdgd-light export --gdb <path> [--layers CTMT,SSDMT,...] [--out data/parquet]`:
- Por padrão exporta todas as camadas em `CAMADAS_CHAVE` (`catalogo.py`).
- Camadas geográficas → GeoParquet (EPSG:4674 preservado) e, opcionalmente, um GeoPackage único (`--gpkg`).
- Tabelas sem geometria (CRVCRG, EQTRMT, EQSE, SEGCON, BASE, UCBT_tab, UCMT_tab) → Parquet.
- Atenção: na Light 2025 V11 **não existe camada SUB**; subestação = UNTRAT/CTAT e coluna `SUB` do CTMT.
- Leitura com `geopandas.read_file(..., engine="pyogrio")`; para camadas grandes (UCBT, SSDBT) ler em
  lotes (`pyogrio.read_dataframe` com `skip_features/max_features` ou `use_arrow=True`) para não estourar memória.
- Log com contagem de feições e tempo por camada (rich).

## Critérios de aceite
- [ ] `bdgd-light export` documentado no README.
- [ ] Testes com um GeoPackage sintético em `tests/fixtures/` contendo CTMT, SSDMT, UNSEMT, UCBT com 3–5 feições.
- [ ] Camada inexistente gera erro claro, não traceback.
- [ ] CI verde.
