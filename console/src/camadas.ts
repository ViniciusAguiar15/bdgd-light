/**
 * Estilo por camada da BDGD (source-layers do PMTiles gerado por `bdgd-light tiles`).
 * Cada grupo vira um item do painel (toggle) e pode ter mais de uma layer MapLibre.
 */
import type { LayerSpecification } from "maplibre-gl";
import { idChave } from "./icones";

export const FONTE = "bdgd";

export interface Grupo {
  id: string;
  titulo: string;
  descricao: string;
  /** cor e forma da amostra no painel */
  amostra: { cor: string; forma: "linha" | "ponto" | "area" | "icone" };
  visivel: boolean;
  layers: LayerSpecification[];
}

// `match` não aceita rótulos numéricos não inteiros → `step` por faixa de tensão (kV)
const COR_MT: unknown[] = [
  "step",
  ["to-number", ["get", "TEN_KV"], 13.2],
  "#ff9f1c", // < 13,5 → 13,2 kV
  13.5,
  "#ffbf69", // 13,8 kV
  20,
  "#e63946", // 34,5 kV
];

const ABERTA = ["==", ["get", "P_N_OPE"], "A"];
const TLCD = ["==", ["to-number", ["get", "TLCD"], 0], 1];
const TIE = ["==", ["get", "TIE"], true];

/** icon-image da chave a partir de P_N_OPE/TLCD/TIE. */
function iconeChave(): unknown[] {
  const casos: unknown[] = ["case"];
  for (const aberta of [true, false])
    for (const tlcd of [true, false])
      for (const tie of [true, false]) {
        casos.push([
          "all",
          aberta ? ABERTA : ["!", ABERTA],
          tlcd ? TLCD : ["!", TLCD],
          tie ? TIE : ["!", TIE],
        ]);
        casos.push(idChave(aberta, tlcd, tie));
      }
  casos.push(idChave(false, false, false));
  return casos;
}

export const GRUPOS: Grupo[] = [
  {
    id: "SUB",
    titulo: "SUB — subestação (área)",
    descricao: "polígono da subestação",
    amostra: { cor: "#1d4ed8", forma: "area" },
    visivel: true,
    layers: [
      {
        id: "SUB-area",
        type: "fill",
        source: FONTE,
        "source-layer": "SUB",
        paint: { "fill-color": "#1d4ed8", "fill-opacity": 0.15 },
      },
      {
        id: "SUB-borda",
        type: "line",
        source: FONTE,
        "source-layer": "SUB",
        paint: { "line-color": "#60a5fa", "line-width": 1.5, "line-dasharray": [3, 2] },
      },
    ],
  },
  {
    id: "SSDBT",
    titulo: "SSDBT — rede BT",
    descricao: "trechos de baixa tensão (zoom ≥ 13)",
    amostra: { cor: "#8ab4f8", forma: "linha" },
    visivel: true,
    layers: [
      {
        id: "SSDBT",
        type: "line",
        source: FONTE,
        "source-layer": "SSDBT",
        minzoom: 13,
        paint: {
          "line-color": "#8ab4f8",
          "line-width": ["interpolate", ["linear"], ["zoom"], 13, 0.8, 16, 2.2],
          "line-opacity": 0.9,
        },
      },
    ],
  },
  {
    id: "SSDMT",
    titulo: "SSDMT — rede MT",
    descricao: "cor por tensão nominal (TEN_KV): 13,2 kV laranja, 34,5 kV vermelho",
    amostra: { cor: "#ff9f1c", forma: "linha" },
    visivel: true,
    layers: [
      {
        id: "SSDMT-halo",
        type: "line",
        source: FONTE,
        "source-layer": "SSDMT",
        paint: {
          "line-color": "#111111",
          "line-width": ["interpolate", ["linear"], ["zoom"], 9, 2.5, 13, 4.5, 16, 7],
          "line-opacity": 0.6,
        },
        layout: { "line-cap": "round", "line-join": "round" },
      },
      {
        id: "SSDMT",
        type: "line",
        source: FONTE,
        "source-layer": "SSDMT",
        paint: {
          "line-color": COR_MT as never,
          "line-width": ["interpolate", ["linear"], ["zoom"], 9, 1, 13, 2.5, 16, 4],
        },
        layout: { "line-cap": "round", "line-join": "round" },
      },
    ],
  },
  {
    id: "PONNOT",
    titulo: "PONNOT — postes",
    descricao: "pontos notáveis (zoom ≥ 15)",
    amostra: { cor: "#cbd5e1", forma: "ponto" },
    visivel: false,
    layers: [
      {
        id: "PONNOT",
        type: "circle",
        source: FONTE,
        "source-layer": "PONNOT",
        minzoom: 15,
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 15, 1.5, 17, 3],
          "circle-color": "#cbd5e1",
          "circle-opacity": 0.8,
        },
      },
    ],
  },
  {
    id: "UCBT",
    titulo: "UCBT — consumidores BT",
    descricao: "UCBT_tab agregada por poste (N_UC); zoom ≥ 14",
    amostra: { cor: "#ffd166", forma: "ponto" },
    visivel: true,
    layers: [
      {
        id: "UCBT",
        type: "circle",
        source: FONTE,
        "source-layer": "UCBT",
        minzoom: 14,
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            14,
            ["min", 4, ["+", 1.5, ["*", 0.3, ["get", "N_UC"]]]],
            17,
            ["min", 9, ["+", 3, ["*", 0.5, ["get", "N_UC"]]]],
          ],
          "circle-color": "#ffd166",
          "circle-stroke-color": "#3b2f00",
          "circle-stroke-width": 0.5,
          "circle-opacity": 0.9,
        },
      },
    ],
  },
  {
    id: "UNTRMT",
    titulo: "UNTRMT — transformadores",
    descricao: "círculo cresce com POT_NOM (kVA); zoom ≥ 12",
    amostra: { cor: "#06d6a0", forma: "ponto" },
    visivel: true,
    layers: [
      {
        id: "UNTRMT",
        type: "circle",
        source: FONTE,
        "source-layer": "UNTRMT",
        minzoom: 12,
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            12,
            ["+", 2, ["/", ["to-number", ["get", "POT_NOM"], 75], 150]],
            16,
            ["+", 5, ["/", ["to-number", ["get", "POT_NOM"], 75], 60]],
          ],
          "circle-color": "#06d6a0",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1,
        },
      },
    ],
  },
  {
    id: "UNCRMT",
    titulo: "UNCRMT — reguladores/capacitores",
    descricao: "unidades compensadoras MT",
    amostra: { cor: "#c77dff", forma: "ponto" },
    visivel: true,
    layers: [
      {
        id: "UNCRMT",
        type: "circle",
        source: FONTE,
        "source-layer": "UNCRMT",
        minzoom: 11,
        paint: {
          "circle-radius": 6,
          "circle-color": "#c77dff",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
        },
      },
    ],
  },
  {
    id: "UNSEBT",
    titulo: "UNSEBT — chaves BT",
    descricao: "chaves de baixa tensão (zoom ≥ 14)",
    amostra: { cor: "#b5179e", forma: "ponto" },
    visivel: false,
    layers: [
      {
        id: "UNSEBT",
        type: "circle",
        source: FONTE,
        "source-layer": "UNSEBT",
        minzoom: 14,
        paint: {
          "circle-radius": 3.5,
          "circle-color": ["case", ABERTA as never, "#ffffff", "#b5179e"],
          "circle-stroke-color": "#b5179e",
          "circle-stroke-width": 1.5,
        },
      },
    ],
  },
  {
    id: "UNSEMT",
    titulo: "UNSEMT — chaves MT",
    descricao: "NF verde · NA branco/vermelho · raio = telecomandada (TLCD) · anel = interligação",
    amostra: { cor: "#2dc653", forma: "icone" },
    visivel: true,
    layers: [
      {
        id: "UNSEMT",
        type: "symbol",
        source: FONTE,
        "source-layer": "UNSEMT",
        minzoom: 11,
        layout: {
          "icon-image": iconeChave() as never,
          "icon-size": ["interpolate", ["linear"], ["zoom"], 11, 0.45, 14, 0.7, 17, 1],
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
          "text-field": ["step", ["zoom"], "", 15, ["get", "COD_ID"]],
          "text-size": 10,
          "text-offset": [0, 1.3],
          "text-anchor": "top",
          "text-optional": true,
        },
        paint: {
          "text-color": "#ffffff",
          "text-halo-color": "#000000",
          "text-halo-width": 1,
        },
      },
    ],
  },
  {
    id: "INTERLIGACOES",
    titulo: "Interligações (ties)",
    descricao: "chave NA ≤ 2 m de trecho de outro CTMT; rótulo = CTMT vizinho",
    amostra: { cor: "#ff9f1c", forma: "icone" },
    visivel: true,
    layers: [
      {
        id: "INTERLIGACOES",
        type: "symbol",
        source: FONTE,
        "source-layer": "INTERLIGACOES",
        minzoom: 10,
        layout: {
          "icon-image": "interligacao",
          "icon-size": ["interpolate", ["linear"], ["zoom"], 10, 0.5, 14, 0.8],
          "icon-allow-overlap": true,
          "text-field": ["step", ["zoom"], "", 13, ["concat", "→ ", ["get", "CTMT_VIZ"]]],
          "text-size": 11,
          "text-offset": [0, -1.4],
          "text-anchor": "bottom",
          "text-optional": true,
        },
        paint: {
          "text-color": "#ffd8a8",
          "text-halo-color": "#000000",
          "text-halo-width": 1.2,
        },
      },
    ],
  },
  {
    id: "UNTRAT",
    titulo: "UNTRAT — subestação (trafos AT/MT)",
    descricao: "transformadores de força da SE",
    amostra: { cor: "#1d4ed8", forma: "icone" },
    visivel: true,
    layers: [
      {
        id: "UNTRAT",
        type: "symbol",
        source: FONTE,
        "source-layer": "UNTRAT",
        layout: {
          "icon-image": "subestacao",
          "icon-size": ["interpolate", ["linear"], ["zoom"], 9, 0.6, 14, 1],
          "icon-allow-overlap": true,
          "text-field": ["step", ["zoom"], "", 13, ["concat", ["get", "POT_NOM"], " kVA"]],
          "text-size": 11,
          "text-offset": [0, 1.4],
          "text-anchor": "top",
          "text-optional": true,
        },
        paint: {
          "text-color": "#bfdbfe",
          "text-halo-color": "#000000",
          "text-halo-width": 1.2,
        },
      },
    ],
  },
];

/** Layers em que o clique abre popup (as visíveis por cima primeiro). */
export const INTERATIVAS = GRUPOS.flatMap((g) => g.layers.map((l) => l.id)).filter(
  (id) => !id.endsWith("-halo") && !id.endsWith("-area"),
);

/** Camadas do estado do grafo (`bdgd-light grafo --geojson`), por cima dos tiles. */
export const FONTE_ESTADO = "estado";
export const LAYERS_ESTADO: LayerSpecification[] = [
  {
    id: "estado-trechos",
    type: "line",
    source: FONTE_ESTADO,
    filter: ["==", ["get", "camada"], "SSDMT"],
    paint: {
      "line-color": ["case", ["==", ["get", "energizado"], true], "#00e676", "#ff1744"],
      "line-width": ["interpolate", ["linear"], ["zoom"], 10, 2, 16, 6],
      "line-opacity": 0.85,
      "line-dasharray": ["case", ["==", ["get", "energizado"], true], ["literal", [1, 0]], ["literal", [2, 1.5]]] as never,
    },
    layout: { "line-cap": "round", "line-join": "round" },
  },
  {
    id: "estado-chaves",
    type: "circle",
    source: FONTE_ESTADO,
    filter: ["==", ["get", "camada"], "UNSEMT"],
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 4, 16, 9],
      "circle-color": ["case", ["==", ["get", "aberta"], true], "#ffffff", "#00e676"],
      "circle-stroke-color": ["case", ["==", ["get", "aberta"], true], "#ff1744", "#004d40"],
      "circle-stroke-width": 2.5,
    },
  },
  {
    id: "estado-trafos",
    type: "circle",
    source: FONTE_ESTADO,
    filter: ["==", ["get", "camada"], "UNTRMT"],
    minzoom: 12,
    paint: {
      "circle-radius": 4,
      "circle-color": ["case", ["==", ["get", "energizado"], true], "#00e676", "#ff1744"],
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 1,
    },
  },
];
