# bdgd-light

POC/MVP de um **Centro de Operação da Distribuição (COD) agêntico** sobre a **BDGD da Light**
(Rio de Janeiro), usando dados abertos da ANEEL. A ideia: expor a rede (topologia, chaves, cargas,
gêmeo digital em OpenDSS) como ferramentas para um agente de IA que monitora eventos, propõe manobras
(ex.: FLISR) e as submete à aprovação de um operador humano, num console com mapa.

Plano completo, módulos e fases em [`docs/PLANO.md`](docs/PLANO.md).

## Estrutura

```
src/bdgd_light/        pacote Python (ingest, grid, twin, mcp_server, agent, sim)
  catalogo.py          IDs da BDGD por distribuidora/ano e camadas-chave
scripts/
  baixar_bdgd.py       baixa e extrai a BDGD (Light 2025 por padrão)
  listar_camadas.py    lista as camadas do .gdb
  converter.py         camada → GeoJSON (EPSG:4326) com recorte por bbox
index.html             visor Leaflet legado (será substituído pelo console MapLibre)
docs/                  plano, ADRs
tests/                 pytest (fixtures sintéticas; dados reais nunca vão para o git)
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

## Fluxo de trabalho

Backlog em Issues/Projects; issues são especificadas com critérios de aceite e implementadas pelo
GitHub Copilot (coding agent) em PRs revisados. Convenções em
[`.github/copilot-instructions.md`](.github/copilot-instructions.md).

## Referências

- ANEEL — [BDGD (Módulo 10 do PRODIST)](https://dadosabertos.aneel.gov.br/dataset/base-de-dados-geografica-da-distribuidora-bdgd) e [Manual da BDGD](https://dadosabertos-aneel.opendata.arcgis.com/documents/f0d5c43ac67d4f5eb2ddffa4589501b2)
- Badmus et al., *PowerChain: A Verifiable Agentic AI System for Automating Distribution Grid Analyses* — [arXiv:2508.17094](https://arxiv.org/abs/2508.17094)
- [bdgd2opendss](https://github.com/PauloRadatz/bdgd2opendss) (MIT) — conversão BDGD → OpenDSS
- [OpenDSSDirect.py](https://github.com/dss-extensions/OpenDSSDirect.py)
