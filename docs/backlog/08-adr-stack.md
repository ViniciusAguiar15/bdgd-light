---
title: "docs: ADR-001 decisões de stack e arquitetura"
labels: area:docs, phase:F1, copilot
milestone: F1 Dados + mapa
---
## Tarefa
Escrever `docs/adr/ADR-001-stack.md` (formato ADR curto: contexto, decisão, consequências) cobrindo:
GeoParquet/GeoPackage como formato intermediário; MapLibre + PMTiles em vez de Leaflet + GeoJSON;
OpenDSS via OpenDSSDirect + bdgd2opendss; networkx para topologia; MCP como interface agente↔ferramentas;
GitHub Models atrás de `LLMClient`; modo HITL (nível 2 de autonomia) e logs de auditoria. Basear-se em
`docs/PLANO.md`.

## Critérios de aceite
- [ ] ADR linkado no README.
