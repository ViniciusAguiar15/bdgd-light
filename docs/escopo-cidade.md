# Escopo v3 — panorama da cidade do Rio e opções por bairro

> **Tabela por região desatualizada para ties de SE.** Os números de "ties TLCD" abaixo foram calculados
> antes da folga `EM_SUB` de 50 m (PR #37): chaves NA no pátio da SE (barras não modeladas) ainda contam
> como ties de campo — Ipanema/Leblon, por exemplo, tinha 35/36 assim no LDS 9210. Regeneração do
> inventário e da tabela: #39.

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

## v3.1 — o que os dados mostraram ao construir os clusters

Recorte, grafo, gêmeo OpenDSS e tiles dos dois clusters foram gerados (backlog 09, issue #30). Comandos, por
cluster, em `README.md` ("Clusters da demo"); resultados abaixo (BDGD 2025-12-31, dia útil de janeiro, DU01).

| cluster | CTMT | feições | nós MT / km / chaves (grafo) | ties de campo (TLCD) | clientes | fluxo base DU01 | perdas | V MT (pu) | tempo |
|---|---|---|---|---|---|---|---|---|---|
| A Tijuca | ALC9925, ALC9946, URG29983, RCP9882 | 29.331 | 1.662 / 20,4 / 148 | 23 (5) | 16.248 UCBT, 235 trafos (31,6 MVA) | 13.286 kW / 6.256 kvar (4.094 + 2.715 + 3.134 + 3.343) | 839 kW (6,3 %) | 1,036–1,045 | 6 it., 2,5 s |
| B Ipanema | PTS0001, PTS9088, PTS9924, PTS4022 | 13.249 | 1.838 / 15,5 / 95 | 1 (0) — 74 interligações `EM_SUB` | 4.720 UCBT, 33 trafos (14,0 MVA) | 7.803 kW / 3.832 kvar (2.802 + 2.560 + 1.155 + 1.285) | 537 kW (6,9 %) | 1,041–1,045 | 7 it., 0,6 s |

(OpenDSS: Tijuca 10.029 barras / 32.132 cargas / 283 trafos; Ipanema 6.990 barras / 9.272 cargas / 33 trafos.
Como em TQR, a BT herda ramais suspeitos da BDGD e tem nós abaixo de 0,5 pu — o veredito é sempre MT.)

**Cenário A (Tijuca) confirmado nos dados.** Falta no trecho `11304252` (tronco de `ALC9925` CABOFRIO) → isolar
abrindo `10927447` e `11035901` → 315 nós, **4.036 UCBT, 6 UCMT, 63 trafos (8.960 kVA)** ficam restauráveis por
qualquer uma de **três SEs**. O gêmeo ranqueia as opções:

| restaurar por | fonte que absorve | perdas | V MT mín (ALC9925 / vizinho) | leitura |
|---|---|---|---|---|
| `974020904` → ALC9946 RIMARAES (mesma SE) | 6.793 kW | 876 kW (6,6 %) | 1,027 / 1,030 | melhor opção |
| `746851189` → RCP9882 BOMPASTOR (SE Rio Comprido) | 7.395 kW | 893 kW (6,7 %) | 1,018 / 1,024 | viável |
| `977361689` → URG29983 AMALIA (SE Uruguai) | 7.177 kW | 902 kW (6,8 %) | 1,014 / 1,021 | viável, pior tensão |

(Estado "falta sem restauração": 9.192 kW, 4.838 nós a 0 pu.) Exemplo no console: `?cenario=tijuca`.

**Ranking elétrico do verificador (`twin.score_eletrico`, PR #42)** — o fluxo por opção, com corrente no
disjuntor da fonte receptora e carregamento dos condutores MT no perímetro transferido, muda a leitura acima:

| opção | I disjuntor / nominal | margem | V MT mín | veredito |
|---|---|---|---|---|
| ALC9946 RIMARAES | 320 A / 592 A | **46 %** | 1,027 | viável — melhor |
| RCP9882 BOMPASTOR | 351 A / 438 A | **20 %** | 1,018 | viável |
| URG29983 AMALIA | — | — | 1,014 | **inviável**: o trecho `11051956` (20 m, condutor `456027629_43_3`, CNOM 132 A) no caminho até a tie vai a **180 %** de carregamento |

O score topológico (clientes/perdas/tensão de barra) não enxerga o gargalo; o elétrico enxerga — é o argumento
"verificador determinístico por cima do LLM" da demo. **Pergunta aberta:** o condutor fino em `11051956` é
cadastro (erro na BDGD) ou restrição real? Se for real, AMALIA só serve com transferência parcial; se for
cadastro, é exatamente o tipo de inconsistência que o gêmeo ajuda a apontar. Reprodução:
`uv run bdgd-light grafo --gpkg data/feeders/cluster_tijuca.gpkg --falha 11304252 --score`.

**Cenário B (Ipanema) não é reprodutível literalmente — vira cenário *negativo*.** As 35 chaves NA de `PTS0001` e
as ties "3–4 por vizinho" da tabela acima são o **pátio de manobra da SE Posto Seis** (PACs `PTSTSL42/43_MT_*`, a
12–40 m do polígono `SUB`, 492 m²), não interligações de campo: nenhuma delas aparece em `SSDMT` de nenhum CTMT da
BDGD inteira, e o lado "de fora" coincide geometricamente com a cabeceira dos vizinhos. Consequências:

- `detectar_interligacoes` passou a marcar `EM_SUB` com folga de 50 m ao redor do polígono da SE
  (`raio_sub_m`, antes era `within` estrito); com isso as 74 interligações de `PTS0001` ficam `EM_SUB=True` e o
  grafo (que ignora ties na SE por padrão) não tem opção de restauração para nenhuma zona de PTS0001/PTS9088/PTS9924.
- O cenário B da demo é: falta no trecho `11409068` (tronco de `PTS0001`, 144 m da SE) → abrir `10933610`
  (disjuntor), `505111870` e `561826961` → zona isolada de 298 nós / 1.251 UCBT; 15 nós / 479 UCBT desligados e
  **"nenhuma chave NA restaura"** — o agente deve reconhecer a ausência de opção e recomendar despacho de equipe
  (ou manobra na SE, fora do escopo do MVP). No gêmeo, PTS0001 vai a 0 kW (8.624 nós a 0 pu) e os vizinhos
  seguem em 1,041–1,045 pu. Exemplo no console: `?cenario=ipanema`.
- `PTS4022` (0 UCBT, só `CargasMT`: 1.285 kW de UCMT) exigiu que o Master do cluster aceitasse circuito sem
  `CargasBT`.

**Bugs encontrados e corrigidos no caminho** (detalhes em `docs/review/NOITE-2.md`): (1) ties de anel interno
com chave NA ambígua (`757513244`, `977464757`) atravessavam a chave aberta no grafo — corrigido em
`grid/rede.py`; (2) o bdgd2opendss escreve bancos de unidades monofásicas (`TIP_TRAFO=DF`, 24 em Tijuca) como
trifásicos com barras de 2 nós, o que aterrava um vértice do delta (perdas 64 %, 0,2 pu) — corrigido por
pós-processamento em `twin/convert.py` (`corrigir_bancos_monofasicos`). TQR não tem nenhum dos dois casos, por
isso passou despercebido na v2.
