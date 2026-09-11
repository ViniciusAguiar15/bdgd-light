---
title: "agent: a GD muda a decisão de restauração?"
labels: area:agent, area:twin, area:bench, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
Pergunta de operação real, e boa para a dissertação: a GD **não** sustenta a rede durante a falta
(por regulação, o inversor desconecta na ausência de tensão), mas ela muda o carregamento do
alimentador **socorredor** no momento da manobra — se a transferência acontece ao meio-dia, a carga
que o socorredor precisa absorver é menor do que à noite. Hoje o score elétrico ignora isso.

## Tarefa
- Rodar as opções de restauração dos três cenários e de 3 alimentadores de alta penetração (#35) em
  dois instantes: meio-dia com GD plena e ponta da noite sem GD.
- Medir, por opção: margem no disjuntor do socorredor, Vmin/Vmax MT, viabilidade — e **se a opção
  vencedora muda** entre os dois instantes.
- Escrever a conclusão em `docs/gd-restauracao.md` com a formulação correta: a GD não restaura, mas
  pode mudar qual socorro é viável, e em quais alimentadores isso já acontece na base de hoje.
- Se a opção vencedora mudar em algum caso, abrir issue de acompanhamento propondo que o horário do
  evento entre como premissa explícita do score (não implementar aqui).

## Critérios de aceite
- [ ] Tabela por cenário e instante, versionada.
- [ ] Afirmação explícita sobre ilhamento: a GD não é contada como fonte durante a falta.
- [ ] Conclusão escrita mesmo que seja "não muda nenhuma decisão na base atual".
