# Benchmark do agente — openai-hard-k5 (2026-09-11)

- provedor/modelo: **openai** · gpt-4.1-mini-2025-04-14
- modo: exemplos anotados sim (top-k 3); compactação dos retornos sim
- k = 5; repetições por tarefa = 5; semente = None
- tarefas: 11 de `bench/tarefas.yaml`; execuções: 55; erros: 0
- commit: `d741a62`; CSV: `docs/bench/2026-09-11-openai-hard-k5.csv`

## Métricas por nível

| nível | tarefas | exec. | pass@1 | pass@5 | ordem | precisão | tokens médios | tokens/pass@1 | US$/exec. | US$/pass@1 | chars ferr. | s/exec. | rodadas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hard | 11 | 55 | 100 % | 100 % | 100 % | 97 % | 18.897 | 18.897 | 0.0081 | 0.0081 | 16.084 | 18,7 | 3,6 |
| total | 11 | 55 | 100 % | 100 % | 100 % | 97 % | 18.897 | 18.897 | 0.0081 | 0.0081 | 16.084 | 18,7 | 3,6 |

> US$ = preço de lista de `gpt-4.1-mini-2025-04-14` (US$ 0.40/M tokens de entrada, US$ 1.60/M de saída, raciocínio incluído) × tokens informados pelo provedor; sem cache de contexto nem lote.

## Por tarefa

| id | nível | cluster | acertos | pass@1 | ordem | sequência típica | esperado | obtido (último) | tokens médios | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|
| H01 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 974020904, 529355823 | 974020904 | 25.636 | 28,7 |
| H02 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 45,978 | 46 | 10.908 | 22,6 |
| H03 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 4 | 4 | 9.070 | 16,6 |
| H04 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 746851189 | 746851189 | 25.804 | 18,8 |
| H05 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 644 | 644 | 23.952 | 14,4 |
| H06 | hard | ipanema | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | ∅ (sem chave) | — | 13.337 | 11,2 |
| H07 | hard | ipanema | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 479 | 479 | 9.194 | 8,3 |
| H08 | hard | taquara | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 11053620, 11056672, 789941518, 11053522, 11053627, 1007642983, 752622332, 11026494, 134733185, 258481641 | 11056672 | 33.489 | 27,7 |
| H09 | hard | taquara | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 10 | 10 | 11.958 | 22,0 |
| H10 | hard | taquara | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 11053522, 11053620, 11056672, 752622332, 134733185, 258481641 | 11056672 | 31.712 | 24,1 |
| H11 | hard | ipanema | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | ∅ (sem chave) | — | 12.809 | 11,1 |

## Comparativo (todos os CSVs de `docs/bench/`)

| provedor · modo | modelo | tarefas | pass@1 simple | pass@1 medium | pass@1 hard | pass@1 total | pass@5 total | ordem | precisão | tokens/pass@1 | US$/exec. | chars ferr./exec. | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openai | gpt-4.1-mini-2025-04-14 | 11 | — | — | 100 % | 100 % | 100 % | 100 % | 97 % | 18.897 | 0.0081 | 16.084 | 18,7 |
