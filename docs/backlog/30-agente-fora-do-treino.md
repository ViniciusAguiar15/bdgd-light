---
title: "bench: o agente em alimentadores fora dos três clusters"
labels: area:agent, area:bench, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
Complementa a #29: depois de saber que o **pipeline** roda num alimentador novo, falta saber se o
**agente** decide bem lá. Os exemplos anotados, os cenários e o gabarito do benchmark foram todos
escritos olhando Tijuca/Ipanema/Taquara.

## Tarefa
- Selecionar, entre os alimentadores que passaram na #29, um subconjunto (10 é suficiente) com
  falta injetada de forma determinística e gabarito **recalculado pelas próprias ferramentas**
  (nunca escrito à mão).
- Rodar o agente com `--provider openai`, k=3, seed fixa, e medir as mesmas métricas do benchmark:
  pass@1, ordem, precisão, chamadas desnecessárias, rodadas, tokens, custo — e a **taxa de
  reprovação do verificador**, que é o número que mais interessa fora do treino.
- Comparar lado a lado com o recorte *hard* dos três clusters conhecidos, deixando explícito que os
  conjuntos têm dificuldade diferente (não é A/B controlado).
- Registrar em `docs/bench.md` e alimentar `docs/resultados.md` pelo script existente.

## Critérios de aceite
- [ ] CSV e relatório versionados; seção nova em `docs/bench.md`.
- [ ] Nenhum gabarito escrito à mão.
- [ ] Se o desempenho cair fora dos clusters conhecidos, isso é escrito com todas as letras.
