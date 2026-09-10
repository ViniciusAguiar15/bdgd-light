# Escopo geográfico: alimentadores escolhidos

**Versão 2 (2026-09-09, após o inventário da issue #2).** A versão 1 escolhia o cluster PDG (MENEZES/XINGU/DANTAS);
o inventário mostrou que as interligações telecomandadas entre eles eram todas **disjuntores dentro da SE**
(`EM_SUB = True`), não chaves de campo — ou seja, não servem para transferência de carga num FLISR.
A escolha abaixo usa só interligações de campo.

## Método
- Interligação (tie) = chave `UNSEMT` normalmente aberta (`P_N_OPE = "A"`) a até 2 m de uma extremidade de
  `SSDMT` de **outro** CTMT (`ingest/interligacoes.py`); os `PAC` são numerados por alimentador, então não há
  ligação topológica entre CTMT, só geométrica. Chaves dentro de polígono `SUB` são descontadas.
- Priorizado: município do Rio (`MUN = 3304557`), rede aérea (`LDA`), 13,2 kV nominal (`TEN_NOM = 46`),
  três alimentadores **mutuamente** interligados por chaves de campo, com pelo menos uma telecomandada
  (`TLCD = 1`) em cada par.
- Na Light 2025: 5.031 chaves NA de interligação; 381 dentro de SE; 4.650 de campo, das quais 659 telecomandadas.
  Só **dois** trios aéreos no Rio fecham triângulo com ties telecomandadas de campo em todos os pares.

## Escolha: cluster TQR — SETD Taquara (Jacarepaguá)

| CTMT | nome | km MT | MWh/ano | UCBT | DER | trafos | chaves MT | telecom. |
|---|---|---|---|---|---|---|---|---|
| **TQR0007** | LDA PARNAIBA | 16,5 | 23.886 | 6.268 | 118 | 82 | 50 | 7 |
| **TQR33859** | LDA CURUMAU | 18,0 | 27.156 | 5.885 | 124 | 99 | 54 | 7 |
| **TQR33862** | LDA BOCARI | 12,2 | 20.509 | 4.351 | 199 | 82 | 58 | 6 |

Interligações de campo entre eles: PARNAIBA–BOCARI **8** (2 telecomandadas), CURUMAU–BOCARI **7** (1),
PARNAIBA–CURUMAU **2** (1). Total 17 ties, 4 telecomandadas. Mesma subestação (fonte única no OpenDSS).
Bbox 4326 aproximado: lon −43,450 a −43,373; lat −22,932 a −22,905 (Taquara / Curicica / Freguesia).

Cenário FLISR de referência: falta em BOCARI (`TQR33862`), que tem duas rotas de restauração telecomandadas
(por PARNAIBA e por CURUMAU) — o agente compara as duas no OpenDSS.

**Métricas de decisão (MVP): MT, não BT.** O gêmeo OpenDSS reproduz fielmente ramais de ligação (`RAMLIG.COMP`)
de 700–900 m em 220 V cadastrados na BDGD, que derrubam a BT abaixo de 0,5 pu em algumas pontas e geram as
sobrecargas reportadas; são dado suspeito, não erro de conversão (`docs/spike-opendss.md`). O veredito de uma
manobra usa tensão MT (0,93–1,05 pu) e corrente no disjuntor/tronco (`twin.score_eletrico`, issue #18).

## Alternativa: cluster BMT/CBI — SETD Boca do Mato + SETD Cachambi (Méier)
`BMT0001` LDA DEPAIVA (6,5 km, 17 chaves telecomandadas), `BMT29737` LDA AVEMAR (5,3 km), `CBI33798` LDA RABELO
(5,8 km). 10 ties de campo (3 telecomandadas), **duas subestações** — menor e mais rápido no OpenDSS, e mostra
transferência entre SEs. Bom segundo cenário se o TQR ficar pesado.

## Histórico
- v1: PDG29724 MENEZES / PDG33499 XINGU / PDG29731 DANTAS (SE 10385916). Descartado: ties entre eles são
  disjuntores de SE; as ties de campo de cada um vão para outros CTMT (PDG33651, PDG29776, PDG29820).
