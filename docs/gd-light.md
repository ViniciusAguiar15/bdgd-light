# GD na Light a partir da MMGD ANEEL

Relatório gerado por `scripts/gerar_gd_light.py` a partir da MMGD pública da ANEEL e de
`data/parquet` da BDGD Light.

## 1. Fonte usada nesta execução

- Extraído em (`data/gd/metadata.json`): **2026-09-11T22:17:57-03:00**.
- Distribuidora filtrada: **LIGHT SERVICOS DE ELETRICIDADE S A** (`NumCNPJDistribuidora = 60444437000146`, `SigUF = RJ`).
- Data de geração do conjunto MMGD (`DatGeracaoConjuntoDados`): **2026-09-11**.
- Período de referência (`AnmPeriodoReferencia`): **09/2026**.
- Linhas MMGD Light filtradas: **64.233** empreendimentos, **843.404,78 kW**.

Campos do dicionário PDF v2.3 efetivamente usados no pipeline:

- junção: `CodEmpreendimento` (MMGD) ↔ `CEG_GD` (BDGD `UGBT_tab` / `UGMT_tab`);
- potência: `MdaPotenciaInstaladaKW` (MMGD) e `POT_INST` (BDGD);
- classe/subgrupo: `DscClasseConsumo`, `DscSubGrupoTarifario`;
- fonte: `SigTipoGeracao`, `DscFonteGeracao`;
- campo temporal disponível: `DthAtualizaCadastralEmpreend`.

> O dicionário PDF v2.3 expõe como único campo temporal do arquivo `DthAtualizaCadastralEmpreend`. Apesar do texto descritivo citar 'data da conexão', não há outra coluna temporal no Parquet; a evolução anual abaixo usa exatamente esse campo.

## 2. Chave de junção encontrada — e onde ela não basta

- **Há chave direta** para boa parte da base: `CodEmpreendimento` ↔ `CEG_GD`.
- Matches exatos MMGD → BDGD: **56.941 / 64.233 = 88,65 %**, cobrindo **699.667,12 / 843.404,78 kW = 82,96 %**.
- Sem match direto na MMGD: **7.292** empreendimentos e **143.737,66 kW**.
- Linhas BDGD sem `CEG_GD` preenchido: **1.197**, somando **92.199,47 kW**.
- CEGs repetidos no mesmo CTMT (anomalia BT/MT da própria BDGD): **3**.
- CEGs apontando para mais de um CTMT: **0**.

Evidência negativa importante: o arquivo MMGD **não traz** `CTMT`, `UNI_TR_MT`,
código da UC beneficiária ou outro identificador elétrico fino. Quando
`CodEmpreendimento` não casa com `CEG_GD`, a agregação honesta restante é
**por município**; qualquer rateio por alimentador
seria inventar precisão que o dado não oferece.

## 3. Divergência global entre MMGD e BDGD

- BDGD (`UGBT_tab` + `UGMT_tab`, após deduplicar repetição idêntica BT/MT): **58.190** linhas, **870.756,92 kW**.
- BDGD com `CEG_GD` presente também na MMGD: **56.941** linhas, **715.091,44 kW**.
- BDGD sem correspondência na MMGD (inclui `CEG_GD` vazio): **1.249** linhas, **155.665,48 kW**.

Essa divergência é, ela própria, um resultado sobre defasagem e qualidade
cadastral entre a
foto anual da BDGD e a base MMGD mais recente.

## 4. Potência por alimentador (somente matches exatos)

A tabela abaixo mostra onde a junção é direta. `penetração_gd_pct = potência MMGD exata ÷
carga instalada do alimentador (kVA_instalado da BDGD)`.

| COD_ID | NOME | CONJ_NOME | empreendimentos_mmgd | potencia_kw_mmgd | kW_DER | penetracao_gd_pct | fonte_predominante |
|---|---|---|---|---|---|---|---|
| CEN002 | LSA CAMBARA | CENTENARIO AEREO AT/MT | 572 | 19.593,27 | 24.577,25 | 19,12 % | UFV — Radiação solar |
| SRD002 | LSA RADIO | SEROPEDICA AEREO | 134 | 15.744,08 | 16.250,64 | 45,47 % | UFV — Radiação solar |
| CEN003 | LSA QUIRINO | CENTENARIO AEREO MT/MT | 285 | 13.418,23 | 21.551,35 | 15,19 % | UFV — Radiação solar |
| BRI001 | LSA SAMBAR | BRISA MAR | 31 | 12.165,25 | 15.464,22 | 59,18 % | UFV — Radiação solar |
| TRS014 | LSA INEMA | TRES RIOS AEREO AT/MT | 345 | 11.319,39 | 12.344,45 | 15,05 % | UFV — Radiação solar |
| INF0003 | LSA CARMENSE I | SAPUCAIA | 246 | 10.729,31 | 14.839,85 | 26,04 % | UFV — Radiação solar |
| BRI00005 | LSA ZELITUS | BRISA MAR | 159 | 9.151,15 | 11.021,21 | 27,77 % | UFV — Radiação solar |
| TRS011 | LSA BASTILHA | TRES RIOS AEREO MT/MT | 110 | 9.021,28 | 9.375,48 | 28,04 % | UFV — Radiação solar |
| TRS013 | LSA DONCARLOS | TRES RIOS AEREO MT/MT | 178 | 7.760,40 | 9.032,20 | 17,67 % | UFV — Radiação solar |
| SCI006 | LSA TAMANDARE | SANTA CECILIA AEREO MT/MT | 222 | 7.551,36 | 14.746,71 | 14,38 % | UFV — Radiação solar |
| VRD021 | LSA VOTORANTIM | VOLTA REDONDA AEREO MT/MT | 207 | 7.431,19 | 7.558,68 | 25,17 % | UFV — Radiação solar |
| CEN006 | LSA SAO ROQUE | CENTENARIO AEREO MT/MT | 72 | 7.323,91 | 12.472,17 | 30,85 % | UFV — Radiação solar |
| SPC001 | LSA PORTONOVO | SAPUCAIA | 162 | 6.134,73 | 7.767,95 | 11,90 % | UFV — Radiação solar |
| INF0005 | LSA JACUBA | SAPUCAIA | 132 | 5.875,16 | 6.107,32 | 38,87 % | UFV — Radiação solar |
| CEN004 | LSA CARVALHEIRA | CENTENARIO AEREO AT/MT | 243 | 5.198,96 | 5.756,93 | 10,57 % | UFV — Radiação solar |
| VIG001 | LSA PADILHA | VIGARIO | 109 | 5.035,72 | 10.139,40 | 18,93 % | UFV — Radiação solar |
| CEN005 | LSA MATACAES | CENTENARIO AEREO MT/MT | 165 | 4.656,37 | 8.483,41 | 9,55 % | UFV — Radiação solar |
| SRD0005 | LSA RODUTRA | SEROPEDICA AEREO | 105 | 4.610,97 | 4.999,64 | 9,87 % | UFV — Radiação solar |
| VRD015 | LSA JAPUIRA | VOLTA REDONDA AEREO MT/MT | 86 | 4.495,97 | 4.696,30 | 13,01 % | UFV — Radiação solar |
| ESP018 | LSA FRAMBEL | ESPERANCA AEREO MT/MT | 120 | 4.383,65 | 6.060,70 | 14,44 % | UFV — Radiação solar |

## 5. Potência por conjunto (somente matches exatos)

| CONJ_CODIGO | CONJ_NOME | alimentadores | empreendimentos_mmgd | potencia_kw_mmgd | potencia_kw_bdgd_total | penetracao_gd_pct | fonte_predominante |
|---|---|---|---|---|---|---|---|
| 15074 | CENTENARIO AEREO AT/MT | 3 | 1089 | 27.327,62 | 43.647,98 | 13,25 % | UFV — Radiação solar |
| 15091 | SAPUCAIA | 5 | 643 | 26.655,50 | 35.478,37 | 20,13 % | UFV — Radiação solar |
| 15043 | SEROPEDICA AEREO | 7 | 697 | 26.587,73 | 32.325,74 | 11,65 % | UFV — Radiação solar |
| 15089 | CENTENARIO AEREO MT/MT | 3 | 522 | 25.398,51 | 42.506,93 | 15,79 % | UFV — Radiação solar |
| 15006 | BRISA MAR | 4 | 335 | 22.513,83 | 27.850,06 | 25,84 % | UFV — Radiação solar |
| 15090 | SANTA CECILIA AEREO MT/MT | 6 | 537 | 22.508,33 | 37.508,95 | 14,45 % | UFV — Radiação solar |
| 15087 | TRES RIOS AEREO AT/MT | 9 | 805 | 21.908,95 | 23.791,35 | 14,89 % | UFV — Radiação solar |
| 15088 | TRES RIOS AEREO MT/MT | 4 | 418 | 20.689,90 | 22.924,66 | 19,18 % | UFV — Radiação solar |
| 14999 | RECREIO | 17 | 2512 | 20.564,46 | 23.500,69 | 10,91 % | UFV — Radiação solar |
| 16902 | PORTA DAGUA AEREO | 23 | 2552 | 19.965,15 | 36.997,28 | 8,31 % | UFV — Radiação solar |
| 15029 | JABOATAO AEREO | 23 | 2533 | 18.233,75 | 18.498,36 | 9,42 % | UFV — Radiação solar |
| 15086 | VOLTA REDONDA AEREO MT/MT | 4 | 666 | 16.934,20 | 30.673,63 | 11,83 % | UFV — Radiação solar |
| 15023 | TAQUARA AEREO | 21 | 1766 | 14.935,21 | 20.759,72 | 7,79 % | UFV — Radiação solar |
| 15011 | CACHAMORRA | 19 | 1930 | 14.576,72 | 15.128,22 | 9,08 % | UFV — Radiação solar |
| 15004 | ALVORADA | 26 | 1021 | 13.243,14 | 13.520,19 | 8,51 % | UFV — Radiação solar |

## 6. Evolução anual pelo campo temporal disponível

| ano | empreendimentos | potencia_kw |
|---|---|---|
| 2010 | 1 | 6,00 |
| 2013 | 5 | 28,70 |
| 2014 | 12 | 434,30 |
| 2015 | 77 | 502,11 |
| 2016 | 261 | 1.546,34 |
| 2017 | 469 | 3.749,00 |
| 2018 | 956 | 12.722,74 |
| 2019 | 2168 | 28.686,51 |
| 2020 | 2872 | 40.589,85 |
| 2021 | 6187 | 80.774,45 |
| 2022 | 11991 | 138.146,71 |
| 2023 | 10065 | 175.743,81 |
| 2024 | 11737 | 153.186,08 |
| 2025 | 12714 | 144.047,60 |
| 2026 | 4718 | 63.240,58 |

## 7. Saldo sem chave direta — agregado só onde o dado permite

| cod_municipio_ibge | municipio | empreendimentos_sem_chave | potencia_kw_sem_chave | alimentadores_bdgd | conjuntos_bdgd |
|---|---|---|---|---|---|
| 3304557 | Rio de Janeiro | 4574 | 57.534,68 | 1406 | 77 |
| 3305554 | Seropédica | 48 | 11.765,45 | 5 | 1 |
| 3302007 | Itaguaí | 104 | 9.174,88 | 15 | 3 |
| 3306206 | Vassouras | 35 | 7.011,48 | 6 | 2 |
| 3304508 | Rio das Flores | 9 | 6.862,90 | 0 | 0 |
| 3303500 | Nova Iguaçu | 447 | 5.268,44 | 76 | 7 |
| 3301702 | Duque de Caxias | 344 | 5.202,02 | 78 | 7 |
| 3306305 | Volta Redonda | 330 | 4.385,35 | 33 | 4 |
| 3302908 | Miguel Pereira | 57 | 4.327,66 | 0 | 0 |
| 3302270 | Japeri | 21 | 4.206,00 | 0 | 0 |
| 3300407 | Barra Mansa | 190 | 4.056,20 | 16 | 2 |
| 3303708 | Paraíba do Sul | 65 | 3.495,17 | 0 | 0 |
| 3303856 | Paty do Alferes | 70 | 3.048,98 | 0 | 0 |
| 3300308 | Barra do Piraí | 76 | 2.553,14 | 8 | 2 |
| 3302809 | Mendes | 11 | 2.243,28 | 0 | 0 |

## 8. Maiores divergências de potência na mesma chave

| CodEmpreendimento | Municipio | CTMT | PotenciaKW_MMGD | PotenciaKW_BDGD | DeltaKW_MMGD_menos_BDGD |
|---|---|---|---|---|---|
| GD.RJ.001.182.928 | Duque de Caxias | CXS007 | 7,00 | 7.000,00 | -6.993,00 |
| GD.RJ.001.182.929 | Rio de Janeiro | TQR33830 | 5,00 | 5.000,00 | -4.995,00 |
| GD.RJ.000.329.177 | Paraíba do Sul | TRS014 | 1.000,00 | 72,00 | 928,00 |
| GD.RJ.000.137.042 | Nova Iguaçu | ABR009 | 6,00 | 360,00 | -354,00 |
| GD.RJ.000.189.525 | Rio de Janeiro | FND3262 | 3,96 | 330,00 | -326,04 |
| GD.RJ.000.069.645 | Três Rios | TRS008 | 8,20 | 330,00 | -321,80 |
| GD.RJ.000.088.513 | Rio das Flores | CEN003 | 750,00 | 1.000,00 | -250,00 |
| GD.RJ.001.916.343 | Rio de Janeiro | CCD3348 | 35,20 | 259,96 | -224,76 |
| GD.RJ.000.350.494 | Rio de Janeiro | AFR004 | 98,40 | 272,00 | -173,60 |
| GD.RJ.000.069.620 | Paraíba do Sul | TRS005 | 1,32 | 132,00 | -130,68 |
| GD.RJ.000.189.505 | Rio de Janeiro | HMT3144 | 147,00 | 30,00 | 117,00 |
| GD.RJ.000.056.790 | Volta Redonda | RTO002 | 20,00 | 105,00 | -85,00 |
| GD.RJ.000.001.386 | Miguel Pereira | CEN002 | 3,18 | 75,00 | -71,82 |
| GD.RJ.000.040.860 | Mesquita | NIG014 | 3,18 | 75,00 | -71,82 |
| GD.RJ.002.376.521 | Nova Iguaçu | RFR004 | 75,00 | 4,00 | 71,00 |

## 9. Arquivos auxiliares versionados

- `docs/dados/gd-light-alimentadores.csv`
- `docs/dados/gd-light-conjuntos.csv`
- `docs/dados/gd-light-evolucao-anual.csv`
- `docs/dados/gd-light-municipios-sem-chave.csv`
- `docs/dados/gd-light-divergencias.csv`

## 10. Reprodução

```bash
uv run python scripts/baixar_gd.py
uv run python scripts/gerar_gd_light.py \
  --mmgd data/gd/empreendimento-geracao-distribuida.parquet \
  --parquet-dir data/parquet \
  --out docs/gd-light.md
```
