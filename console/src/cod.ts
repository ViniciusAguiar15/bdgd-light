/**
 * Painel do COD (fase 3): fila de eventos, proposta do agente, aprovação humana e trilha de
 * auditoria, falando com o backend `bdgd-light serve` (FastAPI).
 *
 * Base da API: `?api=http://host:porta` ou a própria origem do site (`/api/...`). Se `GET
 * api/estado` não responder (ex.: GitHub Pages, `vite dev` sem `serve`), a seção fica oculta e o
 * console continua só com mapa + estado estático. Estado exposto em `window.cod` para o smoke.
 */
import type { Map as MapaLibre } from "maplibre-gl";
import type { Cenario } from "./cenarios";
import { carregarEstado } from "./estado";

interface Clientes {
  ucbt: number;
  ucmt: number;
  trafos: number;
  kva: number;
  total: number;
}

interface Score {
  viavel: boolean;
  convergiu: boolean;
  margem_disjuntor: number | null;
  vmin_mt_pu: number | null;
  carregamento_max_mt_pct: number | null;
  motivos: string[];
}

interface Verificador {
  ok: boolean;
  eletrico: boolean;
  checagens: Record<string, boolean>;
  problemas: string[];
  avisos: string[];
}

interface RestricaoOperacional {
  motivo: string;
}

export interface Proposta {
  id: string;
  criada_em: string;
  falta: string | null;
  chave: string | null;
  fonte: string | null;
  manobras: { acao: string; chave: string }[];
  /** manobras já aplicadas (modo passo a passo); `proximo_passo` é a manobras[executadas] */
  executadas: number;
  n_passos: number;
  proximo_passo: { acao: string; chave: string } | null;
  clientes: Clientes | null;
  score: Score | null;
  status: "pendente" | "aprovada" | "executada" | "rejeitada" | "expirada" | string;
  aprovada_por: string | null;
  motivo: string | null;
  replanejada_apos_rejeicao: string | null;
  verificador: Verificador | null;
  ja_satisfeitas: string[];
  alternativas?: Alternativa[];
}

interface Alternativa {
  chave: string;
  fonte: string;
  tlcd: boolean;
  clientes: Clientes;
  escolhida: boolean;
  score: Score | null;
  bloqueada?: string | null;
}

interface Execucao {
  proposta: string | null;
  rodadas: number;
  n_ferramentas?: number;
  recusas_verificador: unknown[];
  segundos_total?: number;
  resposta?: string;
  erro: string | null;
  modelo?: string | null;
}

interface Agente {
  ocupado: boolean;
  provider: string | null;
  modelo: string | null;
  evento_atual: Evento | null;
  erro: string | null;
  inicio: string | null;
  n_execucoes: number;
  ultima: Execucao | null;
}

interface Evento {
  id?: number;
  tipo: string;
  cluster: string;
  hora: string;
  trecho?: string;
  ctmt?: string;
  chave?: string;
  cenario?: string;
  detalhes: Record<string, unknown>;
}

export interface Estado {
  cluster: string | null;
  cluster_demo: string | null;
  falta: string | null;
  religador: string | null;
  sem_tensao: { n_nos: number; clientes: Clientes } | null;
  propostas: Proposta[];
  audit_n: number | null;
  hash: string | null;
  eventos_n: number;
  agente: Agente | null;
  autorizacao: "segredo" | "sem-segredo" | "bloqueado";
  restricoes: RestricaoOperacional[];
  replanejamentos_evento: number;
  limite_replanejamentos_evento: number;
  ultima_rejeicao: string | null;
  hora: string;
}

interface Auditoria {
  n_total: number;
  integra: boolean | null;
  hash: string | null;
  registros: {
    seq: number;
    ts: string;
    tipo: string;
    ferramenta?: string;
    operador?: string;
    proposta_id?: string;
    erro?: string | null;
    ms?: number;
  }[];
}

interface RejeicaoResposta {
  replanejamento?: {
    status: string;
    mensagem: string;
  };
}

/** Cenário do console → cenário nomeado do simulador (`bdgd_light.sim.CENARIOS`). */
export const CENARIO_SIM: Record<string, string> = {
  tijuca: "tijuca_cabofrio_tronco",
  ipanema: "ipanema_9210",
  taquara: "taquara_bocari",
};

const INTERVALO_MS = 2000;
const CHAVE_OPERADOR = "bdgd-light.operador";
const CHAVE_TOKEN = "bdgd-light.token";
const SUGESTOES_REJEICAO = [
  "a chave 974020904 está em manutenção",
  "não quero carregar o BOMPASTOR",
  "prefiro a rota telecomandada",
];

export interface EstadoCod {
  api: string;
  ativo: boolean;
  estado: Estado | null;
  ultimoErro: string | null;
  atualizacoes: number;
  /** resolve após a sonda inicial (`ativo` já definido) */
  pronto: Promise<void>;
  /** força uma leitura imediata (smoke/depuração) */
  atualizar: () => Promise<void>;
  injetar: (cenario?: string) => Promise<unknown>;
  aprovar: (id: string) => Promise<unknown>;
  /** modo passo a passo: aprova (se pendente) e executa só a próxima manobra */
  passo: (id: string) => Promise<unknown>;
  rejeitar: (id: string, motivo?: string) => Promise<unknown>;
}

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Record<string, string> = {},
  ...filhos: (Node | string)[]
): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  e.append(...filhos);
  return e;
}

/** Uma linha explicando por que a alternativa não foi a proposta (pedido PR-15): o motivo do
 *  score quando inviável; senão a comparação com a escolhida (margem, clientes, telecomando). */
function motivoDescarte(a: Alternativa, escolhida: Alternativa | undefined): string {
  if (a.bloqueada) return a.bloqueada;
  if (a.score && !a.score.viavel) return a.score.motivos?.length ? a.score.motivos.join("; ") : "inviável";
  if (!a.tlcd && escolhida?.tlcd) return "sem telecomando";
  if (!escolhida) return "não escolhida";
  const m = a.score?.margem_disjuntor;
  const me = escolhida.score?.margem_disjuntor;
  if (m != null && me != null && m < me) return `margem ${pct(m)} < ${pct(me)} da escolhida`;
  if (a.clientes.ucbt < escolhida.clientes.ucbt)
    return `atende ${a.clientes.ucbt} UCBT < ${escolhida.clientes.ucbt}`;
  return "equivalente à escolhida";
}

function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`;
}

function pu(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${v.toFixed(3)} pu`;
}

function hora(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString("pt-BR");
}

function rotuloTipo(tipo: string): string {
  return (
    {
      falta_permanente: "falta permanente",
      falta_transitoria: "falta transitória",
      pico_carga: "pico de carga",
      chave_indisponivel: "chave indisponível",
    }[tipo] ?? tipo
  );
}

/** Resolve a base da API: `?api=` explícito ou `api/` relativo à base do site. */
export function baseApi(params: URLSearchParams, base: URL): string {
  const p = params.get("api");
  const u = p ? new URL(p.endsWith("/") ? p : p + "/", location.href) : new URL("api/", base);
  return u.href;
}

class ErroApi extends Error {
  constructor(
    public status: number,
    detail: string,
  ) {
    super(detail);
  }
}

export function montarCod(mapa: MapaLibre, api: string, cenario: Cenario | undefined): EstadoCod {
  const secao = document.getElementById("secao-cod")!;
  const raiz = document.getElementById("cod")!;
  const inputOperador = document.getElementById("cod-operador") as HTMLInputElement;
  const inputToken = document.getElementById("cod-token") as HTMLInputElement;
  const btnInjetar = document.getElementById("cod-injetar") as HTMLButtonElement;
  const cenarioSim = cenario ? CENARIO_SIM[cenario.id] : undefined;

  inputOperador.value = localStorage.getItem(CHAVE_OPERADOR) ?? "operador";
  inputToken.value = localStorage.getItem(CHAVE_TOKEN) ?? "";
  inputOperador.addEventListener("change", () =>
    localStorage.setItem(CHAVE_OPERADOR, inputOperador.value.trim()),
  );
  inputToken.addEventListener("change", () => localStorage.setItem(CHAVE_TOKEN, inputToken.value.trim()));

  const cod: EstadoCod = {
    api,
    ativo: false,
    estado: null,
    ultimoErro: null,
    atualizacoes: 0,
    pronto: Promise.resolve(),
    atualizar,
    injetar,
    aprovar: (id) => acao(`propostas/${id}/aprovar`, {}),
    passo: (id) => acao(`propostas/${id}/passo`, {}),
    rejeitar: (id, motivo = "") => acao(`propostas/${id}/rejeitar`, { motivo }),
  };
  (window as unknown as { cod: EstadoCod }).cod = cod;

  let hashMapa: string | null = null; // hash da auditoria quando o mapa foi redesenhado
  let mapaDesenhado = false;
  let ocupado = false; // ação humana em curso
  let atualizando = false; // leitura em curso (evita sobrepor polls lentos)

  function cabecalhos(): Record<string, string> {
    const h: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Operador": inputOperador.value.trim() || "operador",
    };
    const token = inputToken.value.trim();
    if (token) h["X-Console-Token"] = token;
    return h;
  }

  async function chamar<T>(rota: string, corpo?: unknown): Promise<T> {
    const resp = await fetch(api + rota, {
      method: corpo === undefined ? "GET" : "POST",
      headers: corpo === undefined ? {} : cabecalhos(),
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try {
        const j = (await resp.json()) as { detail?: unknown };
        if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
      } catch {
        /* sem corpo JSON */
      }
      throw new ErroApi(resp.status, detail);
    }
    return (await resp.json()) as T;
  }

  async function acao(rota: string, corpo: unknown): Promise<unknown> {
    if (ocupado) return null;
    ocupado = true;
    mostrarErro(null);
    try {
      const r = await chamar(rota, corpo);
      await atualizar();
      return r;
    } catch (e) {
      mostrarErro(e instanceof Error ? e.message : String(e));
      throw e;
    } finally {
      ocupado = false;
    }
  }

  async function injetar(nome = cenarioSim): Promise<unknown> {
    if (!nome) throw new Error("cenário sem evento nomeado no simulador");
    // com uma falta já tratada, reinicia a demo: recarrega o cluster (rede normal) antes de injetar
    return acao("eventos", { cenario: nome, recarregar: !!cod.estado?.falta });
  }

  function mostrarErro(msg: string | null) {
    cod.ultimoErro = msg;
    const p = document.getElementById("cod-erro")!;
    p.hidden = !msg;
    p.textContent = msg ?? "";
  }

  async function redesenharMapa(estado: Estado) {
    // o GeoJSON do backend reflete o gêmeo depois de isolar/executar; recarrega quando a auditoria
    // avançou (hash novo) e há cluster carregado
    if (!estado.cluster || (mapaDesenhado && estado.hash === hashMapa)) return;
    hashMapa = estado.hash;
    mapaDesenhado = true;
    try {
      if (!mapa.isStyleLoaded()) await new Promise<void>((r) => mapa.once("idle", () => r()));
      await carregarEstado(mapa, api + "estado.geojson");
    } catch (e) {
      mostrarErro(e instanceof Error ? e.message : String(e));
    }
  }

  async function atualizar(): Promise<void> {
    if (atualizando) return;
    atualizando = true;
    try {
      await _atualizar();
    } finally {
      atualizando = false;
    }
  }

  async function _atualizar(): Promise<void> {
    let estado: Estado;
    try {
      estado = await chamar<Estado>("estado");
    } catch (e) {
      if (!cod.ativo) {
        secao.hidden = true;
        return;
      }
      mostrarErro(`backend indisponível: ${e instanceof Error ? e.message : String(e)}`);
      return;
    }
    cod.ativo = true;
    cod.estado = estado;
    cod.atualizacoes++;
    secao.hidden = false;
    const pendente = estado.propostas.find((p) => p.status === "pendente" || p.status === "aprovada");
    let detalhe: Proposta | null = null;
    let auditoria: Auditoria | null = null;
    try {
      if (pendente) detalhe = await chamar<Proposta>(`propostas/${pendente.id}`);
      auditoria = await chamar<Auditoria>("auditoria?n=8");
    } catch (e) {
      mostrarErro(e instanceof Error ? e.message : String(e));
    }
    render(estado, detalhe, auditoria);
    await redesenharMapa(estado);
  }

  function render(estado: Estado, detalhe: Proposta | null, auditoria: Auditoria | null) {
    raiz.replaceChildren();
    const ag = estado.agente;
    const clusterCerto = !cenario || !estado.cluster_demo || estado.cluster_demo === cenario.id;

    // -- situação ------------------------------------------------------------------------------
    const linhas: string[] = [];
    linhas.push(`cluster: ${estado.cluster ?? "nenhum carregado"}`);
    if (estado.falta) linhas.push(`falta em ${estado.falta} · religador ${estado.religador ?? "—"}`);
    if (estado.sem_tensao && estado.sem_tensao.n_nos)
      linhas.push(
        `sem tensão: ${estado.sem_tensao.n_nos} nós · ${estado.sem_tensao.clientes.ucbt} UCBT · ` +
          `${estado.sem_tensao.clientes.trafos} trafos`,
      );
    linhas.push(
      `agente: ${ag ? `${ag.provider ?? "?"}${ag.modelo ? ` · ${ag.modelo}` : ""}` : "desligado"}` +
        (ag?.ocupado ? " · pensando…" : ""),
    );
    linhas.push(`eventos na fila: ${estado.eventos_n} · autorização: ${estado.autorizacao}`);
    linhas.push(
      `replanejamentos automáticos: ${estado.replanejamentos_evento}/${estado.limite_replanejamentos_evento}`,
    );
    if (estado.restricoes?.length)
      linhas.push(`restrições ativas: ${estado.restricoes.map((r) => r.motivo).join(" · ")}`);
    const situacao = el("div", { class: "cod-situacao", id: "cod-situacao" });
    for (const l of linhas) situacao.append(el("div", {}, l));
    if (!clusterCerto)
      situacao.append(
        el(
          "div",
          { class: "aviso" },
          `o backend está com o cluster "${estado.cluster_demo}"; abra ?cenario=${estado.cluster_demo}`,
        ),
      );
    if (ag?.erro) situacao.append(el("div", { class: "erro" }, `agente: ${ag.erro}`));
    raiz.append(situacao);

    // -- evento em curso -----------------------------------------------------------------------
    if (ag?.ocupado && ag.evento_atual) {
      const ev = ag.evento_atual;
      raiz.append(
        el(
          "p",
          { class: "cod-evento", id: "cod-evento" },
          `⏳ ${rotuloTipo(ev.tipo)} em ${ev.trecho ?? ev.chave ?? ev.ctmt ?? "—"} — o agente localiza, ` +
            "isola e avalia opções no gêmeo…",
        ),
      );
    }

    btnInjetar.disabled = !cenarioSim || !!ag?.ocupado || estado.autorizacao === "bloqueado";
    btnInjetar.textContent = estado.falta ? "reiniciar e injetar falta" : "injetar falta";
    btnInjetar.title = cenarioSim
      ? `POST api/eventos {cenario: "${cenarioSim}"${estado.falta ? ", recarregar: true" : ""}}`
      : "escolha um cenário da demo para injetar a falta";

    // -- proposta ------------------------------------------------------------------------------
    const p = detalhe ?? estado.propostas.find((x) => x.status === "pendente") ?? null;
    if (p) raiz.append(cartaoProposta(p, estado));
    else if (ag?.ultima && !ag.ocupado) {
      const u = ag.ultima;
      const texto = u.erro
        ? `última execução falhou: ${u.erro}`
        : u.proposta
          ? `última proposta ${u.proposta} concluída`
          : (u.resposta ?? "o agente não gerou proposta");
      raiz.append(el("p", { class: "dica cod-ultima" }, texto));
    }

    // -- histórico curto -----------------------------------------------------------------------
    const anteriores = estado.propostas.filter((x) => x.id !== p?.id).slice(-3).reverse();
    if (anteriores.length) {
      const ul = el("ul", { class: "cod-historico" });
      for (const a of anteriores)
        ul.append(
          el(
            "li",
            {},
            `${a.id} · ${a.status}${a.aprovada_por ? ` por ${a.aprovada_por}` : ""} · ${a.falta ?? ""} → ${a.chave ?? "—"}`,
          ),
        );
      raiz.append(ul);
    }

    // -- auditoria -----------------------------------------------------------------------------
    raiz.append(blocoAuditoria(auditoria, estado));
  }

  function cartaoProposta(p: Proposta, estado: Estado): HTMLElement {
    const card = el("div", { class: `cod-proposta status-${p.status}`, id: "cod-proposta" });
    card.append(
      el("h3", {}, `${p.id} · ${p.status}`),
      el("div", { class: "dica" }, `falta ${p.falta ?? "—"} · criada ${hora(p.criada_em)}`),
    );
    // a sequência marca o que já foi aplicado (✓) e o próximo passo (▶) no modo passo a passo
    const feitas = p.executadas ?? 0;
    const emCurso = p.status === "pendente" || p.status === "aprovada";
    const seq = el("ol", { class: "cod-manobras" });
    p.manobras.forEach((m, i) => {
      const classe = i < feitas ? "feita" : i === feitas && emCurso ? "atual" : "";
      const marca = i < feitas ? "✓ " : i === feitas && emCurso && feitas > 0 ? "▶ " : "";
      seq.append(el("li", { class: classe }, `${marca}${m.acao} ${m.chave}`));
    });
    const progresso = feitas ? ` · ${feitas}/${p.manobras.length} executadas` : "";
    card.append(el("div", { class: "rotulo" }, `manobras (→ ${p.fonte ?? "—"})${progresso}`), seq);
    if (p.ja_satisfeitas?.length)
      card.append(el("div", { class: "dica" }, `já abertas: ${p.ja_satisfeitas.join(", ")}`));
    if (p.clientes)
      card.append(
        el(
          "div",
          {},
          `clientes recuperados: ${p.clientes.ucbt} UCBT · ${p.clientes.ucmt} UCMT · ` +
            `${p.clientes.trafos} trafos (${p.clientes.kva.toFixed(0)} kVA)`,
        ),
      );
    if (p.score)
      card.append(
        el(
          "div",
          { class: p.score.viavel ? "ok" : "erro" },
          `gêmeo: ${p.score.viavel ? "viável" : "inviável"} · margem disjuntor ${pct(p.score.margem_disjuntor)} · ` +
            `Vmin MT ${pu(p.score.vmin_mt_pu)}` +
            (p.score.motivos?.length ? ` · ${p.score.motivos.join("; ")}` : ""),
        ),
      );
    if (p.replanejada_apos_rejeicao)
      card.append(
        el(
          "div",
          { class: "cod-motivo" },
          `replanejada após rejeição: ${p.replanejada_apos_rejeicao}`,
        ),
      );
    if (p.verificador) {
      const v = p.verificador;
      const n = Object.keys(v.checagens ?? {}).length;
      const okN = Object.values(v.checagens ?? {}).filter(Boolean).length;
      card.append(
        el(
          "div",
          { class: v.ok ? "ok" : "erro" },
          `verificador: ${v.ok ? "aprovou" : "recusou"} (${okN}/${n} checagens)` +
            (v.problemas?.length ? ` · ${v.problemas.join("; ")}` : ""),
        ),
      );
    }
    if (p.motivo) card.append(el("p", { class: "cod-motivo" }, p.motivo));
    if (p.alternativas?.length) {
      const det = el("details", {});
      det.append(el("summary", {}, `alternativas (${p.alternativas.length})`));
      const ul = el("ul", {});
      const escolhida = p.alternativas.find((a) => a.escolhida);
      for (const a of p.alternativas)
        ul.append(
          el(
            "li",
            { class: a.escolhida ? "escolhida" : "" },
            `${a.chave} → ${a.fonte}${a.tlcd ? "" : " (sem telecomando)"} · ${a.clientes.ucbt} UCBT` +
              (a.score
                ? ` · ${a.score.viavel ? "viável" : "inviável"} · margem ${pct(a.score.margem_disjuntor)}`
                : " · sem score") +
              (a.escolhida ? " ← escolhida" : ` · ${motivoDescarte(a, escolhida)}`),
          ),
        );
      det.append(ul);
      card.append(det);
    }
    if (emCurso) {
      const bloqueado = estado.autorizacao === "bloqueado";
      const restantes = p.manobras.length - feitas;
      const aprovar = el(
        "button",
        { type: "button", id: "cod-aprovar", class: "primario" },
        !feitas ? "Aprovar e executar" : restantes === 1 ? "Executar a última" : `Executar as ${restantes} restantes`,
      );
      // pedido 1 da revisão PR-15: uma manobra por clique (passo único do MCP), o mapa recolore a cada uma
      const proximo = p.proximo_passo ?? p.manobras[feitas];
      const passo = el(
        "button",
        { type: "button", id: "cod-passo" },
        `${feitas ? "Próxima" : "Aprovar e executar a 1ª"} manobra` +
          (proximo ? `: ${proximo.acao} ${proximo.chave}` : "") +
          ` (${feitas + 1}/${p.manobras.length})`,
      );
      const motivo = el("input", {
        type: "text",
        id: "cod-rejeitar-motivo",
        placeholder: "motivo da rejeição",
      }) as HTMLInputElement;
      const sugestoes = el("div", { class: "cod-sugestoes" });
      for (const texto of SUGESTOES_REJEICAO) {
        const botao = el("button", { type: "button", class: "cod-sugestao" }, texto);
        botao.addEventListener("click", () => {
          motivo.value = texto;
          motivo.focus();
        });
        sugestoes.append(botao);
      }
      const rejeitar = el("button", { type: "button", id: "cod-rejeitar" }, "Rejeitar e replanejar");
      aprovar.disabled = passo.disabled = bloqueado || !!estado.agente?.ocupado;
      if (estado.agente?.ocupado) aprovar.title = passo.title = "aguarde o agente concluir a resposta";
      else passo.title = `POST api/propostas/${p.id}/passo — aprova (se pendente) e executa só a próxima manobra`;
      rejeitar.disabled = motivo.disabled = bloqueado || feitas > 0; // com manobras já aplicadas não há mais o que rejeitar
      sugestoes.querySelectorAll("button").forEach((b) => {
        (b as HTMLButtonElement).disabled = rejeitar.disabled;
      });
      aprovar.addEventListener("click", () => void cod.aprovar(p.id).catch(() => undefined));
      passo.addEventListener("click", () => void cod.passo(p.id).catch(() => undefined));
      rejeitar.addEventListener("click", () => {
        void cod
          .rejeitar(p.id, motivo.value)
          .then((r) => {
            const resposta = r as RejeicaoResposta | null;
            const msg = resposta?.replanejamento?.mensagem;
            if (msg && resposta?.replanejamento?.status !== "iniciado" && resposta?.replanejamento?.status !== "concluido")
              mostrarErro(msg);
          })
          .catch(() => undefined);
      });
      card.append(
        el("div", { class: "cod-acoes" }, aprovar, rejeitar),
        el("div", { class: "cod-acoes" }, passo),
        el("label", { class: "cod-rejeicao" }, "Motivo da rejeição", motivo),
        sugestoes,
      );
      if (bloqueado)
        card.append(
          el(
            "p",
            { class: "erro" },
            "backend sem BDGD_CONSOLE_TOKEN: defina a variável (ou rode `serve --sem-segredo`) para aprovar.",
          ),
        );
    } else if (p.aprovada_por) {
      card.append(el("div", { class: "dica" }, `${p.status} por ${p.aprovada_por}`));
    }
    return card;
  }

  function blocoAuditoria(a: Auditoria | null, estado: Estado): HTMLElement {
    const bloco = el("div", { class: "cod-auditoria", id: "cod-auditoria" });
    const n = a?.n_total ?? estado.audit_n ?? 0;
    const hashCurto = (a?.hash ?? estado.hash)?.slice(0, 12) ?? "—";
    const integra = a?.integra;
    const rotulo = el(
      "div",
      { class: `rotulo ${integra === false ? "erro" : ""}` },
      `auditoria: ${n} registros · ` +
        (integra === null || integra === undefined
          ? "sem trilha"
          : integra
            ? "trilha íntegra ✓ "
            : "TRILHA CORROMPIDA ✗ "),
    );
    if (integra !== null && integra !== undefined) rotulo.append(el("code", { class: "hash" }, hashCurto));
    bloco.append(rotulo);
    if (a?.registros.length) {
      const ul = el("ul", {});
      for (const r of [...a.registros].reverse())
        ul.append(
          el(
            "li",
            {},
            `${hora(r.ts)} · ${r.tipo}${r.ferramenta ? ` ${r.ferramenta}` : ""}` +
              `${r.operador ? ` · ${r.operador}` : ""}${r.proposta_id ? ` · ${r.proposta_id}` : ""}` +
              `${r.erro ? ` · erro: ${r.erro}` : ""}`,
          ),
        );
      bloco.append(ul);
    }
    return bloco;
  }

  btnInjetar.addEventListener("click", () => void injetar().catch(() => undefined));

  // sonda inicial + polling; a seção só aparece se o backend responder
  cod.pronto = atualizar().then(() => {
    if (cod.ativo) setInterval(() => void atualizar(), INTERVALO_MS);
  });
  return cod;
}
