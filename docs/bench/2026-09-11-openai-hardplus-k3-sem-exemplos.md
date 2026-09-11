# Benchmark do agente — openai-hardplus-k3-sem-exemplos (2026-09-11)

- provedor/modelo: **openai** · gpt-4.1-mini-2025-04-14
- modo: exemplos anotados não (top-k 0); compactação dos retornos sim
- k = 3; repetições por tarefa = 3; semente = 42
- tarefas: 4 de `bench/tarefas.yaml`; execuções: 12; erros: 0
- commit: `eca5df2`; CSV: `docs/bench/2026-09-11-openai-hardplus-k3-sem-exemplos.csv`

## Métricas por nível

| nível | tarefas | exec. | pass@1 | pass@3 | ordem | precisão | ferr. desnec. | tokens médios | tokens/pass@1 | US$/exec. | US$/pass@1 | chars ferr. | s/exec. | rodadas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hard | 4 | 12 | 100 % | 100 % | 96 % | 69 % | 1,25 | 44.417 | 44.417 | 0.0184 | 0.0184 | 17.871 | 17,9 | 4,6 |
| total | 4 | 12 | 100 % | 100 % | 96 % | 69 % | 1,25 | 44.417 | 44.417 | 0.0184 | 0.0184 | 17.871 | 17,9 | 4,6 |

> US$ = preço de lista de `gpt-4.1-mini-2025-04-14` (US$ 0.40/M tokens de entrada, US$ 1.60/M de saída, raciocínio incluído) × tokens informados pelo provedor; sem cache de contexto nem lote.

## Por tarefa

| id | nível | cluster | acertos | pass@1 | ordem | ferr. desnec. | sequência típica | esperado | obtido (último) | tokens médios | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| H12 | hard | tijuca | 3/3 | 100 % | 100 % | 0,00 | locate_fault → isolate_fault → restore_options → propose_plan | 746851189, 23313112 | 746851189 | 27.707 | 19,1 |
| H13 | hard | tijuca | 3/3 | 100 % | 83 % | 1,00 | locate_fault → restore_options → propose_plan → propose_plan | ∅ (sem chave) | — | 18.169 | 16,3 |
| H14 | hard | tijuca | 3/3 | 100 % | 100 % | 2,00 | locate_fault → isolate_fault → restore_options → propose_plan | 529355823 | 529355823 | 68.669 | 19,4 |
| H15 | hard | tijuca | 3/3 | 100 % | 100 % | 2,00 | locate_fault → isolate_fault → restore_options → propose_plan | ∅ (sem chave) | — | 63.123 | 16,8 |

## Comparativo (todos os CSVs de `docs/bench/`)

| provedor · modo | modelo | tarefas | pass@1 simple | pass@1 medium | pass@1 hard | pass@1 total | pass@3 total | ordem | precisão | ferr. desnec. | tokens/pass@1 | US$/exec. | chars ferr./exec. | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openai | gpt-4.1-mini-2025-04-14 | 4 | — | — | 100 % | 100 % | 100 % | 100 % | 68 % | 1,42 | 41.269 | 0.0172 | 18.315 | 17,6 |
| openai-sem-exemplos | gpt-4.1-mini-2025-04-14 | 4 | — | — | 100 % | 100 % | 100 % | 96 % | 69 % | 1,25 | 44.417 | 0.0184 | 17.871 | 17,9 |
