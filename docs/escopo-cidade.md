# Escopo v3 — panorama da cidade do Rio e opções por bairro

Análise (2026-09-10) sobre `data/inventario_ctmt.csv` + interligações **de campo** (fora de SE), agrupando os
1.405 alimentadores do município por proximidade a bairros de referência. Números: n = alimentadores,
LDA = aéreos, LDS = subterrâneos, ties = interligações de campo telecomandadas.

| região | n | LDA | LDS | km mediana | UCBT mediana | ties TLCD | leitura |
|---|---|---|---|---|---|---|---|
| Centro | 203 | 3 | 197 | 2,7 | 142 | 15 | rede subterrânea **reticulada** (malha secundária, network protectors); não é cenário de FLISR por chaves |
| Ipanema/Leblon | 76 | 1 | 75 | 3,2 | 972 | **141** | subterrânea **radial com telecontrole** — ótima para self-healing subterrâneo |
| Botafogo/Humaitá | 45 | 0 | 45 | 2,9 | 1.091 | 6 | subterrânea, poucas ties de campo |
| Copacabana/Leme | 38 | 1 | 37 | 3,3 | 1.664 | 0 | subterrânea, sem ties de campo telecomandadas |
| Flamengo/Catete | 27 | 0 | 27 | 3,5 | 1.584 | 6 | idem Botafogo |
| Lapa/Glória | 36 | 1 | 35 | 3,5 | 456 | 10 | subterrânea |
| Laranjeiras/Cosme Velho | 16 | 7 | 9 | 5,9 | 1.965 | 17 | mista; LDS 34707 com 20 chaves telecomandadas |
| Tijuca | 37 | 24 | 13 | 3,6 | 2.197 | 25 | **aérea densa**, várias SEs vizinhas, estrelas de ties |
| Vila Isabel/Grajaú | 24 | 18 | 6 | 5,0 | 3.474 | 15 | aérea, triângulo na SE Leopoldo |
| Méier | 61 | 57 | 0 | 5,2 | 3.237 | 56 | aérea, 18 estrelas, único triângulo aéreo completo da cidade consolidada |
| Jacarepaguá/Taquara | 27+ | 23 | 0 | 9,7 | 3.821 | 40 | aérea suburbana, alimentadores longos (cluster TQR atual) |
| Barra / Recreio | 74 | 30 | 44 | 7–12 | ~1.000–3.700 | 64 | mista, alimentadores muito longos (até 22 km) |

## Recomendação: dois clusters, dois cenários

**Cenário A — FLISR aéreo (principal): Tijuca, SE Aldeia Campista.** Centro da estrela `ALC9925` LDA CABOFRIO
(4,2 km, 4.036 UCBT, 4 chaves telecomandadas) com tie telecomandada para três vizinhos de **três subestações**:
`ALC9946` RIMARAES (Aldeia Campista, 3,3 km), `URG29983` AMALIA (SE Uruguai, 6,1 km, 54 DER) e `RCP9882`
BOMPASTOR (SE Rio Comprido, 6,8 km, 5.824 UCBT). Falta em CABOFRIO → três rotas de restauração, cada uma por outra
SE: é o cenário mais rico para o agente comparar no OpenDSS, num bairro que todo aluno reconhece (Praça Saens Peña,
Conde de Bonfim). Cluster: `ALC9925,ALC9946,URG29983,RCP9882`.

**Cenário B — self-healing subterrâneo (Zona Sul): Ipanema, SE Posto Seis.** `PTS0001` LDS 9210 (3,4 km, 1.730 UCBT,
**63 chaves, 48 telecomandadas**) com 3–4 ties telecomandadas para cada vizinho `PTS9088`, `PTS9924`, `PTS4022`,
`PTS9297`. Mostra que a mesma arquitetura opera rede subterrânea radial telecomandada — o "outro Rio". Cluster:
`PTS0001,PTS9088,PTS9924,PTS4022`. Ressalva: PTS4022/PTS9297 têm 0 UCBT (circuitos expressos/reserva); o OpenDSS
precisa tratá-los como fonte sem carga.

**Alternativas aéreas:** Vila Isabel (SE Leopoldo: `LPD29168` AQUINO, `LPD29145` ISAQUITA, `LPD33251` CONDEBEL —
triângulo 5+2+3 ties, 2 telecomandadas); Méier (`BMT0001,BMT29737,CBI33798`, único triângulo aéreo com tie
telecomandada em todos os pares).

**Centro / Botafogo / Flamengo / Copacabana:** rede reticulada. Fica como **cenário C futuro** (contingência N-1 de
alimentador na malha), que exige modelagem diferente (network protectors) e não entra no MVP.

**Cluster TQR (Taquara):** continua como rede de regressão/benchmark (já convertida, testada e nos exemplos), mas
sai da demo.
