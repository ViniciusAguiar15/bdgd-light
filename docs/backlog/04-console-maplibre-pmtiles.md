---
title: "console: mapa MapLibre GL JS + PMTiles publicado no GitHub Pages"
labels: area:console, phase:F1, copilot
milestone: F1 Dados + mapa
---
## Contexto
O `index.html` atual usa Leaflet com GeoJSON arrastado; não escala para a rede inteira nem para
atualização de estado em tempo real.

## Tarefa
- Criar `console/` (Vite + TypeScript + MapLibre GL JS + pmtiles). Base: Esri World Imagery (com atribuição) e
  opção OSM. Camadas vetoriais lidas de arquivos `.pmtiles` (protocolo `pmtiles://`).
- Script `bdgd-light tiles --gpkg data/feeders/X.gpkg --out console/public/tiles/X.pmtiles` que exporta as
  camadas para GeoJSON (EPSG:4326) e chama `tippecanoe` (documentar instalação; falhar com mensagem
  clara se não estiver no PATH).
- Estilo por camada: SSDMT por tensão, SSDBT, UNTRMT (círculos), UNSEMT (ícone NA/NF), UCBT (pontos
  pequenos, só em zoom alto), SUB. Popup de atributos e painel lateral com toggle de camadas.
- Workflow `.github/workflows/pages.yml` que faz build do console e publica no GitHub Pages (tiles
  de exemplo pequenos podem ser commitados em `console/public/tiles/exemplo.pmtiles`, < 5 MB).

## Critérios de aceite
- [ ] `npm run dev` abre o mapa com o tile de exemplo.
- [ ] Pages publicado a partir de `main`.
- [ ] README do console com instruções.
