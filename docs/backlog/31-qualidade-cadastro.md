---
title: "ingest: perfil de qualidade do cadastro da BDGD Light 2025"
labels: area:ingest, area:docs, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
Várias decisões do projeto nasceram de anomalias do cadastro descobertas por acidente: `PN_CON`
apontando para postes a dezenas de km, `FAS_CON = AN` em massa, `RAMLIG` acima de 300 m, chaves de
pátio de subestação contadas como interligação. Falta medir isso de forma sistemática — hoje são
anedotas, e anedota não entra em dissertação.

## Tarefa
- `scripts/qualidade_bdgd.py`, rodando sobre a base inteira da Light (não só os clusters), com uma
  verificação por anomalia, cada uma reportando **contagem, percentual e 5 exemplos de COD_ID**:
  1. `FAS_CON` por camada e por alimentador (distribuição; concentração de monofásico)
  2. `RAMLIG` com comprimento acima de 300 m (e o percentil 99 do comprimento)
  3. `PN_CON` de UCBT/UCMT a mais de 2 km do transformador da UC
  4. trechos sem `TIP_CND` correspondente em SEGCON
  5. `CTMT` referenciado por feições mas ausente da camada CTMT (e o inverso)
  6. PACs que aparecem em mais de um alimentador
  7. geometria inválida ou vazia, por camada
  8. coordenadas fora da bbox do município/área de concessão
  9. chaves com `TLCD` nulo/indefinido
- `docs/qualidade-bdgd.md` gerado pelo script (determinístico, com data-base das fontes), com uma
  seção final "perguntas para a distribuidora" listando o que o dado sozinho não decide.

## Critérios de aceite
- [ ] Relatório gerado por script, sem número digitado à mão.
- [ ] Cada anomalia com contagem, percentual, exemplos e o impacto no pipeline (ou "nenhum").
- [ ] A seção de perguntas para a Light sai pronta para ser enviada.
