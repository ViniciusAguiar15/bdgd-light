---
title: "agent: orquestrador + verificador HITL sobre o MCP (padrão PowerChain)"
labels: area:agent, phase:F3, copilot
milestone: F3 Agente
---
## Contexto
Referência: PowerChain (arXiv 2508.17094): orquestrador gera workflow (DAG de chamadas) guiado por pares
tarefa↔workflow anotados; verificador executa, captura erros e realimenta. Nível 2 de autonomia: só propõe.

## Tarefa
`bdgd_light.agent.orquestrador`: recebe um evento (#23) ou uma pergunta em linguagem natural, monta o prompt com
descritores das ferramentas MCP + top-K exemplos anotados (`docs/agent/exemplos.yaml`: ~10 pares
"tarefa → sequência de ferramentas + justificativa", cobrindo falta simples, falta com 2 rotas, rota inviável por
tensão, pico de carga, pergunta informativa), chama o `LLMClient`, executa as ferramentas via MCP, valida
(verificador: convergência, limites 0,93–1,05 pu MT, corrente ≤ nominal, chaves existem, sequência abre-antes-de-fechar),
replaneja até N rodadas, e termina em `propose_plan` (proposta pendente com raciocínio resumido e alternativas
descartadas) — **nunca chama `set_switch`**. `bdgd-light agente --evento <json>|--pergunta "..." [--provider]`
imprime a proposta e grava no audit. Métricas por execução: ferramentas chamadas, rodadas, tokens, tempo.

## Critérios de aceite
- [ ] Com `FakeLLMClient` roteirizado, o cenário `taquara_bocari` produz proposta correta (testes).
- [ ] Com OpenAI real (mantenedor valida), os 3 cenários nomeados terminam em proposta viável.
- [ ] `docs/agent.md`: arquitetura, prompt, exemplos, limites.
