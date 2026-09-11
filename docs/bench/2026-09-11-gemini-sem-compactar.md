# Benchmark do agente — gemini-sem-compactar (2026-09-11)

- provedor/modelo: **gemini** · gemini-2.5-flash
- modo: exemplos anotados sim (top-k 3); compactação dos retornos não
- k = 2; repetições por tarefa = 2; semente = 42
- tarefas: 34 de `/Users/vinicius/repos/bdgd-light/bench/tarefas.yaml`; execuções: 68; erros: 2
- commit: `791ca3d`; CSV: `docs/bench/2026-09-11-gemini-sem-compactar.csv`

## Métricas por nível

| nível | tarefas | exec. | pass@1 | pass@2 | ordem | precisão | tokens médios | tokens/pass@1 | US$/exec. | US$/pass@1 | chars ferr. | s/exec. | rodadas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| simple | 10 | 20 | 100 % | 100 % | 100 % | 100 % | 11.064 | 11.064 | 0.0037 | 0.0037 | 10.957 | 2,1 | 2,0 |
| medium | 13 | 26 | 100 % | 100 % | 92 % | 100 % | 6.808 | 6.808 | 0.0025 | 0.0025 | 2.391 | 2,3 | 1,9 |
| hard | 11 | 22 | 91 % | 100 % | 95 % | 100 % | 40.184 | 44.202 | 0.0157 | 0.0172 | 15.759 | 17,8 | 4,4 |
| total | 34 | 68 | 97 % | 100 % | 96 % | 100 % | 18.858 | 19.429 | 0.0071 | 0.0073 | 9.236 | 7,2 | 2,7 |

> US$ = preço de lista de `gemini-2.5-flash` (US$ 0.30/M tokens de entrada, US$ 2.50/M de saída, raciocínio incluído) × tokens informados pelo provedor; sem cache de contexto nem lote.

## Por tarefa

| id | nível | cluster | acertos | pass@1 | ordem | sequência típica | esperado | obtido (último) | tokens médios | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|
| S01 | simple | tijuca | 2/2 | 100 % | 100 % | get_topology | 4,246 | 4,246 | 11.156 | 2,1 |
| S02 | simple | tijuca | 2/2 | 100 % | 100 % | get_topology | 5.824 | 5.824 | 11.352 | 1,8 |
| S03 | simple | tijuca | 2/2 | 100 % | 100 % | get_topology | 9 | 9 | 10.346 | 2,1 |
| S04 | simple | tijuca | 2/2 | 100 % | 100 % | get_topology | 436 | 436 | 10.791 | 2,4 |
| S05 | simple | ipanema | 2/2 | 100 % | 100 % | get_topology | 1.816 | 1.816 | 5.963 | 1,7 |
| S06 | simple | ipanema | 2/2 | 100 % | 100 % | get_topology | 31 | 31 | 11.944 | 1,7 |
| S07 | simple | ipanema | 2/2 | 100 % | 100 % | get_topology | 5,956 | 5,956 | 6.061 | 2,2 |
| S08 | simple | taquara | 2/2 | 100 % | 100 % | get_topology | 17,979 | 17,979 | 14.390 | 2,4 |
| S09 | simple | taquara | 2/2 | 100 % | 100 % | get_topology | 82 | 82 | 13.125 | 1,8 |
| S10 | simple | taquara | 2/2 | 100 % | 100 % | get_topology | 58 | 58 | 15.516 | 2,4 |
| M01 | medium | tijuca | 2/2 | 100 % | 100 % | downstream_customers | 1.307 | 1.307 | 5.298 | 2,4 |
| M02 | medium | tijuca | 2/2 | 100 % | 100 % | downstream_customers | 1.395 | 1.395 | 5.160 | 2,0 |
| M03 | medium | taquara | 2/2 | 100 % | 100 % | downstream_customers | 1.361 | 1.361 | 5.302 | 2,3 |
| M04 | medium | taquara | 2/2 | 100 % | 100 % | downstream_customers | 1.261 | 1.261 | 5.187 | 1,6 |
| M05 | medium | ipanema | 2/2 | 100 % | 100 % | downstream_customers | 404 | 404 | 5.161 | 2,0 |
| M06 | medium | tijuca | 2/2 | 100 % | 100 % | locate_fault | 35 | 35 | 6.542 | 1,6 |
| M07 | medium | tijuca | 2/2 | 100 % | 50 % | isolate_fault | 4.036 | 4.036 | 11.732 | 2,7 |
| M08 | medium | ipanema | 2/2 | 100 % | 100 % | locate_fault | 1.251 | 1.251 | 13.450 | 2,1 |
| M09 | medium | taquara | 2/2 | 100 % | 50 % | isolate_fault | 2.023 | 2.023 | 12.091 | 2,4 |
| M10 | medium | taquara | 2/2 | 100 % | 100 % | locate_fault | 4 | 4 | 6.983 | 2,3 |
| M11 | medium | ipanema | 2/2 | 100 % | 100 % | downstream_customers | 271 | 271 | 5.173 | 2,0 |
| M12 | medium | ipanema | 2/2 | 100 % | 100 % | — | 1.816 | 1.816 | 3.338 | 3,7 |
| M13 | medium | ipanema | 2/2 | 100 % | 100 % | — | 1.730 | 1.730 | 3.082 | 2,4 |
| H01 | hard | tijuca | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 974020904, 529355823 | 974020904 | 52.931 | 25,7 |
| H02 | hard | tijuca | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 45,978 | 45,980 | 33.952 | 17,7 |
| H03 | hard | tijuca | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 4 | 4 | 32.408 | 13,5 |
| H04 | hard | tijuca | 1/2 | 50 % | 75 % | locate_fault → isolate_fault | 746851189 | 746851189 | 31.221 | 13,0 |
| H05 | hard | tijuca | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 644 | 644 | 22.005 | 11,2 |
| H06 | hard | ipanema | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | ∅ (sem chave) | — | 66.340 | 15,4 |
| H07 | hard | ipanema | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 479 | 479 | 46.288 | 8,7 |
| H08 | hard | taquara | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 11053620, 11056672, 789941518, 11053522, 11053627, 1007642983, 752622332, 11026494, 134733185, 258481641 | 11056672 | 59.376 | 35,4 |
| H09 | hard | taquara | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options | 10 | 10 | 35.377 | 19,3 |
| H10 | hard | taquara | 2/2 | 100 % | 100 % | locate_fault → isolate_fault → restore_options → propose_plan | 11053522, 11053620, 11056672, 752622332, 134733185, 258481641 | 11056672 | 43.238 | 27,6 |
| H11 | hard | ipanema | 1/2 | 50 % | 75 % | locate_fault → isolate_fault | ∅ (sem chave) | — | 18.884 | 8,6 |

## Erros

- H04 (rep. 1): mensagem sem 'content' nem 'tool_calls' (finish_reason='function_call_filter: MALFORMED_FUNCTION_CALL'): {"choices": [{"finish_reason": "function_call_filter: MALFORMED_FUNCTION_CALL", "index": 0, "message": {"role": "assistant"}}], "created": 1789126526, "id": "feejas_iKuaJz7IPxeXbiQ0", "model": "gemini-2.5-flash", "object": "chat.completion", "usage": {"completion_tokens": 0, "prompt_tokens": 6624, "…
- H11 (rep. 1): mensagem sem 'content' nem 'tool_calls' (finish_reason='function_call_filter: MALFORMED_FUNCTION_CALL'): {"choices": [{"finish_reason": "function_call_filter: MALFORMED_FUNCTION_CALL", "index": 0, "message": {"role": "assistant"}}], "created": 1789126534, "id": "heejapCYIbKcqtsP39K_yQk", "model": "gemini-2.5-flash", "object": "chat.completion", "usage": {"completion_tokens": 0, "prompt_tokens": 3832, "…

## Comparativo (todos os CSVs de `docs/bench/`)

| provedor · modo | modelo | tarefas | pass@1 simple | pass@1 medium | pass@1 hard | pass@1 total | pass@2 total | ordem | precisão | tokens/pass@1 | US$/exec. | chars ferr./exec. | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fake | fake-operador | 34 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0 | — | 1.806 | 2,3 |
| fake-sem-compactar | fake-operador | 34 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0 | — | 6.352 | 2,1 |
| fake-sem-exemplos | fake-operador | 34 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0 | — | 1.806 | 1,9 |
| gemini | gemini-2.5-flash | 34 | 100 % | 100 % | 85 % | 94 % | 99 % | 95 % | 99 % | 12.354 | 0.0051 | 2.366 | 8,6 |
| gemini-sem-compactar | gemini-2.5-flash | 34 | 100 % | 100 % | 91 % | 97 % | 100 % | 96 % | 100 % | 19.429 | 0.0071 | 9.236 | 7,2 |
| gemini-sem-exemplos | gemini-2.5-flash | 34 | 100 % | 100 % | 95 % | 99 % | 100 % | 98 % | 96 % | 9.429 | 0.0044 | 2.244 | 8,1 |
