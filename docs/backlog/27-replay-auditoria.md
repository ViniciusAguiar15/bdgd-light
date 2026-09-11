---
title: "cli: bdgd-light replay — reconstruir um evento a partir do log auditado"
labels: area:agent, area:cli, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
O log de auditoria é encadeado por hash e registra evento, chamadas de ferramenta, veredito do
verificador, aprovação humana e execução. Hoje ninguém consegue **usar** isso: não há comando que
leia o log e mostre o que aconteceu. Para um COD real, a capacidade de reconstruir e conferir a
cadeia é o que separa "log" de "auditoria".

## Tarefa
- `bdgd-light replay <id-do-evento>`: lê `data/audit/*.jsonl` e imprime a linha do tempo do evento —
  evento injetado, ferramentas chamadas na ordem, opções avaliadas com o score, veredito do
  verificador (gates que passaram e falharam), rejeições e replanejamentos, aprovação (quem e
  quando) e execução.
- `--verificar-cadeia`: recalcula o encadeamento de hash e diz se o log está íntegro, apontando o
  primeiro registro divergente se não estiver.
- `--json` para saída estruturada; sem flag, texto legível em pt-BR.
- Teste: gerar um evento completo com `--provider fake`, rodar o replay e conferir que a linha do
  tempo bate; teste negativo adulterando um registro e conferindo que `--verificar-cadeia` acusa.
- Uma linha em `docs/demo-profissional.md`: depois de aprovar a manobra, rodar o replay é a resposta
  para "como vocês provam o que o agente fez?".

## Critérios de aceite
- [ ] `replay` imprime a linha do tempo completa de um evento gerado na hora.
- [ ] `--verificar-cadeia` acusa adulteração no teste negativo.
- [ ] Documentado em `docs/comandos.md`.
