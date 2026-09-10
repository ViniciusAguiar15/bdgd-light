---
title: "agent: ADR-003 provedor LLM (OpenAI padrão + Gemini compatível) e secrets"
labels: area:agent, area:docs, phase:F3, copilot
milestone: F3 Agente
---
## Tarefa
- `docs/adr/ADR-003-provedor-llm.md`: OpenAI (`gpt-4.1`/`gpt-5`, tool calling) como padrão; Gemini pelo endpoint
  compatível com OpenAI (`https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`) como segundo
  provedor para comparação no benchmark; Ollama para dev offline; GitHub Models aposentado; Vertex fora por ora.
- `bdgd_light.agent.llm`: perfis nomeados (`BDGD_LLM_PROVIDER=openai|gemini|ollama|fake`) que preenchem endpoint,
  modelo padrão e nome da variável do token (`OPENAI_API_KEY`, `GEMINI_API_KEY`); `bdgd-light llm --provider`.
  `listar_modelos` deve funcionar nos dois provedores (Gemini expõe `/models`).
- CI: testes continuam sem rede; adicionar job opcional `llm-smoke` que roda `bdgd-light llm "Quanto é 2+3?"` só
  quando o secret existir (`if: ${{ secrets.OPENAI_API_KEY != '' }}`).
- Documentar em `docs/spike-llm.md` os limites de taxa observados e o custo por chamada de teste.

## Critérios de aceite
- [ ] `uv run bdgd-light llm --provider openai "Quanto é 2+3?"` e `--provider gemini` funcionam com as chaves do mantenedor (ele valida).
- [ ] Nenhum segredo no código; teste de varredura mantido.
