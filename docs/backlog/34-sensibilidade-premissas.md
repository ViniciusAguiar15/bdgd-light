---
title: "twin: a decisão de restauração muda com as premissas?"
labels: area:twin, area:bench, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
A proposta do agente depende de números do gêmeo que, por sua vez, dependem de premissas: curva de
carga (`CRVCRG`) contra carga nominal, `loadmult`, tratamento de `FAS_CON`, tempo de reparo. Se a
opção escolhida mudar com uma premissa plausível, isso precisa estar dito — é a diferença entre
"o sistema recomenda" e "o sistema recomenda, dado X".

## Tarefa
- Para cada um dos três cenários (Tijuca, Ipanema, Taquara) e para 3 alimentadores da #29, varrer:
  `loadmult` em {0,6, 0,8, 1,0, 1,2, 1,4}; carga pela curva × carga nominal; e, onde aplicável,
  `FAS_CON` como cadastrado × rebalanceado.
- Registrar, para cada combinação: opção escolhida pelo score, margem no disjuntor, Vmin MT,
  viabilidade — e **se a opção vencedora muda**.
- `docs/sensibilidade.md`: tabela de quando a decisão vira, e uma frase direta sobre a robustez
  ("a escolha se mantém até loadmult X; acima disso a opção Y passa a ser inviável").
- Se alguma premissa inverter a decisão, acrescentar isso ao que o console mostra ao operador —
  abrir issue de acompanhamento em vez de mudar a UI aqui.

## Critérios de aceite
- [ ] Varredura completa versionada em CSV.
- [ ] `docs/sensibilidade.md` com o ponto de virada de cada cenário (ou "não vira na faixa testada").
- [ ] Nenhuma mudança de comportamento do agente nesta issue.
