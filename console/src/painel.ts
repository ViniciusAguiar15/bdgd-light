/**
 * Painel lateral: bases, toggles de camada (só as presentes no PMTiles), info dos tiles e erros.
 */
import type { Map as MapaLibre } from "maplibre-gl";
import { GRUPOS, type Grupo } from "./camadas";
import type { Cenario } from "./cenarios";

export interface Base {
  id: string;
  titulo: string;
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

/** Seletor de cenário (tiles + estado + vista inicial); `ativo` null = tiles avulsos via ?tiles=. */
export function montarCenarios(
  cenarios: Cenario[],
  ativo: string | null,
  aoEscolher: (id: string) => void,
) {
  const raiz = document.getElementById("cenarios")!;
  raiz.replaceChildren();
  for (const c of cenarios) {
    const input = el("input", { type: "radio", name: "cenario", value: c.id });
    input.checked = c.id === ativo;
    input.addEventListener("change", () => aoEscolher(c.id));
    const lbl = el("label", { class: "item" }, input, c.titulo);
    lbl.title = c.descricao;
    raiz.append(lbl);
  }
  const atual = cenarios.find((c) => c.id === ativo);
  raiz.append(
    el("p", { class: "dica", id: "cenario-descricao" }, atual?.descricao ?? "tiles avulsos (?tiles=)"),
  );
}

export function montarBases(mapa: MapaLibre, bases: Base[], ativa: string) {
  const raiz = document.getElementById("bases")!;
  raiz.replaceChildren();
  for (const b of bases) {
    const input = el("input", { type: "radio", name: "base", value: b.id });
    input.checked = b.id === ativa;
    input.addEventListener("change", () => {
      for (const o of bases)
        mapa.setLayoutProperty(o.id, "visibility", o.id === b.id ? "visible" : "none");
    });
    raiz.append(el("label", { class: "item" }, input, b.titulo));
  }
}

function amostra(g: Grupo): HTMLElement {
  const s = el("span", { class: `amostra ${g.amostra.forma}` });
  if (g.amostra.forma === "area") {
    s.style.background = g.amostra.cor + "40";
    s.style.borderColor = g.amostra.cor;
  } else {
    s.style.background = g.amostra.cor;
  }
  return s;
}

/**
 * Monta os toggles das camadas. `presentes` = nomes de source-layer no PMTiles (metadata
 * vector_layers); `contagens` = nº de feições por camada, se disponível no metadata.
 */
export function montarCamadas(
  mapa: MapaLibre,
  presentes: Set<string>,
  contagens: Record<string, number>,
) {
  const raiz = document.getElementById("camadas")!;
  raiz.replaceChildren();
  const grupos = [...GRUPOS].reverse(); // desenhadas por cima primeiro na lista
  for (const g of grupos) {
    if (!presentes.has(g.id)) continue;
    const input = el("input", { type: "checkbox" });
    input.checked = g.visivel;
    input.addEventListener("change", () => {
      for (const l of g.layers)
        mapa.setLayoutProperty(l.id, "visibility", input.checked ? "visible" : "none");
    });
    const texto = el("span", {}, g.titulo);
    texto.title = g.descricao;
    const n = contagens[g.id];
    const lbl = el("label", { class: "item" }, input, amostra(g), texto);
    if (n !== undefined) lbl.append(el("span", { class: "n" }, n.toLocaleString("pt-BR")));
    raiz.append(lbl);
  }
  if (!raiz.childElementCount)
    raiz.append(el("p", { class: "dica" }, "nenhuma camada conhecida neste PMTiles"));
}

export function mostrarErro(msg: string | null) {
  const p = document.getElementById("erro")!;
  p.hidden = !msg;
  p.textContent = msg ?? "";
}

export function infoTiles(texto: string) {
  document.getElementById("info-tiles")!.textContent = texto;
}

export function subtitulo(texto: string) {
  document.getElementById("subtitulo")!.textContent = texto;
}

export function formTiles(valor: string, aoEnviar: (url: string) => void) {
  const input = document.getElementById("url-tiles") as HTMLInputElement;
  input.value = valor;
  document.getElementById("form-tiles")!.addEventListener("submit", (ev) => {
    ev.preventDefault();
    aoEnviar(input.value.trim());
  });
}

/** Legenda + resumo do estado do grafo (`?estado=`). */
export function mostrarEstado(resumo: {
  url: string;
  trechos: number;
  desenergizados: number;
  chavesAbertas: number;
  trafosSemTensao: number;
} | null) {
  const secao = document.getElementById("secao-estado")!;
  const raiz = document.getElementById("estado")!;
  raiz.replaceChildren();
  secao.hidden = !resumo;
  if (!resumo) return;
  const linha = (cor: string, forma: string, txt: string) => {
    const s = el("span", { class: `amostra ${forma}` });
    s.style.background = cor;
    return el("label", { class: "item" }, s, txt);
  };
  raiz.append(
    linha("#00e676", "linha", `trechos energizados: ${resumo.trechos - resumo.desenergizados}`),
    linha("#ff1744", "linha", `trechos desenergizados: ${resumo.desenergizados}`),
    linha("#ffffff", "ponto", `chaves abertas: ${resumo.chavesAbertas}`),
    linha("#ff1744", "ponto", `trafos sem tensão: ${resumo.trafosSemTensao}`),
    el("p", { class: "dica" }, resumo.url),
  );
}
