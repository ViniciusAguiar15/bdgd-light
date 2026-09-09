# Instruções para o GitHub Copilot (coding agent) — bdgd-light

## O que é este projeto
POC/MVP de um **Centro de Operação da Distribuição (COD) agêntico** sobre a **BDGD da Light**
(distribuidora 382, Rio de Janeiro), dados abertos da ANEEL. Pipeline: BDGD (.gdb) → camadas em
Parquet/GeoPackage → grafo por alimentador (networkx) → gêmeo digital em OpenDSS → servidor MCP com
ferramentas de rede → agente orquestrador/verificador em modo *human-in-the-loop* → console web
(mapa MapLibre + fila de eventos). Referências de arquitetura: PowerChain (arXiv 2508.17094) e o
roteiro de modernização do COD em `docs/PLANO.md`.

## Convenções obrigatórias
- Ambiente **sempre via uv**: `uv sync --extra dev` cria o `.venv`; todo comando roda com `uv run ...`
  (`uv run pytest`, `uv run ruff check .`, `uv run bdgd-light ...`). Dependências entram com `uv add`
  (nunca `pip install` no Python do sistema). Commitar `uv.lock`.
- Python >= 3.11, layout `src/bdgd_light/`; testes em `tests/` com pytest; lint/format com **ruff**
  (line-length 100). CI (`.github/workflows/ci.yml`) precisa passar.
- Código, docstrings, mensagens de commit e issues em **português do Brasil**; nomes de
  identificadores podem ser em inglês quando forem termos técnicos consagrados.
- Commits no padrão *Conventional Commits* (`feat:`, `fix:`, `docs:`, `chore:`, `test:`).
- **Nunca** commitar dados da BDGD nem derivados (`data/`, `*.gdb`, `*.zip`, `*.parquet`, `*.gpkg`,
  `*.pmtiles`). Testes usam fixtures pequenas e sintéticas em `tests/fixtures/`.
- Leitura de geodados com `geopandas` + engine `pyogrio`; CRS da BDGD é SIRGAS 2000 (EPSG:4674);
  saídas para web em EPSG:4326.
- CLI com `typer` em `src/bdgd_light/cli.py` (entry point `bdgd-light`).
- Camadas e códigos da BDGD: ver `src/bdgd_light/catalogo.py` (`CAMADAS_CHAVE`) e o Manual da BDGD
  (Módulo 10 do PRODIST). Chave de alimentador é a coluna `CTMT` nas camadas de rede; identificador
  universal é `COD_ID`.
- OpenDSS via `opendssdirect.py` (sem COM, roda em macOS/Linux); conversão BDGD→.dss preferencialmente
  com `bdgd2opendss` (MIT, Paulo Radatz).
- A camada de LLM deve ficar atrás de uma interface (`LLMClient`) — provedor inicial: GitHub Models.
- Toda ação do agente que altera estado de rede (abrir/fechar chave) passa por aprovação humana no MVP.

## Como trabalhar uma issue
1. Leia a issue inteira; critérios de aceite são a definição de pronto.
2. Implemente com testes. Se precisar de dados reais para validar, descreva no PR o comando que o
   mantenedor deve rodar localmente (ele tem a BDGD em `data/`).
3. Atualize `README.md`/`docs/` quando mudar CLI ou fluxo.
4. PR pequeno, focado, com resumo do que foi feito e como testar.
