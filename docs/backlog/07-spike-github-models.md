---
title: "agent: spike GitHub Models — interface LLMClient e tool calling"
labels: area:agent, phase:F3, copilot, spike
milestone: F3 Agente
---
## Tarefa
- Criar `bdgd_light.agent.llm` com a interface `LLMClient` (`chat(messages, tools) -> ToolCalls|Text`) e a
  implementação `GitHubModelsClient` (endpoint de inferência do GitHub Models, autenticação por
  `GITHUB_TOKEN`, modelo configurável por env `BDGD_LLM_MODEL`).
- Script `scripts/listar_modelos.py` que lista os modelos disponíveis (destacar Claude/OpenAI com suporte a
  tool calling) e `docs/spike-llm.md` com limites de taxa/tokens observados e recomendação de modelo padrão.
- Exemplo mínimo de tool calling: ferramenta `soma(a,b)`; teste com cliente *fake* (sem rede) para a lógica
  de parsing.

## Critérios de aceite
- [ ] Nenhuma chamada de rede nos testes (cliente fake).
- [ ] Segredos só por variável de ambiente; nada hardcoded.
