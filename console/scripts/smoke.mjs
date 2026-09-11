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
 *   SMOKE_PASSOS=1 (com SMOKE_FLUXO) usa o modo passo a passo: clica "próxima manobra" até a
 *     proposta ficar executada e exige exatamente n cliques para n manobras.
 *   SMOKE_CAPTURAS=<pasta> salva uma captura por etapa (1-evento, 2-proposta, [2b-passo,] 3-executada)
 *     — são as imagens do README; SMOKE_BASE=base-nenhuma troca a base para o fundo escuro (PNG menor).
 * Sai com código 1 se houver erro de estilo/JS, nenhuma feição vetorial renderizada ou, com
 * SMOKE_FLUXO, se a proposta não for executada em até 60 s após o agente concluir / o mapa não mudar.
 */
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

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

// demo ponta a ponta no painel do COD (precisa do backend `bdgd-light serve` na mesma origem/?api=),
// em etapas para poder fotografar cada tela: 1 injetar → proposta; 2 agente ocioso (alternativas
// abertas); 3 aprovar e executar (ou n cliques de "próxima manobra") → mapa recolorido.
const PASSOS = !!process.env.SMOKE_PASSOS;
const CAPTURAS = process.env.SMOKE_CAPTURAS;
const capturar = async (nome) => {
  if (!CAPTURAS) return;
  mkdirSync(CAPTURAS, { recursive: true });
  // deixa o cartão da proposta (com os botões) visível no painel antes de fotografar
  await avaliar(`(async () => { document.querySelector("#cod-proposta .cod-acoes:last-of-type, #cod-proposta, #cod-evento")?.scrollIntoView({ block: "end" }); await new Promise((r) => setTimeout(r, 400)); })()`);
  const shot = await enviar("Page.captureScreenshot", { format: "png" });
  if (shot.result?.data) writeFileSync(join(CAPTURAS, `${nome}.png`), Buffer.from(shot.result.data, "base64"));
};
const PREPARO = `(() => {
  window.__smoke = { t0: performance.now(), dormir: (ms) => new Promise((r) => setTimeout(r, ms)),
    apagados: () => window.mapa.getSource("estado")
      ? window.mapa.querySourceFeatures("estado").filter((f) => f.properties.camada === "SSDMT" && f.properties.energizado === false).length
      : null,
    s: () => +((performance.now() - window.__smoke.t0) / 1000).toFixed(1) };
  const cod = window.cod;
  const out = { ativo: cod?.ativo ?? false, cluster: cod?.estado?.cluster ?? null };
  if (!out.ativo) return JSON.stringify({ ...out, erro: "painel do COD inativo: backend não respondeu em " + (cod?.api ?? "?") });
  const base = ${JSON.stringify(process.env.SMOKE_BASE ?? "")};
  if (base) document.querySelector('input[name="base"][value="' + base + '"]')?.click();
  document.getElementById("cod-operador").value = ${JSON.stringify(process.env.SMOKE_OPERADOR ?? "smoke")};
  document.getElementById("cod-token").value = ${JSON.stringify(process.env.SMOKE_TOKEN ?? "")};
  out.desenergizados = { antes: window.__smoke.apagados() };
  return JSON.stringify(out);
})()`;
const ETAPA_EVENTO = `(async () => {
  const { dormir } = window.__smoke; const cod = window.cod;
  document.getElementById("cod-injetar").click();
  // espera o evento aparecer em curso (tela 1) — ou a proposta, se o agente for muito rápido
  for (let i = 0; i < 40 && !cod.estado?.agente?.ocupado && !cod.estado?.propostas.some((x) => x.status === "pendente"); i++) { await dormir(250); await cod.atualizar(); }
  return JSON.stringify({ evento: document.getElementById("cod-evento")?.textContent ?? null, tEvento_s: window.__smoke.s() });
})()`;
const ETAPA_PROPOSTA = `(async () => {
  const { dormir } = window.__smoke; const cod = window.cod;
  let p = null;
  for (let i = 0; i < 200 && !p; i++) { await dormir(300); await cod.atualizar(); p = cod.estado?.propostas.find((x) => x.status === "pendente"); }
  const out = { tProposta_s: window.__smoke.s() };
  if (!p) return JSON.stringify({ ...out, erro: cod.ultimoErro ?? "sem proposta pendente em 60 s" });
  out.proposta = { id: p.id, falta: p.falta, chave: p.chave, fonte: p.fonte, manobras: p.manobras.map((m) => m.acao + " " + m.chave), viavel: p.score?.viavel ?? null };
  // o botão fica desabilitado enquanto o agente termina a resposta final (provedores reais levam segundos)
  for (let i = 0; i < 200 && cod.estado?.agente?.ocupado; i++) { await dormir(300); await cod.atualizar(); }
  out.tAgente_s = window.__smoke.s();
  await dormir(500);
  const det = document.querySelector("#cod-proposta details"); if (det) det.open = true; // tela 2: alternativas e motivos
  out.cartao = document.getElementById("cod-proposta")?.textContent.slice(0, 200) ?? null;
  out.durante = window.__smoke.apagados();
  return JSON.stringify(out);
})()`;
const ETAPA_PASSO = `(async () => {
  const { dormir } = window.__smoke; const cod = window.cod;
  const p = cod.estado?.propostas.find((x) => x.status === "pendente" || x.status === "aprovada");
  const antes = p?.executadas ?? 0;
  const btn = document.getElementById("cod-passo");
  if (!btn) return JSON.stringify({ erro: "botão cod-passo ausente" });
  const rotulo = btn.textContent; btn.click();
  let q = null;
  for (let i = 0; i < 100 && !q; i++) { await dormir(300); await cod.atualizar(); q = cod.estado?.propostas.find((x) => x.id === p.id && (x.executadas > antes || x.status === "executada")); }
  await dormir(800);
  return JSON.stringify({ rotulo, executadas: q?.executadas ?? null, status: q?.status ?? null, aprovadaPor: q?.aprovada_por ?? null, apagados: window.__smoke.apagados(), erro: cod.ultimoErro });
})()`;
const ETAPA_APROVAR = `(async () => {
  const { dormir } = window.__smoke; const cod = window.cod;
  const p = cod.estado?.propostas.find((x) => x.status === "pendente");
  document.getElementById("cod-aprovar").click();
  let exec = null;
  for (let i = 0; i < 200 && !exec; i++) { await dormir(300); await cod.atualizar(); exec = cod.estado?.propostas.find((x) => x.id === p.id && x.status === "executada"); }
  await dormir(1500);
  return JSON.stringify({ executada: !!exec, aprovadaPor: exec?.aprovada_por ?? null, depois: window.__smoke.apagados(), erro: cod.ultimoErro });
})()`;
const ETAPA_FIM = `JSON.stringify({ auditoria: document.getElementById("cod-auditoria")?.firstChild?.textContent ?? null, tTotal_s: window.__smoke.s(), erro: window.cod.ultimoErro })`;

let fluxo = null;
if (process.env.SMOKE_FLUXO) {
  const ler = async (expr) => JSON.parse((await avaliar(expr)) ?? "{}");
  fluxo = await ler(PREPARO);
  if (!fluxo.erro) {
    Object.assign(fluxo, await ler(ETAPA_EVENTO));
    await capturar("1-evento");
    const prop = await ler(ETAPA_PROPOSTA);
    Object.assign(fluxo, prop);
    fluxo.desenergizados.durante = prop.durante;
    delete fluxo.durante;
    await capturar("2-proposta");
  }
  if (!fluxo.erro && PASSOS) {
    // n cliques = n manobras; cada clique aplica exatamente uma e o mapa recolore quando a rede muda
    fluxo.passos = [];
    const n = fluxo.proposta.manobras.length;
    for (let k = 0; k < n + 1; k++) {
      const st = fluxo.passos.at(-1)?.status;
      if (st === "executada") break;
      const r = await ler(ETAPA_PASSO);
      fluxo.passos.push(r);
      if (r.erro) break;
      if (k === 0) await capturar("2b-passo");
    }
    const ultimo = fluxo.passos.at(-1) ?? {};
    fluxo.cliques = fluxo.passos.length;
    fluxo.executada = ultimo.status === "executada";
    fluxo.desenergizados.depois = ultimo.apagados ?? null;
    fluxo.aprovadaPor = ultimo.aprovadaPor ?? null;
    if (fluxo.cliques !== n) fluxo.erro = fluxo.erro ?? `${fluxo.cliques} cliques para ${n} manobras`;
    else if (fluxo.passos.some((r, i) => r.executadas !== i + 1)) fluxo.erro = fluxo.erro ?? "um clique não aplicou exatamente uma manobra";
  } else if (!fluxo.erro) {
    const ap = await ler(ETAPA_APROVAR);
    Object.assign(fluxo, { executada: ap.executada, aprovadaPor: ap.aprovadaPor, erro: ap.erro });
    fluxo.desenergizados.depois = ap.depois;
  }
  if (fluxo.ativo) {
    await capturar("3-executada");
    Object.assign(fluxo, await ler(ETAPA_FIM), { erro: fluxo.erro ?? null });
  }
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
