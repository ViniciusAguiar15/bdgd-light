# Generalização do pipeline em alimentador nunca visto

## Escopo e método

A issue #91 mede se o pipeline determinístico do projeto roda, sem ajuste manual, em um
alimentador nunca usado na demo. O universo foi o inventário versionado em `data/inventario_ctmt.csv`,
restrito ao município do Rio de Janeiro (`MUN = 3304557`).

Configuração da rodada:

- amostra: **30 CTMTs**;
- semente fixa: **91**;
- estratificação: **região × porte**, onde região vem do centróide do `bbox` do inventário (mesmas
  referências de `scripts/regioes_inventario.py`) e porte vem dos tercis do número de trechos
  `SSDMT` em `data/parquet/SSDMT.parquet`;
- dia/mês do gêmeo: **DU/01**;
- quando o CTMT sorteado tem vizinhos no inventário, o script inclui automaticamente o alimentador
  principal e seus vizinhos diretos no recorte/cluster para que `restore_options(score=true)` seja
  avaliado no gêmeo sem intervenção manual.

Comando usado nesta rodada:

```bash
uv run python scripts/generalizacao.py \
  --n 30 \
  --seed 91 \
  --inventario data/inventario_ctmt.csv \
  --parquet data/parquet \
  --out docs/bench/2026-09-11-generalizacao.csv \
  --workdir scratch/issue-91-generalizacao \
  --manter-workdir
```

CSV detalhado: [`docs/bench/2026-09-11-generalizacao.csv`](bench/2026-09-11-generalizacao.csv).

A mesma semente reproduz exatamente o mesmo conjunto de 30 CTMTs.

## Amostra sorteada

- regiões: Barra/Recreio 5, Botafogo/Humaitá 3, Centro 9, Copacabana/Leme 1,
  Flamengo/Catete 1, Ipanema/Leblon 4, Jacarepaguá/Taquara 2, Lapa/Glória 1, Méier 2, Tijuca 2;
- portes: P 9, M 11, G 10;
- CTMTs: `RCP33308`, `SAT1960`, `CBI24982`, `AVD33625`, `ITP00005`, `PDG33010`, `BPD9350`,
  `COP2700`, `LBN00061`, `PTS9310`, `FCN9735`, `SAT9793`, `ALC683`, `SMT30735`, `PDD33096`,
  `SAT1246`, `BRR37090`, `HMT0001`, `PTS9240`, `CMT1`, `BPD24726`, `BRR38521`, `SLZ30050`,
  `SAT4908`, `MKZ9030`, `SAT9358`, `AVD0001`, `TQR0007`, `BFG24599`, `PTS9775`.

## Tabela por etapa

| etapa | n | sucesso | falha | taxa de sucesso | motivo mais comum |
|---|---:|---:|---:|---:|---|
| recorte | 30 | 30 | 0 | 100,0% | — |
| grafo | 30 | 30 | 0 | 100,0% | — |
| gpkg2dss | 30 | 30 | 0 | 100,0% | — |
| fluxo_base | 30 | 30 | 0 | 100,0% | — |
| deteccao_ties | 30 | 30 | 0 | 100,0% | — |
| injecao_falta | 30 | 30 | 0 | 100,0% | — |
| restore_options | 30 | 30 | 0 | 100,0% | — |

### Falhas por etapa

Nenhuma etapa falhou nesta amostra. O CSV detalhado continua sendo a fonte canônica linha a linha,
com uma linha por `CTMT × etapa`.

## Resultado negativo que importa: tie não implica restauração viável

O fato de o pipeline executar não significa que todo alimentador tenha transferência de carga útil.
Nesta amostra:

- **18/30 (60,0%)** não tinham tie ligada ao CTMT sorteado para o recorte/falta analisados;
- **12/30 (40,0%)** tinham ao menos uma tie ligada ao CTMT sorteado;
- **7/30 (23,3%)** geraram pelo menos uma opção de restauração para a falta injetada no maior trecho
  do tronco;
- essas 7 execuções produziram **42** opções avaliadas no gêmeo, das quais **39** foram viáveis;
- **5/30 (16,7%)** tinham tie, mas **0** opção de restauração para a falta escolhida: `CBI24982`,
  `CMT1`, `BPD24726`, `TQR0007` e `BFG24599`.

### Casos com opções de restauração avaliadas

| CTMT | região | porte | ties | opções | viáveis |
|---|---|---|---:|---:|---:|
| BRR38521 | Barra/Recreio | G | 15 | 15 | 15 |
| AVD0001 | Barra/Recreio | G | 11 | 7 | 7 |
| ALC683 | Tijuca | P | 7 | 6 | 6 |
| PDG33010 | Jacarepaguá/Taquara | M | 7 | 7 | 5 |
| AVD33625 | Barra/Recreio | P | 5 | 4 | 4 |
| ITP00005 | Barra/Recreio | M | 2 | 2 | 1 |
| RCP33308 | Tijuca | G | 1 | 1 | 1 |

### Opções não viáveis no score elétrico

As **3** opções não viáveis apareceram em apenas dois CTMTs:

- `ITP00005`: 1 opção reprovada por **2 trechos MT acima de 100%**;
- `PDG33010`: 1 opção reprovada por **18 trechos MT acima de 100%**;
- `PDG33010`: 1 opção reprovada por **sobretensão MT (`Vmax = 1,962 pu`)** e por **1 trecho MT
  acima de 100%**.

## O que isso permite afirmar

- o pipeline **roda de ponta a ponta**, sem ajuste manual, em uma amostra estratificada de 30 CTMTs
  nunca usados na demo;
- o sorteio é **determinístico**: a mesma semente reproduz o mesmo conjunto de alimentadores;
- a expansão automática para `CTMT + vizinhos diretos` é suficiente para avaliar
  `restore_options(score=true)` quando a restauração depende de transferência por tie.

## O que isso não permite afirmar

- não permite dizer que a Light inteira é restaurável por transferência: **60,0%** da amostra não
  tinham tie útil no caso analisado e **16,7%** tinham tie mas nenhuma opção para a falta injetada;
- não permite dizer que “sucesso no fluxo base” significa “caso base eletricamente saudável”: nesta
  issue, a etapa `fluxo_base` mede **convergência operacional do pipeline**, não sanidade elétrica do
  caso base; isso virou follow-up em **#102**;
- não permite extrapolar para falhas fora do maior trecho do tronco, nem para combinações de múltiplas
  indisponibilidades, porque esta rodada testou apenas a falta determinística definida pela issue.
