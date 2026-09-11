---
title: "docs: resultados consolidados gerados a partir dos CSVs do benchmark"
labels: area:bench, area:docs, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
Os números do projeto estão espalhados por `docs/bench/*.csv`, `docs/bench.md`, `docs/escopo-cidade.md`
e as revisões. Para a apresentação e a dissertação falta uma página só, com os números atuais, e que
não seja digitada à mão (número digitado à mão envelhece e ninguém percebe).

## Tarefa
- `scripts/gerar_resultados.py`: lê os CSVs de `docs/bench/` e os inventários do recorte e escreve
  `docs/resultados.md` com: tamanho do recorte (alimentadores, trechos, chaves, clientes por
  cenário), ties detectados antes/depois da folga `EM_SUB`, tabela por provedor (pass@1 por nível,
  pass@k, ordenação, tokens, US$/execução, s/execução), os 3 cenários ponta a ponta e a taxa de
  reprovação do verificador.
- Cada número com a fonte (arquivo + data da rodada) na própria tabela.
- Alvo `make resultados` (ou comando documentado) e nota em `docs/comandos.md`.
- Nada de valor escrito no texto que não venha do script — se um número não sai dos dados, ele não
  entra.

## Critérios de aceite
- [ ] `docs/resultados.md` gerado pelo script, com data de geração e as fontes por linha.
- [ ] Rodar o script duas vezes não muda o arquivo (saída determinística).
- [ ] Suíte verde; o script tem teste com CSV sintético.
