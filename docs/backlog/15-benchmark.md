---
title: "bench: benchmark estilo PowerChain (tarefas, pass@k, precisão, tokens/pass@1, OpenAI × Gemini)"
labels: area:agent, area:docs, phase:F4, copilot
milestone: F4 Benchmark + governança
---
## Tarefa
`bench/`: 30 tarefas (10 simple / 10 medium / 10 hard) sobre os clusters Tijuca, Ipanema e Taquara, cada uma com
resposta numérica esperada e sequência de ferramentas de referência (anotadas); `bdgd-light bench --provider X
--k 5` executa n vezes, calcula pass@k, precisão de ordenação e tokens por pass@1, grava CSV + relatório
`docs/bench/<data>-<provider>.md` com tabela comparativa entre provedores e entre modos (com/sem exemplos anotados).

## Critérios de aceite
- [ ] Roda com `FakeLLMClient` no CI (tarefas simple) e com provedores reais localmente.
- [ ] Relatório reproduzível por semente.
