# bdgd-light

POC/MVP de um **Centro de Operação da Distribuição (COD) agêntico** sobre a **BDGD da Light**
(Rio de Janeiro), usando dados abertos da ANEEL. A ideia: expor a rede (topologia, chaves, cargas,
gêmeo digital em OpenDSS) como ferramentas para um agente de IA que monitora eventos, propõe manobras
(ex.: FLISR) e as submete à aprovação de um operador humano, num console com mapa.

Plano completo, módulos e fases em [`docs/PLANO.md`](docs/PLANO.md); decisões de stack e
arquitetura (e alternativas descartadas) em [`docs/adr/ADR-001-stack.md`](docs/adr/ADR-001-stack.md).

## Estrutura

```
src/bdgd_light/        pacote Python (ingest, grid, twin, mcp_server, agent, sim)
  catalogo.py          IDs da BDGD por distribuidora/ano, camadas-chave, domínios TEN_NOM e TIP_UNID
  cli.py               CLI `bdgd-light` (typer): export, inventario, vizinhos, recortar, grafo, dss,
                       tiles, llm, audit
  ingest/export.py     exportação de camadas para GeoParquet/Parquet/GeoPackage, em lotes
  ingest/parquet.py    leitura das camadas exportadas com filtros empurrados ao pyarrow
  ingest/interligacoes.py  detecção geométrica de chaves NA de interligação entre CTMT
  ingest/inventario.py inventário de alimentadores (CSV + tabela)
  ingest/recorte.py    recorte de todas as camadas por CTMT → GeoPackage + meta.json
  ingest/tiles.py      recorte GPKG → GeoJSONSeq 4326 (atributos derivados para o estilo) → tippecanoe
                       → PMTiles para o console
  grid/rede.py         grafo MT (networkx) do alimentador/cluster: fonte, chaves, ties, isolamento,
                       restauração; grid/geojson.py exporta o estado em GeoJSON 4326
  twin/convert.py      BDGD → OpenDSS via bdgd2opendss (36 Masters por CTMT); twin/powerflow.py
                       resolve o fluxo com OpenDSSDirect (tensões, violações, perdas, sobrecargas);
                       twin/cluster.py monta o Master do cluster e traduz manobras do grafo em DSS
  agent/llm.py         interface LLMClient (chat com tool calling), FakeLLMClient para testes,
                       OpenAICompatClient (qualquer API chat/completions) e preset GitHubModelsClient;
                       agent/audit.py é o log de auditoria encadeado por hash (JSON Lines)
console/               console do operador: Vite + TypeScript + MapLibre GL JS lendo PMTiles
                       (public/tiles/exemplo_{tijuca,ipanema}.pmtiles = clusters da demo; exemplo.pmtiles
                       = TQR, regressão), seletor de cenário, sobreposição do estado do grafo,
                       smoke test headless (scripts/smoke.mjs); publicado no Pages por Actions
scripts/
  baixar_bdgd.py       baixa e extrai a BDGD (Light 2025 por padrão)
  listar_camadas.py    lista as camadas do .gdb
  converter.py         camada → GeoJSON (EPSG:4326) com recorte por bbox
  listar_modelos.py    lista os modelos do provedor LLM configurado (destaca tool calling)
index.html             visor Leaflet legado (arrastar o GeoJSON de scripts/converter.py); o console
                       novo é console/
docs/                  plano, ADRs (adr/ADR-001-stack.md, ADR-002-console-maplibre-pmtiles.md), notas da
                       BDGD Light 2025 (bdgd-light-2025.md),
                       regras de junção entre camadas (bdgd-relacoes.md), escolha dos alimentadores
                       (escopo-cidade.md = v3, clusters Tijuca e Ipanema; escopo-alimentadores.md = v2,
                       cluster TQR), mapeamento BDGD → grafo (grid-modelo.md),
                       spikes OpenDSS (spike-opendss.md) e LLM (spike-llm.md)
tests/                 pytest (fixtures sintéticas; dados reais nunca vão para o git)
  fixtures/            bdgd_mini.gpkg (BDGD sintética, 21 camadas, 3 CTMT com interligações
                       geométricas), bairro_sintetico.geojson e gerar_fixture.py, que os (re)cria;
                       dss/ieee13/ (alimentador IEEE 13 barras para o fluxo de potência)
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
vizinhos) em [`docs/bdgd-relacoes.md`](docs/bdgd-relacoes.md); a escolha dos clusters da demo (v3:
Tijuca `ALC9925,ALC9946,URG29983,RCP9882` e Ipanema `PTS0001,PTS9088,PTS9924,PTS4022`) em
[`docs/escopo-cidade.md`](docs/escopo-cidade.md) e a do cluster TQR (PARNAIBA / CURUMAU / BOCARI,
SETD Taquara, hoje rede de regressão) em [`docs/escopo-alimentadores.md`](docs/escopo-alimentadores.md).
Chaves NA a até 50 m do polígono da SE contam como "na SE" (`EM_SUB`), não como tie de campo — caso
do pátio da SE Posto Seis, em Ipanema.

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

### `bdgd-light grafo` — grafo do alimentador, falta, isolamento e restauração

Monta a rede MT de um recorte como `networkx.Graph` (nós = PAC; arestas = trechos `SSDMT`, chaves
`UNSEMT` com estado NA/NF e ties da camada `INTERLIGACOES`), energiza a partir do disjuntor de saída
da SE (`CTMT.PAC_INI`) e simula manobras. Mapeamento e decisões em
[`docs/grid-modelo.md`](docs/grid-modelo.md).

```bash
# resumo + ties de um alimentador
uv run bdgd-light grafo --gpkg data/feeders/TQR0007.gpkg
# falta num trecho: chaves a abrir, clientes desligados e chaves NA que restauram; estado em GeoJSON
uv run bdgd-light grafo --gpkg data/feeders/cluster_TQR0007-TQR33859-TQR33862.gpkg \
    --falha 11798327 --geojson data/feeders/estado_tqr.geojson
# manobras manuais antes da análise
uv run bdgd-light grafo --gpkg data/feeders/TQR0007.gpkg --abrir 310744064 --fechar 752622332
```

| opção | padrão | descrição |
|---|---|---|
| `--gpkg` | (obrigatório) | `<CTMT>.gpkg` (um alimentador; vizinhos viram nós externos `EXT:<CTMT>`) ou `cluster_….gpkg` (ties ligadas pelos PAC reais) |
| `--falha` | — | `COD_ID` de um trecho `SSDMT` em falta |
| `--abrir` / `--fechar` | — | `COD_ID` de chaves `UNSEMT` a manobrar antes da análise, por vírgula |
| `--geojson` | — | grava o estado (energizado/fonte por trecho, chaves, trafos) em EPSG:4326; com `--falha`, depois do isolamento |
| `--ties-na-se` | desligado | inclui como ties as chaves NA dentro do polígono da SE |

Em Python:

```python
from bdgd_light.grid import Cluster, Feeder, estado_geojson

f = Feeder.from_gpkg("data/feeders/TQR0007.gpkg")  # 719 nós, 675 trechos, 50 chaves, 13 ties
f.energized_nodes()
f.customers_downstream("TQR0007_MT_52738")
iso = f.isolate_segment("310743928")  # chaves mínimas a abrir, zona, desligados
for op in f.restore_options("310743928"):  # chaves NA que devolvem tensão, por clientes
    print(op.chave, op.fonte, op.tlcd, op.clientes)
c = Cluster.from_gpkg("data/feeders/cluster_TQR0007-TQR33859-TQR33862.gpkg")
estado_geojson(c, "estado.geojson")
```

Cluster TQR na Light 2025: 2.069 nós, 46,65 km, 162 chaves, 35 ties, 16.504 UCBT, 0,1 s para montar.
Falta no tronco de BOCARI (`11798327`): abrir 4 chaves, 2.023 UCBT desligados, 10 opções que
restauram 1.984 via PARNAIBA (3 telecomandadas) ou CURUMAU (1 telecomandada).

### `bdgd-light dss` — alimentador em OpenDSS, fluxo de potência e manobras

Converte CTMT com o [bdgd2opendss](https://github.com/PauloRadatz/bdgd2opendss) (precisa do `.gdb`
inteiro; ≈3 min) e resolve o fluxo de potência snapshot com OpenDSSDirect, reportando tensões por
nó, violações fora de 0,93–1,05 pu, perdas e sobrecargas. Com vários `--ctmt` monta um Master único
do cluster (uma `Vsource` por alimentador) e, com `--gpkg` (recorte do `bdgd-light recortar`),
traduz as manobras do grafo — falta, isolamento e restauração pela tie — em comandos OpenDSS antes
do `Solve`. Requer `uv sync --extra twin`. Relatório do spike (o que o conversor precisou,
resultados, FLISR no gêmeo e decisões) em [`docs/spike-opendss.md`](docs/spike-opendss.md).

```bash
# converte (ou reaproveita data/dss/sub_<SUB>/TQR0007/) e resolve o Master de dia útil de janeiro
uv run bdgd-light dss --gdb data/Light_382_2025-12-31_V11_20260824-0926.gdb --ctmt TQR0007 \
    --out data/dss --json data/dss/TQR0007_fluxo_DU01.json
# só o fluxo, em qualquer Master .dss, com um comando OpenDSS antes do Solve
uv run bdgd-light dss --master "data/dss/sub__10385871/TQR0007/Master_SA07_202608382_TQR0007_------1-----.dss" \
    --comando "set loadmult=0.6"
# cluster TQR (modelos já convertidos em data/dss): falta no trecho 11798327 de BOCARI, isolamento
# pelo grafo e restauração fechando a tie telecomandada 1007642983 (via PARNAIBA)
uv run bdgd-light dss --ctmt TQR0007,TQR33859,TQR33862 --out data/dss \
    --gpkg data/feeders/cluster_TQR0007-TQR33859-TQR33862.gpkg --falha 11798327 --restaurar 1007642983
# cluster Tijuca (demo, cenário A): falta no tronco de CABOFRIO e restauração por outra SE
uv run bdgd-light dss --gdb data/Light_382_2025-12-31_V11_20260824-0926.gdb \
    --ctmt ALC9925,ALC9946,URG29983,RCP9882 --out data/dss --gpkg data/feeders/cluster_tijuca.gpkg \
    --falha 11304252 --restaurar 746851189
```

Bancos de unidades monofásicas (`UNTRMT.TIP_TRAFO = DF`) saem do bdgd2opendss como trifásicos com
barras de 2 nós, o que aterra um vértice do delta; `converter()` corrige isso ao gerar ou reaproveitar
a pasta (`twin.corrigir_bancos_monofasicos`). Pastas convertidas antes dessa correção são consertadas
na primeira reutilização.

| opção | padrão | descrição |
|---|---|---|
| `--ctmt` | — | alimentador(es) por vírgula; com mais de um, escreve `<out>/cluster_<A>-<B>…/Master_<dia><mês>_<cenário>.dss` |
| `--gdb` | — | diretório `.gdb` da BDGD; dispensável se o modelo já estiver em `--out` |
| `--out` | `data/dss` | raiz da saída; o modelo fica em `<out>/sub_<SUB>/<CTMT>/` com 36 Masters (DU/SA/DO × mês). Se já existir, não reconverte |
| `--dia` / `--mes` | `DU` / `1` | Master a resolver |
| `--master` | — | resolve direto este `.dss`, sem converter |
| `--gpkg` | — | grafo do recorte para traduzir manobras (exigido por `--falha`, `--restaurar`, `--abrir`, `--fechar`) |
| `--falha` | — | trecho SSDMT em falta: abre no gêmeo as chaves que o isolam (as de `grafo --falha`) |
| `--restaurar` | — | chave NA a fechar depois do isolamento (cria a `Line` da chave + jumper até o `PAC_VIZ` da tie) |
| `--abrir` / `--fechar` | — | chaves avulsas a manobrar antes do `Solve` (vírgula) |
| `--sem-fluxo` | — | só converte/monta e mostra o Master escolhido |
| `--vmin` / `--vmax` | `0.93` / `1.05` | faixa de tensão (pu) para contar violações |
| `--sem-estabilizar` | — | não aplica a cascata `maxiterations=100` → `vminpu=0.9` → `model=2` quando não converge |
| `--comando` | — | comando OpenDSS extra antes do `Solve` (repetível) |
| `--json` / `--top` | — / `10` | grava resumo (com potência por fonte), piores barras e sobrecargas; tamanho das tabelas |

Sai com código 2 se o fluxo não convergir. Em Python:

```python
from bdgd_light.grid import Cluster
from bdgd_light.twin import (
    comandos_manobras,
    converter,
    escolher_master,
    montar_master_cluster,
    run_powerflow,
)

pasta, segundos = converter(
    "data/Light_382_2025-12-31_V11_20260824-0926.gdb", "TQR0007", "data/dss"
)
r = run_powerflow(escolher_master(pasta, "DU", 1))  # snapshot de pico
r.convergiu, r.ajustes, r.v_min_pu, r.v_max_pu, r.perdas_kw
r.violacoes  # nós de fase fora da faixa   r.sobrecargas  # elementos > 100 % da ampacidade
r.tensoes  # barra, no, fase, kv_base, v_pu   r.correntes  # elemento, i_max_a, i_nominal_a, carregamento_pct

# cluster + manobras do grafo no gêmeo
rede = Cluster.from_gpkg("data/feeders/cluster_TQR0007-TQR33859-TQR33862.gpkg")
opcao = rede.restore_options("11798327")[0]  # melhor opção (TLCD primeiro)
master = montar_master_cluster(
    [f"data/dss/sub__10385871/{c}" for c in rede.ctmts],
    "data/dss/cluster_TQR/Master_flisr.dss",
    comandos=comandos_manobras(rede, opcao.manobras),
)
r = run_powerflow(master)
r.fontes  # kW/kvar por Vsource   r.tensoes_mt()  # nós MT com a coluna ctmt
```

TQR0007 (Light 2025, Master DU01): 6.334 barras, 12.312 cargas, converge em 5 iterações (0,5 s) com
`vminpu=0.9`; MT entre 1,016 e 1,045 pu; 988 nós BT abaixo de 0,93 pu, concentrados em ramais de
ligação com centenas de metros cadastrados na própria BDGD. Cluster TQR (3 alimentadores, 18.554
barras, 33.340 cargas): 9 iterações, 1,2 s; a restauração de BOCARI via PARNAIBA leva o disjuntor de
149 A a 221 A e a MT transferida fica em ≥ 1,004 pu, sem sobrecarga na MT.

Cluster Tijuca (4 alimentadores de 3 SEs, 10.029 barras, 32.132 cargas): 13,3 MW, perdas 6,3 %, MT em
1,036–1,045 pu, 6 iterações em 2,5 s. Falta em `11304252` (tronco de CABOFRIO) deixa 4.036 UCBT sem
luz; as três restaurações possíveis convergem e o gêmeo as ordena — via `974020904` (RIMARAES, mesma
SE) perdas 876 kW e MT ≥ 1,027 pu; via `746851189` (BOMPASTOR, SE Rio Comprido) 893 kW e ≥ 1,018 pu;
via `977361689` (AMALIA, SE Uruguai) 902 kW e ≥ 1,014 pu. Tabela completa em
[`docs/escopo-cidade.md`](docs/escopo-cidade.md).

> **Métricas de decisão do MVP são MT.** A BT do modelo herda ramais de ligação (`RAMLIG.COMP`)
> suspeitos da própria BDGD (700–900 m em 220 V), que produzem as tensões BT abaixo de 0,5 pu e as
> sobrecargas reportadas; o veredito de uma manobra usa **tensão MT** (0,93–1,05 pu) e **corrente no
> disjuntor/tronco**, nunca a BT (`docs/spike-opendss.md`, revisão `docs/review/PR-04.md`).

### `bdgd-light tiles` — recorte → PMTiles para o console

Exporta cada camada geográfica de um GeoPackage de `recortar` para GeoJSONSeq em EPSG:4326 e chama o
[tippecanoe](https://github.com/felt/tippecanoe) para gerar **um arquivo `.pmtiles`** com uma
*source-layer* por camada, que o console lê direto (sem servidor de tiles). O tippecanoe é externo:
`brew install tippecanoe` (macOS) ou `sudo apt install tippecanoe`; sem ele o comando falha com essa
instrução ou, com `--geojson-only`, deixa só os GeoJSON.

```bash
uv run bdgd-light tiles --gpkg data/feeders/cluster_TQR0007-TQR33859-TQR33862.gpkg \
    --out console/public/tiles/exemplo.pmtiles
#   camada          feições   GeoJSON
#   SSDMT             1.924   console/public/tiles/exemplo_geojson/SSDMT.geojsonl
#   INTERLIGACOES        36   …
#   UNSEMT              162
#   UNTRMT              263
#   SSDBT             4.713   UCBT 1.759   PONNOT 2.664   (11 camadas)
#   bbox 4326: -43.49307, -23.01403, -43.17526, -22.90352
#   ✔ console/public/tiles/exemplo.pmtiles (1.43 MB, zoom 9–16, 1.4 s)
```

| opção | padrão | descrição |
|---|---|---|
| `--gpkg` | — | GeoPackage de um recorte (`bdgd-light recortar`) |
| `--out` | — | `.pmtiles` de saída, ex.: `console/public/tiles/TQR0007.pmtiles` |
| `--geojson` | `<out>_geojson/` | pasta dos GeoJSON intermediários (um `.geojsonl` por camada) |
| `--geojson-only` | off | não chama o tippecanoe |
| `--zoom-min` / `--zoom-max` | 9 / 16 | faixa de zoom do PMTiles |

Além das colunas da BDGD, o tile leva os atributos que o estilo usa e que vêm de outras camadas do
recorte: `TEN_KV`/`NOME_CTMT` no SSDMT (de `CTMT.TEN_NOM` e `NOME`), `TIE`/`CTMT_VIZ`/`EM_SUB` nas
chaves (da camada `INTERLIGACOES`), `N_UCBT` por trafo (de `UCBT_tab.UNI_TR_MT`) e a camada derivada
**`UCBT`** (unidades de `UCBT_tab` agregadas por poste `PN_CON` → `PONNOT`, com `N_UC`). Cada camada
tem um zoom mínimo (`tippecanoe.minzoom`): tronco MT a partir do 9, chaves 11, trafos 12, BT 13,
UC/postes 14–15. Em Python: `from bdgd_light.ingest.tiles import gerar_tiles`.

Os tiles dos clusters da demo ficam versionados em `console/public/tiles/exemplo_tijuca.pmtiles`
(0,98 MB) e `exemplo_ipanema.pmtiles` (0,78 MB), gerados de `data/feeders/cluster_tijuca.gpkg` e
`cluster_ipanema.gpkg` (`bdgd-light recortar --ctmt ALC9925,ALC9946,URG29983,RCP9882 --nome-cluster
cluster_tijuca …`). Ressalva: `PONNOT`/`UCBT` trazem postes referenciados por `UCBT_tab.PN_CON` fora
do bairro, então o bbox do PMTiles é maior que o cluster — o console usa centro/zoom fixos por cenário.

### `bdgd-light llm` — cliente LLM com *tool calling* (spike da issue #7)

Exemplo mínimo do agente: manda a pergunta ao modelo com a ferramenta `soma(a, b)` disponível,
executa as chamadas que ele pedir e imprime a resposta. Precisa do extra `agent`
(`uv sync --extra agent`).

```bash
uv run bdgd-light llm --fake "Quanto é 2 + 3?"                       # cliente fake, sem rede
#   ⚙ soma({"a": 2.0, "b": 3.0}) → 5.0
#   O resultado é 5.
export BDGD_LLM_ENDPOINT=https://SEU-PROVEDOR/v1/chat/completions   # API compatível com a OpenAI
export BDGD_LLM_TOKEN=...   BDGD_LLM_MODEL=gpt-4.1-mini              # segredos só por ambiente
uv run bdgd-light llm "Quanto é 2 + 3?" --json data/conversa.json    # grava a conversa completa
uv run scripts/listar_modelos.py --tools                             # modelos com tool calling
uv run bdgd-light audit data/audit/llm.jsonl --mostrar 5             # confere o log de auditoria
```

| opção | padrão | descrição |
|---|---|---|
| `PERGUNTA` | — | mensagem do usuário |
| `--fake` | off | `FakeLLMClient` determinístico que imita um modelo chamando `soma` |
| `--endpoint` | `$BDGD_LLM_ENDPOINT` | URL `…/chat/completions`; sem ela e com `GITHUB_TOKEN`, usa o preset GitHub Models |
| `--modelo` | `$BDGD_LLM_MODEL` | id do modelo |
| `--sistema` | assistente do COD | mensagem de sistema |
| `--json` | — | grava mensagens, chamadas de ferramenta, resultados e uso de tokens |
| `--audit` | `data/audit/llm.jsonl` | log de auditoria só de acréscimo (ADR-001, decisão 6); `--sem-audit` desliga |

Toda conversa é anexada ao **log de auditoria**: JSON Lines em que cada registro (`llm.rodada` com as
mensagens enviadas, a resposta, as chamadas de ferramenta com argumentos e resultados e o uso de
tokens; `conversa.fim`/`conversa.erro` no encerramento) carrega o hash SHA-256 do registro anterior.
`bdgd-light audit ARQUIVO` recalcula a cadeia e sai com código 1 se alguma linha foi alterada,
removida ou reordenada. É a base do RACI-A e do benchmark (tokens/pass@1).

O **GitHub Models foi aposentado em 30/07/2026** (a API responde `410
github_models_retirement_brownout`); `GitHubModelsClient` continua como *preset* que falha com uma
mensagem clara, e o cliente real é `OpenAICompatClient` (Azure AI Foundry, OpenAI, Ollama local…).
Detalhes, limites e recomendação em [`docs/spike-llm.md`](docs/spike-llm.md). Em Python:

```python
from bdgd_light.agent import Message, SOMA, cliente_do_ambiente, conversar, fake_soma

cliente = fake_soma()  # ou cliente_do_ambiente() com BDGD_LLM_ENDPOINT/BDGD_LLM_TOKEN
conversa = conversar(cliente, [Message.user("Quanto é 2 + 3?")], [SOMA])
conversa.resposta.content  # 'O resultado é 5.'
conversa.to_dict()  # histórico serializável

from bdgd_light.agent import AuditLog

log = AuditLog("data/audit/llm.jsonl")  # continua a cadeia se o arquivo existir
conversa = conversar(cliente, [Message.user("Quanto é 2 + 3?")], [SOMA], audit=log)
conversa.hash_auditoria, conversa.uso_total  # hash do último registro, tokens somados
AuditLog.verificar_arquivo("data/audit/llm.jsonl")  # nº de registros ou AuditError
```

## Console (mapa do operador)

`console/` é o front-end estático (Vite + TypeScript + [MapLibre GL JS](https://maplibre.org/) +
[PMTiles](https://protomaps.com/docs/pmtiles)) que abre o `.pmtiles` de um recorte com a simbologia
do COD — tronco MT por tensão, chaves NA/NF e telecomandadas, ties com o CTMT vizinho, trafos, BT,
postes e UC por poste — e sobrepõe o estado do grafo (`bdgd-light grafo --geojson`).

```bash
cd console && npm ci
npm run dev        # http://localhost:5173 → cenário Tijuca (public/tiles/exemplo_tijuca.pmtiles)
#   ?cenario=ipanema | taquara          outro cenário da demo (tiles + estado + enquadramento)
#   ?tiles=tiles/OUTRO.pmtiles          outro recorte gerado por `bdgd-light tiles`
#   ?estado=exemplos/estado_TQR0007_falta.geojson   falta simulada por cima dos tiles (`none` desliga)
npm run build && npm run smoke          # build (tsc + vite) e smoke test no Chrome headless
```

O workflow [`pages.yml`](.github/workflows/pages.yml) compila o console a cada push em `main` que toque
`console/` e o publica no GitHub Pages: **<https://viniciusaguiar15.github.io/bdgd-light/>**. Detalhes
e armadilhas em [`console/README.md`](console/README.md); decisões em
[`docs/adr/ADR-002-console-maplibre-pmtiles.md`](docs/adr/ADR-002-console-maplibre-pmtiles.md).

## Fluxo de trabalho

Backlog em Issues/Projects; issues são especificadas com critérios de aceite e implementadas pelo
GitHub Copilot (coding agent) em PRs revisados. Convenções em
[`.github/copilot-instructions.md`](.github/copilot-instructions.md).

## Referências

- ANEEL — [BDGD (Módulo 10 do PRODIST)](https://dadosabertos.aneel.gov.br/dataset/base-de-dados-geografica-da-distribuidora-bdgd) e [Manual da BDGD](https://dadosabertos-aneel.opendata.arcgis.com/documents/f0d5c43ac67d4f5eb2ddffa4589501b2)
- Badmus et al., *PowerChain: A Verifiable Agentic AI System for Automating Distribution Grid Analyses* — [arXiv:2508.17094](https://arxiv.org/abs/2508.17094)
- [bdgd2opendss](https://github.com/PauloRadatz/bdgd2opendss) (MIT) — conversão BDGD → OpenDSS
- [OpenDSSDirect.py](https://github.com/dss-extensions/OpenDSSDirect.py)
