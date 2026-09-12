# Benchmark do agente — openai-fora-treino-k3 (2026-09-12)

- provedor/modelo: **openai** · gpt-4.1-mini-2025-04-14
- modo: exemplos anotados sim (top-k 3); compactação dos retornos sim
- k = 3; repetições por tarefa = 3; semente = 92
- tarefas: 10 de `bench/tarefas_fora_treino.yaml`; execuções: 30; erros: 3
- commit: `33f23fd`; CSV: `docs/bench/2026-09-12-openai-fora-treino-k3.csv`

## Métricas por nível

| nível | tarefas | exec. | pass@1 | pass@3 | ordem | precisão | ferr. desnec. | tokens médios | tokens/pass@1 | US$/exec. | US$/pass@1 | chars ferr. | s/exec. | rodadas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hard | 10 | 30 | 90 % | 90 % | 98 % | 100 % | 0,00 | 20.897 | 23.219 | 0.0090 | 0.0100 | 15.307 | 12,8 | 4,3 |
| total | 10 | 30 | 90 % | 90 % | 98 % | 100 % | 0,00 | 20.897 | 23.219 | 0.0090 | 0.0100 | 15.307 | 12,8 | 4,3 |

> US$ = preço de lista de `gpt-4.1-mini-2025-04-14` (US$ 0.40/M tokens de entrada, US$ 1.60/M de saída, raciocínio incluído) × tokens informados pelo provedor; sem cache de contexto nem lote.

## Por tarefa

| id | nível | cluster | acertos | pass@1 | ordem | ferr. desnec. | sequência típica | esperado | obtido (último) | tokens médios | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FT01 | hard | RCP33308-RCP9882 | 3/3 | 100 % | 100 % | 0,00 | locate_fault → isolate_fault → restore_options → propose_plan | 757513244 | 757513244 | 43.058 | 11,7 |
| FT02 | hard | SAT1960-SAT9523 | 0/3 | 0 % | 75 % | 0,00 | locate_fault → isolate_fault → restore_options | ∅ (sem chave) | — | 23.654 | 19,6 |
| FT03 | hard | CBI24982-CBI24896-CBI24963-CBI24970-TRG959 | 3/3 | 100 % | 100 % | 0,00 | locate_fault → isolate_fault → restore_options → propose_plan | ∅ (sem chave) | — | 13.388 | 9,2 |
| FT04 | hard | AVD33625-AVD33340-AVD33357-GDN0011 | 3/3 | 100 % | 100 % | 0,00 | locate_fault → isolate_fault → restore_options → propose_plan | 11138583 | 11138583 | 26.225 | 12,2 |
| FT05 | hard | ITP00005-ITP33172 | 3/3 | 100 % | 100 % | 0,00 | locate_fault → isolate_fault → restore_options → propose_plan | 456765966 | 456765966 | 21.692 | 12,6 |
| FT06 | hard | PDG33010-PDG219-PDG29015-PDG29724-PDG29731-PDG33499-PDG33662-TQR00005 | 3/3 | 100 % | 100 % | 0,00 | locate_fault → isolate_fault → restore_options → propose_plan | 11009531 | 11009531 | 27.827 | 28,0 |
| FT07 | hard | BPD9350 | 3/3 | 100 % | 100 % | 0,00 | locate_fault → isolate_fault → restore_options → propose_plan | ∅ (sem chave) | — | 13.084 | 7,9 |
| FT08 | hard | COP2700 | 3/3 | 100 % | 100 % | 0,00 | locate_fault → isolate_fault → restore_options → propose_plan | ∅ (sem chave) | — | 13.354 | 8,6 |
| FT09 | hard | LBN00061 | 3/3 | 100 % | 100 % | 0,00 | locate_fault → isolate_fault → restore_options → propose_plan | ∅ (sem chave) | — | 13.164 | 9,1 |
| FT10 | hard | PTS9310-PTS0001 | 3/3 | 100 % | 100 % | 0,00 | locate_fault → isolate_fault → restore_options → propose_plan | ∅ (sem chave) | — | 13.524 | 9,1 |

## Erros

- FT02 (rep. 2): sem proposta após 2 replanejamento(s): o modelo encerrou sem chamar propose_plan (ou o verificador recusou todas)
- FT02 (rep. 3): sem proposta após 2 replanejamento(s): o modelo encerrou sem chamar propose_plan (ou o verificador recusou todas)
- FT02 (rep. 1): sem proposta após 2 replanejamento(s): o modelo encerrou sem chamar propose_plan (ou o verificador recusou todas)

## Comparativo (todos os CSVs de `docs/bench/`)

| provedor · modo | modelo | tarefas | pass@1 simple | pass@1 medium | pass@1 hard | pass@1 total | pass@3 total | ordem | precisão | ferr. desnec. | tokens/pass@1 | US$/exec. | chars ferr./exec. | s/exec. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fake | fake-operador | 34 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0,00 | 0 | — | 1.806 | 2,3 |
| fake-sem-compactar | fake-operador | 34 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0,00 | 0 | — | 6.352 | 2,1 |
| fake-sem-exemplos | fake-operador | 34 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 0,00 | 0 | — | 1.806 | 1,9 |
| gemini | gemini-2.5-flash | 34 | 100 % | 100 % | 85 % | 94 % | 100 % | 95 % | 99 % | 0,02 | 12.354 | 0.0051 | 2.366 | 8,6 |
| gemini-hard-k5-sem-exemplos | gemini-2.5-flash | 11 | — | — | 100 % | 100 % | 100 % | 96 % | 98 % | 0,07 | 25.401 | 0.0118 | 14.006 | 17,8 |
| gemini-sem-compactar | gemini-2.5-flash | 34 | 100 % | 100 % | 91 % | 97 % | 100 % | 96 % | 100 % | 0,00 | 19.429 | 0.0071 | 9.236 | 7,2 |
| gemini-sem-exemplos | gemini-2.5-flash | 34 | 100 % | 100 % | 95 % | 99 % | 100 % | 98 % | 96 % | 0,09 | 9.429 | 0.0044 | 2.244 | 8,1 |
| openai | gpt-4.1-mini-2025-04-14 | 34 | 100 % | 85 % | 100 % | 94 % | 94 % | 99 % | 95 % | 0,10 | 10.153 | 0.0041 | 5.687 | 8,4 |
| openai-fora-treino-k3 | gpt-4.1-mini-2025-04-14 | 10 | — | — | 90 % | 90 % | 90 % | 98 % | 100 % | 0,00 | 23.219 | 0.0090 | 15.307 | 12,8 |
| openai-hard-k5 | gpt-4.1-mini-2025-04-14 | 11 | — | — | 100 % | 100 % | 100 % | 100 % | 97 % | 0,11 | 18.897 | 0.0081 | 16.084 | 18,7 |
| openai-hard-k5-sem-exemplos | gpt-4.1-mini-2025-04-14 | 11 | — | — | 100 % | 100 % | 100 % | 96 % | 98 % | 0,09 | 17.714 | 0.0075 | 15.583 | 16,4 |
| openai-hardplus-k3 | gpt-4.1-mini-2025-04-14 | 4 | — | — | 100 % | 100 % | 100 % | 100 % | 68 % | 1,42 | 41.269 | 0.0172 | 18.315 | 17,6 |
| openai-hardplus-k3-sem-exemplos | gpt-4.1-mini-2025-04-14 | 4 | — | — | 100 % | 100 % | 100 % | 96 % | 69 % | 1,25 | 44.417 | 0.0184 | 17.871 | 17,9 |
