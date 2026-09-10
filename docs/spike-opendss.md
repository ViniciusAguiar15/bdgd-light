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
   quando não converge.
4. **Nós de fase × neutro.** O bdgd2opendss aterra o neutro BT (`.4`) por reator; esses nós ficam a
   ~0 pu e não são violações. `PowerFlowResult.fases` considera só condutores 1–3 com V > 0; nós de
   fase a 0 pu contam como `n_desenergizados`.
5. **Ampacidade**: `carregamento_pct` vem de `PDElements.AllPctNorm`; reatores e chaves (sem
   `normamps`) ficam com `NaN` e não entram em `sobrecargas`.
6. **`compile` muda o cwd do processo** (para a pasta do Master). `run_powerflow` restaura; há teste.
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
9. **Master a partir do GPKG do recorte** (observação da PR-03): o bdgd2opendss só lê o `.gdb`
   inteiro (`os.listdir` + 18 tabelas, sem filtro espacial), então o gêmeo ainda parte do GDB e não
   do `data/feeders/<CTMT>.gpkg`. Para o spike está ok (a conversão é idempotente e o CLI reaproveita
   `data/dss`). Caminho futuro: gravar o recorte como FileGDB (driver `OpenFileGDB` do GDAL ≥ 3.6
   escreve) com as 18 tabelas que o conversor exige, ou o conversor mínimo próprio a partir do
   GeoPackage — só vale se aparecer necessidade de rodar sem o GDB.

## Resultado em TQR0007 (Master DU01, snapshot de pico)

```
Convergiu                 sim (5 iterações, 0,53 s) — estabilizadores: maxiterations=100, vminpu=0.9
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

## Como reproduzir (mantenedor)

```bash
uv sync --extra dev --extra twin
# converte (≈3 min; lê o GDB inteiro) e resolve o Master DU01 — reaproveita data/dss se já existir
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
uv run python tests/fixtures/dss/gerar_cluster_mini.py   # regenera a fixture sintética do cluster
uv run pytest tests/test_twin.py -q      # 23 testes; a fumaça usa data/dss se existir
```

## Próximos passos sugeridos

- Score elétrico das opções de `restore_options`: rodar o gêmeo para cada opção e devolver I no
  disjuntor da fonte, MT mínima nos nós transferidos e carregamento máximo do tronco (a tabela acima
  feita à mão), combinando com o score topológico do grafo.
- Filtro de qualidade de dado antes do fluxo: ramais `COMP > 100 m` e trafos com kVA incompatível
  com a carga reportados (e opcionalmente truncados) — hoje ficam visíveis em
  `piores_barras`/`sobrecargas`.
- Rodar o `mode=daily` completo (24 h × DU/SA/DO) para curvas de tensão por trafo e para saber a hora
  crítica da transferência (o snapshot usa o pico das curvas).
- Master a partir do recorte GPKG (decisão 9), se a dependência do GDB inteiro incomodar.
