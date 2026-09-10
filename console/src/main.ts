/**
 * Console bdgd-light: MapLibre GL + PMTiles (sem servidor de tiles). Lê o PMTiles gerado por
 * `bdgd-light tiles`, monta o painel de camadas a partir do metadata e permite sobrepor o estado
 * do grafo (`?estado=`).
 *
 * Parâmetros de URL:
 *   ?cenario=tijuca|ipanema|taquara  cenário da demo (tiles + estado + vista inicial; ver cenarios.ts)
 *   ?tiles=tiles/X.pmtiles   caminho (relativo à base do site) ou URL absoluta do PMTiles
 *   ?estado=URL.geojson      GeoJSON de `bdgd-light grafo --geojson`
 *   ?estado=none             não carrega o estado do cenário
 *   ?api=http://host:porta   backend `bdgd-light serve` (padrão: mesma origem, /api); ver cod.ts
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
import { CENARIO_PADRAO, CENARIOS, cenarioPorId } from "./cenarios";
import { baseApi, montarCod } from "./cod";
import { carregarEstado } from "./estado";
import { registrarIcones } from "./icones";
import {
  formTiles,
  infoTiles,
  montarBases,
  montarCamadas,
  montarCenarios,
  mostrarErro,
  subtitulo,
  type Base,
} from "./painel";

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
// sem ?cenario= nem ?tiles=, abre o cenário padrão; ?tiles=/?estado= explícitos prevalecem
const cenario = cenarioPorId(params.get("cenario")) ?? (params.has("tiles") ? undefined : cenarioPorId(CENARIO_PADRAO));
const tilesParam = params.get("tiles") ?? cenario?.tiles ?? CENARIOS[CENARIOS.length - 1].tiles;
const tilesUrl = new URL(tilesParam, base).href;
const estadoBruto = params.get("estado") ?? cenario?.estado ?? null;
const estadoParam = estadoBruto === "none" ? null : estadoBruto;

montarCenarios(CENARIOS, cenario?.id ?? null, (id) => {
  const u = new URL(location.href);
  u.search = "";
  u.searchParams.set("cenario", id);
  u.hash = "";
  location.href = u.href;
});

formTiles(tilesParam, (novo) => {
  const u = new URL(location.href);
  u.searchParams.delete("cenario");
  u.searchParams.delete("estado");
  u.searchParams.set("tiles", novo || CENARIOS[CENARIOS.length - 1].tiles);
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
  center: cenario?.centro ?? [-43.33, -22.95],
  zoom: cenario?.zoom ?? 10,
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
// painel do COD (fila, proposta, aprovação); some se não houver backend `bdgd-light serve`
const cod = montarCod(mapa, baseApi(params, base), cenario);
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
    `--out console/public/${tilesParam}\nou escolha outro cenário / aponte ?tiles= para outro PMTiles.`
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
    // sem hash na URL: cenário → vista inicial no bairro; senão enquadra o bbox do PMTiles
    if (!location.hash && !cenario)
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
  // com backend e cluster carregado, o estado vivo (api/estado.geojson) substitui o do cenário
  await cod.pronto;
  if (estadoParam && !(cod.ativo && cod.estado?.cluster)) {
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
