# Spike: BDGD → OpenDSS com bdgd2opendss + OpenDSSDirect (issue #5)

Objetivo: validar o caminho BDGD → modelo OpenDSS → fluxo de potência em um alimentador real
(TQR0007, Light 2025) e deixar a base do gêmeo elétrico (`bdgd_light.twin`). Resultado em uma linha:
**funciona** — o bdgd2opendss converte TQR0007 em 180 s sem nenhum ajuste na BDGD, e o fluxo
converge em 5 iterações (0,5 s) depois de um estabilizador padrão; MT entre 1,016 e 1,045 pu; a BT
tem ~1.000 nós abaixo de 0,93 pu por causa de ramais de ligação com centenas de metros na própria
BDGD. Indo além do pedido: o cluster TQR inteiro (PARNAIBA + CURUMAU + BOCARI) roda num Master único
e a manobra FLISR do grafo (falta em BOCARI → restauração via PARNAIBA ou via CURUMAU) foi
reproduzida no gêmeo, com fluxo convergindo e sem sobrecarga na MT (seção "FLISR no gêmeo").

## O que foi feito

| Peça | Onde |
|---|---|
| Extras `twin` (`opendssdirect.py>=0.9`, `bdgd2opendss>=1.2`) | `pyproject.toml` (já existiam); CI instala `--extra twin` |
| `converter(gdb, ctmt, out)`, `localizar_pasta`, `listar_masters`, `escolher_master` | `src/bdgd_light/twin/convert.py` |
| `run_powerflow(master) -> PowerFlowResult`, cascata `ESTABILIZADORES` | `src/bdgd_light/twin/powerflow.py` |
| `montar_master_cluster(pastas, out, comandos)`, `comandos_manobras(rede, manobras)` | `src/bdgd_light/twin/cluster.py` |
| `bdgd-light dss --gdb … --ctmt A[,B,C] [--out] [--dia] [--mes] [--master] [--gpkg --falha --restaurar --abrir --fechar] [--comando] [--json]` | `src/bdgd_light/cli.py` |
| Fixtures IEEE 13 barras e `cluster_mini` (RJO001+RJO002 no layout do bdgd2opendss, gerada por script) + 23 testes | `tests/fixtures/dss/`, `tests/test_twin.py` |

Versões: bdgd2opendss 1.2.5, opendssdirect-py 0.9.4, dss-python 0.15.7 (DSS C-API 0.14.5), Python
3.13 em macOS arm64. Instalação via `uv sync --extra dev --extra twin` sem nenhum problema (o
bdgd2opendss arrasta customtkinter, plotly, xlsxwriter e holidays, ~40 MB).

## O que o bdgd2opendss precisou

- **Só aceita o `.gdb` inteiro.** `bdgd_type()` faz `os.listdir` no caminho para decidir se a BDGD é
  pública ou privada; não lê GPKG nem Parquet, e não tem filtro espacial: carrega as 18 tabelas
  completas (BASE, CTMT, SEGCON, CRVCRG, SSDMT, UNSEMT, UNSEBT, UNTRMT, EQTRMT, UNREMT, EQRE, SSDBT,
  RAMLIG, UCMT_tab, UCBT_tab, PIP, UGBT_tab, UGMT_tab) antes de filtrar o CTMT. `RAMLIG` sozinha tem
  3,8 milhões de linhas. Só `UNSEBT` e `UNTRAT` são opcionais; as demais precisam existir.
- **Tempo**: 179,9 s para um alimentador (a maior parte lendo o GDB; `Case.PopulaCase()` é rápido).
  Converter os três CTMT do cluster TQR de uma vez (`lst_feeders=[...]`) custa quase o mesmo.
- **Saída**: `<out>/sub_<SUB>/<CTMT>/` (a Light usa `SUB="_10385871"`, daí `sub__10385871`) com 122
  arquivos / 116 MB: `CircuitoMT` (Vsource 13,2 kV, 1,045 pu, `bus1=TQR0007_MT_52737` — o mesmo
  `PAC_INI` que o grafo usa como fonte), `CodCondutor` (4.892 linecodes), `SegmentosMT` (675),
  `ChavesMT` (40 chaves **NF** como `Line … switch=T`; as 10 **NA** vão comentadas com `!`),
  `TransformadorMTMTMTBT` (82 trafos + 82 reatores de neutro de 15 Ω), `SegmentosBT` (1.708),
  `ChavesBT` (7), `RamaisBT` (3.821), `Medidores` (1 EnergyMeter no disjuntor), `CurvaCarga` (132
  loadshapes CRVCRG × DU/SA/DO), `GD_BT` (118 `Generator` com perfil solar padrão), 36 pares
  `CargasBT_*`/`CargasMT_*` (12.304 cargas BT + 8 MT por tipo de dia × mês) e **36 Masters**
  `Master_{DU,SA,DO}{01..12}_<ano><distribuidora>_<CTMT>_<config>.dss`.
- **Modelo de carga**: cada UC vira duas cargas (`_M1 model=2` impedância constante e `_M2 model=3`
  corrente constante, 50/50 — metodologia ANEEL de perdas), `kw` = pico da curva, `vminpu=0.5`,
  `daily=<CRVCRG>`. O Master fica em `Set mode=daily` e com o `Solve` comentado: quem chama decide o
  que resolver.
- Avisos do conversor: "No RegControls found", "No UGMT found" (esperados para TQR0007).

## O que faltou / decisões

1. **Não fez falta um conversor próprio.** A regra do modo noturno era escrever um (Vsource + Lines
   + Transformers + Loads) só se o bdgd2opendss não instalasse ou não convertesse; ele fez as duas
   coisas. Decisão: manter o bdgd2opendss como conversor e concentrar o código nosso em orquestração
   (`converter`) e análise (`run_powerflow`).
2. **Snapshot, não daily.** `run_powerflow` envia `set mode=snapshot` antes do `Solve`: resolve o
   patamar de pico (`kw` das cargas), que é o cenário de interesse para manobra. Para um patamar
   horário use `--comando "set loadmult=0.6"` ou, em Python, `comandos_extra=["set mode=daily
   stepsize=1h number=1 hour=15"]` e `modo=None`.
3. **Estabilizadores em cascata.** No modelo bruto o método padrão do OpenDSS **não converge** (15 e
   nem 100 iterações): há barras BT abaixo de 0,5 pu e as cargas `model=3` oscilam entre corrente
   constante e o `vminpu=0.5`. Em vez de esconder isso, `run_powerflow` tenta, em ordem, e registra em
   `PowerFlowResult.ajustes` o que foi preciso: `set maxiterations=100` → `batchedit load..*
   vminpu=0.9` (abaixo de 0,9 pu a carga vira impedância constante; é a recomendação do próprio
   OpenDSS para barras deprimidas) → `batchedit load..* model=2` (último recurso). Em TQR0007 bastou o
   segundo degrau: 5 iterações. `--sem-estabilizar` mostra o resultado bruto e o CLI sai com código 2
   quando não converge. Desde a issue #44 o rótulo é exato: como a não convergência é um
   **ciclo-limite** (não lentidão), `maxiterations=100` nunca resolve sozinho e só aparece em `ajustes`
   quando o `Solve` final precisou de mais iterações que o limite original — todo Master da BDGD sai
   hoje com `ajustes = ["vminpu=0.9"]` (ver "Diagnóstico de convergência do cluster Tijuca").
4. **Nós de fase × neutro.** O bdgd2opendss aterra o neutro BT (`.4`) por reator; esses nós ficam a
   ~0 pu e não são violações. `PowerFlowResult.fases` considera só condutores 1–3 com V > 0; nós de
   fase a 0 pu contam como `n_desenergizados`.
5. **Ampacidade**: `carregamento_pct` vem de `PDElements.AllPctNorm`; reatores e chaves (sem
   `normamps`) ficam com `NaN` e não entram em `sobrecargas`.
6. **`compile` muda o cwd do processo** (para a pasta do Master). `run_powerflow` restaura; há teste.
   - **O motor roda num subprocesso reciclável** (`twin.powerflow.no_motor`, issue #48): o DSS
     C-API só aceita chamadas da thread que o importou (`SIGILL`) e a sua finalização derrubava a
     CI Linux na saída (`SIGSEGV`); por isso `run_powerflow`/`ampacidade_tronco` executam num filho
     dedicado que é recriado se morrer (`MotorError`). Detalhes em `docs/console.md` (Decisões).
7. **Chaves NA não estão no modelo** (comentadas) e cada CTMT é um circuito com a própria Vsource.
   Resolvido em `twin/cluster.py`: `montar_master_cluster` escreve um Master único com a `Circuit`
   no barramento do primeiro CTMT e uma `Vsource.<CTMT>` por vizinho (mesma SE, 13,2 kV, 1,045 pu),
   redirecionando os arquivos de elementos de todos; `comandos_manobras` traduz a sequência
   `manobras` do grafo (`Isolamento`/`OpcaoRestauracao`, PR-03) em DSS: `abrir` NF → `open
   line.cmt_<COD_ID> term=1`; `fechar` NA → `New "Line.CMT_<COD_ID>" … switch=T` entre os PAC da
   chave **mais um jumper** `Line.TIE_<COD_ID>_<n>` do PAC da chave até o `PAC_VIZ` da tie
   geométrica (as ties da Light não compartilham PAC, `docs/bdgd-relacoes.md`). Os nomes de barra do
   bdgd2opendss são os PAC da BDGD, então os nós do grafo e do gêmeo coincidem sem tabela de
   tradução.
8. **`GD_BT` fica de fora por padrão.** O bdgd2opendss gera o arquivo com os `Generator` da UGBT_tab
   mas **não o inclui no seu Master**; ao incluí-lo no cluster, TQR33859 e TQR33862 divergem (NaN
   mesmo com `model=2`). `montar_master_cluster(gd=True)` liga se quiser investigar. Além disso a
   base da Light tem GD com `COD_ID` em branco (`New "generator. "`) em TQR0007 e TQR33862; no
   mesmo circuito isso vira "duplicate element definition" (#266), que o dss-python trata como
   exceção — por isso o Master do cluster tem `Set AllowDuplicates=yes` logo após a `Circuit` (também
   cobre linecodes/loadshapes repetidos entre CTMT, que são definições idênticas).
   - **Bancos de unidades monofásicas (`UNTRMT.TIP_TRAFO = DF`/`DA`)** saem do bdgd2opendss 1.2.5
     como `phases=3` com barras de 2 nós (aterra um vértice do delta: 64 % de perdas e 0,2 pu na BT
     de Tijuca). `twin.corrigir_bancos_monofasicos` reescreve como `phases=1 kvs=[13.2 0.127]`; caso
     mínimo em `tests/fixtures/dss/bancos_monofasicos.dss`; reportado em
     [PauloRadatz/bdgd2opendss#35](https://github.com/PauloRadatz/bdgd2opendss/issues/35).
9. **Master a partir do GPKG do recorte** (observação da PR-03; **implementado na #17**): o
   bdgd2opendss só lê o `.gdb` inteiro (`os.listdir` + 18 tabelas, sem filtro espacial). O módulo
   `twin.gpkg2dss` reproduz a modelagem dele direto do `data/feeders/<CTMT>.gpkg` (ou do GPKG do
   cluster) — ver "Master a partir do GPKG" abaixo. `bdgd-light dss --gpkg X` sem `--gdb` usa esse
   caminho e grava em `data/dss/gpkg/<CTMT>/`; o bdgd2opendss continua disponível com `--gdb` e é a
   referência de paridade.

## Quando usar `--gpkg` × `--gdb`

| | `--gpkg` (padrão) | `--gdb` (bdgd2opendss) |
|---|---|---|
| Entrada | GeoPackage do `bdgd-light recortar` — **a mesma rede do grafo** | `.gdb` inteiro da BDGD |
| Saída | `data/dss/gpkg/<CTMT>/` (só DU/SA/DO do mês pedido) | `data/dss/sub_<SUB>/<CTMT>/` (36 Masters) |
| Tempo | ≈1 s por alimentador | ≈3 min por alimentador (carrega o GDB todo) |
| Usar para | tudo: `dss`, `grafo --score`, MCP, agente, console, testes | **regressão de paridade** do conversor (`tests/test_gpkg2dss.py::test_paridade_tqr0007_real`) e conferência de um resultado suspeito contra o oráculo |
| Não misturar | os `--out` são distintos por padrão; `dss --out data/dss` força os modelos do bdgd2opendss num cenário |

Regra: a rede que o operador vê (grafo/console) e a rede que o gêmeo resolve são **o recorte**; o
bdgd2opendss só entra quando o conversor muda ou os recortes são regerados — aí o mantenedor roda:

```bash
uv run bdgd-light dss --gdb data/Light_382_2025-12-31_V11_20260824-0926.gdb --ctmt TQR0007 --out data/dss --sem-fluxo
uv run pytest tests/test_gpkg2dss.py -q -k paridade     # skip automático sem data/feeders + data/dss
```

## Master a partir do GPKG (issue #17)

`bdgd_light.twin.gpkg2dss` (`converter_ctmt`, `converter_gpkg`, `listar_ctmts`, `dias_por_tipo`)
lê só as camadas do recorte (SSDMT, UNSEMT, UNTRMT, EQTRMT, SSDBT, UNSEBT, RAMLIG, UCBT_tab,
UCMT_tab, UGBT_tab, UGMT_tab, PIP, SEGCON, CRVCRG) e escreve `<out>/<CTMT>/<Prefixo>_gpkg_<CTMT>.dss` +
`Master_<DIA><MM>_gpkg_<CTMT>.dss`, com os mesmos nomes de elemento do bdgd2opendss (as barras são
os PAC), então `montar_master_cluster`/`comandos_manobras` funcionam sem tradução. Leva ≈1 s por
alimentador (o bdgd2opendss leva ≈3 min porque carrega o GDB inteiro).

**Paridade em TQR0007** (`tests/test_gpkg2dss.py::test_paridade_tqr0007_real`, roda quando
`data/feeders/TQR0007.gpkg` e `data/dss/sub__10385871/TQR0007` existem):

| Arquivo | bdgd2opendss 1.2.5 | gpkg2dss | Diferença |
|---|---|---|---|
| SegmentosMT / ChavesMT / SegmentosBT / ChavesBT / RamaisBT | 675 / 50 / 1.708 / 7 / 3.821 | idem | **nenhuma** (linha a linha) |
| TransformadorMTMTMTBT | 82 unidades | 82 | **nenhuma** |
| CargasBT_DU01 (UCBT + PIP) | 6.152 cargas × M1/M2 | 6.152 | **nenhuma** (nomes, barras, kW) |
| CargasMT_DU01 | 4 | 4 | nenhuma |
| CodCondutor / CurvaCarga | catálogo inteiro (6.115 / 132) | só os usados (428 / 42) | cosmética |
| Medidores | `Energymeter.BusA4-_…_CHVMT_358368825` | `Energymeter.M_TQR0007` | nome (mesmo elemento) |
| Circuit | `pu=1.0449999570846558` | `pu=1.045` | float32 → texto |
| Fluxo DU01 | 6.334 barras, 12.312 cargas, 3.076,76 kW, perdas 264,335 kW | idem | **\|ΔV\| máx = 0 pu** em 14.695 nós |

Achados durante a paridade (todos corrigidos no conversor e/ou no recorte):

- **PIP (iluminação pública) faltava no recorte.** O bdgd2opendss escreve cada PIP como
  `Load.BT_IP<COD_ID>` no mesmo `CargasBT` — em TQR0007 são 1.235 das 6.152 cargas BT (≈4 % da
  energia). A camada entrou no catálogo, no recorte (por `UNI_TR_MT`) e no `CRVCRG`; os GPKG antigos
  precisam de `bdgd-light export --layers PIP` + novo `recortar`.
- **Ordem e duplicatas de UCBT**: o bdgd2opendss agrupa por `COD_ID` (somando energias) antes de
  numerar ramais repetidos (`BT_<RAMAL>_1`, `_2`…); reproduzido para os nomes baterem.
- **Bancos DF/DA** (`EQTRMT` com 2–3 unidades por UNTRMT): o bdgd2opendss usa o kVA da **unidade**
  (`EQTRMT.POT_NOM`, código TPOTAPRT) mas as perdas do **conjunto** (`UNTRMT.PER_TOT/PER_FER`), o
  que triplica as perdas do banco — reportado em
  [PauloRadatz/bdgd2opendss#36](https://github.com/PauloRadatz/bdgd2opendss/issues/36). O gpkg2dss
  divide as perdas pelas unidades (bate com `EQTRMT.PER_*`) e já escreve `phases=1` (#35). No
  cluster Tijuca (24 bancos DF, 72 unidades) isso muda as perdas de 876 kW para 804 kW (6,6 % →
  6,1 %) no cenário A; tensões MT idênticas, 32.132 cargas nos dois.
- Comprimento de linha é `COMP/1000` sem piso (só `COMP ≤ 0` vira 1 mm), como o bdgd2opendss.
- Elementos sem caminho até o `PAC_INI` (mesmo critério de grafo) saem **comentados** (`!New …`) com
  contagem em `contagem["isolados_<tabela>"]`, em vez de omitidos — auditável no arquivo.

## Resultado em TQR0007 (Master DU01, snapshot de pico)

```
Convergiu                 sim (5 iterações, 0,53 s) — estabilizadores: vminpu=0.9 (o rótulo antigo listava também maxiterations=100; ver #44)
Elementos                 6.334 barras, 20.313 nós, 6.251 linhas, 82 trafos, 12.312 cargas
Potência na fonte         3.077 kW / 1.395 kvar
Perdas                    264 kW (8,6 %)
Tensão (nós de fase)      mín 0,369 pu, máx 1,045 pu
Fora de [0,93, 1,05] pu   988 sub, 0 sobre (de 14.695 nós; 0 a 0 pu)
Sobrecargas (> 100 %)     17
```

- **MT está saudável**: 2.148 nós de 13,2 kV entre **1,016 e 1,045 pu** (média 1,027) — coerente
  com um alimentador curto (16,5 km) e 3 MW.
- **BT concentra todos os desvios.** As piores barras (`567952367_2` a 0,37 pu, `255418973_2` a
  0,46 pu, `255281591_2`, `580170997_2`) são a ponta de **ramais de ligação (`RAMLIG`) com 943, 714,
  727 e 783 m** em 220 V alimentando 34–65 UCBT cada. `RAMLIG` não tem geometria na Light (é tabela),
  então o comprimento vem de `COMP`, que o bdgd2opendss reproduz fielmente. A mediana dos 3.821 ramais
  de TQR0007 é 17 m; 142 têm mais de 100 m e 10 mais de 300 m. É **qualidade de dado da BDGD** (ramal
  cadastrado como se fosse o circuito BT inteiro, provável em ocupações densas), não erro de
  conversão. As 17 sobrecargas são os mesmos ramais/segmentos BT (`Line.rbt_833185769` a 250 %) e
  dois trafos (`trf_11071479a` 148 %, `trf_34450955a` 125 %).
- Sem estabilizador (`--sem-estabilizar`): não converge em 15 iterações e o CLI sai com código 2.
- Com `--comando "set loadmult=0.6"`: converge (mesmo degrau), mín 0,51 pu, 275 nós fora da faixa.
- Fixture IEEE 13: 4 iterações, 16 barras / 41 nós, mín 0,961 pu (`611.3`), máx 1,056 pu
  (`rg60.1/.3`, o regulador), perdas 112,4 kW, `Line.650632` a 148 % — bate com os valores publicados.

## FLISR no gêmeo (cluster TQR, Master DU01, snapshot de pico)

Cenário de referência de `docs/review/PR-02.md`/`PR-03.md`: falta no trecho `11798327` de BOCARI
(TQR33862). O grafo (`bdgd-light grafo --falha 11798327`) abre 4 chaves (`11026473`, `22826994`,
`528574225`, `790615689`), isola 43 nós / 516 UC e desliga 295 nós / 2.023 UCBT restauráveis; há 10
opções de restauração, todas com 287 nós / 1.984 UCBT / 51 trafos (5.317 kVA): via PARNAIBA
(TQR0007) pela tie telecomandada `1007642983` ou via CURUMAU (TQR33859) pela tie telecomandada
`789941518`. Cada cenário é um Master em `data/dss/cluster_TQR0007-TQR33859-TQR33862/` e roda em
≈1,2 s (8–9 iterações, `vminpu=0.9`):

| cenário | kW PARNAIBA | kW CURUMAU | kW BOCARI | I disj. (A) PAR / CUR / BOC | MT mín (pu) PAR / CUR / BOC | nós MT em BOC | sobrecargas MT |
|---|---|---|---|---|---|---|---|
| base (estado normal) | 3.077 | 3.369 | 3.024 | 149 / 190 / 144 | 1,016 / 1,017 / 1,026 | 1.806 | 0 |
| falta isolada, sem restauração | 3.077 | 3.369 | 1.258 | 149 / 190 / 60 | 1,016 / 1,017 / 1,043 | 804 (9.092 nós de fase a 0 pu) | 0 |
| restauração via PARNAIBA (`1007642983`) | **4.603** | 3.369 | 1.258 | **221** / 190 / 60 | **1,003** / 1,017 / 1,004 | 1.656 | 0 (tronco `smt_11795885` a 76 %) |
| restauração via CURUMAU (`789941518`) | 3.077 | **4.900** | 1.258 | 149 / **262** / 60 | 1,016 / 1,009 / 1,010 | 1.653 | 0 |

- As duas opções são eletricamente viáveis: os 287 nós transferidos ficam entre 1,004 e 1,023 pu, sem
  nenhum trecho MT acima de 100 % (o tronco de PARNAIBA vai a 76 % da ampacidade). Fica por conta do
  operador/score o critério de escolha — CURUMAU recebe 1,5 MW a mais e chega a 262 A no disjuntor;
  PARNAIBA recebe os mesmos 1,5 MW mas parte de 149 A. O grafo já ordena TLCD primeiro; o fluxo agora
  fornece I no disjuntor, MT mínima e carregamento do tronco para o score (issue futura).
- Os 1.395 nós de fase que permanecem a 0 pu depois da restauração são a zona da falta (43 PAC e sua
  BT), como esperado; o número de nós MT de BOCARI cai de 1.806 para 1.656 pelo mesmo motivo.
- As perdas altas do cluster (14 %) e as 87 sobrecargas são as mesmas da BT vista em TQR0007 (ramais
  `COMP` longos) — CURUMAU sozinho perde 862 kW (26 %) e tem um banco `trf_11071281b/c` de 3,6 A
  nominais a 1.100 %, outro indício de cadastro; nada muda com a manobra.
- Mesmo cenário na fixture sintética (`tests/test_twin.py::test_flisr_no_gemeo`): base 302 + 83 kW;
  isolar SEG001 zera RJO001_MT_1..6 e a fonte de RJO001; fechar CH003 (+ jumper até RJO002_MT_5)
  devolve tensão a tudo menos SEG001/TR003 e RJO002 passa a suprir ~354 kW.

## Score elétrico das opções de restauração (issue #18)

`twin.score_eletrico(opcoes, rede, master_cluster)` (`src/bdgd_light/twin/score.py`) é o verificador
determinístico da ADR-001 (decisão 6): para cada `OpcaoRestauracao` do grafo compila o Master **base**
do cluster, aplica as manobras da opção (`comandos_manobras`) antes do `Solve` e devolve um
`ScoreEletrico` — `convergiu`, `i_disjuntor_a` (corrente máxima de fase na `Vsource` da fonte que
recebe a carga), `i_nominal_a`, `margem_disjuntor`, `vmin_mt_pu`/`vmax_mt_pu` (nós MT da fonte e da
zona transferida), `sobrecargas_mt` (trechos `SMT_*` da fonte/zona acima de 100 %), `perdas_kw`,
`viavel` e `motivos`. A lista já sai ordenada por viável → margem (0,1 %) → UCBT; a BT fica fora do
veredito. `bdgd-light grafo --falha X --score` imprime tudo na tabela de opções.

**Corrente nominal do disjuntor.** `UNSEMT.COR_NOM` é um código de domínio do Manual da BDGD
(a Light usa 26 códigos; os disjuntores das SE saem como `40`, `39`, `46`, `35`) e o GDB entregue
**não embute** as tabelas de domínio (`GDB_Items` só tem as 45 feature classes/tabelas). Sem a
tabela oficial, e como o modelo OpenDSS da chave sai sem ampacidade (`normamps` padrão de 400 A,
fictício), a referência é a ampacidade `normamps` do(s) trecho(s) SSDMT imediatamente a jusante do
disjuntor (`twin.trechos_tronco`/`ampacidade_tronco`; nos 4 alimentadores da Tijuca há exatamente um
trecho-tronco cada). `nominais={"CTMT": A}` sobrepõe quando a corrente nominal real for conhecida.
Pendência: obter a tabela `COR_NOM` do Manual (Módulo 10) e colocá-la em `catalogo.py`.

**Tijuca, cenário A** (`cluster_tijuca.gpkg`, falta em `11304252`, Masters do GPKG, DU01):

| fechar | fonte | TLCD | I disj. (A) | I nom. (A) | margem | Vmin MT (pu) | sobrec. MT | perdas (kW) | viável |
|---|---|---|---|---|---|---|---|---|---|
| `974020904` / `529355823` | ALC9946 | sim / não | 320 | 592 | 46 % | 1,027 | 0 | 804 | **sim** |
| `746851189` / `23313112` | RCP9882 | sim / não | 351 | 438 | 20 % | 1,018 | 0 | 821 | **sim** |
| `977361689` / `11006808` / `11006815` | URG29983 | sim / não / não | 346 | 592 | 42 % | 1,014 | 1 | 830 | não |
| `1009901594` / `11035887` | URG29706 (externa) | — | — | — | — | — | — | — | não (sem modelo) |
| `494303815` | ALC740 (externa) | — | — | — | — | — | — | — | não (sem modelo) |

- A opção de referência do escopo (`974020904` → ALC9946) é a melhor pelo critério: 46 % de margem
  no disjuntor e Vmin 1,027 pu nos 4.036 UCBT transferidos. RCP9882 também fecha, com menos folga.
- URG29983 é **inviável**: o trecho `11051956` (20 m, condutor `456027629_43_3`, CNOM 132 A) no
  caminho até a tie vai a **180 %** da ampacidade — um gargalo que o score topológico do grafo não
  vê. Fica como pergunta ao mantenedor se é cadastro (condutor fino num tronco) ou real.
- Fontes fora do cluster (URG29706, ALC740) não são simuladas: saem inviáveis com o motivo
  registrado — o recorte precisa incluir o CTMT para pontuá-las.
- Tempo: 7 fluxos (compile + solve do cluster de 4 alimentadores, 32 mil cargas) em ≈10 s; todos
  precisaram do `vminpu=0.9`, como o Master base do cluster (o rótulo da época dizia
  `maxiterations=100` + `vminpu=0.9`; o diagnóstico do #44 mostrou que o primeiro degrau nunca
  contribuiu).
- Na fixture sintética (`tests/test_twin.py::test_score_eletrico_*`): CH003/CH005 viáveis com 16 A num
  tronco de 200 A (margem 92 %); `set loadmult=25` leva a 312 A, 3–5 trechos acima de 100 % e
  margem negativa; `nominais={"RJO002": 10}` e `vmin=1.045` derrubam pelo disjuntor e pela tensão.

## Diagnóstico de convergência do cluster Tijuca (issue #44)

Pergunta da issue: por que o Master do cluster A (`ALC9925,RCP9882,ALC9946,URG29983`, 10.029 barras,
34.095 nós, 32.132 cargas — metade `model=3`, corrente constante) só convergia com
`maxiterations=100` + `vminpu=0.9`, e onde estão as barras responsáveis? Ferramenta:
`scripts/diagnostico_convergencia.py <Master>` (matriz de ajustes → oscilação iteração a iteração →
cargas críticas; ≈20 s no cluster). Achados, com o Master DU01 do GPKG:

| ajuste (a partir do Master bruto, `vminpu=0.5`) | converge | iterações |
|---|---|---|
| padrão (`maxiterations=15`) | não | 15 |
| `maxiterations=100` | **não** | 100 |
| `vminpu=0.9` (com `maxiterations=15`) | **sim** | 6 |
| `vminpu=0.95` / `0.7` / `0.8` / `0.6` | sim / sim / não / não | 5 / 22 / — / — |
| `model=2` em todas as cargas | sim | 2 |
| `algorithm=newton` + 100 iterações; `tolerance=1e-3`; `model=1` | não | — |
| `loadmult` 0,9 / 0,8 / 0,6 + 100 iterações | não | — |

1. **É um ciclo-limite, não convergência lenta.** Rodando `Solve` uma iteração por vez, o
   `max|ΔV|` repete um padrão de **período 6**: 0,097 pu toda iteração (nó `335019687_2.1`) e 0,24 pu
   a cada seis nos nós de neutro `11366449_bt_*.4` (0,40 ↔ 0,64 pu). 164 nós oscilam com amplitude
   > 0,01 pu, quase todos em dois circuitos BT: `TRF_28262926A` (RCP9882, 122 nós) e `TRF_11366449A`
   (38 nós). Por isso `maxiterations=100` nunca ajudou — e por isso o rótulo antigo era enganoso.
2. **Quem oscila são as cargas de corrente constante com tensão *terminal* abaixo de 0,9 pu.**
   Medir a tensão fase-neutro nos terminais da carga (não nó–terra, que o deslocamento do neutro
   contamina) separa 4.588 cargas < 0,9 pu (2.294 `model=3`; mínima 0,017 pu). Aplicar `vminpu=0.9`
   **só nessas 2.294** converge em 6 iterações com `maxiterations=15` — o mesmo que aplicar em todas.
   Circuitos com mais cargas críticas: `TRF_10951643A` (625, Vterm mín 0,017 pu), `TRF_10951769C`
   (213, 0,405), `TRF_28262926A` (187, 0,399), `TRF_217954888TZ132904A` (162, 0,888),
   `TRF_10951649TZ143389A` (161, 0,791), `TRF_10908985TZ137308A` (127), `TRF_10951751A` (111),
   `TRF_10908727A` (83), `TRF_10951427A` (76), `TRF_10951721AP76761A` (54, 0,303).
3. **A causa é o desequilíbrio de fase cadastrado na BDGD, não a carga nem os ramais longos.**
   No cluster, `UCBT_tab.FAS_CON` dá 7.229 `ABCN`, 4.170 `AN`, 1.978 `BN`, 1.382 `CN`, 944 `ABN`,
   273 `BCN`, 272 `CAN`: 14 trafos (com ≥ 20 UC monofásicas) têm ≥ 90 % delas **na mesma fase** —
   `10951643` (638 de 678 em A), `28262926` (192 de 192 em A), `10951787AP85826` (148 em A),
   `10951499` (98 em A), `10908727` (95 em A), `10938261` (90 em B), `10938105` (87 em A),
   `10951751` (57 em A), `10938279` (55 em A), `31178791` (46 em A), `10915053` (34 em A),
   `10951577AP84296` (30 em A), `10951547` (29 em A), `10909015TZ173889` (21 em B). No modelo, 138
   das 140 cargas de `28262926`
   pendem do nó `.1.4`; o neutro desse circuito fica a 0,18 pu e as fases em 0,79 pu na solução
   convergida. Teste de necessidade: `vminpu=0.9` em **tudo menos** `28262926` não converge; deixar
   só `11366449` em 0,5 converge no limite (14 iterações). Reduzir a carga (`loadmult`) não muda nada
   — é a geometria do desequilíbrio, não o carregamento.
4. **Ramais longos são outro problema de dado, sem relação com a convergência.** O cluster tem 7
   `RAMLIG` com mais de 300 m; `RBT_589704551` (988 m, 55 UC, trafo `10951721AP76761`) é a barra a
   **0,303 pu** que aparece como pior tensão — ela já está abaixo de 0,5 pu e não participa do
   ciclo-limite. Como em TQR0007 (943 m, 714 m…), é o circuito BT inteiro cadastrado como ramal.
5. **Não é exclusividade da Tijuca.** Nenhum Master da BDGD converge com `vminpu=0.5`: TQR0007
   (bdgd2opendss) precisa de `vminpu=0.9` e converge em 5 iterações, o cluster TQR em 9, Ipanema em 7
   (com um único trafo de fase única, `11043897` em PTS9088), Tijuca em 6 — a diferença de rótulo
   entre eles vinha só da cascata cumulativa.

**Decisões** (marcar e manter, não filtrar):

- `PowerFlowResult.ajustes` passa a listar **só o que foi necessário** (`_rotular_ajustes`):
  `maxiterations=100` sai do rótulo quando o `Solve` final convergiu dentro do limite original. A
  cascata continua cumulativa (menos invasivo primeiro), só o relato mudou.
- O conversor **marca os suspeitos** em `avisos` e `contagem` (`ramais_longos` = `RAMLIG` com
  `COMP > 300 m`; `trafos_fase_unica` = trafos com ≥ 20 UC monofásicas e ≥ 90 % delas na mesma fase),
  com os piores casos nominalmente no aviso. O modelo continua fiel à BDGD — o veredito do
  verificador é MT, e a BT deprimida aparece em `piores_barras` como sempre.
- `vminpu=0.9` fica como estabilizador padrão e documentado: é o comportamento recomendado pelo
  OpenDSS para barras deprimidas e, no cluster, muda só as 2.294 cargas que já estavam abaixo de 0,9 pu
  — o resultado MT (potência 13.250 kW, perdas 766 kW, V MT 1,036–1,045 pu) é o mesmo dos rótulos
  antigos.
- **Rejeitado: rebalancear as UC monofásicas entre A/B/C na conversão.** Foi testado (round-robin por
  trafo degenerado): o OpenDSS "converge" em 2 iterações para lixo (119 pu, −1,2 GW) porque os
  `SSDBT`/`RAMLIG` desses circuitos são cadastrados como `AN` — **dois fios**; não existe condutor B/C
  para receber a carga. Uma versão segura teria de olhar as fases disponíveis em cada PAC e ainda
  assim não removeria a necessidade do `vminpu=0.9` (o circuito `28262926` não tem para onde ir).
  Também não ajudaram: neutro multiaterrado (reator de 15 Ω em todos os 8.304 nós `.4` da BT) e
  `algorithm=newton`.

**Pendências para o mantenedor/Light**: (a) confirmar se `FAS_CON = AN` em massa é fase real ou
padrão de cadastro — se for cadastro, a lista de `trafos_fase_unica` é a fila de correção; (b) os
ramais > 300 m (`ramais_longos`) seguem como pergunta de qualidade de dado; (c) o registro
`docs/agent/sessao-tijuca.json` mantém o rótulo antigo (é histórico).

## Como reproduzir (mantenedor)

```bash
uv sync --extra dev --extra twin
# padrão: Master direto do GPKG do recorte (≈1 s por CTMT, em data/dss/gpkg/<CTMT>/)
uv run bdgd-light dss --gpkg data/feeders/TQR0007.gpkg --json data/dss/gpkg/TQR0007_DU01.json
# oráculo (bdgd2opendss, ≈3 min; lê o GDB inteiro) — só para a paridade; reaproveita data/dss se já existir
uv run bdgd-light dss --gdb data/Light_382_2025-12-31_V11_20260824-0926.gdb --ctmt TQR0007 \
    --out data/dss --json data/dss/TQR0007_fluxo_DU01.json
# outro patamar / outro Master / sem estabilizadores
uv run bdgd-light dss --ctmt TQR0007 --gdb data/Light_382_2025-12-31_V11_20260824-0926.gdb --dia SA --mes 7
uv run bdgd-light dss --master "data/dss/sub__10385871/TQR0007/Master_DU01_202608382_TQR0007_------1-----.dss" \
    --comando "set loadmult=0.6" --sem-estabilizar
# cluster TQR (reaproveita os três modelos em data/dss; sem --gdb não converte nada)
G=data/feeders/cluster_TQR0007-TQR33859-TQR33862.gpkg
uv run bdgd-light dss --ctmt TQR0007,TQR33859,TQR33862 --out data/dss --gpkg $G                       # base
uv run bdgd-light dss --ctmt TQR0007,TQR33859,TQR33862 --out data/dss --gpkg $G --falha 11798327      # isolada
uv run bdgd-light dss --ctmt TQR0007,TQR33859,TQR33862 --out data/dss --gpkg $G --falha 11798327 \
    --restaurar 1007642983 --json data/dss/cluster_TQR_via_PARNAIBA.json                              # via PARNAIBA
uv run bdgd-light dss --ctmt TQR0007,TQR33859,TQR33862 --out data/dss --gpkg $G --falha 11798327 \
    --restaurar 789941518                                                                             # via CURUMAU
# para converter os vizinhos de uma vez (≈5 min), passe --gdb junto com os três --ctmt
# cluster Tijuca direto do GPKG (--reconverter reimprime os avisos de ramais longos / trafos de fase única)
uv run bdgd-light dss --gpkg data/feeders/cluster_tijuca.gpkg --falha 11304252 --restaurar 974020904
uv run bdgd-light dss --gpkg data/feeders/cluster_tijuca.gpkg --reconverter
# diagnóstico de convergência de um Master (matriz de ajustes, ciclo-limite, cargas críticas; issue #44)
uv run scripts/diagnostico_convergencia.py data/dss/gpkg/cluster_ALC9925-RCP9882-ALC9946-URG29983/Master_DU01_base.dss
# score elétrico de todas as opções de restauração (Masters do GPKG em data/dss/gpkg)
uv run bdgd-light grafo --gpkg data/feeders/cluster_tijuca.gpkg --falha 11304252 --score
uv run python tests/fixtures/dss/gerar_cluster_mini.py   # regenera a fixture sintética do cluster
uv run pytest tests/test_twin.py tests/test_gpkg2dss.py -q   # a paridade/fumaça usam data/ se existir
```

## Próximos passos sugeridos

- ~~Score elétrico das opções de `restore_options`~~ — feito (`twin.score_eletrico`, issue #18);
  falta a tabela `COR_NOM` do Manual para a corrente nominal real do disjuntor.
- Filtro de qualidade de dado antes do fluxo: ramais `COMP > 300 m` e trafos de fase única já saem
  em `avisos`/`contagem` (#44); falta reportar trafos com kVA incompatível com a carga e decidir se
  algo é truncado — hoje ficam visíveis em `piores_barras`/`sobrecargas`.
- Rodar o `mode=daily` completo (24 h × DU/SA/DO) para curvas de tensão por trafo e para saber a hora
  crítica da transferência (o snapshot usa o pico das curvas).
- ~~Master a partir do recorte GPKG (decisão 9)~~ — feito (#17, `twin.gpkg2dss`).
