---
title: "twin: spike bdgd2opendss + OpenDSSDirect em um alimentador"
labels: area:twin, phase:F2, copilot, spike
milestone: F2 Grafo + gêmeo
---
## Tarefa
Validar o caminho BDGD → OpenDSS:
- Adicionar `bdgd2opendss` e `opendssdirect.py` ao extra `twin` e criar `bdgd_light.twin.convert`
  (`bdgd-light dss --gdb <path> --ctmt <COD_ID> --out data/dss/<COD_ID>/`) que chama o `bdgd2opendss`
  para gerar o modelo `.dss` do alimentador.
- Criar `bdgd_light.twin.powerflow` com `run_powerflow(master_dss) -> PowerFlowResult` (convergiu?,
  tensões por barra em pu, perdas, corrente por trecho, violações fora de 0,93–1,05 pu) usando OpenDSSDirect.
- Notebook/relatório `docs/spike-opendss.md` com o que funcionou, o que faltou na BDGD e o tempo de execução.

## Critérios de aceite
- [ ] Teste unitário com um circuito OpenDSS mínimo (IEEE 13 barras, arquivos em `tests/fixtures/dss/`) que
  roda `run_powerflow` e verifica convergência.
- [ ] Comando documentado; PR descreve o comando que o mantenedor deve rodar com a BDGD real.
