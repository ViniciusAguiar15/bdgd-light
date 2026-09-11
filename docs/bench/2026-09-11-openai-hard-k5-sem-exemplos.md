# Benchmark do agente — openai-hard-k5-sem-exemplos (2026-09-11)

- provedor/modelo: **openai** · gpt-4.1-mini-2025-04-14
- modo: exemplos anotados não (top-k 0); compactação dos retornos sim
- k = 5; repetições por tarefa = 5; semente = None
- tarefas: 11 de `bench/tarefas.yaml`; execuções: 55; erros: 0
- commit: `d741a62`; CSV: `docs/bench/2026-09-11-openai-hard-k5-sem-exemplos.csv`

## Métricas por nível

| nível | tarefas | exec. | pass@1 | pass@5 | ordem | precisão | tokens médios | tokens/pass@1 | US$/exec. | US$/pass@1 | chars ferr. | s/exec. | rodadas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hard | 11 | 55 | 100 % | 100 % | 96 % | 98 % | 17.714 | 17.714 | 0.0075 | 0.0075 | 15.583 | 16,4 | 3,9 |
| total | 11 | 55 | 100 % | 100 % | 96 % | 98 % | 17.714 | 17.714 | 0.0075 | 0.0075 | 15.583 | 16,4 | 3,9 |

> US$ = preço de lista de `gpt-4.1-mini-2025-04-14` (US$ 0.40/M tokens de entrada, US$ 1.60/M de saída, raciocínio incluído) × tokens informados pelo provedor; sem cache de contexto nem lote.

## Por tarefa

| id | nível | cluster | acertos | pass@1 | ordem | sequência típica | esperado | obtido (último) | tokens médios | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|
| H01 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 974020904, 529355823 | 974020904 | 23.937 | 18,5 |
| H02 | hard | tijuca | 5/5 | 100 % | 93 % | locate_fault → isolate_fault → restore_options | 45,978 | 46 | 13.955 | 17,2 |
| H03 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 4 | 4 | 10.863 | 15,3 |
| H04 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 746851189 | 746851189 | 24.615 | 17,2 |
| H05 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 644 | 644 | 18.559 | 13,4 |
| H06 | hard | ipanema | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | ∅ (sem chave) | — | 11.813 | 12,5 |
| H07 | hard | ipanema | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 479 | 479 | 7.563 | 7,9 |
| H08 | hard | taquara | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 11053620, 11056672, 789941518, 11053522, 11053627, 1007642983, 752622332, 11026494, 134733185, 258481641 | 11056672 | 31.849 | 26,4 |
| H09 | hard | taquara | 5/5 | 100 % | 67 % | locate_fault → restore_options | 10 | 10 | 9.269 | 20,2 |
| H10 | hard | taquara | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 11053522, 11053620, 11056672, 752622332, 134733185, 258481641 | 11056672 | 29.921 | 21,2 |
| H11 | hard | ipanema | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | ∅ (sem chave) | — | 12.507 | 11,2 |

## Comparativo (todos os CSVs de `docs/bench/`)

| provedor · modo | modelo | tarefas | pass@1 simple | pass@1 medium | pass@1 hard | pass@1 total | pass@5 total | ordem | precisão | tokens/pass@1 | US$/exec. | chars ferr./exec. | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openai-sem-exemplos | gpt-4.1-mini-2025-04-14 | 11 | — | — | 100 % | 100 % | 100 % | 96 % | 98 % | 17.714 | 0.0075 | 15.583 | 16,4 |
