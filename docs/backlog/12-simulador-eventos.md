---
title: "sim: simulador de eventos (faltas e picos de carga) sobre o cluster"
labels: area:agent, phase:F3, copilot
milestone: F3 Agente
---
## Tarefa
`bdgd_light.sim`: gera eventos com semente (`--seed`) sobre um cluster: falta permanente em trecho MT (escolhido ou
aleatório ponderado por km), falta transitória (religador religa), pico de carga (`loadmult`), chave telecomandada
indisponível. Cada evento vira uma mensagem `{"tipo","cluster","trecho"|"ctmt","hora","detalhes"}` publicada numa fila
simples (arquivo JSONL `data/eventos/` + `bdgd-light sim --emitir 1 --tipo falta`), que o agente (#24) consome e o
console (#25) mostra. Cenários nomeados: `tijuca_cabofrio_tronco`, `ipanema_9210`, `taquara_bocari` (os da
`escopo-cidade.md`) e `aleatorio`.

## Critérios de aceite
- [ ] Reprodutível por semente; testes com cluster sintético.
- [ ] `docs/sim.md` com o formato do evento.
