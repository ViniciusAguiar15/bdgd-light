# Benchmark do agente — gemini-sem-exemplos (2026-09-11)

- provedor/modelo: **gemini** · gemini-2.5-flash
- modo: exemplos anotados não (top-k 0); compactação dos retornos sim
- k = 2; repetições por tarefa = 2; semente = 42
- tarefas: 34 de `/Users/vinicius/repos/bdgd-light/bench/tarefas.yaml`; execuções: 68; erros: 1
- commit: `791ca3d`; CSV: `docs/bench/2026-09-11-gemini-sem-exemplos.csv`

## Métricas por nível

| nível | tarefas | exec. | pass@1 | pass@2 | ordem | precisão | tokens médios | tokens/pass@1 | US$/exec. | US$/pass@1 | chars ferr. | s/exec. | rodadas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| simple | 10 | 20 | 100 % | 100 % | 100 % | 100 % | 5.286 | 5.286 | 0.0019 | 0.0019 | 1.662 | 1,9 | 2,0 |
| medium | 13 | 26 | 100 % | 100 % | 98 % | 96 % | 5.036 | 5.036 | 0.0021 | 0.0021 | 404 | 2,5 | 2,0 |
| hard | 11 | 22 | 95 % | 100 % | 95 % | 91 % | 17.958 | 18.813 | 0.0095 | 0.0100 | 4.947 | 20,5 | 4,5 |
| total | 34 | 68 | 99 % | 100 % | 98 % | 96 % | 9.290 | 9.429 | 0.0044 | 0.0045 | 2.244 | 8,1 | 2,8 |

> US$ = preço de lista de `gemini-2.5-flash` (US$ 0.30/M tokens de entrada, US$ 2.50/M de saída, raciocínio incluído) × tokens informados pelo provedor; sem cache de contexto nem lote.

## Por tarefa

| id | nível | cluster | acertos | pass@1 | ordem | sequência típica | esperado | obtido (último) | tokens médios | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|
| S01 | simple | tijuca | 2/2 | 100 % | 100 % | get_topology | 4,246 | 4,246 | 5.463 | 1,8 |
| S02 | simple | tijuca | 2/2 | 100 % | 100 % | get_topology | 5.824 | 5.824 | 5.308 | 2,4 |
| S03 | simple | tijuca | 2/2 | 100 % | 100 % | get_topology | 9 | 9 | 5.106 | 2,0 |
| S04 | simple | tijuca | 2/2 | 100 % | 100 % | get_topology | 436 | 436 | 5.282 | 1,8 |
| S05 | simple | ipanema | 2/2 | 100 % | 100 % | get_topology | 1.816 | 1.816 | 4.706 | 1,7 |
| S06 | simple | ipanema | 2/2 | 100 % | 100 % | get_topology | 31 | 31 | 4.754 | 1,7 |
| S07 | simple | ipanema | 2/2 | 100 % | 100 % | get_topology | 5,956 | 5,956 | 4.763 | 1,8 |
| S08 | simple | taquara | 2/2 | 100 % | 100 % | get_topology | 17,979 | 17,979 | 5.795 | 1,9 |
| S09 | simple | taquara | 2/2 | 100 % | 100 % | get_topology | 82 | 82 | 5.585 | 1,7 |
| S10 | simple | taquara | 2/2 | 100 % | 100 % | get_topology | 58 | 58 | 6.096 | 1,8 |
| M01 | medium | tijuca | 2/2 | 100 % | 100 % | downstream_customers | 1.307 | 1.307 | 4.590 | 1,7 |
| M02 | medium | tijuca | 2/2 | 100 % | 100 % | downstream_customers | 1.395 | 1.395 | 4.511 | 1,5 |
| M03 | medium | taquara | 2/2 | 100 % | 100 % | downstream_customers | 1.361 | 1.361 | 4.586 | 1,9 |
| M04 | medium | taquara | 2/2 | 100 % | 100 % | downstream_customers | 1.261 | 1.261 | 4.542 | 1,7 |
| M05 | medium | ipanema | 2/2 | 100 % | 100 % | downstream_customers | 404 | 404 | 4.555 | 2,5 |
| M06 | medium | tijuca | 2/2 | 100 % | 100 % | locate_fault | 35 | 35 | 4.892 | 2,5 |
| M07 | medium | tijuca | 2/2 | 100 % | 75 % | locate_fault → isolate_fault | 4.036 | 4.036 | 6.479 | 3,8 |
| M08 | medium | ipanema | 2/2 | 100 % | 100 % | locate_fault | 1.251 | 1.251 | 4.812 | 2,4 |
| M09 | medium | taquara | 2/2 | 100 % | 100 % | locate_fault → isolate_fault | 2.023 | 2.023 | 8.234 | 3,9 |
| M10 | medium | taquara | 2/2 | 100 % | 100 % | locate_fault → isolate_fault | 4 | 4 | 8.182 | 3,9 |
| M11 | medium | ipanema | 2/2 | 100 % | 100 % | downstream_customers | 271 | 271 | 4.536 | 2,3 |
| M12 | medium | ipanema | 2/2 | 100 % | 100 % | — | 1.816 | 1.816 | 2.750 | 2,6 |
| M13 | medium | ipanema | 2/2 | 100 % | 100 % | — | 1.730 | 1.730 | 2.794 | 2,2 |
| H01 | hard | tijuca | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 974020904, 529355823 | 974020904 | 22.210 | 23,3 |
| H02 | hard | tijuca | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 45,978 | 46 | 17.389 | 18,1 |
| H03 | hard | tijuca | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 4 | 4 | 16.658 | 16,1 |
| H04 | hard | tijuca | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 746851189 | 746851189 | 23.704 | 24,2 |
| H05 | hard | tijuca | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 644 | 644 | 13.101 | 11,5 |
| H06 | hard | ipanema | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | ∅ (sem chave) | — | 16.761 | 9,4 |
| H07 | hard | ipanema | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 479 | 479 | 16.009 | 11,2 |
| H08 | hard | taquara | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 11053620, 11056672, 789941518, 11053522, 11053627, 1007642983, 752622332, 11026494, 134733185, 258481641 | 11053620 | 23.946 | 37,8 |
| H09 | hard | taquara | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 10 | 10 | 13.764 | 20,8 |
| H10 | hard | taquara | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 11053522, 11053620, 11056672, 752622332, 134733185, 258481641 | 11053522 | 25.118 | 32,9 |
| H11 | hard | ipanema | 1/2 | 50 % | 50 % | locate_fault → isolate_fault → restore_options → propose_plan | ∅ (sem chave) | — | 8.876 | 20,1 |

## Erros

- H11 (rep. 2): ReadTimeout: [Errno 60] Operation timed out

## Comparativo (todos os CSVs de `docs/bench/`)

| provedor · modo | modelo | tarefas | pass@1 simple | pass@1 medium | pass@1 hard | pass@1 total | pass@2 total | ordem | precisão | tokens/pass@1 | US$/exec. | chars ferr./exec. | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fake | fake-operador | 34 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0 | — | 1.806 | 2,3 |
| fake-sem-compactar | fake-operador | 34 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0 | — | 6.352 | 2,1 |
| fake-sem-exemplos | fake-operador | 34 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0 | — | 1.806 | 1,9 |
| gemini | gemini-2.5-flash | 34 | 100 % | 100 % | 85 % | 94 % | 99 % | 95 % | 99 % | 12.354 | 0.0051 | 2.366 | 8,6 |
| gemini-sem-compactar | gemini-2.5-flash | 34 | 100 % | 100 % | 91 % | 97 % | 100 % | 96 % | 100 % | 19.429 | 0.0071 | 9.236 | 7,2 |
| gemini-sem-exemplos | gemini-2.5-flash | 34 | 100 % | 100 % | 95 % | 99 % | 100 % | 98 % | 96 % | 9.429 | 0.0044 | 2.244 | 8,1 |
