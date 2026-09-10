---
title: "escopo v3: clusters Tijuca (A) e Ipanema (B) — recorte, tiles, exemplos, README"
labels: area:ingest, area:console, phase:F3, copilot
milestone: F3 Agente
---
## Contexto
`docs/escopo-cidade.md` substitui o cluster TQR pela demo em dois cenários: **A** Tijuca `ALC9925,ALC9946,URG29983,RCP9882`
(FLISR aéreo, 3 SEs) e **B** Ipanema `PTS0001,PTS9088,PTS9924,PTS4022` (subterrâneo radial telecomandado). TQR fica
como regressão/benchmark.

## Tarefa
- `bdgd-light recortar` dos dois clusters → `data/feeders/`; `bdgd-light grafo` e `bdgd-light dss` (conversão + Master
  do cluster + fluxo base) em ambos; registrar em `docs/escopo-cidade.md` uma tabela de resultados (nós, km, chaves,
  ties de campo, convergência, tensão MT mín/máx, kW por fonte, tempo).
- Cenário A de referência: falta num trecho do tronco de CABOFRIO com ≥ 2 opções telecomandadas; cenário B: falta
  em LDS 9210 com restauração por PTS9088 ou PTS9924. Escolher os trechos, documentar `COD_ID` e gerar
  `console/public/exemplos/estado_<cluster>_falta.geojson` e os PMTiles (`exemplo_tijuca.pmtiles`,
  `exemplo_ipanema.pmtiles`; manter cada um < 5 MB, senão reduzir camadas BT).
- Tratar no gêmeo circuitos sem carga (PTS4022, PTS9297): fonte/Vsource sem cargas, sem erro.
- Console: seletor de cenário (Tijuca / Ipanema / Taquara) que troca tiles + estado; vista inicial no bairro.
- README e `docs/escopo-alimentadores.md`: apontar para `escopo-cidade.md` (v3) e atualizar exemplos de comando.

## Critérios de aceite
- [ ] Ambos os clusters convergem no OpenDSS (com a cascata registrada) e o cenário FLISR roda ponta a ponta (`dss --falha --restaurar`).
- [ ] Testes existentes continuam verdes; fumaça com `data/feeders/<cluster>.gpkg` em `skipif`.
- [ ] Smoke do console passa com os três cenários.
