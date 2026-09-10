/**
 * Sobreposição do estado do grafo: GeoJSON de `bdgd-light grafo --geojson` (props `camada`,
 * `energizado`, `aberta`, `fonte`, ...) desenhado por cima dos tiles.
 */
import type { Feature, FeatureCollection } from "geojson";
import type { GeoJSONSource, Map as MapaLibre } from "maplibre-gl";
import { FONTE_ESTADO, LAYERS_ESTADO } from "./camadas";
import { mostrarEstado } from "./painel";

type Colecao = FeatureCollection;

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
