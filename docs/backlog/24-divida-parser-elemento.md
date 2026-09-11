---
title: "refactor: um único parser de nome de elemento OpenDSS"
labels: area:twin, area:console, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
`_cod_id_trecho` (`twin/score.py`), `_cod_id_elemento_mt` (`mcp_server/sessao.py`) e
`_cod_id_trecho_de_elemento` (`console/api.py`) fazem a mesma coisa: extrair o COD_ID de
`line.smt_<id>`. Se o conversor mudar o prefixo, três lugares quebram e só um vai ser lembrado.

## Tarefa
- Uma função só, ao lado de onde o nome é **gerado** (`twin/gpkg2dss.py`), com o prefixo em
  constante compartilhada; os três chamadores passam a importá-la.
- Teste que amarra geração e leitura: gerar o nome a partir de um COD_ID e recuperá-lo de volta
  (round-trip), para o teste quebrar se alguém mudar só um dos lados.
- Varrer o repo por outras cópias do mesmo padrão (`line.`, `smt_`) e trazer para a função.

## Critérios de aceite
- [ ] `grep -rn "smt_" src/` mostra o prefixo definido em **um** lugar só.
- [ ] Teste de round-trip passando; suíte verde.
