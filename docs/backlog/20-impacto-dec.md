---
title: "metrics: impacto da manobra em consumidor-minutos e DEC do conjunto"
labels: area:grid, area:console, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
"4.036 clientes restaurados" não é a língua da distribuidora. O que ela mede é DEC (duração equivalente
de interrupção por unidade consumidora) e FEC. Traduzir o resultado da manobra para essa métrica é o que
faz um gerente entender o valor em cinco segundos.

## Tarefa
- `bdgd_light.grid.impacto`: dada uma opção de restauração e um **tempo de reparo estimado**
  (`--tempo-reparo`, padrão 180 min, explicitamente uma premissa), calcular: consumidor-minutos evitados
  = clientes restaurados × (tempo de reparo − tempo de manobra, padrão 5 min); clientes que seguem sem
  tensão até o reparo; e, se a camada `CONJ` estiver no recorte, a contribuição ao **DEC do conjunto**
  (consumidor-minutos ÷ total de UC do conjunto ÷ 60, em horas), com o nome e o total de UC do conjunto.
- Nunca apresentar como "redução de DEC realizada": é **impacto estimado de um evento**, sob a premissa
  de tempo de reparo. O texto na tela deve dizer isso.
- Expor em `restore_options` (por opção) e no `propose_plan`; console mostra no cartão: "≈ X mil
  consumidor-minutos evitados · ≈ Y min de DEC no conjunto Z (premissa: reparo em 180 min)".
- `bdgd-light grafo --falha ... --score` ganha a coluna.

## Critérios de aceite
- [ ] Testes com fixture sintética (números conferidos à mão) e com o cluster Tijuca.
- [ ] `docs/grid-modelo.md` com a fórmula, as premissas e o que **não** se pode afirmar.
