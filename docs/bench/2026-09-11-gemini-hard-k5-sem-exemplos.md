# Benchmark do agente — gemini-hard-k5-sem-exemplos (2026-09-11)

- provedor/modelo: **gemini** · gemini-2.5-flash
- modo: exemplos anotados não (top-k 0); compactação dos retornos sim
- k = 5; repetições por tarefa = 5; semente = None
- tarefas: 11 de `bench/tarefas.yaml`; execuções: 55; erros: 0
- commit: `d741a62`; CSV: `docs/bench/2026-09-11-gemini-hard-k5-sem-exemplos.csv`

## Métricas por nível

| nível | tarefas | exec. | pass@1 | pass@5 | ordem | precisão | tokens médios | tokens/pass@1 | US$/exec. | US$/pass@1 | chars ferr. | s/exec. | rodadas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hard | 11 | 55 | 100 % | 100 % | 96 % | 98 % | 25.401 | 25.401 | 0.0118 | 0.0118 | 14.006 | 17,8 | 4,5 |
| total | 11 | 55 | 100 % | 100 % | 96 % | 98 % | 25.401 | 25.401 | 0.0118 | 0.0118 | 14.006 | 17,8 | 4,5 |

> US$ = preço de lista de `gemini-2.5-flash` (US$ 0.30/M tokens de entrada, US$ 2.50/M de saída, raciocínio incluído) × tokens informados pelo provedor; sem cache de contexto nem lote.

## Por tarefa

| id | nível | cluster | acertos | pass@1 | ordem | sequência típica | esperado | obtido (último) | tokens médios | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|
| H01 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 974020904, 529355823 | 974020904 | 37.092 | 23,5 |
| H02 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 45,978 | 46 | 14.980 | 14,4 |
| H03 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 4 | 4 | 14.521 | 12,5 |
| H04 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 746851189 | 746851189 | 37.995 | 21,8 |
| H05 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 644 | 644 | 18.219 | 11,9 |
| H06 | hard | ipanema | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | ∅ (sem chave) | — | 19.103 | 13,4 |
| H07 | hard | ipanema | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 479 | 479 | 15.265 | 8,8 |
| H08 | hard | taquara | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 11053620, 11056672, 789941518, 11053522, 11053627, 1007642983, 752622332, 11026494, 134733185, 258481641 | 11053620 | 47.747 | 32,7 |
| H09 | hard | taquara | 5/5 | 100 % | 60 % | restore_options | 10 | 10 | 10.972 | 15,9 |
| H10 | hard | taquara | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 11053522, 11053620, 11056672, 752622332, 134733185, 258481641 | 11053522 | 44.407 | 26,2 |
| H11 | hard | ipanema | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | ∅ (sem chave) | — | 19.114 | 14,3 |

## Comparativo (todos os CSVs de `docs/bench/`)

| provedor · modo | modelo | tarefas | pass@1 simple | pass@1 medium | pass@1 hard | pass@1 total | pass@5 total | ordem | precisão | tokens/pass@1 | US$/exec. | chars ferr./exec. | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemini-sem-exemplos | gemini-2.5-flash | 11 | — | — | 100 % | 100 % | 100 % | 96 % | 98 % | 25.401 | 0.0118 | 14.006 | 17,8 |
