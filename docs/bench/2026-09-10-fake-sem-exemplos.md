# Benchmark do agente — fake-sem-exemplos (2026-09-10)

- provedor/modelo: **fake** · fake-operador
- modo: exemplos anotados não (top-k 0); compactação dos retornos sim
- k = 5; repetições por tarefa = 5; semente = 42
- tarefas: 30 de `bench/tarefas.yaml`; execuções: 150; erros: 0
- commit: `ab17704`; CSV: `docs/bench/2026-09-10-fake-sem-exemplos.csv`

## Métricas por nível

| nível | tarefas | exec. | pass@1 | pass@5 | ordem | precisão | tokens médios | tokens/pass@1 | chars ferr. | s/exec. | rodadas |
|---|---|---|---|---|---|---|---|---|---|---|---|
| simple | 10 | 50 | 100 % | 100 % | 100 % | 100 % | 0 | 0 | 454 | 0,0 | 2,0 |
| medium | 10 | 50 | 100 % | 100 % | 100 % | 100 % | 0 | 0 | 416 | 0,0 | 2,2 |
| hard | 10 | 50 | 100 % | 100 % | 100 % | 100 % | 0 | 0 | 4.563 | 6,9 | 4,5 |
| total | 30 | 150 | 100 % | 100 % | 100 % | 100 % | 0 | 0 | 1.811 | 2,3 | 2,9 |

## Por tarefa

| id | nível | cluster | acertos | pass@1 | ordem | sequência típica | esperado | obtido (último) | tokens médios | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|
| S01 | simple | tijuca | 5/5 | 100 % | 100 % | get_topology | 4,246 | 4,246 | 0 | 0,0 |
| S02 | simple | tijuca | 5/5 | 100 % | 100 % | get_topology | 5.824 | 5.824 | 0 | 0,0 |
| S03 | simple | tijuca | 5/5 | 100 % | 100 % | get_topology | 9 | 9 | 0 | 0,0 |
| S04 | simple | tijuca | 5/5 | 100 % | 100 % | get_topology | 436 | 436 | 0 | 0,0 |
| S05 | simple | ipanema | 5/5 | 100 % | 100 % | get_topology | 1.816 | 1.816 | 0 | 0,0 |
| S06 | simple | ipanema | 5/5 | 100 % | 100 % | get_topology | 31 | 31 | 0 | 0,0 |
| S07 | simple | ipanema | 5/5 | 100 % | 100 % | get_topology | 5,956 | 5,956 | 0 | 0,0 |
| S08 | simple | taquara | 5/5 | 100 % | 100 % | get_topology | 17,979 | 17,979 | 0 | 0,0 |
| S09 | simple | taquara | 5/5 | 100 % | 100 % | get_topology | 82 | 82 | 0 | 0,0 |
| S10 | simple | taquara | 5/5 | 100 % | 100 % | get_topology | 58 | 58 | 0 | 0,0 |
| M01 | medium | tijuca | 5/5 | 100 % | 100 % | downstream_customers | 1.307 | 1.307 | 0 | 0,0 |
| M02 | medium | tijuca | 5/5 | 100 % | 100 % | downstream_customers | 1.395 | 1.395 | 0 | 0,0 |
| M03 | medium | taquara | 5/5 | 100 % | 100 % | downstream_customers | 1.361 | 1.361 | 0 | 0,0 |
| M04 | medium | taquara | 5/5 | 100 % | 100 % | downstream_customers | 1.261 | 1.261 | 0 | 0,0 |
| M05 | medium | ipanema | 5/5 | 100 % | 100 % | downstream_customers | 404 | 404 | 0 | 0,0 |
| M06 | medium | tijuca | 5/5 | 100 % | 100 % | locate_fault | 35 | 35 | 0 | 0,0 |
| M07 | medium | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault | 4.036 | 4.036 | 0 | 0,0 |
| M08 | medium | ipanema | 5/5 | 100 % | 100 % | locate_fault | 1.251 | 1.251 | 0 | 0,0 |
| M09 | medium | taquara | 5/5 | 100 % | 100 % | locate_fault → isolate_fault | 2.023 | 2.023 | 0 | 0,0 |
| M10 | medium | taquara | 5/5 | 100 % | 100 % | locate_fault | 4 | 4 | 0 | 0,0 |
| H01 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 974020904, 529355823 | 974020904 | 0 | 8,0 |
| H02 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 45,978 | 46 | 0 | 8,8 |
| H03 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 4 | 4 | 0 | 8,2 |
| H04 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 746851189 | 746851189 | 0 | 4,2 |
| H05 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 644 | 644 | 0 | 3,3 |
| H06 | hard | ipanema | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | ∅ (sem chave) | — | 0 | 0,0 |
| H07 | hard | ipanema | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 479 | 479 | 0 | 0,0 |
| H08 | hard | taquara | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 11053620, 11056672, 789941518, 11053522, 11053627, 1007642983, 752622332, 11026494, 134733185, 258481641 | 11053620 | 0 | 14,4 |
| H09 | hard | taquara | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 10 | 10 | 0 | 13,7 |
| H10 | hard | taquara | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 11053522, 11053620, 11056672, 752622332, 134733185, 258481641 | 11053522 | 0 | 8,6 |

## Comparativo (todos os CSVs de `docs/bench/`)

| provedor · modo | modelo | tarefas | pass@1 simple | pass@1 medium | pass@1 hard | pass@1 total | pass@5 total | ordem | precisão | tokens/pass@1 | chars ferr./exec. | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fake | fake-operador | 30 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0 | 1.811 | 2,5 |
| fake-sem-compactar | fake-operador | 30 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0 | 7.114 | 2,5 |
| fake-sem-exemplos | fake-operador | 30 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0 | 1.811 | 2,3 |
| gemini | gemini-2.5-flash | 20 | 100 % | 100 % | — | 100 % | 100 % | 98 % | 100 % | 5.546 | 1.018 | 1,9 |
