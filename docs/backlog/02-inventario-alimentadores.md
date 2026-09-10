---
title: "ingest: inventário de alimentadores (CTMT) para escolha do escopo"
labels: area:ingest, phase:F1, copilot
milestone: F1 Dados + mapa
---
## Contexto
Vamos trabalhar com 2–3 alimentadores da Light. Precisamos de um relatório para escolher os mais
interessantes para um cenário FLISR (chaves NA para transferência de carga, DER, densidade de clientes).

## Tarefa
Criar `bdgd-light inventario --parquet data/parquet --out data/inventario_ctmt.csv` que produz, por CTMT:
`COD_ID`, nome, subestação (coluna `SUB` do CTMT, nome via UNTRAT), tensão nominal, km de rede MT (soma de comprimento SSDMT), nº de
transformadores (UNTRMT), potência instalada (kVA), nº de UCBT e UCMT, energia anual (soma ENE_01..ENE_12
das tabelas UCBT_tab/UCMT_tab), nº de chaves UNSEMT total / NA / NF, nº de UGBT+UGMT (DER), nº de reguladores e capacitores,
e o bbox em EPSG:4326. Também um `--top 20` que imprime tabela ordenada por um score simples
(chaves NA × clientes) e um `--bairro` opcional que filtra por interseção com um polígono GeoJSON.

Depende de #1 (export).

## Critérios de aceite
- [ ] CSV e tabela no terminal.
- [ ] Testes com fixture sintética (2 alimentadores).
- [ ] Documentar no README o significado de cada coluna e as colunas da BDGD usadas.
