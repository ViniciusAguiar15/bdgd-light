---
title: "tech: OpenDSS em subprocesso (#48), inventário com EM_SUB (#39), PONNOT por bbox (#40), convergência BT (#44)"
labels: area:twin, area:ingest, phase:F4, copilot
milestone: F4 Benchmark + governança
---
## Tarefa
Fechar as quatro issues já abertas, cada uma em PR próprio, nesta ordem: #48 (motor OpenDSS em subprocesso com
protocolo simples, removendo a mitigação `os._exit`), #40 (filtrar PONNOT/UCBT pelo bbox do cluster no `recortar`/
`tiles`; regerar PMTiles dos 3 cenários), #39 (regerar `data/inventario_ctmt.csv` com folga `EM_SUB` 50 m e a
tabela por região de `docs/escopo-cidade.md`), #44 (diagnóstico da barra que força `vminpu=0.9` na Tijuca; documentar).
## Critérios de aceite
- [ ] Suite verde; paridade gpkg2dss mantida; tiles regerados < 5 MB cada.
