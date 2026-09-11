# Benchmark do agente — fake-sem-compactar (2026-09-11)

- provedor/modelo: **fake** · fake-operador
- modo: exemplos anotados sim (top-k 3); compactação dos retornos não
- k = 5; repetições por tarefa = 5; semente = 42
- tarefas: 34 de `/Users/vinicius/repos/bdgd-light/bench/tarefas.yaml`; execuções: 170; erros: 0
- commit: `791ca3d`; CSV: `docs/bench/2026-09-11-fake-sem-compactar.csv`

## Métricas por nível

| nível | tarefas | exec. | pass@1 | pass@5 | ordem | precisão | tokens médios | tokens/pass@1 | US$/exec. | US$/pass@1 | chars ferr. | s/exec. | rodadas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| simple | 10 | 50 | 100 % | 100 % | 100 % | 100 % | 0 | 0 | — | — | 454 | 0,0 | 2,0 |
| medium | 13 | 65 | 100 % | 100 % | 100 % | 100 % | 0 | 0 | — | — | 2.660 | 0,0 | 2,0 |
| hard | 11 | 55 | 100 % | 100 % | 100 % | 100 % | 0 | 0 | — | — | 16.076 | 6,6 | 4,5 |
| total | 34 | 170 | 100 % | 100 % | 100 % | 100 % | 0 | 0 | — | — | 6.352 | 2,1 | 2,8 |

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
| M11 | medium | ipanema | 5/5 | 100 % | 100 % | downstream_customers | 271 | 271 | 0 | 0,0 |
| M12 | medium | ipanema | 5/5 | 100 % | 100 % | — | 1.816 | 1.816 | 0 | 0,0 |
| M13 | medium | ipanema | 5/5 | 100 % | 100 % | — | 1.730 | 1.730 | 0 | 0,0 |
| H01 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 974020904, 529355823 | 974020904 | 0 | 8,6 |
| H02 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 45,978 | 46 | 0 | 8,4 |
| H03 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 4 | 4 | 0 | 8,4 |
| H04 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 746851189 | 746851189 | 0 | 4,4 |
| H05 | hard | tijuca | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 644 | 644 | 0 | 3,3 |
| H06 | hard | ipanema | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | ∅ (sem chave) | — | 0 | 0,0 |
| H07 | hard | ipanema | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 479 | 479 | 0 | 0,0 |
| H08 | hard | taquara | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 11053620, 11056672, 789941518, 11053522, 11053627, 1007642983, 752622332, 11026494, 134733185, 258481641 | 11053620 | 0 | 15,1 |
| H09 | hard | taquara | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 10 | 10 | 0 | 14,6 |
| H10 | hard | taquara | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 11053522, 11053620, 11056672, 752622332, 134733185, 258481641 | 11053522 | 0 | 9,4 |
| H11 | hard | ipanema | 5/5 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | ∅ (sem chave) | — | 0 | 0,0 |

## Comparativo (todos os CSVs de `docs/bench/`)

| provedor · modo | modelo | tarefas | pass@1 simple | pass@1 medium | pass@1 hard | pass@1 total | pass@5 total | ordem | precisão | tokens/pass@1 | US$/exec. | chars ferr./exec. | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fake | fake-operador | 34 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0 | — | 1.806 | 2,3 |
| fake-sem-compactar | fake-operador | 34 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0 | — | 6.352 | 2,1 |
| fake-sem-exemplos | fake-operador | 34 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0 | — | 1.806 | 1,9 |
| gemini | gemini-2.5-flash | 34 | 100 % | 100 % | 85 % | 94 % | 100 % | 95 % | 99 % | 12.354 | 0.0051 | 2.366 | 8,6 |
| gemini-sem-compactar | gemini-2.5-flash | 34 | 100 % | 100 % | 91 % | 97 % | 100 % | 96 % | 100 % | 19.429 | 0.0071 | 9.236 | 7,2 |
| gemini-sem-exemplos | gemini-2.5-flash | 34 | 100 % | 100 % | 95 % | 99 % | 100 % | 98 % | 96 % | 9.429 | 0.0044 | 2.244 | 8,1 |
