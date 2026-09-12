# GD no gêmeo da Light

Relatório gerado por `scripts/gerar_gd_gemeo.py` com fluxo OpenDSS em `mode=daily`.

## 1. Premissas desta rodada

- Dia/mês do Master: **DU09**.
- Instantes representativos: **02:00** (madrugada), **12:00** (meio-dia) e **19:00** (ponta da noite).
- Carga segue as curvas `CRVCRG` já usadas pelo conversor; a GD solar entra como `PVSystem` com shape diário sintético de 0→1→0, e as fontes não solares entram como `Generator` com shape plano (1,0 nas 24 h).
- A **flag de GD permanece desligada por padrão**: os Masters base continuam sem `Redirect` de `GD_BT`; a comparação com GD usa um Master de cenário montado com `--gd`.
- Quando a MMGD tem chave direta (`CodEmpreendimento ↔ CEG_GD`), a injeção entra no **PAC da unidade geradora** (`UGBT_tab` / `UGMT_tab`).
- Quando a MMGD da Light não tem chave direta, o saldo é agregado **apenas por município** (limite já documentado na #97) e rateado: 1) entre CTMTs do município, proporcionalmente à carga cadastrada; 2) dentro do CTMT, por transformador BT e PAC MT.

## 2. Casos rodados

- Alimentadores comparados com números versionados:
  - `ALC9925` — cluster Tijuca — CABOFRIO
  - `RCP9882` — cluster Tijuca — AMALIA
  - `URG29983` — cluster Tijuca — BURLE MARX
  - `PTS9924` — cluster Ipanema — alimentador convergente
  - `PTS4022` — cluster Ipanema — alimentador convergente
  - `GDN0022` — alta penetração convergente na #97
  - `TRS003` — alta penetração convergente na #97
- Alimentadores de maior penetração rodados como diagnóstico de estabilidade:
  - `BRI001` — maior penetração da #97/#35
  - `SRD002` — segunda maior penetração da #97/#35
- Clusters completos: `tijuca`, `ipanema`, `taquara`.

## 3. Alocação da GD por alimentador

| CTMT | origem | empreend. exatos | kW exatos | empreend. agregados | kW agregados | critério | grupo agregado |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ALC9925 | cluster Tijuca — CABOFRIO | 29 | 225.860 | 5021 | 79.245 | municipio proporcional à carga | 3303500 / Nova Iguaçu (PVSystem); 3304557 / Rio de Janeiro (Generator); 3304557 / Rio de Janeiro (PVSystem) |
| RCP9882 | cluster Tijuca — AMALIA | 47 | 270.220 | 4574 | 76.018 | municipio proporcional à carga | 3304557 / Rio de Janeiro (Generator); 3304557 / Rio de Janeiro (PVSystem) |
| URG29983 | cluster Tijuca — BURLE MARX | 54 | 472.640 | 4574 | 60.516 | municipio proporcional à carga | 3304557 / Rio de Janeiro (Generator); 3304557 / Rio de Janeiro (PVSystem) |
| PTS9924 | cluster Ipanema — alimentador convergente | 0 | 0.000 | 4574 | 20.645 | municipio proporcional à carga | 3304557 / Rio de Janeiro (Generator); 3304557 / Rio de Janeiro (PVSystem) |
| PTS4022 | cluster Ipanema — alimentador convergente | 0 | 0.000 | 4574 | 25.274 | municipio proporcional à carga | 3304557 / Rio de Janeiro (Generator); 3304557 / Rio de Janeiro (PVSystem) |
| GDN0022 | alta penetração convergente na #97 | 2 | 29.580 | 4574 | 11.920 | municipio proporcional à carga | 3304557 / Rio de Janeiro (Generator); 3304557 / Rio de Janeiro (PVSystem) |
| TRS003 | alta penetração convergente na #97 | 53 | 2022.840 | 4884 | 123.165 | municipio proporcional à carga | 3301801 / Engenheiro Paulo de Frontin (PVSystem); 3303708 / Paraíba do Sul (PVSystem); 3303856 / Paty do Alferes (PVSystem); 3303955 / Pinheiral (PVSystem); 3304557 / Rio de Janeiro (Generator); 3304557 / Rio de Janeiro (PVSystem); 3306008 / Três Rios (PVSystem) |
| BRI001 | maior penetração da #97/#35 | 31 | 12165.250 | 203 | 1644.032 | municipio proporcional à carga | 3302007 / Itaguaí (PVSystem); 3304003 / Piraí (PVSystem); 3304409 / Rio Claro (PVSystem); 3305554 / Seropédica (Generator); 3305554 / Seropédica (PVSystem) |
| SRD002 | segunda maior penetração da #97/#35 | 134 | 15744.080 | 5604 | 4116.120 | municipio proporcional à carga | 3300308 / Barra do Piraí (PVSystem); 3301702 / Duque de Caxias (PVSystem); 3302007 / Itaguaí (PVSystem); 3303500 / Nova Iguaçu (PVSystem); 3304128 / Quatis (PVSystem); 3304557 / Rio de Janeiro (Generator); 3304557 / Rio de Janeiro (PVSystem); 3305554 / Seropédica (Generator); 3305554 / Seropédica (PVSystem) |

## 4. Comparação com/sem GD — alimentadores versionados

| CTMT | instante | Vmax MT sem GD | barra sem GD | Vmax MT com GD | barra com GD | barras >1,05 sem GD | barras >1,05 com GD | sentido sem GD | sentido com GD | perdas sem GD kW | perdas com GD kW | Δ perdas kW |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALC9925 | madrugada | 1.045 | alc9925_mt_50905 | 1.045 | alc9925_mt_50905 | 0 | 0 | SE→rede | SE→rede | 59.104 | 59.028 | -0.076 |
| ALC9925 | meio_dia | 1.045 | alc9925_mt_50905 | 1.045 | alc9925_mt_50905 | 0 | 0 | SE→rede | SE→rede | 68.492 | 66.985 | -1.507 |
| ALC9925 | ponta_noite | 1.045 | alc9925_mt_50905 | 1.045 | alc9925_mt_50905 | 0 | 0 | SE→rede | SE→rede | 68.254 | 68.159 | -0.095 |
| RCP9882 | madrugada | 1.045 | rcp9882_mt_50508 | 1.045 | rcp9882_mt_50508 | 0 | 0 | SE→rede | SE→rede | 105.901 | 105.823 | -0.078 |
| RCP9882 | meio_dia | 1.045 | rcp9882_mt_50508 | 1.045 | rcp9882_mt_50508 | 0 | 0 | SE→rede | SE→rede | 123.513 | 111.062 | -12.451 |
| RCP9882 | ponta_noite | 1.045 | rcp9882_mt_50508 | 1.045 | rcp9882_mt_50508 | 0 | 0 | SE→rede | SE→rede | 126.703 | 126.608 | -0.095 |
| URG29983 | madrugada | 1.045 | urg29983_mt_50724 | 1.045 | urg29983_mt_50724 | 0 | 0 | SE→rede | SE→rede | 52.420 | 52.329 | -0.092 |
| URG29983 | meio_dia | 1.045 | urg29983_mt_50724 | 1.045 | urg29983_mt_50724 | 0 | 0 | SE→rede | SE→rede | 70.934 | 69.892 | -1.042 |
| URG29983 | ponta_noite | 1.045 | urg29983_mt_50724 | 1.045 | urg29983_mt_50724 | 0 | 0 | SE→rede | SE→rede | 64.682 | 64.561 | -0.121 |
| PTS9924 | madrugada | 1.045 | 11309683_2 | 1.045 | 11309683_2 | 0 | 0 | SE→rede | SE→rede | 28.036 | 28.026 | -0.010 |
| PTS9924 | meio_dia | 1.045 | 11309683_2 | 1.045 | 11309683_2 | 0 | 0 | SE→rede | SE→rede | 32.028 | 31.923 | -0.105 |
| PTS9924 | ponta_noite | 1.045 | 11309683_2 | 1.045 | 11309683_2 | 0 | 0 | SE→rede | SE→rede | 32.817 | 32.804 | -0.014 |
| PTS4022 | madrugada | 1.045 | pts4022_mt_51335 | 1.045 | pts4022_mt_51335 | 0 | 0 | SE→rede | SE→rede | 0.699 | 0.695 | -0.004 |
| PTS4022 | meio_dia | 1.045 | pts4022_mt_51335 | 1.045 | pts4022_mt_51335 | 0 | 0 | SE→rede | SE→rede | 1.632 | 1.578 | -0.053 |
| PTS4022 | ponta_noite | 1.045 | pts4022_mt_51335 | 1.045 | pts4022_mt_51335 | 0 | 0 | SE→rede | SE→rede | 1.210 | 1.204 | -0.006 |
| GDN0022 | madrugada | 1.045 | gdn0022_mt_52909 | 1.045 | gdn0022_mt_52909 | 0 | 0 | SE→rede | SE→rede | 1.311 | 1.248 | -0.063 |
| GDN0022 | meio_dia | 1.045 | gdn0022_mt_52909 | 1.045 | gdn0022_mt_52909 | 0 | 0 | SE→rede | SE→rede | 7.389 | 3.463 | -3.926 |
| GDN0022 | ponta_noite | 1.045 | gdn0022_mt_52909 | 1.045 | gdn0022_mt_52909 | 0 | 0 | SE→rede | SE→rede | 4.313 | 4.183 | -0.130 |
| TRS003 | madrugada | 1.045 | trs003_mt_52975 | 1.045 | trs003_mt_367535 | 0 | 0 | SE→rede | SE→rede | 72.176 | 35.910 | -36.266 |
| TRS003 | meio_dia | 1.045 | trs003_mt_52975 | 1.045 | trs003_mt_52975 | 0 | 0 | SE→rede | SE→rede | 96.787 | 96.468 | -0.318 |
| TRS003 | ponta_noite | 1.045 | trs003_mt_52975 | 1.045 | trs003_mt_367535 | 0 | 0 | SE→rede | SE→rede | 92.608 | 35.910 | -56.699 |

## 5. Maiores penetrações e clusters — estabilidade do modelo

| grupo | caso | instante | status sem GD | status com GD | Vmax MT sem GD | Vmax MT com GD | Δ kW na saída |
| --- | --- | --- | --- | --- | --- | --- | --- |
| alimentador | BRI001 | madrugada | ok | ok | 1.045 | 1.046 | -2672.368 |
| alimentador | BRI001 | meio_dia | não convergiu | não convergiu | nan | nan | nan |
| alimentador | BRI001 | ponta_noite | ok | ok | 1.045 | 1.046 | -7301.744 |
| alimentador | SRD002 | madrugada | ok | ok | 1.045 | 1.046 | -1784.493 |
| alimentador | SRD002 | meio_dia | ok | não convergiu | 1.045 | nan | nan |
| alimentador | SRD002 | ponta_noite | ok | ok | 1.045 | 1.046 | -2071.100 |
| cluster | tijuca | madrugada | ok | instável numericamente | 1.045 | 1.045 | nan |
| cluster | tijuca | meio_dia | ok | ok | 1.045 | 1.045 | -1349.168 |
| cluster | tijuca | ponta_noite | ok | instável numericamente | 1.045 | 1.045 | nan |
| cluster | ipanema | madrugada | ok | não convergiu | 1.045 | 1.045 | nan |
| cluster | ipanema | meio_dia | ok | não convergiu | 1.045 | 6898928431465636970364339811293060162556423047109191628557924223672365134794280734786096774976147687136449842239357879564390003977893183488.000 | nan |
| cluster | ipanema | ponta_noite | ok | não convergiu | 1.045 | 427200279053438244646053974188802568297019155760402216508439150842871161113018618135401256761996087450751372191858688.000 | nan |
| cluster | taquara | madrugada | ok | ok | 1.045 | 1.045 | -4587.315 |
| cluster | taquara | meio_dia | ok | não convergiu | 1.045 | nan | nan |
| cluster | taquara | ponta_noite | ok | ok | 1.045 | 1.045 | -5507.310 |

## 6. Leitura

- Nesta rodada, a GD alterou perdas e carregamento, mas **não** gerou sobretensão MT > 1,05 pu nem fluxo reverso nos alimentadores versionados.
- Maiores elevações de Vmax MT ao meio-dia: `ALC9925` +0.000 pu (alc9925_mt_50905); `GDN0022` +0.000 pu (gdn0022_mt_52909); `URG29983` +0.000 pu (urg29983_mt_50724).
- Nenhum dos alimentadores versionados inverteu o fluxo no disjuntor de saída neste recorte temporal.
- Casos ainda instáveis nesta base: `BRI001`/meio_dia (não convergiu → não convergiu), `SRD002`/meio_dia (ok → não convergiu), `tijuca`/madrugada (ok → instável numericamente), `tijuca`/ponta_noite (ok → instável numericamente), `ipanema`/madrugada (ok → não convergiu), `ipanema`/meio_dia (ok → não convergiu), `ipanema`/ponta_noite (ok → não convergiu), `taquara`/meio_dia (ok → não convergiu).
- Limitação importante: o saldo sem chave direta da MMGD continua sendo **municipal**, não por CTMT. Isso evita inventar precisão inexistente, mas ainda pode suavizar picos locais dentro do município.

## 7. Reprodução

```bash
uv run python scripts/gerar_gd_gemeo.py \
  --parquet-dir data/parquet \
  --mmgd data/gd/empreendimento-geracao-distribuida.parquet \
  --out docs/gd-gemeo.md
```
