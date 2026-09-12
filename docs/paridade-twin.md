# Paridade do gêmeo: gpkg2dss × bdgd2opendss

## 1. Escopo e ambiente

- Oráculo tentado e usado com sucesso: `bdgd2opendss 1.2.5`.
- Comando de instalação executado nesta rodada: `uv sync --extra dev --extra twin`.
- Referência chamada pelo próprio projeto via `bdgd_light.twin.convert.converter()`, que aplica a correção idempotente `corrigir_bancos_monofasicos()` após o `bdgd2opendss` por causa do bug upstream já documentado em `docs/spike-opendss.md` (#35/#36).
- Fluxo comparado: `DU01` em `mode=snapshot` para 5 alimentadores reais da Light.

## 2. Alimentadores comparados

| CTMT | Origem na rodada 6 |
| --- | --- |
| `TQR0007` | generalização #91 / baseline histórico do gêmeo |
| `PDG33010` | sensibilidade #96 |
| `ALC683` | sensibilidade #96 |
| `BRR38521` | sensibilidade #96 |
| `TRS003` | GD no gêmeo #98/#99 |

## 3. Resultado numérico por alimentador

| CTMT | Barras MT | `|ΔV|` máx (pu) | `|ΔV|` médio (pu) | Δ perdas (kW) | Δ corrente de saída (A) | Linhas | Trafos | Cargas | Veredito |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `TQR0007` | 2148 | 4.292e-08 | 4.254e-08 | 0.000014 | 0.000002 | 6251/6251 | 82/82 | 12312/12312 | paridade operacional |
| `PDG33010` | 1491 | 4.292e-08 | 4.271e-08 | 0.000011 | 0.000002 | 2110/2110 | 54/54 | 6274/6274 | paridade operacional |
| `ALC683` | 471 | 4.292e-08 | 4.291e-08 | 0.000001 | 0.000000 | 533/533 | 14/14 | 1966/1966 | paridade operacional |
| `BRR38521` | 2052 | 4.292e-08 | 4.276e-08 | 0.000008 | 0.000001 | 10436/10436 | 123/123 | 9346/9346 | paridade operacional |
| `TRS003` | 2325 | 4.292e-08 | 4.269e-08 | 0.000008 | 0.000002 | 3624/3624 | 96/96 | 4398/4398 | paridade operacional |

## 4. Divergências encontradas e causa nomeada

- **Tensões por barra.** Nenhum dos casos comparados passou de 1 % de diferença. O pior caso foi `TQR0007` com `|ΔV|` máx = `4.292e-08 pu`, muito abaixo do limiar da issue. Portanto, **não houve divergência elétrica relevante de tensão para explicar** nesta amostra.
- **Perdas totais.** O maior desvio absoluto foi em `TQR0007`: `0.000014 kW`. Isso é ruído numérico de serialização/float entre arquivos DSS equivalentes; não apareceu padrão sistemático por alimentador.
- **Corrente no disjuntor da saída.** O maior desvio absoluto foi em `TQR0007`: `0.000002 A`, novamente em ordem de arredondamento, sem efeito operacional.
- **Contagem de elementos do circuito ativo.** `Line`, `Transformer`, `Load`, `Reactor` e `Vsource` bateram em todos os 5 alimentadores; logo, o circuito compilado do caso base foi o mesmo dos dois lados.
- **Diferenças fora do circuito ativo (esperadas).** O `bdgd2opendss` escreve o catálogo completo de `CodCondutor` e `CurvaCarga`, além do arquivo `GD_BT`, enquanto o `gpkg2dss` grava só os códigos/curvas usados no CTMT e mantém a GD fora do Master base por padrão. Essa divergência é **de empacotamento**, não de modelagem do fluxo base.

### 4.1 Catálogos e arquivos auxiliares

| CTMT | `CodCondutor` (`gpkg/ref`) | `CurvaCarga` (`gpkg/ref`) | `GD_BT` no oráculo | Causa nomeada |
| --- | ---: | ---: | ---: | --- |
| `TQR0007` | 428/4892 | 42/132 | 118 | catálogo completo no oráculo; catálogo podado + GD fora do Master no gpkg2dss |
| `PDG33010` | 420/4892 | 39/132 | 91 | catálogo completo no oráculo; catálogo podado + GD fora do Master no gpkg2dss |
| `ALC683` | 188/4892 | 30/132 | 15 | catálogo completo no oráculo; catálogo podado + GD fora do Master no gpkg2dss |
| `BRR38521` | 376/4892 | 36/132 | 9 | catálogo completo no oráculo; catálogo podado + GD fora do Master no gpkg2dss |
| `TRS003` | 372/4892 | 51/132 | 50 | catálogo completo no oráculo; catálogo podado + GD fora do Master no gpkg2dss |

## 5. Achados do cadastro que merecem atenção futura

Os avisos abaixo não geraram divergência > 1 % nesta amostra, mas são os pontos do nosso código/dado com maior potencial de diferença em comparações futuras:

- `TQR0007`:
  - TQR0007: 10 ramais RAMLIG com mais de 300 m (maior: 567952367, 943 m, 59 UC) — provável circuito BT cadastrado como ramal
  - TQR0007: 6 trafos com >= 90% das UC monofásicas na mesma fase (11072871 (121 de 125 UC monofásicas em A), 11071545 (120 de 120 UC monofásicas em A), 11072145 (42 de 42 UC monofásicas em A)) — desequilíbrio da BDGD que exige o estabilizador vminpu=0.9 no fluxo (issue #44)
- `PDG33010`:
  - PDG33010: 1 ramais RAMLIG com mais de 300 m (maior: 295735927, 558 m, 42 UC) — provável circuito BT cadastrado como ramal
  - PDG33010: 2 trafos com >= 90% das UC monofásicas na mesma fase (133290308TZ155475 (47 de 47 UC monofásicas em A), 10990103 (32 de 32 UC monofásicas em A)) — desequilíbrio da BDGD que exige o estabilizador vminpu=0.9 no fluxo (issue #44)
- `ALC683`:
  - ALC683: 1 trafos com >= 90% das UC monofásicas na mesma fase (10910581 (62 de 64 UC monofásicas em B)) — desequilíbrio da BDGD que exige o estabilizador vminpu=0.9 no fluxo (issue #44)
- `BRR38521`:
  - BRR38521: 1 ramais RAMLIG com mais de 300 m (maior: 782958424, 566 m, 20 UC) — provável circuito BT cadastrado como ramal
  - BRR38521: 17 trafos com >= 90% das UC monofásicas na mesma fase (488219617 (257 de 265 UC monofásicas em A), 487837606 (162 de 179 UC monofásicas em A), 487356512 (127 de 141 UC monofásicas em A)) — desequilíbrio da BDGD que exige o estabilizador vminpu=0.9 no fluxo (issue #44)
- `TRS003`:
  - TRS003: 2 ramais RAMLIG com mais de 300 m (maior: 833455003, 563 m, 15 UC) — provável circuito BT cadastrado como ramal
  - TRS003: 4 trafos com >= 90% das UC monofásicas na mesma fase (19740491 (50 de 53 UC monofásicas em B), 19642505 (45 de 45 UC monofásicas em A), 19741379 (26 de 26 UC monofásicas em A)) — desequilíbrio da BDGD que exige o estabilizador vminpu=0.9 no fluxo (issue #44)

## 6. Veredito

Para o **fluxo base DU01 sem GD**, o `gpkg2dss` pode ser usado **com confiança** nesta amostra de 5 alimentadores reais: tensões MT, perdas totais, corrente no disjuntor e contagem ativa de elementos ficaram em paridade prática com o `bdgd2opendss`.

O que **ainda não** dá para afirmar com a mesma força, e precisa de rodada futura se virar requisito formal:

- paridade bruta contra o upstream **sem** a correção local dos bancos monofásicos;
- paridade com reguladores (`UNREMT`) em bases que realmente os usem;
- paridade em cenários com GD ligada no Master.

Conclusão honesta desta issue: **há paridade operacional do caso base**, mas o escopo continua restrito ao fluxo base sem GD e à referência já saneada pelo patch local do projeto.
