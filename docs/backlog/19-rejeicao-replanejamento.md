---
title: "agent+console: rejeitar com motivo faz o agente replanejar com a restrição"
labels: area:agent, area:console, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
Hoje o operador aprova ou rejeita e o ciclo acaba. Rejeitar dizendo **por que** ("chave em manutenção",
"não quero carregar o BOMPASTOR", "prefere a rota telecomandada") e o agente replanejar com essa
restrição é o que separa "a IA propõe" de "a IA colabora" — e é o momento mais forte da demo.

## Tarefa
- `POST /api/propostas/{id}/rejeitar` já aceita `motivo`; ao rejeitar, a API deve **reacionar o agente**
  com o motivo anexado ao contexto (nova execução, mesma falta, sem reinjetar o evento).
- `SessaoCOD`: `restricoes` da sessão (chaves proibidas, alimentadores a evitar, "só telecomandadas"),
  alimentadas pelo motivo. O parsing do motivo em restrição é do **LLM** (ele já tem o texto), mas a
  restrição vira estado da sessão e o **verificador** passa a reprovar plano que a viole — nunca confiar
  só no modelo lembrar.
- `restore_options` marca as opções bloqueadas por restrição (`bloqueada: motivo`), sem removê-las.
- Console: campo de motivo no rejeitar (com 3 sugestões clicáveis), e a proposta seguinte mostra
  "replanejada após rejeição: <motivo>". Limite de 3 replanejamentos por evento.
- Auditoria: `hitl.rejeicao` com o motivo e `agente.replanejamento` com a restrição aplicada.

## Critérios de aceite
- [ ] Teste com operador fake: rejeitar "a chave 974020904 está em manutenção" → nova proposta usa outra
      chave viável; o verificador reprova se o agente insistir na proibida.
- [ ] Demo: rejeitar pelo console gera nova proposta em < 40 s com LLM real.
- [ ] `docs/agent.md` e `docs/console.md` documentam o ciclo e o limite de replanejamentos.
