---
title: "metrics: trocar a premissa de 180 min pela distribuição medida de tempo de reparo"
labels: area:agent, area:console, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
Hoje o impacto estimado usa `tempo_reparo_min = 180` como premissa fixa, explicitada na tela — foi a
decisão certa enquanto não havia dado. Com a #39, passa a haver: a distribuição real de duração das
interrupções não programadas da Light, por conjunto e por causa. Premissa arbitrária vira parâmetro
medido, e o número na tela deixa de ser um chute bem rotulado.

**Depende da #39.** Se a #39 não tiver concluído, pule esta e siga a fila.

## Tarefa
- Carregar a distribuição medida (p50/p90 por conjunto, com fallback para a distribuição da Light
  inteira quando o conjunto tiver amostra pequena — definir e documentar o corte, ex.: n < 30).
- O impacto passa a ser reportado como **faixa**, não ponto: consumidor-minutos e DEC calculados com
  p50 e p90, no formato "≈ X a Y" — porque a incerteza é real e esconder isso é pior que mostrar.
- A tela e a doc dizem a origem: "premissa de reparo: mediana 96 min / p90 240 min, medidos em N
  interrupções do conjunto Z entre 2017 e 2026" (números de exemplo). Se o fallback for usado, a
  tela diz que é a distribuição da Light, não a do conjunto.
- Manter a possibilidade de sobrescrever o tempo manualmente (o operador sabe algo que o histórico
  não sabe) — e, nesse caso, rotular como premissa do operador.
- `docs/grid-modelo.md` atualizado: de onde vem o número, qual a amostra, e o que continua sendo
  hipótese (que o reparo desta falta se pareça com os anteriores daquele conjunto).

## Critérios de aceite
- [ ] Impacto em faixa (p50–p90) no console, na CLI e no MCP.
- [ ] Origem e tamanho da amostra visíveis para quem lê o número.
- [ ] Nenhum lugar afirma DEC realizado; continua sendo impacto estimado de um evento.
