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
import { carregarEstado, destacarTrechos } from "./estado";

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
  iteracoes?: number;
  controle_iteracoes?: number | null;
  i_disjuntor_a?: number | null;
  i_nominal_a?: number | null;
  margem_disjuntor: number | null;
  vmin_mt_pu: number | null;
  vmin_mt_barra?: string | null;
  vmax_mt_pu?: number | null;
  vmax_mt_barra?: string | null;
  carregamento_max_mt_pct: number | null;
  trechos_carregados_mt?: TrechoCarregado[];
  perfil_tensao_mt?: PontoPerfilTensao[];
  convergencia?: ConvergenciaEletrica | null;
  perdas_kw?: number | null;
  motivos: string[];
  simulado_em?: string | null;
  estado_rede?: EstadoRedeScore | null;
}

interface TrechoCarregado {
  elemento: string;
  cod_id: string | null;
  i_max_a: number | null;
  i_nominal_a: number | null;
  carregamento_pct: number | null;
}

interface PontoPerfilTensao {
  barra: string;
  distancia_m: number | null;
  v_pu: number | null;
}

interface ConvergenciaEletrica {
  convergiu: boolean;
  iteracoes: number;
  controle_iteracoes: number | null;
  ajustes: string[];
  tempo_s: number;
}

interface ImpactoDECConjunto {
  codigo: string;
  nome: string;
  total_uc: number;
  ucs_restauradas_no_conjunto: number;
  dec_horas: number;
  dec_minutos: number;
}

interface ImpactoEstimado {
  tempo_reparo_min: number;
  tempo_manobra_min: number;
  clientes_restaurados: number;
  clientes_sem_tensao_ate_reparo: number;
  consumidor_minutos_evitados: number;
  premissa: string;
  dec_conjunto: ImpactoDECConjunto | null;
}

interface EstadoRedeScore {
  cluster: string | null;
  falta: string | null;
  religador: string | null;
  manobras: { acao: string; chave: string }[];
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

interface DestaquesExecucao {
  trechos: string[];
  n_subtensao?: number | null;
  n_sobretensao?: number | null;
  n_sobrecargas?: number | null;
  loadmult?: number | null;
}

interface EventoResumo {
  id?: string;
  tipo: string;
  trecho?: string;
  ctmt?: string;
  chave?: string;
  cenario?: string;
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
  impacto?: ImpactoEstimado | null;
  status: "pendente" | "aprovada" | "executada" | "rejeitada" | "expirada" | string;
  aprovada_por: string | null;
  motivo: string | null;
  replanejada_apos_rejeicao: string | null;
  restricoes_resumo?: string[];
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
  impacto?: ImpactoEstimado | null;
  bloqueada?: string | null;
}

interface Execucao {
  tipo?: string;
  evento?: EventoResumo | null;
  alvo?: string | null;
  sem_manobra?: boolean;
  destaques?: DestaquesExecucao | null;
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
  id?: string;
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

interface DetalhesEletricosResposta {
  proposta_id: string;
  status: string;
  falta: string | null;
  escolhida: string | null;
  simulado_em?: string | null;
  estado_rede?: EstadoRedeScore | null;
  opcoes: {
    chave: string;
    fonte: string;
    tlcd: boolean;
    externa: boolean;
    clientes: Clientes;
    escolhida: boolean;
    score: Score;
  }[];
}

/** Cenário do console → cenário nomeado do simulador (`bdgd_light.sim.CENARIOS`). */
export const CENARIO_SIM: Record<string, string> = {
  tijuca: "tijuca_cabofrio_tronco",
  ipanema: "ipanema_9210",
  taquara: "taquara_bocari",
};

type TipoEventoConsole = "falta_permanente" | "pico_carga" | "chave_indisponivel";

const EVENTOS_CONSOLE: Record<string, Partial<Record<TipoEventoConsole, Record<string, unknown>>>> = {
  tijuca: {
    falta_permanente: { cenario: "tijuca_cabofrio_tronco" },
    pico_carga: { tipo: "pico_carga", cluster: "tijuca", ctmt: "ALC9925" },
    chave_indisponivel: { tipo: "chave_indisponivel", cluster: "tijuca" },
  },
  ipanema: {
    falta_permanente: { cenario: "ipanema_9210" },
    pico_carga: { tipo: "pico_carga", cluster: "ipanema", ctmt: "PTS0001" },
    chave_indisponivel: { tipo: "chave_indisponivel", cluster: "ipanema", chave: "10934177" },
  },
  taquara: {
    falta_permanente: { cenario: "taquara_bocari" },
    pico_carga: { tipo: "pico_carga", cluster: "taquara", ctmt: "TQR33862" },
    chave_indisponivel: { tipo: "chave_indisponivel", cluster: "taquara" },
  },
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
  injetar: (tipo?: TipoEventoConsole) => Promise<unknown>;
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

function pctDireto(v: number | null | undefined): string {
  return v === null || v === undefined || Number.isNaN(v) ? "—" : `${Math.round(v)}%`;
}

function pu(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${v.toFixed(3)} pu`;
}

function ampere(v: number | null | undefined): string {
  return v === null || v === undefined || Number.isNaN(v) ? "—" : `${Math.round(v)} A`;
}

function kw(v: number | null | undefined): string {
  return v === null || v === undefined || Number.isNaN(v) ? "—" : `${v.toFixed(1)} kW`;
}

function hora(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString("pt-BR");
}

function horaCurta(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function milConsumidorMinutos(valor: number | null | undefined): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return "—";
  if (Math.abs(valor) >= 1000) return `${(valor / 1000).toFixed(1).replace(".", ",")} mil`;
  return Math.round(valor).toLocaleString("pt-BR");
}

function resumoImpacto(impacto: ImpactoEstimado | null | undefined): string | null {
  if (!impacto) return null;
  const partes = [
    `≈ ${milConsumidorMinutos(impacto.consumidor_minutos_evitados)} consumidor-minutos evitados`,
  ];
  if (impacto.dec_conjunto?.nome && impacto.dec_conjunto.dec_minutos !== undefined)
    partes.push(
      `≈ ${impacto.dec_conjunto.dec_minutos.toFixed(1).replace(".", ",")} min de DEC no conjunto ${impacto.dec_conjunto.nome}`,
    );
  else
    partes.push(`${impacto.clientes_sem_tensao_ate_reparo} clientes seguem sem tensão até o reparo`);
  partes.push(
    `premissa: reparo em ${impacto.tempo_reparo_min} min, manobra em ${impacto.tempo_manobra_min} min`,
  );
  return partes.join(" · ");
}

function sparklinePerfil(perfil: PontoPerfilTensao[]): SVGSVGElement | null {
  const pontos = perfil.filter((p) => p.v_pu != null && p.distancia_m != null);
  if (pontos.length < 2) return null;
  const svgNs = "http://www.w3.org/2000/svg";
  const largura = 260;
  const altura = 84;
  const padX = 10;
  const padY = 10;
  const distMax = Math.max(...pontos.map((p) => p.distancia_m ?? 0), 1);
  const vMin = Math.min(...pontos.map((p) => p.v_pu ?? 1));
  const vMax = Math.max(...pontos.map((p) => p.v_pu ?? 1));
  const baseMin = Math.min(0.93, vMin);
  const baseMax = Math.max(1.05, vMax);
  const x = (distancia: number) => padX + ((largura - 2 * padX) * distancia) / distMax;
  const y = (tensao: number) =>
    altura -
    padY -
    ((altura - 2 * padY) * (tensao - baseMin)) / Math.max(baseMax - baseMin, 0.001);
  const polilinha = pontos.map((p) => `${x(p.distancia_m ?? 0)},${y(p.v_pu ?? 1)}`).join(" ");

  const svg = document.createElementNS(svgNs, "svg");
  svg.setAttribute("viewBox", `0 0 ${largura} ${altura}`);
  svg.setAttribute("class", "cod-sparkline");

  for (const ref of [0.93, 1.0, 1.05]) {
    if (ref < baseMin || ref > baseMax) continue;
    const linha = document.createElementNS(svgNs, "line");
    linha.setAttribute("x1", String(padX));
    linha.setAttribute("x2", String(largura - padX));
    linha.setAttribute("y1", String(y(ref)));
    linha.setAttribute("y2", String(y(ref)));
    linha.setAttribute("class", ref === 1.0 ? "referencia" : "limite");
    svg.append(linha);
  }

  const curva = document.createElementNS(svgNs, "polyline");
  curva.setAttribute("points", polilinha);
  curva.setAttribute("fill", "none");
  curva.setAttribute("class", "perfil");
  svg.append(curva);

  for (const p of [pontos[0], pontos[pontos.length - 1]]) {
    const no = document.createElementNS(svgNs, "circle");
    no.setAttribute("cx", String(x(p.distancia_m ?? 0)));
    no.setAttribute("cy", String(y(p.v_pu ?? 1)));
    no.setAttribute("r", "3");
    no.setAttribute("class", "ponto");
    svg.append(no);
  }
  return svg;
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

function descricaoEventoEmCurso(ev: Evento): string {
  if (ev.tipo === "pico_carga") {
    const loadmult =
      typeof ev.detalhes.loadmult === "number" ? ` com loadmult ${ev.detalhes.loadmult}` : "";
    return `⏳ pico de carga em ${ev.ctmt ?? "—"}${loadmult} — o agente roda o fluxo e verifica tensões e sobrecargas…`;
  }
  if (ev.tipo === "chave_indisponivel")
    return `⏳ chave indisponível em ${ev.chave ?? "—"} — o agente registra a restrição operacional e avalia o impacto a jusante…`;
  return `⏳ ${rotuloTipo(ev.tipo)} em ${ev.trecho ?? ev.chave ?? ev.ctmt ?? "—"} — o agente localiza, isola e avalia opções no gêmeo…`;
}

function resumoTrecho(t: TrechoCarregado): string {
  return `${t.cod_id ?? t.elemento} · ${pctDireto(t.carregamento_pct)}`;
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
  const seletorTipo = document.getElementById("cod-tipo-evento") as HTMLSelectElement;
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
  let propostaEletricaAberta: string | null = null;
  let trechoDestaque: string | null = null;
  let trechosDestaqueExecucao: string[] = [];
  let detalheAtual: Proposta | null = null;
  let auditoriaAtual: Auditoria | null = null;
  const detalhesEletricos = new Map<string, DetalhesEletricosResposta>();
  const carregandoDetalhes = new Set<string>();

  function tipoSelecionado(): TipoEventoConsole {
    const tipo = seletorTipo.value as TipoEventoConsole;
    if (tipo === "pico_carga" || tipo === "chave_indisponivel") return tipo;
    return "falta_permanente";
  }

  function eventoConfigAtual(tipo: TipoEventoConsole): Record<string, unknown> {
    const chave = cenario?.id ?? cod.estado?.cluster_demo ?? "";
    const base = { ...(EVENTOS_CONSOLE[chave]?.[tipo] ?? { tipo }) };
    if (!("cenario" in base) && !("tipo" in base)) base.tipo = tipo;
    if (!("cenario" in base) && !("cluster" in base) && cod.estado?.cluster_demo)
      base.cluster = cod.estado.cluster_demo;
    if (cod.estado?.falta) base.recarregar = true;
    return base;
  }

  function aplicarDestaqueAtual() {
    destacarTrechos(mapa, trechoDestaque ? [trechoDestaque] : trechosDestaqueExecucao);
  }

  function atualizarBotaoInjecao(estado: Estado | null = cod.estado) {
    const tipo = tipoSelecionado();
    const podeInjetar = !!(cenarioSim || estado?.cluster);
    btnInjetar.disabled = !podeInjetar || !!estado?.agente?.ocupado || estado?.autorizacao === "bloqueado";
    btnInjetar.textContent =
      tipo === "falta_permanente"
        ? estado?.falta
          ? "reiniciar e injetar falta"
          : "injetar falta"
        : `injetar ${rotuloTipo(tipo)}`;
    const corpo = eventoConfigAtual(tipo);
    btnInjetar.title = podeInjetar
      ? `POST api/eventos ${JSON.stringify(corpo)}`
      : "abra um cenário da demo ou conecte o console a um backend com cluster carregado";
  }

  seletorTipo.addEventListener("change", () => atualizarBotaoInjecao());

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

  async function injetar(tipo = tipoSelecionado()): Promise<unknown> {
    const corpo = eventoConfigAtual(tipo);
    if (!corpo.cenario && !corpo.cluster && !cod.estado?.cluster)
      throw new Error("abra um cenário da demo ou carregue um cluster no backend antes de injetar");
    return acao("eventos", corpo);
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
      aplicarDestaqueAtual();
    } catch (e) {
      mostrarErro(e instanceof Error ? e.message : String(e));
    }
  }

  async function carregarDetalhesEletricos(propostaId: string): Promise<void> {
    if (detalhesEletricos.has(propostaId) || carregandoDetalhes.has(propostaId)) return;
    carregandoDetalhes.add(propostaId);
    try {
      const resposta = await chamar<DetalhesEletricosResposta>(`propostas/${propostaId}/eletrico`);
      detalhesEletricos.set(propostaId, resposta);
    } catch (e) {
      mostrarErro(e instanceof Error ? e.message : String(e));
    } finally {
      carregandoDetalhes.delete(propostaId);
      if (cod.estado) render(cod.estado, detalheAtual, auditoriaAtual);
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
    detalheAtual = detalhe;
    auditoriaAtual = auditoria;
    render(estado, detalhe, auditoria);
    await redesenharMapa(estado);
  }

  function render(estado: Estado, detalhe: Proposta | null, auditoria: Auditoria | null) {
    raiz.replaceChildren();
    const ag = estado.agente;
    const clusterCerto = !cenario || !estado.cluster_demo || estado.cluster_demo === cenario.id;
    if (!detalhe && ag?.ultima?.evento?.tipo === "pico_carga") {
      trechosDestaqueExecucao = ag.ultima.destaques?.trechos ?? [];
      if (trechoDestaque && !trechosDestaqueExecucao.includes(trechoDestaque)) trechoDestaque = null;
    } else {
      trechosDestaqueExecucao = [];
      if (!detalhe) trechoDestaque = null;
    }

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
      raiz.append(el("p", { class: "cod-evento", id: "cod-evento" }, descricaoEventoEmCurso(ev)));
    }

    atualizarBotaoInjecao(estado);
    seletorTipo.disabled = !!ag?.ocupado || estado.autorizacao === "bloqueado";

    // -- proposta ------------------------------------------------------------------------------
    const p =
      detalhe ?? estado.propostas.find((x) => x.status === "pendente" || x.status === "aprovada") ?? null;
    if (p) raiz.append(cartaoProposta(p, estado));
    else if (ag?.ultima && !ag.ocupado) raiz.append(cartaoExecucao(ag.ultima));

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
    aplicarDestaqueAtual();
  }

  function cartaoExecucao(u: Execucao): HTMLElement {
    const evento = u.evento;
    const card = el("div", { class: "cod-execucao", id: "cod-execucao" });
    const titulo = evento ? `${evento.id ?? "último evento"} · ${rotuloTipo(evento.tipo)}` : "última execução";
    card.append(el("h3", {}, titulo));
    if (evento) {
      const origem = evento.cenario ? `cenário ${evento.cenario}` : "injeção direta";
      card.append(
        el(
          "div",
          { class: "dica" },
          `${u.alvo ?? evento.trecho ?? evento.ctmt ?? evento.chave ?? "—"} · ${origem}`,
        ),
      );
    }
    if (u.sem_manobra) {
      card.append(
        el(
          "div",
          { class: "ok" },
          "veredito: sem manobra · somente diagnóstico e orientação operacional",
        ),
      );
    } else if (u.proposta) {
      card.append(el("div", { class: "dica" }, `última proposta ${u.proposta} concluída`));
    }
    if (u.resposta) card.append(el("p", {}, u.resposta));
    if (u.destaques) {
      const partes: string[] = [];
      if (u.destaques.loadmult != null) partes.push(`loadmult ${u.destaques.loadmult}`);
      if (u.destaques.n_sobrecargas != null) partes.push(`${u.destaques.n_sobrecargas} sobrecarga(s)`);
      if (u.destaques.n_subtensao != null) partes.push(`${u.destaques.n_subtensao} nó(s) em subtensão`);
      if (u.destaques.n_sobretensao) partes.push(`${u.destaques.n_sobretensao} nó(s) em sobretensão`);
      if (partes.length) card.append(el("div", { class: "rotulo" }, `fluxo previsto · ${partes.join(" · ")}`));
      if (u.destaques.trechos.length) {
        const botoes = el("div", { class: "cod-destaques" });
        for (const codTrecho of u.destaques.trechos) {
          const botao = el("button", { type: "button" }, codTrecho);
          botao.addEventListener("click", () => {
            trechoDestaque = trechoDestaque === codTrecho ? null : codTrecho;
            aplicarDestaqueAtual();
            if (cod.estado) render(cod.estado, detalheAtual, auditoriaAtual);
          });
          botoes.append(botao);
        }
        card.append(el("div", { class: "rotulo" }, "trechos violados destacados no mapa"), botoes);
      }
    }
    if (u.erro) card.append(el("div", { class: "erro" }, `falha: ${u.erro}`));
    return card;
  }

  function blocoDetalhesEletricos(p: Proposta, estado: Estado): HTMLElement {
    const det = el("details", { class: "cod-eletrico" });
    if (propostaEletricaAberta === p.id) det.open = true;
    const cache = detalhesEletricos.get(p.id);
    const nOpcoes = cache?.opcoes.length ?? p.alternativas?.filter((a) => a.score).length ?? 0;
    const cabecalho = `detalhes elétricos${nOpcoes ? ` (${nOpcoes} opção${nOpcoes > 1 ? "ões" : ""})` : ""}${
      cache?.simulado_em ? ` · simulado às ${horaCurta(cache.simulado_em)}` : ""
    }`;
    det.append(
      el("summary", {}, cabecalho),
    );
    det.addEventListener("toggle", () => {
      propostaEletricaAberta = det.open ? p.id : null;
      if (!det.open) {
        trechoDestaque = null;
        aplicarDestaqueAtual();
        return;
      }
      void carregarDetalhesEletricos(p.id);
    });

    if (propostaEletricaAberta === p.id && carregandoDetalhes.has(p.id) && !cache) {
      det.append(el("div", { class: "dica" }, "carregando visão do OpenDSS…"));
      return det;
    }
    if (!cache) {
      det.append(el("div", { class: "dica" }, "abra para carregar corrente, tensão, perdas e convergência."));
      return det;
    }

    const tabela = el("table", { class: "cod-tabela-eletrica" });
    tabela.append(
      el(
        "thead",
        {},
        el(
          "tr",
          {},
          el("th", {}, "opção"),
          el("th", {}, "fonte"),
          el("th", {}, "margem"),
          el("th", {}, "I disj."),
          el("th", {}, "Vmin"),
          el("th", {}, "Vmax"),
          el("th", {}, "trecho crítico"),
          el("th", {}, "perdas"),
          el("th", {}, "conv."),
        ),
      ),
    );
    const corpo = el("tbody");
    for (const opcao of cache.opcoes) {
      const score = opcao.score;
      const pior = score.trechos_carregados_mt?.[0];
      corpo.append(
        el(
          "tr",
          { class: opcao.escolhida ? "escolhida" : score.viavel ? "viavel" : "inviavel" },
          el("td", {}, `${opcao.chave}${opcao.escolhida ? " ← escolhida" : ""}`),
          el("td", {}, `${opcao.fonte}${opcao.tlcd ? "" : " · manual"}`),
          el("td", {}, pct(score.margem_disjuntor)),
          el("td", {}, ampere(score.i_disjuntor_a)),
          el("td", {}, `${pu(score.vmin_mt_pu)}${score.vmin_mt_barra ? ` · ${score.vmin_mt_barra}` : ""}`),
          el("td", {}, `${pu(score.vmax_mt_pu)}${score.vmax_mt_barra ? ` · ${score.vmax_mt_barra}` : ""}`),
          el("td", {}, pior ? resumoTrecho(pior) : "—"),
          el("td", {}, kw(score.perdas_kw)),
          el("td", {}, score.convergiu ? `${score.iteracoes ?? score.convergencia?.iteracoes ?? 0} it.` : "não"),
        ),
      );
    }
    tabela.append(corpo);
    det.append(tabela);

    const escolhida = cache.opcoes.find((o) => o.escolhida) ?? cache.opcoes[0];
    const score = escolhida.score;
    const painel = el("div", { class: "cod-eletrico-escolhida" });
    painel.append(
      el("div", { class: "rotulo" }, `opção escolhida · ${escolhida.chave} → ${escolhida.fonte}`),
      el(
        "div",
        { class: score.viavel ? "ok" : "erro" },
        `${score.viavel ? "viável" : "inviável"} · perdas ${kw(score.perdas_kw)} · ` +
          `ajustes ${score.convergencia?.ajustes?.length ? score.convergencia.ajustes.join(", ") : "nenhum"}`,
      ),
    );
    const spark = sparklinePerfil(score.perfil_tensao_mt ?? []);
    if (spark) painel.append(spark);
    const perfil = score.perfil_tensao_mt ?? [];
    if (perfil.length) {
      const primeiro = perfil[0];
      const ultimo = perfil[perfil.length - 1];
      painel.append(
        el(
          "div",
          { class: "dica" },
          `perfil MT da fonte até a ponta: ${primeiro.barra} (${pu(primeiro.v_pu)}) → ` +
            `${ultimo.barra} (${pu(ultimo.v_pu)}) · ${ultimo.distancia_m?.toFixed(0) ?? "0"} m`,
        ),
      );
    }

    const trechos = el("table", { class: "cod-tabela-eletrica cod-trechos-carregados" });
    trechos.append(
      el(
        "thead",
        {},
        el(
          "tr",
          {},
          el("th", {}, "trecho"),
          el("th", {}, "carga"),
          el("th", {}, "corrente"),
          el("th", {}, "limite"),
        ),
      ),
    );
    const linhas = el("tbody");
    for (const trecho of score.trechos_carregados_mt ?? []) {
      const tr = el(
        "tr",
        {
          class: trecho.cod_id === trechoDestaque ? "selecionado" : "",
          title: trecho.cod_id
            ? `destacar ${trecho.cod_id} no mapa`
            : "trecho sem correspondência no mapa",
        },
        el("td", {}, trecho.cod_id ?? trecho.elemento),
        el("td", {}, pctDireto(trecho.carregamento_pct)),
        el("td", {}, ampere(trecho.i_max_a)),
        el("td", {}, ampere(trecho.i_nominal_a)),
      );
      if (trecho.cod_id) {
        tr.classList.add("clicavel");
        tr.addEventListener("click", () => {
          trechoDestaque = trechoDestaque === trecho.cod_id ? null : trecho.cod_id;
          aplicarDestaqueAtual();
          render(estado, detalheAtual, auditoriaAtual);
        });
      }
      linhas.append(tr);
    }
    trechos.append(linhas);
    painel.append(el("div", { class: "rotulo" }, "trechos mais carregados (clique para destacar no mapa)"), trechos);
    det.append(painel);
    return det;
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
    const impacto = resumoImpacto(p.impacto);
    if (impacto) card.append(el("div", { class: "dica" }, impacto));
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
    if (p.restricoes_resumo?.length)
      card.append(el("div", { class: "dica" }, `restrição aplicada: ${p.restricoes_resumo.join(" · ")}`));
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
    if (p.score) card.append(blocoDetalhesEletricos(p, estado));
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
