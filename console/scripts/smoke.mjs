#!/usr/bin/env node
/**
 * Smoke test do console sem dependências: abre o Chrome headless via DevTools Protocol, espera o
 * mapa ficar ocioso (tiles carregados), reporta erros de console/estilo, conta feições renderizadas
 * e salva um screenshot.
 *
 * Uso: node scripts/smoke.mjs [URL] [saida.png]
 *   URL padrão: http://localhost:5173/?cenario=tijuca (cenário A; ?cenario=ipanema|taquara para os outros)
 *   CHROME=/caminho/para/chrome para outro binário.
 *   SMOKE_EXPR="..." avalia uma expressão JS na página e imprime o resultado.
 *   SMOKE_FLUXO=1 (com `bdgd-light serve` atrás da URL) roda a demo ponta a ponta no painel do COD:
 *     injetar falta → esperar a proposta → aprovar e executar → conferir o mapa recolorido.
 *     SMOKE_TOKEN=<BDGD_CONSOLE_TOKEN> se o backend exige segredo; SMOKE_OPERADOR (padrão "smoke").
 * Sai com código 1 se houver erro de estilo/JS, nenhuma feição vetorial renderizada ou, com
 * SMOKE_FLUXO, se a proposta não for executada em até 60 s / o mapa não mudar.
 */
import { spawn } from "node:child_process";
import { existsSync, writeFileSync } from "node:fs";

const url = process.argv[2] ?? "http://localhost:5173/?cenario=tijuca";
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

// demo ponta a ponta no painel do COD (precisa do backend `bdgd-light serve` na mesma origem/?api=)
const FLUXO = `(async () => {
  const t0 = performance.now();
  const dormir = (ms) => new Promise((r) => setTimeout(r, ms));
  const cod = window.cod;
  const apagados = () => window.mapa.getSource("estado")
    ? window.mapa.querySourceFeatures("estado").filter((f) => f.properties.camada === "SSDMT" && f.properties.energizado === false).length
    : null;
  const out = { ativo: cod?.ativo ?? false, cluster: cod?.estado?.cluster ?? null };
  if (!out.ativo) return JSON.stringify({ ...out, erro: "painel do COD inativo: backend não respondeu em " + (cod?.api ?? "?") });
  document.getElementById("cod-operador").value = ${JSON.stringify(process.env.SMOKE_OPERADOR ?? "smoke")};
  document.getElementById("cod-token").value = ${JSON.stringify(process.env.SMOKE_TOKEN ?? "")};
  out.desenergizados = { antes: apagados() };
  document.getElementById("cod-injetar").click();
  let p = null;
  for (let i = 0; i < 200 && !p; i++) { await dormir(300); await cod.atualizar(); p = cod.estado?.propostas.find((x) => x.status === "pendente"); }
  out.tProposta_s = +((performance.now() - t0) / 1000).toFixed(1);
  if (!p) return JSON.stringify({ ...out, erro: cod.ultimoErro ?? "sem proposta pendente em 60 s" });
  out.proposta = { id: p.id, falta: p.falta, chave: p.chave, fonte: p.fonte, manobras: p.manobras.map((m) => m.acao + " " + m.chave), viavel: p.score?.viavel ?? null };
  out.cartao = document.getElementById("cod-proposta")?.textContent.slice(0, 200) ?? null;
  await dormir(500);
  out.desenergizados.durante = apagados();
  document.getElementById("cod-aprovar").click();
  let exec = null;
  for (let i = 0; i < 200 && !exec; i++) { await dormir(300); await cod.atualizar(); exec = cod.estado?.propostas.find((x) => x.id === p.id && x.status === "executada"); }
  await dormir(1500);
  out.desenergizados.depois = apagados();
  out.executada = !!exec; out.aprovadaPor = exec?.aprovada_por ?? null;
  out.auditoria = document.getElementById("cod-auditoria")?.firstChild?.textContent ?? null;
  out.tTotal_s = +((performance.now() - t0) / 1000).toFixed(1);
  out.erro = cod.ultimoErro;
  return JSON.stringify(out);
})()`;
let fluxo = null;
if (process.env.SMOKE_FLUXO) {
  fluxo = JSON.parse((await avaliar(FLUXO)) ?? "{}");
  console.log("SMOKE_FLUXO →", JSON.stringify(fluxo));
}

const shot = await enviar("Page.captureScreenshot", { format: "png" });
if (shot.result?.data) writeFileSync(saida, Buffer.from(shot.result.data, "base64"));

console.log(JSON.stringify({ url, screenshot: saida, ...dados, errosJS: erros }, null, 2));
let falhou = !dados.pronto || dados.erro || erros.length || dados.feicoes === 0;
if (fluxo) {
  const d = fluxo.desenergizados ?? {};
  const recoloriu = d.durante > 0 && d.depois !== null && d.depois < d.durante;
  if (!fluxo.executada || fluxo.erro || !recoloriu) {
    console.error("fluxo do COD falhou:", fluxo.erro ?? (fluxo.executada ? "mapa não recoloriu" : "proposta não executada"));
    falhou = true;
  }
}
encerrar(falhou ? 1 : 0);
