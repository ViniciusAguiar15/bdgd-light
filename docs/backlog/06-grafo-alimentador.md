---
title: "grid: grafo do alimentador em networkx com estado de chaves"
labels: area:grid, phase:F2, copilot
milestone: F2 Grafo + gêmeo
---
## Tarefa
`bdgd_light.grid.Feeder.from_gpkg(path)` constrói um `networkx.Graph` a partir do recorte (#3):
- Nós: pontos de conexão (`PAC_1`/`PAC_2` dos segmentos SSDMT/SSDBT e das chaves/transformadores).
- Arestas: segmentos SSDMT/SSDBT (atributos: comprimento, condutor, tensão, `COD_ID`) e chaves UNSEMT/UNSEBT
  (atributo `estado` NA/NF a partir de `P_N_OPE`), transformadores UNTRMT ligando MT→BT.
- Fonte: barra da subestação do CTMT.
- Métodos: `energized_nodes()` (BFS ignorando chaves NA/abertas), `downstream(node)`, `customers_downstream(node)`
  (UCs ligadas via UNTRMT), `open_switch(id)`, `close_switch(id)`, `tie_switches()` (NAs que ligam a outro
  CTMT), `isolate_segment(seg_id)` → chaves mínimas a abrir, e `restore_options(seg_id)` → NAs candidatas para
  reenergizar os trechos a jusante.
- Export para GeoJSON do estado (energizado/desenergizado por trecho) para o console.

## Critérios de aceite
- [ ] Testes com fixture sintética (alimentador radial com 1 NA de interligação): energização, isolamento e restauração.
- [ ] `docs/grid-modelo.md` explicando o mapeamento BDGD → grafo.
