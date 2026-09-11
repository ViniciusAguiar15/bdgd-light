# Grafo do alimentador — mapeamento BDGD → `bdgd_light.grid`

Como o recorte de um alimentador (`bdgd-light recortar`, issue #3) vira um `networkx.Graph` com
estado de chaves (issue #6), o que foi medido na BDGD da Light 2025 para decidir cada regra e o que
ficou de fora. Regras de junção entre camadas em [`bdgd-relacoes.md`](bdgd-relacoes.md).

## Em uma frase

**Nós são os PAC de média tensão; arestas são trechos `SSDMT`, chaves `UNSEMT` e interligações
(`INTERLIGACOES`); a fonte é o PAC do disjuntor de saída da SE; clientes ficam pendurados no nó MT do
transformador.** A rede BT não entra no grafo.

```
CTMT.PAC_INI ──[UNSEMT NF: disjuntor]── PAC ──[SSDMT]── PAC ──[UNSEMT NF]── PAC ──[SSDMT]── … ──[UNSEMT NA: tie]── PAC_VIZ (outro CTMT)
     fonte                                       │
                                            UNTRMT.PAC_1 → UCBT_tab (UNI_TR_MT), UCMT_tab (PAC)
```

## Nós

| nó | origem | atributos |
|---|---|---|
| PAC MT (`<CTMT>_MT_<n>`) | `SSDMT.PAC_1/PAC_2`, `UNSEMT.PAC_1/PAC_2`, `UNTRMT.PAC_1`, `CTMT.PAC_INI` | `ctmt`, `tipo="pac"`, `x`/`y` (EPSG:4674, do vértice da geometria do trecho) |
| externo (`EXT:<CTMT>`) | vizinho referenciado em `INTERLIGACOES` mas **não carregado** no grafo | `tipo="externo"`, `ctmt` — tratado como fonte sempre energizada |

Na Light os PAC são numerados por alimentador e **nenhum PAC de `SSDMT` aparece em dois CTMT**
(1,0 M de linhas); o grafo interno usa o PAC como chave de nó sem risco de colisão. Os números depois
de `_MT_` são globais: o par de uma tie `TQR0007_MT_583748 ↔ TQR33859_MT_583748` é o mesmo ponto
físico registrado com o prefixo de cada CTMT (4.540 de 5.833 ties têm essa coincidência).

Trechos sem `PAC_1`/`PAC_2` (ou com `PAC_1 == PAC_2`) são ignorados com aviso em `Rede.avisos`; na
Light 2025 não há nenhum. Não há par (PAC_1, PAC_2) repetido entre `SSDMT` e `UNSEMT`, então basta um
`nx.Graph` simples (sem multi-arestas).

## Arestas

| `tipo` | origem | atributos | passa corrente? |
|---|---|---|---|
| `trecho` | `SSDMT` (uma por linha) | `cod` (`COD_ID`), `ctmt`, `comp` (m, coluna `COMP`), `tip_cnd` (→ `SEGCON`) | sempre |
| `chave` | `UNSEMT` (uma por linha) | `cod`, `ctmt`, `normal` (`NA`/`NF` de `P_N_OPE`: `A` → NA, `F` → NF), `aberta` (estado atual), `tlcd` (`TLCD == 1`), `tip_unid`, `externa` | se `aberta == False` |
| `tie` | `INTERLIGACOES` | `chave` (COD_ID da chave NA), `ctmt`, `ctmt_viz`, `dist_m` | sempre (impedância zero, geométrica) |

Orientação: `PAC_1` ↔ primeiro vértice e `PAC_2` ↔ último vértice da geometria (verificado; dispersão
máxima 5 m, 23 de 1.606 nós com > 1 m no cluster TQR). A geometria só serve para dar `x`/`y` ao nó e
para o fallback da fonte; a conectividade vem inteiramente dos PAC.

Nos disjuntores e chaves em série `PAC_1` é o lado da fonte. Essa convenção é usada para decidir qual
ponta de uma tie está "do lado de fora" quando a informação não é conclusiva (ver abaixo).

## Fonte (nó energizado de partida)

`CTMT.PAC_INI` é **sempre** o `PAC_1` de uma `UNSEMT` (1.802 de 1.802 CTMT) e **nunca** um PAC de
`SSDMT`: é o barramento da SE, e a chave que sai dele é o disjuntor de saída (`TIP_UNID = 29` na
maioria). Em TQR0007, `PAC_INI = TQR0007_MT_52737` é o `PAC_1` do disjuntor `358368825` (NF, TLCD),
cujo `PAC_2` (`TQR0007_MT_52738`) já é um PAC de `SSDMT`. 151 CTMT têm várias chaves partindo do
mesmo `PAC_INI` (até 53 — baias do barramento); todas ficam ligadas ao nó-fonte.

Regra: `fonte[CTMT] = PAC_INI` se ele estiver no grafo. Se não estiver (dados incompletos, fixture
`RJO003`), a fonte passa a ser o PAC de `SSDMT` daquele CTMT mais próximo do polígono da `SUB` (o primeiro PAC
em ordem alfabética se não houver camada `SUB` ou geometria), com aviso em `avisos`.

## Interligações (ties)

A camada `INTERLIGACOES` do recorte (issue #2/#3) já tem, para cada chave NA de interligação, o CTMT
dono, o `PAC_VIZ` (PAC do `SSDMT` vizinho a ≤ 2 m) e o `CTMT_VIZ`. O grafo cria uma aresta `tie`
entre a **ponta de fora** da chave e o vizinho:

1. **Ponta de fora** = o PAC da chave que **não** está no conjunto de PAC de `SSDMT` do CTMT dono
   (4.959 de 5.833 ties têm exatamente um PAC solto). Se os dois estão na própria rede (90 casos:
   ambíguo) ou nenhum está (784, das quais 634 dentro da SE), usa-se `PAC_2` por convenção (`PAC_1` é
   o lado da fonte), com aviso no primeiro caso. **Tie ambígua** (os dois PAC na própria rede) é
   tipicamente uma chave NA de anel interno que também encosta num vizinho: a aresta `tie` recebe
   `via_chave=<cod>` e só é atravessável com a chave **fechada** (`tie_switches()` tem a coluna
   `ambigua`); antes, o grafo passava pela tie e contornava a chave aberta — com isso a zona da falta
   "vazava" para o anel e `restore_options` sugeria transferir carga já energizada (Tijuca:
   `757513244` RCP9882→RCP33308 e `977464757` URG29983→URG30000).
2. **Vizinho carregado** (`Cluster`): a tie liga a ponta de fora ao `PAC_VIZ` real. A rede do vizinho
   fica conectada de verdade e uma transferência de carga aparece como energização vinda de outra
   fonte (`energized_by`).
3. **Vizinho não carregado** (`Feeder`, ou CTMT fora do cluster): a tie liga a ponta de fora ao nó
   `EXT:<CTMT_VIZ>`, que é uma fonte sempre energizada. Assim `restore_options` enxerga a alternativa
   mesmo num alimentador sozinho — sem saber, claro, quanta carga o vizinho já tem (`clientes_fonte`
   fica vazio e a CLI mostra `?`).
4. **Chave do vizinho** que encosta na nossa rede (a `UNSEMT` do recorte só tem as chaves cadastradas
   no CTMT; as do vizinho estão em `INTERLIGACOES`): entra como aresta `chave` com `externa=True`
   entre o nosso `PAC_VIZ` e `EXT:<dono>` (ou, num `Cluster` em que o dono está carregado, é a chave
   normal dele + tie). Se a mesma chave externa toca mais de um PAC nosso, vale o mais próximo
   (`DIST_M`), com aviso.
5. **Chaves dentro da SE** (`EM_SUB = True`) são ignoradas por padrão (`ties_na_se=False`): são
   disjuntores/baias do barramento e não transferem carga em campo — a mesma regra do inventário
   (`NA_interligacao_campo`) e de `vizinhos --sem-se`. `EM_SUB` considera uma folga de 50 m ao redor do
   polígono `SUB` (`detectar_interligacoes(raio_sub_m=…)`): o pátio da SE Posto Seis (Ipanema) tem 35
   chaves NA de transferência de barra a 12–40 m do polígono cadastrado, todas sem `SSDMT` — não são
   ties de campo (`docs/escopo-cidade.md`, v3.1).

Números no cluster TQR (PARNAIBA / CURUMAU / BOCARI): 2.069 nós, 1.924 trechos (46,65 km), 162
chaves, 35 ties (12 de chaves de CTMT fora do cluster, 7 CTMT externos), 2.068 nós energizados (o
único sem tensão é um PAC solto de chave). Cada CTMT é alimentado só pela própria fonte no estado
normal — nenhuma chave NF fecha um caminho entre dois alimentadores.

## Clientes

| camada | ligação | nó do grafo | contribui com |
|---|---|---|---|
| `UNTRMT` | `PAC_1` (lado MT; sempre em `SSDMT` do próprio CTMT — 99.490 de 99.490) | `PAC_1` | `trafos`, `kva` (`POT_NOM`) |
| `UCBT_tab` | `UNI_TR_MT` → `UNTRMT.COD_ID` | `PAC_1` do transformador | `ucbt` |
| `UCMT_tab` | `PAC` (é um PAC MT) | `PAC` | `ucmt` |

`Clientes` (dataclass `ucbt`, `ucmt`, `trafos`, `kva`) soma por nó; `customers(nos)`,
`customers_downstream(no)`, `Isolamento.clientes_*` e `OpcaoRestauracao.clientes*` usam a mesma
estrutura. UC cujo transformador ou PAC não está na rede MT geram aviso (1 UCMT no cluster TQR).

A rede BT (`SSDBT`, `UNSEBT`, `RAMLIG`) **não entra no grafo**: é radial por transformador e não muda
a análise de manobras MT. No gêmeo OpenDSS ([spike-opendss.md](spike-opendss.md)) o bdgd2opendss a
modela por completo (segmentos, ramais e uma carga por UC), e é nela que aparecem as violações de
tensão. `PAC_2`/`PAC_3` do `UNTRMT` (lado BT, `<UNTRMT>_BT_<n>`) são ignorados aqui.

## Consultas e manobras

| método | o que faz |
|---|---|
| `energized_nodes()` / `energized_by(no)` | BFS multi-fonte (fontes dos CTMT carregados + nós `EXT:`) por arestas passáveis; devolve os PAC com tensão / o CTMT que alimenta cada um. Nós `EXT:` não entram na contagem. |
| `downstream(no)` | nós que ficam sem tensão se `no` for removido (vale em anel: é o que só tem caminho passando por `no`). |
| `customers_downstream(no)` | `customers(downstream(no))`. |
| `open_switch` / `close_switch` / `is_open` / `reset_switches` | estado atual das chaves (`aberta`); `reset` volta ao `P_N_OPE`. |
| `tie_switches()` | tabela das ties (próprias e externas) com PAC, PAC_VIZ, TLCD, TIP_UNID, distância e estado. |
| `isolate_segment(cod, aplicar=False)` | zona = fecho do trecho por arestas que não são chave (trechos e ties); `chaves` = chaves **fechadas** na fronteira da zona (a primeira em cada direção — mínimas); `desligados` = nós sãos que perdem tensão com a manobra (energizados antes − depois − zona). |
| `restore_options(cod)` | chaves **abertas** (exceto as recém-abertas) com uma ponta nos `desligados` e a outra energizada (inclusive `EXT:`); agrupadas por componente conexo dos desligados; cada opção traz nós, clientes recuperados, CTMT que passa a alimentar (`fonte`), TLCD, se é externa e `clientes_fonte` (carga já atendida por essa fonte, para o operador julgar sobrecarga). Ordem: clientes ↓, TLCD ↓, código. Não altera o estado. |
| `estado_geojson(rede, caminho)` | `FeatureCollection` EPSG:4326 com trechos (`energizado`, `fonte`, `COMP`, `TIP_CND`), chaves (`normal`, `aberta`, `TLCD`, `TIP_UNID`, `tie`, `externa`; as externas com a geometria de `INTERLIGACOES`) e transformadores (`POT_NOM`, `n_UCBT`, `energizado`). |

Anéis internos (chave NA entre dois pontos do mesmo CTMT, como `CH006` na fixture) aparecem em
`restore_options` com `fonte` igual ao próprio CTMT — desde que uma das pontas continue energizada.

Cada `OpcaoRestauracao` carrega a **sequência de manobras** explícita em `manobras` — os passos
`{"acao": "abrir", "chave": …}` do isolamento seguidos de `{"acao": "fechar", "chave": <NA>}` — para o
agente propor e o operador aprovar passo a passo. `Isolamento.to_dict()`, `OpcaoRestauracao.to_dict()`
e `Rede.resumo()` são serializáveis em JSON (conjuntos → listas ordenadas, `Clientes` → dict): é o
que o servidor MCP (fase 3) devolve ao LLM.

> **O grafo não verifica capacidade.** `restore_options` diz *quem* pode ser reenergizado e por qual
> fonte, mais `clientes_fonte` como indício de carga; **não** confere corrente no tronco receptor nem
> tensão na ponta transferida. Isso é papel do gêmeo OpenDSS (`bdgd_light.twin`,
> [spike-opendss.md](spike-opendss.md)), que deve ler o estado `aberta` das chaves deste grafo e
> resolver o fluxo depois da manobra.

## Impacto estimado da manobra em consumidor-minutos e DEC

Quando existe uma opção de restauração, o projeto também estima o **impacto potencial do evento**
caso a manobra seja executada e o reparo da falta demore um certo tempo. A premissa entra como
`tempo_reparo` (padrão **180 min**) e é tratada explicitamente como **hipótese operacional**, nunca
como fato medido.

Fórmulas:

- **consumidor-minutos evitados** = `clientes_restaurados × max(tempo_reparo − tempo_manobra, 0)`
- **clientes que seguem sem tensão até o reparo** = `clientes_desligados − clientes_restaurados`
- se a camada `CONJ` estiver no recorte e o conjunto puder ser identificado:
  **contribuição estimada ao DEC do conjunto (h)** =
  `consumidor_minutos_evitados ÷ total_uc_do_conjunto ÷ 60`

Premissas explícitas do MVP:

- `tempo_manobra = 5 min` é um valor operacional fixo para traduzir a proposta em ordem de grandeza;
- `tempo_reparo` é fornecido pelo operador/fluxo chamador e representa um **cenário hipotético**;
- o total de UC do conjunto é contado no recorte (`UCBT_tab` + `UCMT_tab`) para o `CONJ` da área
  restaurada.

O que **não** se pode afirmar a partir desse número:

- não é “redução de DEC realizada”;
- não é medição regulatória oficial do evento;
- não substitui apuração pós-operação, telemetria, OMS ou histórico real de recomposição;
- não significa que todo o conjunto sofreu a interrupção — apenas estima o impacto da parcela de
  clientes que a manobra conseguiria restaurar sob aquela hipótese de reparo.

## Exemplo real — falta no tronco de BOCARI (cluster TQR)

```bash
uv run bdgd-light grafo --gpkg data/feeders/cluster_TQR0007-TQR33859-TQR33862.gpkg --falha 11798327
```

Abrir 4 chaves (`11026473`, `22826994`, `528574225`, `790615689`); zona isolada 43 nós / 516 UCBT;
295 nós / 2.023 UCBT sãos desligados. 10 opções restauram 287 nós / 1.984 UCBT: por PARNAIBA
(`1007642983` TLCD, `752622332` TLCD, `11026494`, `134733185`, `258481641` — PARNAIBA já com 6.272 UC)
ou por CURUMAU (`789941518` TLCD, `11053522`, `11053620`, `11053627`, `11056672` — 5.889 UC). Os 8 nós
restantes (39 UCBT) não têm NA para nenhuma fonte. É exatamente o cenário FLISR do
[escopo](escopo-alimentadores.md): falta em BOCARI, restauração via PARNAIBA ou CURUMAU.

## Limitações conhecidas

- Sem fases, impedâncias ou limites: a energização é puramente topológica. Corrente, tensão e
  sobrecarga vêm do gêmeo OpenDSS (`bdgd_light.twin`, [spike-opendss.md](spike-opendss.md)); a
  integração estado das chaves do grafo → `open/close` no circuito ainda não existe (as chaves NA
  saem comentadas do bdgd2opendss e cada CTMT é um circuito separado).
- `UNREMT` (reguladores) e `UNCRMT` (capacitores) não são arestas nem nós — estão em série na rede
  pelos PAC de `SSDMT` e não alteram conectividade.
- A ponta de fora de uma tie ambígua (os dois PAC na própria rede) é `PAC_2` por convenção; 90 casos
  na Light, nenhum no cluster TQR.
- Uma chave externa que toca vários PAC nossos fica só com o mais próximo (`137253951`, de TQR33830,
  no cluster TQR).
