/**
 * Ícones desenhados em canvas (sem arquivos de imagem): chaves NA/NF (com variantes
 * telecomandada e de interligação), ponto de interligação e subestação.
 */
import type { Map as MapaLibre } from "maplibre-gl";

const TAMANHO = 32;
const ESCALA = 2; // pixelRatio: nítido em telas retina

function canvas(): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement("canvas");
  c.width = TAMANHO * ESCALA;
  c.height = TAMANHO * ESCALA;
  const ctx = c.getContext("2d")!;
  ctx.scale(ESCALA, ESCALA);
  return [c, ctx];
}

function registrar(mapa: MapaLibre, id: string, c: HTMLCanvasElement) {
  const ctx = c.getContext("2d")!;
  const dados = ctx.getImageData(0, 0, c.width, c.height);
  if (!mapa.hasImage(id)) mapa.addImage(id, dados, { pixelRatio: ESCALA });
}

/** Chave: quadrado arredondado; NF verde cheio com barra contínua, NA branco com borda vermelha e
 *  barra interrompida. TLCD ganha um raio amarelo no canto; tie ganha anel laranja. */
export function desenharChave(aberta: boolean, tlcd: boolean, tie: boolean): HTMLCanvasElement {
  const [c, ctx] = canvas();
  const m = 6;
  const lado = TAMANHO - 2 * m;
  if (tie) {
    ctx.beginPath();
    ctx.arc(TAMANHO / 2, TAMANHO / 2, TAMANHO / 2 - 1.5, 0, Math.PI * 2);
    ctx.strokeStyle = "#ff9f1c";
    ctx.lineWidth = 2.5;
    ctx.stroke();
  }
  ctx.beginPath();
  ctx.roundRect(m, m, lado, lado, 4);
  ctx.fillStyle = aberta ? "#ffffff" : "#2dc653";
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = aberta ? "#e63946" : "#1b7a3a";
  ctx.stroke();
  // barra da chave
  ctx.lineWidth = 2.5;
  ctx.lineCap = "round";
  ctx.strokeStyle = aberta ? "#e63946" : "#ffffff";
  const y = TAMANHO / 2;
  ctx.beginPath();
  ctx.moveTo(m + 4, y);
  ctx.lineTo(m + 9, y);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(m + lado - 9, y);
  ctx.lineTo(m + lado - 4, y);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(m + 9, y);
  if (aberta) ctx.lineTo(m + lado - 11, y - 7);
  else ctx.lineTo(m + lado - 9, y);
  ctx.stroke();
  if (tlcd) {
    // raio amarelo no canto superior direito
    ctx.fillStyle = "#ffd60a";
    ctx.strokeStyle = "#1b1b1b";
    ctx.lineWidth = 1;
    const x0 = TAMANHO - m - 3;
    const y0 = m - 1;
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x0 - 4, y0 + 7);
    ctx.lineTo(x0, y0 + 6);
    ctx.lineTo(x0 - 2, y0 + 12);
    ctx.lineTo(x0 + 4, y0 + 4);
    ctx.lineTo(x0, y0 + 5);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }
  return c;
}

/** Ponto de interligação (losango laranja com centro claro). */
export function desenharInterligacao(): HTMLCanvasElement {
  const [c, ctx] = canvas();
  const cx = TAMANHO / 2;
  ctx.beginPath();
  ctx.moveTo(cx, 4);
  ctx.lineTo(TAMANHO - 4, cx);
  ctx.lineTo(cx, TAMANHO - 4);
  ctx.lineTo(4, cx);
  ctx.closePath();
  ctx.fillStyle = "#ff9f1c";
  ctx.fill();
  ctx.strokeStyle = "#1b1b1b";
  ctx.lineWidth = 1.5;
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(cx, cx, 4, 0, Math.PI * 2);
  ctx.fillStyle = "#fff3e0";
  ctx.fill();
  return c;
}

/** Subestação / transformador AT-MT: quadrado azul com "SE". */
export function desenharSubestacao(): HTMLCanvasElement {
  const [c, ctx] = canvas();
  ctx.beginPath();
  ctx.roundRect(2, 2, TAMANHO - 4, TAMANHO - 4, 5);
  ctx.fillStyle = "#1d4ed8";
  ctx.fill();
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.fillStyle = "#ffffff";
  ctx.font = "bold 13px system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("SE", TAMANHO / 2, TAMANHO / 2 + 1);
  return c;
}

export function idChave(aberta: boolean, tlcd: boolean, tie: boolean): string {
  return `chave-${aberta ? "na" : "nf"}${tlcd ? "-tlcd" : ""}${tie ? "-tie" : ""}`;
}

/** Registra todos os ícones no mapa (idempotente). */
export function registrarIcones(mapa: MapaLibre) {
  for (const aberta of [false, true])
    for (const tlcd of [false, true])
      for (const tie of [false, true])
        registrar(mapa, idChave(aberta, tlcd, tie), desenharChave(aberta, tlcd, tie));
  registrar(mapa, "interligacao", desenharInterligacao());
  registrar(mapa, "subestacao", desenharSubestacao());
}
