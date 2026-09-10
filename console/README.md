# Console — mapa do alimentador (MapLibre GL JS + PMTiles)

Front-end estático do COD agêntico (issue #4): um mapa que lê **um arquivo `.pmtiles`** gerado por
`bdgd-light tiles` a partir do recorte de alimentadores e desenha a rede com a simbologia do
operador — tronco MT colorido por tensão, chaves NA/NF (telecomandadas em destaque), **ties** com o
CTMT vizinho, transformadores, BT, postes e unidades consumidoras agregadas por poste. Opcionalmente
sobrepõe o **estado do grafo** (`bdgd-light grafo --geojson`): trechos desenergizados, chaves
abertas e trafos sem tensão.

Sem servidor de tiles: PMTiles é um único arquivo lido por *range requests*, servível por qualquer
hospedagem estática (GitHub Pages inclusive). Decisões de projeto em
[`docs/adr/ADR-002-console-maplibre-pmtiles.md`](../docs/adr/ADR-002-console-maplibre-pmtiles.md).

## Rodar

```bash
cd console
npm ci                # Node ≥ 20 (testado com 22)
npm run dev           # http://localhost:5173 — abre o cenário Tijuca (public/tiles/exemplo_tijuca.pmtiles)
npm run build         # tsc --noEmit + vite build → dist/
npm run preview       # serve dist/ (use o mesmo VITE_BASE do build)
npm run smoke         # abre o Chrome headless (?cenario=tijuca), espera o mapa, conta feições e salva smoke.png
```

## Cenários da demo

O painel tem um seletor **Cenário** (`src/cenarios.ts`) que troca tiles, estado sobreposto e
enquadramento de uma vez (`?cenario=<id>`):

| id | cluster | tiles / estado | o que mostra |
|---|---|---|---|
| `tijuca` (padrão) | ALC9925, ALC9946, URG29983, RCP9882 — SEs Aldeia Campista, Uruguai e Rio Comprido | `exemplo_tijuca.pmtiles` (0,98 MB) / `estado_tijuca_falta.geojson` | falta no tronco de CABOFRIO (`11304252`): 4.036 UCBT desligados e três ties telecomandadas de restauração, uma por SE |
| `ipanema` | PTS0001, PTS9088, PTS9924, PTS4022 — SE Posto Seis (subterrâneo) | `exemplo_ipanema.pmtiles` (0,78 MB) / `estado_ipanema_falta.geojson` | falta no tronco de PTS0001 (`11409068`): cenário *negativo*, nenhuma chave NA de campo restaura |
| `taquara` | TQR0007, TQR33859, TQR33862 (regressão) | `exemplo.pmtiles` (1,4 MB) / `estado_TQR0007_falta.geojson` | falta em PARNAIBA (`254862954`), cenário da v2 |

Os arquivos vêm de `bdgd-light recortar` → `bdgd-light tiles` e `bdgd-light grafo --falha … --geojson`
(clusters em [`docs/escopo-cidade.md`](../docs/escopo-cidade.md)); `?tiles=` sem `?cenario=` abre
qualquer PMTiles sem estado, e `?estado=none` desliga o estado do cenário.

O `exemplo.pmtiles` (1,4 MB, versionado) é o cluster **TQR0007 + TQR33859 + TQR33862** de
`docs/escopo-alimentadores.md`; `public/exemplos/estado_TQR0007_falta.geojson` é a saída de
`bdgd-light grafo --falha 254862954` sobre TQR0007. Abra
`http://localhost:5173/?estado=exemplos/estado_TQR0007_falta.geojson#14/-22.9144/-43.4005` para ver
a falta simulada por cima dos tiles.

## Gerar tiles de outro recorte

```bash
uv run bdgd-light recortar --parquet data/parquet --ctmt TQR0007,TQR33859,TQR33862 --out data/feeders
uv run bdgd-light tiles --gpkg data/feeders/cluster_TQR0007-TQR33859-TQR33862.gpkg \
    --out console/public/tiles/TQR.pmtiles
# depois: http://localhost:5173/?tiles=tiles/TQR.pmtiles
```

`bdgd-light tiles` exporta cada camada geográfica do GPKG para GeoJSONSeq em EPSG:4326 (com os
atributos derivados que o estilo usa: `TEN_KV`, `NOME_CTMT`, `TIE`/`CTMT_VIZ`/`EM_SUB`, `N_UCBT`, e
a camada `UCBT` agregada por poste) e chama o [tippecanoe](https://github.com/felt/tippecanoe)
(`brew install tippecanoe`). Sem tippecanoe, `--geojson-only` deixa os GeoJSON prontos na pasta
`<out>_geojson/`.

## Parâmetros da URL

| Parâmetro | Exemplo | Efeito |
|---|---|---|
| `?cenario=` | `?cenario=ipanema` | cenário da demo (`tijuca` padrão, `ipanema`, `taquara`): tiles + estado + centro/zoom |
| `?tiles=` | `?tiles=tiles/TQR.pmtiles` ou uma URL absoluta | PMTiles a abrir (sem `?cenario=`, desliga o cenário padrão e enquadra o bbox); relativo à base do site |
| `?estado=` | `?estado=exemplos/estado_TQR0007_falta.geojson`, `?estado=none` | GeoJSON de `bdgd-light grafo --geojson` sobreposto (trechos vermelhos = desenergizados); `none` desliga o do cenário |
| `#z/lat/lon` | `#14/-22.9144/-43.4005` | posição do mapa (MapLibre `hash: true`); sem hash, usa o centro do cenário ou enquadra o bbox do PMTiles |

O painel lateral lista as camadas do PMTiles (`vector_layers` + contagens de `tilestats`) com
liga/desliga, troca o fundo (satélite Esri, OpenStreetMap ou fundo escuro sem base) e mostra os atributos da
feição clicada. Ties aparecem como losangos rotulados com o CTMT vizinho.

## Publicação (GitHub Pages)

`.github/workflows/pages.yml` roda a cada push em `main` que toque `console/` (e por
`workflow_dispatch`): `npm ci`, `npm run build` com `VITE_BASE=/bdgd-light/` e publica `dist/` em
**<https://viniciusaguiar15.github.io/bdgd-light/>** (Settings › Pages › Source: *GitHub Actions*,
habilitado em 2026-09-10). Se o Pages for desabilitado, o workflow só compila e anexa o artefato
`console-dist` à execução.

## Estrutura

```
console/
├── index.html            mapa + painel lateral
├── src/main.ts           protocolo pmtiles, estilo, popups, parâmetros da URL
├── src/cenarios.ts       cenários da demo (tiles + estado + centro/zoom por id)
├── src/camadas.ts        simbologia por camada da BDGD (cores por TEN_KV, chaves, ties, BT, UCBT)
├── src/icones.ts         ícones desenhados em canvas (chave NA/NF, telecomandada, tie, SE)
├── src/painel.ts         painel: cenários, camadas, fundo, atributos, resumo do estado
├── src/estado.ts         sobreposição do GeoJSON de `bdgd-light grafo`
├── scripts/smoke.mjs     smoke test via Chrome DevTools Protocol (sem dependências)
└── public/tiles/exemplo_{tijuca,ipanema}.pmtiles, exemplo.pmtiles (TQR);
    public/exemplos/estado_{tijuca,ipanema,TQR0007}_falta.geojson
```

## Armadilhas conhecidas

- **maplibre-gl v6 é ESM puro** e resolve o *worker* por `new URL('./maplibre-gl-worker.mjs',
  import.meta.url)`, que o Vite não empacota — sem `setWorkerUrl(workerUrl)` com
  `import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url"` o mapa abre e os
  tiles vetoriais **nunca aparecem** (o worker recebe o `index.html`).
- Expressões `match` não aceitam rótulos numéricos não inteiros; a cor por tensão usa `step` em
  `TEN_KV`.
- `vite preview` precisa do mesmo `VITE_BASE` do build; o servidor de desenvolvimento responde
  `index.html` para arquivos ausentes (SPA), então um `.pmtiles` com caminho errado aparece como
  "cabeçalho inválido" — o painel mostra a dica.
