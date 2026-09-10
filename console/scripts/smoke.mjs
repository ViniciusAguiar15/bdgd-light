#!/usr/bin/env node
/**
 * Smoke test do console sem dependências: abre o Chrome headless via DevTools Protocol, espera o
 * mapa ficar ocioso (tiles carregados), reporta erros de console/estilo, conta feições renderizadas
 * e salva um screenshot.
 *
 * Uso: node scripts/smoke.mjs [URL] [saida.png]
 *   URL padrão: http://localhost:5173/#14/-22.9144/-43.4005 (cluster TQR do exemplo.pmtiles)
 *   CHROME=/caminho/para/chrome para outro binário.
 * Sai com código 1 se houver erro de estilo/JS ou nenhuma feição vetorial renderizada.
 */
import { spawn } from "node:child_process";
import { existsSync, writeFileSync } from "node:fs";

const url = process.argv[2] ?? "http://localhost:5173/#14/-22.9144/-43.4005";
const saida = process.argv[3] ?? "smoke.png";
const porta = 9333 + Math.floor(Math.random() * 500);

const candidatos = [
  process.env.CHROME,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
].filter(Boolean);
const chrome = candidatos.find((c) => existsSync(c));
if (!chrome) {
  console.error("Chrome não encontrado; defina CHROME=/caminho/do/binario");
  process.exit(2);
}

const proc = spawn(
  chrome,
  [
    "--headless=new",
    "--disable-gpu",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--ignore-gpu-blocklist",
    "--hide-scrollbars",
    "--no-first-run",
    "--window-size=1400,900",
    `--remote-debugging-port=${porta}`,
    `--user-data-dir=/tmp/bdgd-console-smoke-${porta}`,
    "about:blank",
  ],
  { stdio: "ignore" },
);
const encerrar = (codigo) => {
  proc.kill("SIGKILL");
  process.exit(codigo);
};

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

let alvo;
for (let i = 0; i < 50 && !alvo; i++) {
  await dormir(200);
  try {
    const lista = await (await fetch(`http://127.0.0.1:${porta}/json`)).json();
    alvo = lista.find((t) => t.type === "page");
  } catch {
    /* Chrome ainda subindo */
  }
}
if (!alvo) {
  console.error("não conectou ao Chrome");
  encerrar(2);
}

const ws = new WebSocket(alvo.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let seq = 0;
const pendentes = new Map();
const erros = [];
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pendentes.has(m.id)) {
    pendentes.get(m.id)(m);
    pendentes.delete(m.id);
  } else if (m.method === "Runtime.exceptionThrown") {
    erros.push(`exceção: ${m.params.exceptionDetails.text} ${m.params.exceptionDetails.exception?.description ?? ""}`);
  } else if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") {
    erros.push(`console.error: ${m.params.args.map((a) => a.value ?? a.description).join(" ")}`);
  }
};
const enviar = (method, params = {}) =>
  new Promise((r) => {
    const id = ++seq;
    pendentes.set(id, r);
    ws.send(JSON.stringify({ id, method, params }));
  });
const avaliar = async (expression) => {
  const r = await enviar("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (r.result?.exceptionDetails) console.error("eval:", r.result.exceptionDetails.text, r.result.exceptionDetails.exception?.description);
  return r.result?.result?.value;
};

await enviar("Page.enable");
await enviar("Runtime.enable");
await enviar("Page.navigate", { url });

let pronto = false;
for (let i = 0; i < 60 && !pronto; i++) {
  await dormir(1000);
  pronto = await avaliar(
    "!!(window.mapa && window.mapa.loaded() && window.mapa.areTilesLoaded() && window.mapa.isStyleLoaded())",
  );
}
await dormir(1500);

const info = await avaliar(`JSON.stringify({
  pronto: ${pronto},
  erro: document.getElementById("erro")?.textContent ?? "",
  subtitulo: document.getElementById("subtitulo")?.textContent ?? "",
  camadasPainel: document.querySelectorAll("#camadas label").length,
  layers: window.mapa ? window.mapa.getStyle().layers.map((l) => l.id) : [],
  feicoes: window.mapa ? window.mapa.queryRenderedFeatures().filter((f) => f.source === "bdgd").length : 0,
  porCamada: window.mapa ? Object.fromEntries(
    Object.entries(window.mapa.queryRenderedFeatures().filter((f) => f.source === "bdgd")
      .reduce((acc, f) => { acc[f.sourceLayer] = (acc[f.sourceLayer] ?? 0) + 1; return acc; }, {}))) : {},
  centro: window.mapa ? window.mapa.getCenter().toArray().map((v) => +v.toFixed(4)) : null,
  zoom: window.mapa ? +window.mapa.getZoom().toFixed(2) : null,
})`);
const dados = JSON.parse(info ?? "{}");

if (process.env.SMOKE_EXPR) console.log("SMOKE_EXPR →", await avaliar(process.env.SMOKE_EXPR));

const shot = await enviar("Page.captureScreenshot", { format: "png" });
if (shot.result?.data) writeFileSync(saida, Buffer.from(shot.result.data, "base64"));

console.log(JSON.stringify({ url, screenshot: saida, ...dados, errosJS: erros }, null, 2));
const falhou = !dados.pronto || dados.erro || erros.length || dados.feicoes === 0;
encerrar(falhou ? 1 : 0);
