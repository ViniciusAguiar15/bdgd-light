# Plano do MVP — bdgd-light

COD agêntico para a Light (Rio de Janeiro), com dupla finalidade: demo funcional de ponta a ponta
(cenário FLISR em modo HITL) e instrumentação de pesquisa (benchmark estilo PowerChain).

## Dados
- BDGD Light (382) 2025-12-31 V11 como base; 2024 opcional para evolução. IDs em `src/bdgd_light/catalogo.py`.
- Histórico público: curvas típicas (CRVCRG) e energia mensal por UC (na BDGD); DEC/FEC por conjunto e
  base de interrupções (ANEEL). Telemetria em tempo real é sintética (simulador).

## Stack
Python 3.11+ (geopandas, networkx, OpenDSSDirect.py, bdgd2opendss, typer, pytest, ruff) ·
MapLibre GL JS + PMTiles no GitHub Pages · servidor MCP em Python · LLM via GitHub Models (abstraído) ·
GitHub Issues/Projects + Copilot coding agent + Actions + Codespaces.

## Módulos
| módulo | responsabilidade |
|---|---|
| `bdgd_light.ingest` | download por ID, listar camadas, exportar camadas-chave para Parquet/GeoPackage, recorte por CTMT |
| `bdgd_light.grid` | grafo por alimentador (nós/arestas/chaves NA-NF), energização, clientes a jusante, NAs vizinhas |
| `bdgd_light.twin` | conversão para OpenDSS, fluxo de potência, injeção de falta, hosting capacity |
| `bdgd_light.mcp_server` | ferramentas: load_feeder, get_topology, run_powerflow, inject_fault, locate_fault, downstream_customers, propose_flisr, hosting_capacity, set_switch |
| `bdgd_light.agent` | orquestrador + verificador, exemplos anotados, logs de auditoria |
| `console/` | mapa, estado de chaves, fila de eventos, aprovar/rejeitar manobra, log de raciocínio |
| `bdgd_light.sim` | gerador de eventos (faltas, picos de carga) |
| `bench/` | tarefas simple/medium/hard, pass@k, precisão de ordenação, tokens/pass@1 |

## Fases
- **F0 Kickoff** — repo, CI, devcontainer, download Light 2025. *(feito manualmente)*
- **F1 Dados + mapa** — exportar camadas, inventário de alimentadores, escolha de 2–3 CTMT, PMTiles, console no Pages.
- **F2 Grafo + gêmeo** — networkx + OpenDSS dos alimentadores escolhidos, testes.
- **F3 Agente** — MCP server, orquestrador/verificador HITL, simulador de eventos, FLISR ponta a ponta.
- **F4 Benchmark + governança** — tarefas e métricas, logs imutáveis, matriz RACI-A, polimento da demo.

## Governança (do roteiro de modernização do COD)
Nível 2 de autonomia (HITL) no MVP; toda manobra proposta é aprovada pelo operador; intertravamentos
determinísticos simulados no gêmeo (não fechar chave em trecho com falta/em manutenção); logs imutáveis
de raciocínio, chamadas de ferramenta e decisões humanas.
