# Resultados consolidados

Documento gerado deterministicamente por `uv run python scripts/gerar_resultados.py`.
Data-base das fontes versionadas mais recentes: **2026-09-11**.

## Escopo das fontes

| item | valor | fonte |
|---|---:|---|
| tarefas catalogadas no benchmark | 38 | docs/bench.md (2026-09-11) |
| CSVs lidos em `docs/bench/` | 16 | docs/bench/ |

## Recortes e cenários usados pelos benchmarks

| cenário | alimentadores | trechos MT | chaves | ties de campo | clientes | fonte |
|---|---:|---:|---:|---:|---|---|
| Ipanema | 4 | — | 95 | 1 | 4.720 UCBT, 33 trafos (14,0 MVA) | docs/escopo-cidade.md (análise 2026-09-10; inventário regerado em 2026-09-11) |
| Taquara | 3 | 1.924 | 162 | 35 | 16.504 UCBT | docs/review/NOITE.md (2026-09-09) |
| Tijuca | 4 | 1.528 | 148 | 23 | 16257 clientes totais (16248 UCBT) | docs/agent/sessao-tijuca.json (criada_em 2026-09-10) |

Notas de rastreabilidade:
- Ipanema: o documento versionado traz alimentadores, chaves, clientes e ties, mas não a contagem de trechos MT; o consolidado mantém esse campo em branco para não inferir valor.

## Efeito da folga `EM_SUB` nas interligações

| escopo | antes | depois | delta | fonte |
|---|---:|---:|---:|---|
| Município do Rio — ties TLCD de campo | 962 | 814 | -148 | docs/escopo-cidade.md (análise 2026-09-10; inventário regerado em 2026-09-11) |
| Município do Rio — ties de campo totais | 6.135 | 5.773 | -362 | docs/escopo-cidade.md (análise 2026-09-10; inventário regerado em 2026-09-11) |
| Município do Rio — ties em SE | 814 | 1.176 | +362 | docs/escopo-cidade.md (análise 2026-09-10; inventário regerado em 2026-09-11) |
| Light inteira — chaves em SE | 1.138 | 1.683 | +545 em 282 alimentadores | docs/escopo-cidade.md (análise 2026-09-10; inventário regerado em 2026-09-11) |

## Benchmarks consolidados por arquivo mais recente de cada família

Nas colunas **ordem** e **precisão**, a fração entre parênteses agrega passos (LCS/passos da referência ou chamadas totais) para dar a escala do percentual.

| família | modo | modelo | tarefas | execuções | k efetivo | pass@1 simple | pass@1 medium | pass@1 hard | pass@k total | ordem | precisão | ferr. desnec./exec. | tokens/exec. | US$/exec. | s/exec. | fonte |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| fake | com exemplos, compactado ★ padrão | fake-operador | 34 | 170 | 5 | 100 % | 100 % | 100 % | 100 % | 100,0 % (310/310) | 100,0 % (310/310) | 0,00 | 0 | — | 2,3 | docs/bench/2026-09-11-fake.csv (2026-09-11) |
| fake | com exemplos, sem compactação | fake-operador | 34 | 170 | 5 | 100 % | 100 % | 100 % | 100 % | 100,0 % (310/310) | 100,0 % (310/310) | 0,00 | 0 | — | 2,1 | docs/bench/2026-09-11-fake-sem-compactar.csv (2026-09-11) |
| fake | sem exemplos, compactado | fake-operador | 34 | 170 | 5 | 100 % | 100 % | 100 % | 100 % | 100,0 % (310/310) | 100,0 % (310/310) | 0,00 | 0 | — | 1,9 | docs/bench/2026-09-11-fake-sem-exemplos.csv (2026-09-11) |
| gemini | com exemplos, compactado ★ padrão | gemini-2.5-flash | 34 | 124 | 5 | 100 % | 100 % | 85 % | 100 % | 94,8 % (245/264) | 98,8 % (245/248) | 0,02 | 11.557 | 0,0051 | 8,6 | docs/bench/2026-09-11-gemini.csv (2026-09-11) |
| gemini | com exemplos, sem compactação | gemini-2.5-flash | 34 | 68 | 2 | 100 % | 100 % | 91 % | 100 % | 95,6 % (116/124) | 100,0 % (116/116) | 0,00 | 18.858 | 0,0071 | 7,2 | docs/bench/2026-09-11-gemini-sem-compactar.csv (2026-09-11) |
| gemini | sem exemplos, compactado | gemini-2.5-flash | 34 | 68 | 2 | 100 % | 100 % | 95 % | 100 % | 97,8 % (119/124) | 95,6 % (119/125) | 0,09 | 9.290 | 0,0044 | 8,1 | docs/bench/2026-09-11-gemini-sem-exemplos.csv (2026-09-11) |
| gemini-hard-k5 | sem exemplos, compactado | gemini-2.5-flash | 11 | 55 | 5 | — | — | 100 % | 100 % | 96,4 % (189/195) | 98,2 % (189/193) | 0,07 | 25.401 | 0,0118 | 17,8 | docs/bench/2026-09-11-gemini-hard-k5-sem-exemplos.csv (2026-09-11) |
| openai | com exemplos, compactado ★ padrão | gpt-4.1-mini-2025-04-14 | 34 | 102 | 3 | 100 % | 85 % | 100 % | 94 % | 98,5 % (183/186) | 95,1 % (183/193) | 0,10 | 9.556 | 0,0041 | 8,4 | docs/bench/2026-09-11-openai.csv (2026-09-11) |
| openai-hard-k5 | com exemplos, compactado ★ padrão | gpt-4.1-mini-2025-04-14 | 11 | 55 | 5 | — | — | 100 % | 100 % | 100,0 % (195/195) | 97,3 % (195/201) | 0,11 | 18.897 | 0,0081 | 18,7 | docs/bench/2026-09-11-openai-hard-k5.csv (2026-09-11) |
| openai-hard-k5 | sem exemplos, compactado | gpt-4.1-mini-2025-04-14 | 11 | 55 | 5 | — | — | 100 % | 100 % | 96,4 % (189/195) | 97,8 % (189/194) | 0,09 | 17.714 | 0,0075 | 16,4 | docs/bench/2026-09-11-openai-hard-k5-sem-exemplos.csv (2026-09-11) |
| openai-hardplus-k3 | com exemplos, compactado ★ padrão | gpt-4.1-mini-2025-04-14 | 4 | 12 | 3 | — | — | 100 % | 100 % | 100,0 % (36/36) | 68,1 % (36/53) | 1,42 | 41.269 | 0,0172 | 17,6 | docs/bench/2026-09-11-openai-hardplus-k3.csv (2026-09-11) |
| openai-hardplus-k3 | sem exemplos, compactado | gpt-4.1-mini-2025-04-14 | 4 | 12 | 3 | — | — | 100 % | 100 % | 95,8 % (34/36) | 69,2 % (34/49) | 1,25 | 44.417 | 0,0184 | 17,9 | docs/bench/2026-09-11-openai-hardplus-k3-sem-exemplos.csv (2026-09-11) |

## Comparação A/B — exemplos anotados

| família | braço | execuções | pass@1 total | ordem | precisão | ferr. desnec./exec. | tokens/exec. | US$/exec. | fonte |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| fake | com exemplos | 170 | 100 % | 100,0 % (310/310) | 100,0 % (310/310) | 0,00 | 0 | — | docs/bench/2026-09-11-fake.csv (2026-09-11) |
| fake | sem exemplos | 170 | 100 % | 100,0 % (310/310) | 100,0 % (310/310) | 0,00 | 0 | — | docs/bench/2026-09-11-fake-sem-exemplos.csv (2026-09-11) |
| gemini | com exemplos | 124 | 94 % | 94,8 % (245/264) | 98,8 % (245/248) | 0,02 | 11.557 | 0,0051 | docs/bench/2026-09-11-gemini.csv (2026-09-11) |
| gemini | sem exemplos | 68 | 99 % | 97,8 % (119/124) | 95,6 % (119/125) | 0,09 | 9.290 | 0,0044 | docs/bench/2026-09-11-gemini-sem-exemplos.csv (2026-09-11) |
| openai-hard-k5 | com exemplos | 55 | 100 % | 100,0 % (195/195) | 97,3 % (195/201) | 0,11 | 18.897 | 0,0081 | docs/bench/2026-09-11-openai-hard-k5.csv (2026-09-11) |
| openai-hard-k5 | sem exemplos | 55 | 100 % | 96,4 % (189/195) | 97,8 % (189/194) | 0,09 | 17.714 | 0,0075 | docs/bench/2026-09-11-openai-hard-k5-sem-exemplos.csv (2026-09-11) |
| openai-hardplus-k3 | com exemplos | 12 | 100 % | 100,0 % (36/36) | 68,1 % (36/53) | 1,42 | 41.269 | 0,0172 | docs/bench/2026-09-11-openai-hardplus-k3.csv (2026-09-11) |
| openai-hardplus-k3 | sem exemplos | 12 | 100 % | 95,8 % (34/36) | 69,2 % (34/49) | 1,25 | 44.417 | 0,0184 | docs/bench/2026-09-11-openai-hardplus-k3-sem-exemplos.csv (2026-09-11) |

## Comparação A/B — compactação das respostas de ferramenta

| família | braço | execuções | pass@1 total | precisão | chars ferr./exec. | tokens/exec. | US$/exec. | fonte |
|---|---|---:|---:|---:|---:|---:|---:|---|
| fake | compactado | 170 | 100 % | 100,0 % (310/310) | 1.806 | 0 | — | docs/bench/2026-09-11-fake.csv (2026-09-11) |
| fake | sem compactação | 170 | 100 % | 100,0 % (310/310) | 6.352 | 0 | — | docs/bench/2026-09-11-fake-sem-compactar.csv (2026-09-11) |
| gemini | compactado | 124 | 94 % | 98,8 % (245/248) | 2.366 | 11.557 | 0,0051 | docs/bench/2026-09-11-gemini.csv (2026-09-11) |
| gemini | sem compactação | 68 | 97 % | 100,0 % (116/116) | 9.236 | 18.858 | 0,0071 | docs/bench/2026-09-11-gemini-sem-compactar.csv (2026-09-11) |

## Taxa de reprovação do verificador nos CSVs mais recentes

| família | modo | execuções com recusa | recusas totais | média de recusas/exec. | fonte |
|---|---|---:|---:|---:|---|
| fake | com exemplos, compactado ★ padrão | 0/170 (0 %) | 0 | 0,00 | docs/bench/2026-09-11-fake.csv (2026-09-11) |
| fake | com exemplos, sem compactação | 0/170 (0 %) | 0 | 0,00 | docs/bench/2026-09-11-fake-sem-compactar.csv (2026-09-11) |
| fake | sem exemplos, compactado | 0/170 (0 %) | 0 | 0,00 | docs/bench/2026-09-11-fake-sem-exemplos.csv (2026-09-11) |
| gemini | com exemplos, compactado ★ padrão | 0/124 (0 %) | 0 | 0,00 | docs/bench/2026-09-11-gemini.csv (2026-09-11) |
| gemini | com exemplos, sem compactação | 0/68 (0 %) | 0 | 0,00 | docs/bench/2026-09-11-gemini-sem-compactar.csv (2026-09-11) |
| gemini | sem exemplos, compactado | 0/68 (0 %) | 0 | 0,00 | docs/bench/2026-09-11-gemini-sem-exemplos.csv (2026-09-11) |
| gemini-hard-k5 | sem exemplos, compactado | 0/55 (0 %) | 0 | 0,00 | docs/bench/2026-09-11-gemini-hard-k5-sem-exemplos.csv (2026-09-11) |
| openai | com exemplos, compactado ★ padrão | 0/102 (0 %) | 0 | 0,00 | docs/bench/2026-09-11-openai.csv (2026-09-11) |
| openai-hard-k5 | com exemplos, compactado ★ padrão | 0/55 (0 %) | 0 | 0,00 | docs/bench/2026-09-11-openai-hard-k5.csv (2026-09-11) |
| openai-hard-k5 | sem exemplos, compactado | 1/55 (2 %) | 1 | 0,02 | docs/bench/2026-09-11-openai-hard-k5-sem-exemplos.csv (2026-09-11) |
| openai-hardplus-k3 | com exemplos, compactado ★ padrão | 4/12 (33 %) | 4 | 0,33 | docs/bench/2026-09-11-openai-hardplus-k3.csv (2026-09-11) |
| openai-hardplus-k3 | sem exemplos, compactado | 3/12 (25 %) | 3 | 0,25 | docs/bench/2026-09-11-openai-hardplus-k3-sem-exemplos.csv (2026-09-11) |

## Cenários ponta a ponta já versionados

| cenário | provedor | proposta final | verificador | rodadas | tokens totais | LLM / ferramentas | fonte |
|---|---|---|---|---:|---|---|---|
| tijuca_cabofrio_tronco | Gemini | **P-0001: abrir 11035901, fechar 974020904 → ALC9946**, 4042 clientes, margem 46 %, Vmin 1,027 pu | ok (11 checagens) | 5 | 49 360 + 735 = 53 480 | ≈23 s / 6,9 s | docs/agent.md (2026-09-10) |
| ipanema_9210 | Gemini | **P-0002 sem chave** (isolar 505111870 e 561826961; religador já aberto) + despacho de equipe | ok (só topologia: 5 checagens, sem chave) | 5 | 63 179 + 389 = 65 474 | 14,4 s / 0,1 s | docs/agent.md (2026-09-10) |
| taquara_bocari | Gemini | **P-0003: abrir 11026473, 22826994, 528574225, 790615689; fechar 10924213 (religador); fechar 11056672 → TQR33859**, 1984 clientes, margem 62 %, Vmin 0,998 pu | ok | 5 | 54 075 + 468 = 59 395 | 25,8 s / 18,5 s | docs/agent.md (2026-09-10) |
| tijuca_cabofrio_tronco | OpenAI | **P-0001: abrir 11035901, fechar 974020904 → ALC9946**, 4042 clientes, margem 45,98 %, Vmin 1,027 pu (mesma do Gemini) | ok | 4 | 32 154 + 508 = 32 662 | 14,3 s / 9,8 s | docs/agent.md (2026-09-10) |
| ipanema_9210 | OpenAI | **P-0002 sem chave** (isolar 505111870 e 561826961) + despacho (mesma do Gemini) | ok (5 checagens) | 4 | 32 559 + 376 = 32 935 | 10,2 s / 0,04 s | docs/agent.md (2026-09-10) |
| taquara_bocari | OpenAI | **P-0003: abrir 11026473, 22826994, 528574225, 790615689; fechar 10924213; fechar 11053620 → TQR33859**, 1984 clientes, margem 61,96 %, Vmin 1,009 pu (chave NA equivalente à do Gemini: mesma fonte, mesmos clientes, empate de margem) | ok | 5 | 37 150 + 385 = 37 535 | 15,0 s / 24,8 s | docs/agent.md (2026-09-10) |

## Limitações conhecidas

- Este consolidado só usa números encontrados em arquivos versionados; onde a documentação não expõe um valor estruturado, o campo fica em branco em vez de ser inferido.
- Os CSVs gerais de 2026-09-11 ainda cobrem a suíte-base de 34 tarefas; as 4 tarefas hard+ (H12–H15) aparecem nos arquivos dedicados `openai-hardplus-k3*`, mantendo a rastreabilidade sem misturar execuções heterogêneas.
