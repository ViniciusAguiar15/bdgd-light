/**
 * Cenários da demo (`docs/escopo-cidade.md` v3): cada um aponta um PMTiles, um estado do grafo
 * (falta simulada) e a vista inicial no bairro. `?cenario=<id>` na URL escolhe um; `?tiles=` e
 * `?estado=` explícitos têm precedência sobre os do cenário.
 */
export interface Cenario {
  id: string;
  titulo: string;
  descricao: string;
  /** caminho relativo à base do site (ou URL absoluta) */
  tiles: string;
  estado?: string;
  centro: [number, number];
  zoom: number;
}

export const CENARIOS: Cenario[] = [
  {
    id: "tijuca",
    titulo: "Tijuca — FLISR aéreo (A)",
    descricao:
      "ALC9925 CABOFRIO + ALC9946, URG29983, RCP9882 (3 SEs). Falta no tronco 11304252: " +
      "isola com 10927447 e 11035901; 315 nós/4.036 UCBT restauráveis por 4 ties telecomandadas.",
    tiles: "tiles/exemplo_tijuca.pmtiles",
    estado: "exemplos/estado_tijuca_falta.geojson",
    centro: [-43.2375, -22.924],
    zoom: 14.5,
  },
  {
    id: "ipanema",
    titulo: "Ipanema — subterrâneo (B)",
    descricao:
      "PTS0001 LDS 9210 + PTS9088, PTS9924, PTS4022 (SE Posto Seis). Falta no tronco 11409068: " +
      "abre 10933610, 505111870 e 561826961; rede radial sem ties de campo — nenhuma chave NA restaura.",
    tiles: "tiles/exemplo_ipanema.pmtiles",
    estado: "exemplos/estado_ipanema_falta.geojson",
    centro: [-43.2019, -22.9847],
    zoom: 15,
  },
  {
    id: "taquara",
    titulo: "Taquara — regressão (TQR)",
    descricao:
      "TQR0007 + TQR33859 + TQR33862 (escopo v2). Falta em 254862954 sobre TQR0007.",
    tiles: "tiles/exemplo.pmtiles",
    estado: "exemplos/estado_TQR0007_falta.geojson",
    centro: [-43.4005, -22.9144],
    zoom: 14,
  },
];

export const CENARIO_PADRAO = "tijuca";

export function cenarioPorId(id: string | null): Cenario | undefined {
  return id ? CENARIOS.find((c) => c.id === id) : undefined;
}
