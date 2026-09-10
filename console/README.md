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
npm run dev           # http://localhost:5173 — abre o cluster TQR de exemplo (public/tiles/exemplo.pmtiles)
npm run build         # tsc --noEmit + vite build → dist/
npm run preview       # serve dist/ (use o mesmo VITE_BASE do build)
npm run smoke         # abre o Chrome headless, espera o mapa, conta feições e salva smoke.png
```

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
| `?tiles=` | `?tiles=tiles/TQR.pmtiles` ou uma URL absoluta | PMTiles a abrir (padrão `tiles/exemplo.pmtiles`); relativo à base do site |
| `?estado=` | `?estado=exemplos/estado_TQR0007_falta.geojson` | GeoJSON de `bdgd-light grafo --geojson` sobreposto (trechos vermelhos = desenergizados) |
| `#z/lat/lon` | `#14/-22.9144/-43.4005` | posição do mapa (MapLibre `hash: true`); sem hash, enquadra o bbox do PMTiles |

O painel lateral lista as camadas do PMTiles (`vector_layers` + contagens de `tilestats`) com
liga/desliga, troca o fundo (satélite Esri, OpenStreetMap ou fundo escuro sem base) e mostra os atributos da
feição clicada. Ties aparecem como losangos rotulados com o CTMT vizinho.

## Publicação (GitHub Pages)

`.github/workflows/pages.yml` roda a cada push em `main` que toque `console/`: `npm ci`,
`npm run build` com `VITE_BASE=/bdgd-light/` e, **se o Pages estiver habilitado no repositório**,
publica `dist/` em `https://viniciusaguiar15.github.io/bdgd-light/`. Enquanto o repositório for
privado num plano sem Pages (a API devolve `422 Your current plan does not support GitHub Pages`),
o workflow só compila e anexa o artefato `console-dist` à execução. Para habilitar: tornar o repo
público (ou mudar de plano) → Settings › Pages › Source: *GitHub Actions* → reexecutar o workflow.

## Estrutura

```
console/
├── index.html            mapa + painel lateral
├── src/main.ts           protocolo pmtiles, estilo, popups, parâmetros da URL
├── src/camadas.ts        simbologia por camada da BDGD (cores por TEN_KV, chaves, ties, BT, UCBT)
├── src/icones.ts         ícones desenhados em canvas (chave NA/NF, telecomandada, tie, SE)
├── src/painel.ts         painel: camadas, fundo, atributos, resumo do estado
├── src/estado.ts         sobreposição do GeoJSON de `bdgd-light grafo`
├── scripts/smoke.mjs     smoke test via Chrome DevTools Protocol (sem dependências)
└── public/tiles/exemplo.pmtiles, public/exemplos/estado_TQR0007_falta.geojson
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
