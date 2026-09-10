/**
 * Console bdgd-light: MapLibre GL + PMTiles (sem servidor de tiles). Lê o PMTiles gerado por
 * `bdgd-light tiles`, monta o painel de camadas a partir do metadata e permite sobrepor o estado
 * do grafo (`?estado=`).
 *
 * Parâmetros de URL:
 *   ?tiles=tiles/X.pmtiles   caminho (relativo à base do site) ou URL absoluta do PMTiles
 *   ?estado=URL.geojson      GeoJSON de `bdgd-light grafo --geojson`
 */
import {
  addProtocol,
  Map as MapaLibre,
  NavigationControl,
  Popup,
  ScaleControl,
  type LayerSpecification,
  type MapGeoJSONFeature,
  setWorkerUrl,
  type ErrorEvent,
  type MapMouseEvent,
} from "maplibre-gl";
// maplibre-gl v6 é ESM com worker em arquivo separado; com bundler é preciso apontar a URL
// (receita oficial para Vite: `?worker&url` gera um chunk autocontido).
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { PMTiles, Protocol } from "pmtiles";
import "maplibre-gl/dist/maplibre-gl.css";
import "./style.css";
import { FONTE, GRUPOS, INTERATIVAS } from "./camadas";
import { carregarEstado } from "./estado";
import { registrarIcones } from "./icones";
import {
  formTiles,
  infoTiles,
  montarBases,
  montarCamadas,
  mostrarErro,
  subtitulo,
  type Base,
} from "./painel";

const TILES_PADRAO = "tiles/exemplo.pmtiles";
const GLIFOS = "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf";
const FONTE_TEXTO = ["Open Sans Semibold"];

const BASES: Base[] = [
  { id: "base-esri", titulo: "Satélite (Esri World Imagery)" },
  { id: "base-osm", titulo: "OpenStreetMap" },
  { id: "base-nenhuma", titulo: "Sem base (fundo escuro)" },
];

interface CamadaVetorial {
  id: string;
  fields?: Record<string, string>;
}

interface Metadata {
  name?: string;
  vector_layers?: CamadaVetorial[];
  tilestats?: { layers?: { layer: string; count: number }[] };
}

const params = new URLSearchParams(location.search);
const base = new URL(import.meta.env.BASE_URL, location.href);
const tilesParam = params.get("tiles") ?? TILES_PADRAO;
const tilesUrl = new URL(tilesParam, base).href;
const estadoParam = params.get("estado");

formTiles(tilesParam, (novo) => {
  const u = new URL(location.href);
  u.searchParams.set("tiles", novo || TILES_PADRAO);
  u.hash = "";
  location.href = u.href;
});

setWorkerUrl(workerUrl);

const protocolo = new Protocol();
addProtocol("pmtiles", protocolo.tile);
const pm = new PMTiles(tilesUrl);
protocolo.add(pm);

const mapa = new MapaLibre({
  container: "mapa",
  hash: true,
  center: [-43.33, -22.95],
  zoom: 10,
  minZoom: 8,
  maxZoom: 19,
  attributionControl: { compact: false },
  style: {
    version: 8,
    glyphs: GLIFOS,
    sources: {
      esri: {
        type: "raster",
        tiles: [
          "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        ],
        tileSize: 256,
        maxzoom: 19,
        attribution:
          "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
      },
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        maxzoom: 19,
        attribution: "© OpenStreetMap contributors",
      },
    },
    layers: [
      { id: "base-nenhuma", type: "background", paint: { "background-color": "#0b0e13" } },
      {
        id: "base-esri",
        type: "raster",
        source: "esri",
        paint: { "raster-saturation": -0.35, "raster-brightness-max": 0.85 },
      },
      { id: "base-osm", type: "raster", source: "osm", layout: { visibility: "none" } },
    ],
  },
});

// exposto para depuração no DevTools e para o smoke test (scripts/smoke.mjs)
(window as unknown as { mapa: MapaLibre }).mapa = mapa;
mapa.addControl(new NavigationControl({ visualizePitch: false }), "top-right");
mapa.addControl(new ScaleControl({ unit: "metric" }), "bottom-right");
montarBases(mapa, BASES, "base-esri");

function comFonteTexto(l: LayerSpecification): LayerSpecification {
  if (l.type === "symbol" && l.layout && "text-field" in l.layout)
    return { ...l, layout: { ...l.layout, "text-font": FONTE_TEXTO } };
  return l;
}

function fmtValor(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  return String(v);
}

function popupHtml(feats: MapGeoJSONFeature[]): string {
  const vistos = new Set<string>();
  const blocos: string[] = [];
  for (const f of feats) {
    const camada = f.sourceLayer ?? f.layer.id;
    const chave = `${camada}:${f.properties.COD_ID ?? f.id}`;
    if (vistos.has(chave)) continue;
    vistos.add(chave);
    const linhas = Object.entries(f.properties)
      .filter(([k]) => k !== "tippecanoe")
      .map(([k, v]) => `<tr><td>${k}</td><td>${fmtValor(v)}</td></tr>`)
      .join("");
    blocos.push(`<div class="popup"><h3>${camada}</h3><table>${linhas}</table></div>`);
    if (blocos.length >= 4) break;
  }
  return blocos.join("");
}

function dicaErroTiles(motivo: string): string {
  return (
    `Não foi possível abrir ${tilesUrl}\n${motivo}\n\n` +
    "Gere o arquivo com:\n  uv run bdgd-light tiles --gpkg data/feeders/<cluster>.gpkg " +
    "--out console/public/tiles/exemplo.pmtiles\nou aponte ?tiles= para outro PMTiles."
  );
}

async function carregarTiles() {
  let meta: Metadata = {};
  try {
    const cab = await pm.getHeader();
    meta = ((await pm.getMetadata()) as Metadata) ?? {};
    const nome = meta.name || tilesParam.split("/").pop() || "PMTiles";
    subtitulo(nome);
    infoTiles(
      `zoom ${cab.minZoom}–${cab.maxZoom} · bbox ${cab.minLon.toFixed(4)}, ${cab.minLat.toFixed(4)}, ` +
        `${cab.maxLon.toFixed(4)}, ${cab.maxLat.toFixed(4)}`,
    );
    if (!location.hash)
      mapa.fitBounds(
        [
          [cab.minLon, cab.minLat],
          [cab.maxLon, cab.maxLat],
        ],
        { padding: 24, duration: 0 },
      );
  } catch (e) {
    const motivo = e instanceof Error ? e.message : String(e);
    mostrarErro(dicaErroTiles(motivo));
    montarCamadas(mapa, new Set(), {});
    return;
  }

  const presentes = new Set((meta.vector_layers ?? []).map((v) => v.id));
  const contagens: Record<string, number> = {};
  for (const l of meta.tilestats?.layers ?? []) contagens[l.layer] = l.count;

  mapa.addSource(FONTE, { type: "vector", url: `pmtiles://${tilesUrl}` });
  for (const g of GRUPOS) {
    if (!presentes.has(g.id)) continue;
    for (const l of g.layers) {
      const spec = comFonteTexto(l);
      mapa.addLayer({
        ...spec,
        layout: { ...(spec.layout ?? {}), visibility: g.visivel ? "visible" : "none" },
      } as LayerSpecification);
    }
  }
  montarCamadas(mapa, presentes, contagens);

  const interativas = INTERATIVAS.filter((id) => mapa.getLayer(id));
  mapa.on("click", (ev: MapMouseEvent) => {
    const feats = mapa.queryRenderedFeatures(ev.point, { layers: interativas });
    if (!feats.length) return;
    new Popup({ maxWidth: "360px" })
      .setLngLat(ev.lngLat)
      .setHTML(popupHtml(feats))
      .addTo(mapa);
  });
  for (const id of interativas) {
    mapa.on("mouseenter", id, () => (mapa.getCanvas().style.cursor = "pointer"));
    mapa.on("mouseleave", id, () => (mapa.getCanvas().style.cursor = ""));
  }
}

mapa.on("load", async () => {
  registrarIcones(mapa);
  await carregarTiles();
  if (estadoParam) {
    try {
      await carregarEstado(mapa, new URL(estadoParam, base).href);
    } catch (e) {
      mostrarErro(e instanceof Error ? e.message : String(e));
    }
  }
});

mapa.on("error", (ev: ErrorEvent) => {
  // erros de tile (ex.: PMTiles ausente → 404) chegam aqui; não repetir a dica se já mostrada
  const msg = ev.error?.message ?? "";
  if (msg && !document.getElementById("erro")!.textContent) mostrarErro(msg);
});
