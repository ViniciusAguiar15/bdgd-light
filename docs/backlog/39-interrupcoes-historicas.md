---
title: "ingest: histórico real de interrupções da Light (ANEEL, 2017–2026)"
labels: area:ingest, area:docs, phase:F5, copilot
milestone: F5 Operação colaborativa
---
## Contexto
A ANEEL publica **todas as interrupções** ocorridas nas redes de distribuição, por ano, com precisão
de hora/minuto/segundo, conjunto elétrico, causa, tipo (programada ou não) e unidades consumidoras
atingidas. É o dado que o projeto nunca teve: até hoje, tudo que envolve tempo é premissa.

Fonte: `https://dadosabertos.aneel.gov.br/dataset/interrupcoes-de-energia-eletrica-nas-redes-de-distribuicao`
(recursos por ano, ZIP e Parquet; há dicionário de dados em PDF — seguir o dicionário, não adivinhar
nome de coluna). Atualização mensal, cobertura 2017–2026.

## Tarefa
- `scripts/baixar_interrupcoes.py`: download parametrizado por ano para `data/interrupcoes/`
  (fora do git), resumível, registrando a data de extração.
- `src/bdgd_light/ingest/interrupcoes.py`: filtrar Light (distribuidora 382) e os conjuntos
  presentes no recorte; normalizar duração (min), causa, tipo e UC atingidas.
- `docs/interrupcoes-light.md`, gerado por script, com:
  - distribuição da **duração** das interrupções não programadas: p50, p90, p99, por conjunto e por
    causa — este é o número que hoje é chutado como 180 min;
  - frequência de interrupções por conjunto e por ano, normalizada por UC;
  - mix de causas e o peso de cada tipo;
  - os conjuntos dos três clusters (Tijuca, Ipanema, Taquara) comparados com o resto da Light.
- Seção final: o que esse dado permite afirmar sobre a escolha dos clusters — se eles são típicos
  ou atípicos em frequência e duração. Se forem atípicos, escrever isso.

## Critérios de aceite
- [ ] Download reprodutível e `data/` fora do git.
- [ ] Distribuição de duração por conjunto e causa, versionada em CSV agregado.
- [ ] Comparação dos clusters com a base inteira, com a conclusão escrita.
