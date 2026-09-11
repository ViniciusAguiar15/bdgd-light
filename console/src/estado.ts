/**
 * Sobreposição do estado do grafo: GeoJSON de `bdgd-light grafo --geojson` (props `camada`,
 * `energizado`, `aberta`, `fonte`, ...) desenhado por cima dos tiles.
 */
import type { Feature, FeatureCollection } from "geojson";
import type { LayerSpecification } from "maplibre-gl";
import type { GeoJSONSource, Map as MapaLibre } from "maplibre-gl";
import { FONTE_ESTADO, LAYERS_ESTADO } from "./camadas";
import { mostrarEstado } from "./painel";

type Colecao = FeatureCollection;
const CAMADA_DESTAQUE_TRECHOS = "estado-trechos-destaque";

export async function carregarEstado(mapa: MapaLibre, url: string): Promise<void> {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`estado ${url}: HTTP ${resp.status}`);
  const fc = (await resp.json()) as Colecao;
  if (fc.type !== "FeatureCollection") throw new Error("estado: esperado FeatureCollection");

  if (mapa.getSource(FONTE_ESTADO)) {
    (mapa.getSource(FONTE_ESTADO) as GeoJSONSource).setData(fc);
  } else {
    mapa.addSource(FONTE_ESTADO, { type: "geojson", data: fc });
    for (const l of LAYERS_ESTADO) if (!mapa.getLayer(l.id)) mapa.addLayer(l);
  }

  const feats: Feature[] = fc.features;
  const trechos = feats.filter((f: Feature) => f.properties?.camada === "SSDMT");
  const chaves = feats.filter((f: Feature) => f.properties?.camada === "UNSEMT");
  const trafos = feats.filter((f: Feature) => f.properties?.camada === "UNTRMT");
  mostrarEstado({
    url,
    trechos: trechos.length,
    desenergizados: trechos.filter((f: Feature) => f.properties?.energizado === false).length,
    chavesAbertas: chaves.filter((f: Feature) => f.properties?.aberta === true).length,
    trafosSemTensao: trafos.filter((f: Feature) => f.properties?.energizado === false).length,
  });
}

function filtroTrechos(codigos: string[]) {
  if (!codigos.length) return ["==", ["get", "COD_ID"], "__sem_destaque__"] as const;
  return [
    "all",
    ["==", ["get", "camada"], "SSDMT"],
    ["match", ["get", "COD_ID"], codigos, true, false],
  ] as const;
}

function garantirCamadaDestaque(mapa: MapaLibre) {
  if (mapa.getLayer(CAMADA_DESTAQUE_TRECHOS)) return;
  const spec: LayerSpecification = {
    id: CAMADA_DESTAQUE_TRECHOS,
    type: "line",
    source: FONTE_ESTADO,
    filter: filtroTrechos([]) as never,
    paint: {
      "line-color": "#ffd54f",
      "line-width": ["interpolate", ["linear"], ["zoom"], 10, 4, 16, 10],
      "line-opacity": 0.95,
    },
    layout: { "line-cap": "round", "line-join": "round" },
  };
  mapa.addLayer(spec);
}

export function destacarTrechos(mapa: MapaLibre, codigos: string[]) {
  if (!mapa.getSource(FONTE_ESTADO)) return;
  garantirCamadaDestaque(mapa);
  mapa.setFilter(CAMADA_DESTAQUE_TRECHOS, filtroTrechos(codigos) as never);
}
