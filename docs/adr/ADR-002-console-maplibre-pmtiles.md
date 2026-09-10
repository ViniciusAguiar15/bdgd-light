# ADR-002 — Console do operador: MapLibre GL JS + PMTiles, publicado como site estático

| | |
|---|---|
| Status | **Aceita** (implementada na issue #4; confirma e detalha a decisão 8 da ADR-001, que fica como está — regra da revisão PR-05) |
| Data | 2026-09-10 |
| Origem | `docs/backlog/04-console-maplibre-pmtiles.md`, `docs/adr/ADR-001-stack.md` (decisão 8), `docs/review/PR-05.md`, `console/README.md` |
| Issue | #4 |

Mesmo formato da ADR-001: **contexto → decisão → consequências**, com os números medidos no cluster
de referência TQR (TQR0007 + TQR33859 + TQR33862; `docs/escopo-alimentadores.md`).

---

## 1. Mapa vetorial em MapLibre GL JS lendo um único `.pmtiles` por recorte

**Contexto.** O cluster TQR tem 1 924 trechos MT, 4 713 trechos BT, 2 664 postes, 1 759 postes com
UC e 162 chaves; um alimentador da Light inteiro passa fácil de 10 mil feições, e o console deve
mostrar vários. GeoJSON solto (Leaflet do protótipo) trava o navegador e não permite estilo por
atributo com zoom dependente. Um servidor de tiles (Martin, tegola, tileserver-gl) seria mais uma
peça a hospedar numa POC que roda em GitHub Pages.

**Decisão.** `console/` em Vite + TypeScript + **MapLibre GL JS 6** (ESM puro, licença BSD) com o
plugin **pmtiles** (`addProtocol("pmtiles", …)`), lendo um arquivo `.pmtiles` por recorte por HTTP
*range requests*. O arquivo é gerado por **`bdgd-light tiles`**: GPKG do recorte → GeoJSONSeq por
camada em EPSG:4326 → `tippecanoe` (`-L camada:arquivo`, `--generate-ids`,
`--drop-densest-as-needed`, zoom 9–16). Cada feição leva `tippecanoe.minzoom` por camada (SSDMT 9,
INTERLIGACOES 10, UNSEMT 11, UNTRMT/UNCRMT 12, SSDBT 13, UNSEBT/UCBT 14, PONNOT 15): o tronco MT
aparece primeiro e o detalhe BT só quando se aproxima.

**Consequências.** O cluster TQR vira **1,43 MB** em 11 *source-layers* em 1,4 s; o mapa abre em
< 1 s local e renderiza ~8 800 feições no zoom 14 sem servidor. Dependência externa de build:
`tippecanoe` (`brew install tippecanoe` / `apt install tippecanoe`); sem ele, `--geojson-only`
deixa os GeoJSON prontos e a mensagem de erro diz como instalar. O `pmtiles` do console é
Python-independente: quem tem só o arquivo consegue abrir o mapa.

## 2. Atributos de estilo pré-calculados no `bdgd-light tiles`, não no navegador

**Contexto.** A simbologia do operador precisa de informação que está em **outras** camadas da
BDGD: a tensão do trecho vem de `CTMT.TEN_NOM` (código → kV pelo catálogo), "é tie" vem da camada
`INTERLIGACOES` do recorte, o nº de UC por trafo vem de `UCBT_tab.UNI_TR_MT`, e as UCBT não têm
geometria própria (só `PN_CON` → `PONNOT`). Juntar isso no cliente exigiria baixar tabelas inteiras.

**Decisão.** `ingest/tiles.py` deriva, na exportação, as colunas que o estilo usa: SSDMT
`TEN_KV`/`NOME_CTMT`; UNSEMT `TIPO` (texto do `TIP_UNID`), `TIE`, `CTMT_VIZ`, `EM_SUB`; UNTRMT
`N_UCBT`; e a camada derivada **`UCBT`** = `UCBT_tab` agrupada por `PN_CON` com `N_UC` e classe
predominante, sobre a geometria de `PONNOT`. O estilo (`console/src/camadas.ts`) é declarativo sobre
essas colunas: cor por `step` em `TEN_KV` (13,2 kV laranja, 20 kV âmbar, 34,5 kV vermelho), ícones
de chave por `P_N_OPE`×`TLCD`×`TIE`, losango com rótulo do `CTMT_VIZ` nas ties, tamanho do trafo
por `POT_NOM`.

**Consequências.** As regras de junção ficam em um só lugar (Python, testado em
`tests/test_tiles.py` com a fixture sintética que tem uma tie geométrica RJO001↔RJO002) e o console
não sabe nada de BDGD além dos nomes das colunas. Mudou a regra de tie? Regera-se o `.pmtiles`.
Custo: o tile carrega alguns atributos redundantes (`NOME_CTMT` repetido em cada trecho) —
irrelevante em 1,4 MB.

## 3. Estado dinâmico como GeoJSON pequeno por cima dos tiles

**Contexto.** Os tiles são estáticos; a operação (falta, chaves abertas, restauração) muda a cada
decisão do agente e precisa aparecer no mapa sem regerar tiles.

**Decisão.** O console aceita `?estado=<url>` com o GeoJSON de `bdgd-light grafo --geojson`
(propriedades `camada`, `energizado`, `aberta`, `fonte`) e o desenha numa *source* GeoJSON própria
com camadas fixas (`LAYERS_ESTADO`): trechos desenergizados em vermelho, energizados por outra fonte
em verde, chaves abertas e trafos sem tensão destacados; o painel resume as contagens. Exemplo
versionado: `public/exemplos/estado_TQR0007_falta.geojson` (falta no trecho 254862954 de TQR0007:
409 trechos desenergizados, 25 chaves a abrir/fechar, 59 trafos sem tensão).

**Consequências.** O mesmo canal serve para o futuro estado em tempo (quase) real: basta o
back-end/agente publicar o GeoJSON (ou o console pedir por `fetch` periódico). A sobreposição é
GeoJSON porque é pequena (265 kB para um alimentador inteiro) e muda; a rede é PMTiles porque é
grande e estável.

## 4. Publicação estática pelo GitHub Pages, com guarda para repositório sem Pages

**Contexto.** O backlog pede o console publicado a partir de `main`. Ao tentar habilitar o Pages
(`gh api -X POST repos/…/pages -f build_type=workflow`) a API respondeu **422 "Your current plan
does not support GitHub Pages for this repository"**: o repositório é privado e o plano não inclui
Pages para privados.

**Decisão.** `.github/workflows/pages.yml` roda a cada push em `main` que toque `console/`: `npm ci`,
`npm run build` com `VITE_BASE=/<repo>/` e, **se `gh api repos/<repo>/pages` responder 200**,
`upload-pages-artifact` + `deploy-pages`; caso contrário só anexa `console-dist` como artefato e
emite um `::notice::`. O build também roda `tsc --noEmit`, então o workflow serve de CI do console
mesmo sem publicar. Fundos de mapa: Esri World Imagery (padrão) e OpenStreetMap, ambos serviços
públicos de terceiros com atribuição, sem chave de API.

**Consequências.** Quando o repositório ficar público (ou mudar de plano), basta *Settings › Pages ›
Source: GitHub Actions* e reexecutar o workflow — nada muda no código. Até lá o console roda local
(`npm run dev`) ou a partir do artefato. Fica registrado que a URL prevista é
`https://viniciusaguiar15.github.io/bdgd-light/`.

## 5. Verificação sem framework de testes de navegador

**Contexto.** Não há Playwright/Cypress no projeto e o bug mais grave do console (tiles vetoriais
que nunca aparecem porque o *worker* do maplibre-gl v6 não é empacotado pelo Vite) **não aparece
em `tsc` nem em `vite build`** — só no navegador.

**Decisão.** `console/scripts/smoke.mjs` (Node puro, sem dependências): abre o Chrome headless pelo
DevTools Protocol, carrega a URL, espera o mapa ficar ocioso, conta as feições vetoriais
renderizadas (`mapa.queryRenderedFeatures()`), captura erros de console/estilo e salva um PNG; sai
com 1 se não houver feições ou houver erros. `npm run smoke` no dev server ou no `vite preview`.
Em código, o *worker* é fixado com `setWorkerUrl(import "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url")`
(receita oficial para Vite).

**Consequências.** Verificação reproduzível em segundos com o Chrome que já existe na máquina, sem
adicionar 300 MB de navegadores ao `node_modules`. Não roda no CI do GitHub (sem Chrome garantido
nem GPU); fica como comando do mantenedor. Se o console crescer, a troca por Playwright é local ao
script.

## Alternativas descartadas

| Alternativa | Por que não |
|---|---|
| Leaflet + GeoJSON (protótipo) | não escala nem permite estilo vetorial por zoom/atributo |
| Servidor de tiles (Martin/tegola) | mais uma peça a hospedar; Pages é estático |
| MBTiles | precisa de servidor; PMTiles é o mesmo conteúdo em um arquivo com *range requests* |
| deck.gl / kepler.gl | ótimo para análise, pesado e sem simbologia cartográfica de operação |
| Mapbox GL JS | licença e token; MapLibre é o *fork* aberto com a mesma API |
| Calcular ties/tensão no navegador | exige baixar CTMT/INTERLIGACOES/UCBT_tab inteiras; regras ficam duplicadas |
| Playwright para o smoke | dependência pesada para uma verificação; CDP direto basta na POC |
