# bdgd-light

POC/MVP de um **Centro de Operação da Distribuição (COD) agêntico** sobre a **BDGD da Light**
(Rio de Janeiro), usando dados abertos da ANEEL. A ideia: expor a rede (topologia, chaves, cargas,
gêmeo digital em OpenDSS) como ferramentas para um agente de IA que monitora eventos, propõe manobras
(ex.: FLISR) e as submete à aprovação de um operador humano, num console com mapa.

Plano completo, módulos e fases em [`docs/PLANO.md`](docs/PLANO.md).

## Estrutura

```
src/bdgd_light/        pacote Python (ingest, grid, twin, mcp_server, agent, sim)
  catalogo.py          IDs da BDGD por distribuidora/ano, camadas-chave, domínios TEN_NOM e TIP_UNID
  cli.py               CLI `bdgd-light` (typer): export, inventario, vizinhos, recortar
  ingest/export.py     exportação de camadas para GeoParquet/Parquet/GeoPackage, em lotes
  ingest/parquet.py    leitura das camadas exportadas com filtros empurrados ao pyarrow
  ingest/interligacoes.py  detecção geométrica de chaves NA de interligação entre CTMT
  ingest/inventario.py inventário de alimentadores (CSV + tabela)
  ingest/recorte.py    recorte de todas as camadas por CTMT → GeoPackage + meta.json
scripts/
  baixar_bdgd.py       baixa e extrai a BDGD (Light 2025 por padrão)
  listar_camadas.py    lista as camadas do .gdb
  converter.py         camada → GeoJSON (EPSG:4326) com recorte por bbox
index.html             visor Leaflet legado (será substituído pelo console MapLibre)
docs/                  plano, ADRs, notas da BDGD Light 2025 (bdgd-light-2025.md), regras de junção
                       entre camadas (bdgd-relacoes.md), escolha dos alimentadores (escopo-alimentadores.md)
tests/                 pytest (fixtures sintéticas; dados reais nunca vão para o git)
  fixtures/            bdgd_mini.gpkg (BDGD sintética, 21 camadas, 3 CTMT com interligações
                       geométricas), bairro_sintetico.geojson e gerar_fixture.py, que os (re)cria
data/                  dados baixados/derivados (ignorado pelo git)
```

## Começando

Ambiente sempre isolado com [uv](https://docs.astral.sh/uv/) (nada é instalado no Python do sistema):

```bash
uv sync --extra dev                # cria .venv e instala; + --extra twin --extra agent para OpenDSS e MCP
uv run scripts/baixar_bdgd.py      # Light 2025-12-31 (~1,1 GB)
uv run scripts/listar_camadas.py data/Light_382_2025-12-31_V11_20260824-0926.gdb
uv run pytest && uv run ruff check .
```

Qualquer comando do projeto é `uv run <comando>`; para adicionar dependência, `uv add <pacote>` (e `uv lock`).

Outras versões: `--dist light --ano 2024` (ver `src/bdgd_light/catalogo.py`).

## Comandos

### `bdgd-light export` — camadas da BDGD → GeoParquet/Parquet

Converte o File Geodatabase (~1,1 GB, 43 camadas) para um formato colunar rápido, base das etapas
seguintes (inventário de alimentadores, grafo, tiles):

```bash
# todas as CAMADAS_CHAVE do catálogo que existirem na base → data/parquet/<CAMADA>.parquet
uv run bdgd-light export --gdb data/Light_382_2025-12-31_V11_20260824-0926.gdb

# só algumas camadas, saída em outro diretório e também num GeoPackage único (abre no QGIS)
uv run bdgd-light export --gdb data/Light_382_2025-12-31_V11_20260824-0926.gdb \
    --layers CTMT,SSDMT,UNSEMT,UNTRAT,CRVCRG --out data/parquet --gpkg data/light.gpkg
```

| opção | padrão | descrição |
|---|---|---|
| `--gdb` | (obrigatório) | caminho do `.gdb` (ou de um GeoPackage) |
| `--layers` | `CAMADAS_CHAVE` | camadas separadas por vírgula; camada inexistente → erro claro (exit 1). Sem `--layers`, camadas do catálogo ausentes na base são apenas avisadas e puladas |
| `--out` | `data/parquet` | diretório de saída, um `.parquet` por camada |
| `--gpkg` | — | grava também todas as camadas exportadas (inclusive tabelas) num GeoPackage único |
| `--batch-size` | `100000` | feições por lote de leitura/escrita |

- Camadas geográficas (SSDMT, UNSEMT, UNTRMT, PONNOT…) viram **GeoParquet** (geometria WKB,
  CRS SIRGAS 2000 / EPSG:4674 preservado): `geopandas.read_parquet("data/parquet/SSDMT.parquet")`.
- Tabelas sem geometria (CTMT, CRVCRG, EQTRMT, SEGCON, UCBT_tab, UCMT_tab…) viram **Parquet**
  comum: `pandas.read_parquet(...)`.
- A leitura usa o *stream* Arrow do GDAL em lotes, então camadas grandes não estouram a memória
  (Light 2025: SSDMT com 1,0 M de trechos em ~4 s e UCBT_tab com 5,0 M de linhas em ~23 s, pico de
  memória < 500 MB). O log mostra feições e tempo por camada.
- Na Light 2025 V11 **CTMT é uma tabela** (sem geometria), **não existe camada `UCBT`/`UCMT`/
  `UGBT`/`UGMT` geográfica** (só as tabelas `*_tab`) e as subestações estão em `SUB`/`UNTRAT`.
  Essas e outras particularidades da base (domínios `TEN_NOM` e `TIP_UNID`, numeração de `PAC` por
  alimentador, contagens por camada) estão em [`docs/bdgd-light-2025.md`](docs/bdgd-light-2025.md).

Para testar sem a BDGD real: `uv run bdgd-light export --gdb tests/fixtures/bdgd_mini.gpkg --out /tmp/parquet`
(a fixture sintética é recriada com `uv run tests/fixtures/gerar_fixture.py`).

### `bdgd-light inventario` — uma linha por alimentador (CTMT)

Relatório para escolher os alimentadores do escopo (cenário FLISR: chaves NA de interligação para
transferência de carga, DER, densidade de clientes). Lê o diretório do `export`; Light 2025 inteira
(1.802 CTMT, 1,0 M de trechos MT, 5,0 M de UCBT) em ~3,5 s.

```bash
uv run bdgd-light inventario --parquet data/parquet --out data/inventario_ctmt.csv --top 20
uv run bdgd-light inventario --parquet data/parquet --bairro data/jacarepagua.geojson --top 10
```

| opção | padrão | descrição |
|---|---|---|
| `--parquet` | `data/parquet` | diretório com as camadas exportadas (`CTMT` e `SSDMT` obrigatórias; as demais opcionais — ausentes geram aviso e colunas zeradas) |
| `--out` | `data/inventario_ctmt.csv` | CSV de saída, ordenado por `score` decrescente |
| `--top` | `20` | quantos CTMT mostrar na tabela do terminal (`0` = nenhuma tabela) |
| `--bairro` | — | polígono (GeoJSON/GPKG, EPSG:4326 se sem CRS) que restringe aos CTMT com rede MT que o intersecta; as interligações continuam sendo detectadas contra a base inteira |
| `--raio-tie` | `2` | raio (m) entre chave NA e extremidade de SSDMT de outro CTMT para contar como interligação |

Colunas do CSV (as regras de junção estão em [`docs/bdgd-relacoes.md`](docs/bdgd-relacoes.md)):

| coluna | significado | colunas da BDGD usadas |
|---|---|---|
| `COD_ID`, `NOME` | código e nome do alimentador | `CTMT.COD_ID`, `CTMT.NOME` |
| `tipo` | prefixo do nome: `LDA` aérea, `LDS` subterrânea, `LSA`/`LSS` 25 kV, `TRAFO` | primeira palavra de `CTMT.NOME` |
| `SUB`, `SUB_NOME` | subestação e seu nome | `CTMT.SUB` → `SUB.COD_ID`, `SUB.NOME` (UNTRAT não tem nome) |
| `UNI_TR_AT` | transformador de força que alimenta o CTMT | `CTMT.UNI_TR_AT` (→ `UNTRAT.COD_ID`) |
| `TEN_NOM`, `TEN_NOM_kV` | código do domínio *TEN* e a tensão em kV (`46` = 13,2; `67` = 25) | `CTMT.TEN_NOM`, `catalogo.TENSAO_KV` |
| `MUN` | município (IBGE) majoritário | moda de `UNTRMT.MUN` (ou `UNSEMT.MUN`) dos ativos do CTMT |
| `km_MT` | extensão da rede MT | Σ `SSDMT.COMP` (m) / 1000, por `SSDMT.CTMT` |
| `ENE_MWh_ano` | energia anual do alimentador | Σ `CTMT.ENE_01..ENE_12` (kWh) / 1000 |
| `ENE_UC_MWh_ano` | energia anual das unidades consumidoras | Σ `ENE_01..12` de `UCBT_tab` (via transformador) + `UCMT_tab` |
| `n_UNTRMT`, `kVA_instalado` | transformadores MT/BT e potência instalada | `UNTRMT.CTMT`, Σ `UNTRMT.POT_NOM` |
| `n_UCBT` | unidades consumidoras BT | `UCBT_tab.UNI_TR_MT` → `UNTRMT.CTMT` (não a coluna `CTMT` da tabela, que diverge em 0,09 % das UCs) |
| `n_UCMT` | unidades consumidoras MT | `UCMT_tab.CTMT` |
| `n_DER`, `kW_DER` | geração distribuída e potência | `UGBT_tab.UNI_TR_MT` → `UNTRMT.CTMT` e `UGMT_tab.CTMT`; Σ `POT_INST` |
| `chaves_total`, `chaves_NA`, `chaves_NF` | chaves MT do alimentador e estado normal | `UNSEMT.CTMT`, `P_N_OPE` (`A` aberta, `F` fechada) |
| `chaves_telecomandadas` | chaves com telecomando | `UNSEMT.TLCD = 1` |
| `NA_interligacao` | chaves NA que interligam este CTMT a outro (**detecção geométrica**, contadas dos dois lados: a chave cadastrada no vizinho a ≤ 2 m de um trecho deste CTMT também conta) | `UNSEMT.geometry` + `P_N_OPE = "A"` × extremidades de `SSDMT` com outro `CTMT` |
| `NA_interligacao_telecomandada` | idem, só telecomandadas | + `UNSEMT.TLCD = 1` |
| `NA_interligacao_SE` | idem, chaves dentro do polígono da subestação (disjuntores de saída de alimentadores da mesma SE — não são *ties* de campo) | + `SUB.geometry` |
| `NA_interligacao_campo` | `NA_interligacao` menos as da SE — as chaves que interessam a um cenário FLISR | `EM_SUB = False` |
| `NA_interligacao_campo_telecomandada` | idem, só telecomandadas | + `UNSEMT.TLCD = 1` |
| `n_vizinhos`, `vizinhos` | CTMT interligados (contagem e lista `;`) | idem |
| `n_UNREMT`, `n_UNCRMT` | reguladores e capacitores | `UNREMT.CTMT`, `UNCRMT.CTMT` |
| `lon_min`, `lat_min`, `lon_max`, `lat_max` | bbox da rede MT em EPSG:4326 | limites de `SSDMT.geometry` por CTMT, reprojetados |
| `score` | `NA_interligacao_campo × (n_UCBT + n_UCMT)` — ordena a tabela `--top` (ties de campo × clientes; os disjuntores da SE não contam) | — |

Na Light 2025 os `PAC` são numerados por alimentador e **não há PAC compartilhado entre CTMT**, por
isso a interligação é detectada geometricamente (chave NA a ≤ 2 m de uma extremidade de `SSDMT` de
outro CTMT, em UTM SIRGAS 2000). Detalhes e ressalvas (chaves em barramento de SE, chaves com vários
vizinhos) em [`docs/bdgd-relacoes.md`](docs/bdgd-relacoes.md); a escolha do cluster TQR (PARNAIBA /
CURUMAU / BOCARI, SETD Taquara) em [`docs/escopo-alimentadores.md`](docs/escopo-alimentadores.md).

### `bdgd-light vizinhos` — com quem um alimentador se interliga

```bash
uv run bdgd-light vizinhos --ctmt TQR0007 --parquet data/parquet            # só ties de campo (padrão)
uv run bdgd-light vizinhos --ctmt TQR0007 --parquet data/parquet --com-se   # inclui disjuntores da SE
```

Tabela com um CTMT vizinho por linha: nº de ties, quantas telecomandadas/manuais, quantas dentro da
SE, quantas chaves são do próprio CTMT e quantas do vizinho, e os `COD_ID` das chaves. Por padrão
(`--sem-se`) as chaves dentro do polígono da SE ficam **fora** de todas as contagens e da lista de
chaves — a coluna "Na SE" mostra quantas foram descontadas e um vizinho ligado só pela SE continua
listado com 0 ties; `--com-se` conta tudo, como no inventário. O título traz os totais em chaves
distintas e em pares chave×vizinho — uma chave num barramento de SE pode tocar vários alimentadores.
Aceita `--raio-tie`.

Para `TQR0007` (PARNAIBA): BOCARI 8 ties (2 telecomandadas), TQR33830 3, CURUMAU 2 (1) — nenhuma na
SE.

### `bdgd-light recortar` — um GeoPackage por alimentador (e um do cluster)

Unidade de trabalho do resto do projeto (grafo, OpenDSS, tiles): todas as camadas de um CTMT num
GPKG (abre no QGIS), mais um `meta.json` com contagens, bbox e interligações.

```bash
# um GPKG por CTMT + o GPKG do cluster (união), em data/feeders/
uv run bdgd-light recortar --parquet data/parquet --ctmt TQR0007,TQR33859,TQR33862 --out data/feeders
# um só CTMT num arquivo com nome escolhido
uv run bdgd-light recortar --parquet data/parquet --ctmt TQR0007 --out data/feeders/parnaiba.gpkg
```

| opção | padrão | descrição |
|---|---|---|
| `--ctmt` | (obrigatório) | `COD_ID` dos alimentadores, separados por vírgula; inexistente → erro claro (exit 1) |
| `--parquet` | `data/parquet` | diretório com as camadas exportadas (`CTMT` obrigatória; ausentes são puladas com aviso) |
| `--out` | `data/feeders` | diretório de saída (`<CTMT>.gpkg` + `<CTMT>.meta.json` por alimentador e, com vários, `cluster_<A>-<B>….gpkg`); com um só CTMT pode ser o caminho de um `.gpkg` |
| `--nome-cluster` | `cluster_<A>-<B>…` | nome do GPKG do cluster |
| `--raio-tie` | `2` | raio da detecção de interligações |

Camadas do GPKG, na ordem: `CTMT`, `SUB`, `UNTRAT` (subestação inteira do CTMT), `SSDMT`, `UNSEMT`,
`UNTRMT`, `UNREMT`, `UNCRMT`, `UCMT_tab`, `UGMT_tab` (pela coluna `CTMT`), `SSDBT`, `UNSEBT`, `RAMLIG`,
`UCBT_tab`, `UGBT_tab` (pelo transformador `UNI_TR_MT`), `PONNOT` (postes referenciados por `PN_CON*`),
`EQTRMT`, `EQSE`, `EQRE`, `EQCR` (equipamentos das unidades), `SEGCON`, `CRVCRG` (só os códigos usados) e
`INTERLIGACOES` — camada calculada com as chaves NA de interligação que envolvem o CTMT, dos dois
lados (`COD_ID`, `CTMT`, `CTMT_VIZ`, `SSDMT_VIZ`, `PAC_VIZ`, `DIST_M`, `TLCD`, `TIP_UNID`, `EM_SUB`). As
camadas `UCBT`/`UCMT`/`UGBT`/`UGMT` geográficas entram se existirem (não existem na Light 2025).
`UNSEMT` do recorte contém só as chaves cadastradas no CTMT; as do vizinho estão em `INTERLIGACOES`.
Camadas sem feição para o CTMT não são gravadas, mas aparecem com `0` no `meta.json`. Os testes
garantem que nada de outro CTMT vaza para o recorte (regras em
[`docs/bdgd-relacoes.md`](docs/bdgd-relacoes.md)).

`meta.json`: `nome`, `ctmt` (`COD_ID`, `NOME`, `SUB`), `gerado_em`, `bdgd_light` (versão), `parquet`,
`crs` (`EPSG:4674`), `bbox_4326`, `camadas` (contagem por camada) e `interligacoes` (por par CTMT–vizinho:
`ties`, `ties_telecomandadas`, `ties_em_SE`, `chaves` — tudo o que a detecção achou — e `ties_campo`,
`ties_campo_telecomandadas`, `chaves_campo` — sem os disjuntores da SE, que é o que o FLISR usa).

Cluster do escopo na Light 2025 (`--ctmt TQR0007,TQR33859,TQR33862`): PARNAIBA 14.146 feições (675
SSDMT, 82 UNTRMT, 50 UNSEMT, 6.268 UCBT), CURUMAU 14.608, BOCARI 10.853, cluster 39.185 (23 camadas
cada) em ~3 s; ties de campo PARNAIBA–BOCARI 8 (2 telecomandadas), CURUMAU–BOCARI 7 (1),
PARNAIBA–CURUMAU 2 (1). Cluster alternativo `BMT0001,BMT29737,CBI33798` (DEPAIVA / AVEMAR / RABELO):
22.039 feições, todos os pares com ≥ 1 tie de campo telecomandada.

## Fluxo de trabalho

Backlog em Issues/Projects; issues são especificadas com critérios de aceite e implementadas pelo
GitHub Copilot (coding agent) em PRs revisados. Convenções em
[`.github/copilot-instructions.md`](.github/copilot-instructions.md).

## Referências

- ANEEL — [BDGD (Módulo 10 do PRODIST)](https://dadosabertos.aneel.gov.br/dataset/base-de-dados-geografica-da-distribuidora-bdgd) e [Manual da BDGD](https://dadosabertos-aneel.opendata.arcgis.com/documents/f0d5c43ac67d4f5eb2ddffa4589501b2)
- Badmus et al., *PowerChain: A Verifiable Agentic AI System for Automating Distribution Grid Analyses* — [arXiv:2508.17094](https://arxiv.org/abs/2508.17094)
- [bdgd2opendss](https://github.com/PauloRadatz/bdgd2opendss) (MIT) — conversão BDGD → OpenDSS
- [OpenDSSDirect.py](https://github.com/dss-extensions/OpenDSSDirect.py)
