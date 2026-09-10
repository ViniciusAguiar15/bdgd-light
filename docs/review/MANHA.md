# Bom dia — resumo da noite de 9→10/09/2026

**Fila inteira entregue.** 7 itens, PRs #9–#21 mergeados em `main`, 162 testes verdes (eram 39), nada de `data/` no git,
sem force-push. Diário completo em `NOITE.md`; minhas revisões em `PR-01.md` … `PR-07.md` (todas aprovadas; os
pedidos que fiz durante a noite o Copilot já aplicou em commits próprios, exceto os marcados como fase 3).

## O que existe agora
`bdgd-light export | inventario | vizinhos | recortar | grafo | dss | tiles | llm | audit`, console MapLibre em `console/`,
ADR-001 e ADR-002, docs de referência da BDGD, do grafo, do OpenDSS e do LLM. O cenário FLISR do escopo v2 (falta em
BOCARI, restauração via PARNAIBA ou CURUMAU) roda de ponta a ponta: grafo → sequência de manobras → OpenDSS →
fluxo convergido, ~1,2 s, as duas rotas viáveis em MT.

## Três decisões suas para hoje
1. **Provedor do LLM do agente.** GitHub Models foi aposentado (410). O cliente `OpenAICompatClient` já aceita
   Azure AI Foundry, OpenAI, Anthropic (endpoint compatível) ou Ollama local. Escolha, cadastre `BDGD_LLM_TOKEN`
   como secret, e o Copilot escreve a ADR-003.
2. **Repo público ou privado?** Pages só funciona em público no seu plano. Público = demo hospedada de graça;
   privado = demo via `npm run dev`.
3. **Cluster TQR confirmado?** Tudo (grafo, gêmeo, tiles, exemplos) usa TQR0007/TQR33859/TQR33862. Se quiser ver
   antes: `cd console && npm ci && npm run dev` e abra `http://localhost:5173/?estado=exemplos/estado_TQR0007_falta.geojson`.

## Próxima fila sugerida (fase 3 — o agente)
- #17 Master do gêmeo a partir do GPKG do recorte (grafo e gêmeo = mesma rede).
- #18 `twin.score_eletrico` — o verificador: roda cada opção de restauração no OpenDSS e devolve viável/inviável com
  I no disjuntor, Vmin MT, sobrecargas.
- **#22 Servidor MCP** (`bdgd_light.mcp_server`): `load_feeder`, `get_topology`, `run_powerflow`, `inject_fault`,
  `locate_fault`, `downstream_customers`, `restore_options` (com score elétrico), `propose_flisr`, `set_switch`
  (exige token de aprovação). Tudo já existe como função Python; é só expor.
- **#23 Simulador de eventos** (`bdgd_light.sim`): injeta falta num trecho aleatório/escolhido do cluster e publica o
  evento para o agente.
- **#24 Agente orquestrador/verificador** (`bdgd_light.agent`): usa o `LLMClient` + MCP, exemplos anotados
  (tarefa → sequência de ferramentas), log de auditoria, modo HITL: gera proposta e espera aprovação.
- **#25 Console F3**: fila de eventos, proposta com raciocínio, botão Aprovar/Rejeitar → chama `set_switch`.
- #26 Benchmark estilo PowerChain (10 tarefas simple/medium/hard sobre o cluster, pass@k, precisão de ordenação,
  tokens/pass@1) — só depois do #24.
Quando decidir os 3 pontos acima, eu escrevo as issues #22–#26 em `docs/backlog/` com critérios de aceite e o prompt
da próxima rodada do Copilot.
