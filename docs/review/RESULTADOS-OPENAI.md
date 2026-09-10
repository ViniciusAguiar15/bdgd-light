# Validação real dos 3 cenários — OpenAI × Gemini (2026-09-10, rodado pelo mantenedor)

| cenário | modelo | rodadas | tokens in+out | LLM | ferramentas | proposta |
|---|---|---|---|---|---|---|
| tijuca_cabofrio_tronco | gpt-4.1-mini | 4 | 32.154 + 508 = 32.662 | 14,3 s | 9,8 s | abrir 11035901 → fechar 974020904 (ALC9946), 4.042 clientes, margem 46 % |
| | gemini-2.5-flash | 5 | 49.360 + 735 = 53.480 | ≈23 s | 6,9 s | idem |
| ipanema_9210 | gpt-4.1-mini | 4 | 32.559 + 376 = 32.935 | 10,2 s | 0,0 s | só isolar (505111870, 561826961) + despachar |
| | gemini-2.5-flash | 5 | 63.179 + 389 = 65.474 | 14,4 s | 0,1 s | idem |
| taquara_bocari | gpt-4.1-mini | 5 | 37.150 + 385 = 37.535 | 15,0 s | 24,8 s | abrir 4 → religar 10924213 → fechar 11053620 (TQR33859), 1.984 clientes, margem 62 % |
| | gemini-2.5-flash | 5 | 54.075 + 468 = 59.395 | 25,8 s | 18,5 s | idem |

Relatórios: `data/relatorios/*_openai.json`. Ambos os modelos: 0 replanejamentos, 0 recusas, mesma proposta do ranking
elétrico; gpt-4.1-mini gasta ≈40 % menos tokens e metade do tempo de LLM. Observação para o benchmark (#36): no
Ipanema o resumo do gpt-4.1-mini citou "1.730 clientes sem tensão" (total do CTMT) em vez dos 479 não restauráveis
presentes no retorno de `restore_options` — pontuar a **correção numérica do resumo**, não só da proposta.

Pedido ao Copilot: incorporar as linhas OpenAI em `docs/agent.md` e a observação em `docs/backlog/15-benchmark.md`.
