"""Atlas de interligações da Light: consolidação por alimentador e métricas do grafo de socorro."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import pandas as pd
from rich.console import Console

from bdgd_light.ingest.inventario import inventariar
from bdgd_light.ingest.parquet import DiretorioParquet

LARGURA_SVG = 960
ALTURA_SVG = 420
MARGEM_ESQ = 70
MARGEM_DIR = 30
MARGEM_SUP = 40
MARGEM_INF = 70


@dataclass(frozen=True)
class ResumoAtlas:
    """Métricas agregadas do atlas."""

    n_alimentadores: int
    n_ties_campo: int
    n_ties_telecomandadas: int
    n_pares_ctmt: int
    n_arestas: int
    n_grau_zero: int
    n_componentes: int
    maior_componente: int
    n_clientes_total: int
    n_clientes_sem_socorro: int
    pct_clientes_sem_socorro: float
    grau_maximo: int


@dataclass(frozen=True)
class ResultadoAtlas:
    """Saídas tabulares e gráficas da consolidação."""

    resumo: ResumoAtlas
    alimentadores: pd.DataFrame
    arestas: pd.DataFrame
    distribuicao_grau: pd.DataFrame
    componentes: pd.DataFrame
    grafo: nx.Graph


def consolidar_atlas(
    parquet_dir: str | Path,
    *,
    console: Console | None = None,
) -> ResultadoAtlas:
    """Consolida ties de campo e o grafo de socorro para todos os CTMT."""
    resultado_inv = inventariar(parquet_dir, console=console or Console(quiet=True))
    alimentadores = resultado_inv.tabela.copy()
    alimentadores["n_clientes"] = alimentadores["n_UCBT"] + alimentadores["n_UCMT"]

    fonte = DiretorioParquet(Path(parquet_dir))
    ctmt_extra = _carregar_ctmt_extra(fonte)
    alimentadores = alimentadores.merge(ctmt_extra, how="left", on="COD_ID")
    alimentadores["CONJ_CODIGO"] = alimentadores["CONJ_CODIGO"].fillna("").astype("string")
    alimentadores["CONJ_NOME"] = alimentadores["CONJ_NOME"].fillna("").astype("string")

    ties_campo = resultado_inv.interligacoes.loc[~resultado_inv.interligacoes["EM_SUB"]].copy()
    pares = _pares_simetricos_campo(ties_campo)
    arestas = _agrupar_arestas(ties_campo, alimentadores)
    grafo = _montar_grafo(alimentadores, arestas)
    componentes = _componentes_do_grafo(grafo, alimentadores)
    por_ctmt = _consolidar_por_ctmt(alimentadores, pares, grafo, componentes)
    distribuicao = _distribuicao_grau(grafo)

    clientes_total = int(por_ctmt["n_clientes"].sum())
    clientes_sem_socorro = int(por_ctmt.loc[por_ctmt["grau"] == 0, "n_clientes"].sum())
    resumo = ResumoAtlas(
        n_alimentadores=int(len(por_ctmt)),
        n_ties_campo=int(ties_campo["COD_ID"].nunique()),
        n_ties_telecomandadas=int(ties_campo.loc[ties_campo["TLCD"] == 1, "COD_ID"].nunique()),
        n_pares_ctmt=int(len(ties_campo)),
        n_arestas=int(len(arestas)),
        n_grau_zero=int((por_ctmt["grau"] == 0).sum()),
        n_componentes=int(nx.number_connected_components(grafo)),
        maior_componente=int(componentes["n_alimentadores"].max()) if not componentes.empty else 0,
        n_clientes_total=clientes_total,
        n_clientes_sem_socorro=clientes_sem_socorro,
        pct_clientes_sem_socorro=_percentual(clientes_sem_socorro, clientes_total),
        grau_maximo=int(por_ctmt["grau"].max()) if not por_ctmt.empty else 0,
    )

    por_ctmt = por_ctmt.sort_values(
        ["ties_campo", "grau", "n_clientes", "COD_ID"], ascending=[False, False, False, True]
    ).reset_index(drop=True)
    arestas = arestas.sort_values(
        ["n_ties_campo", "n_ties_telecomandadas", "CTMT_A", "CTMT_B"],
        ascending=[False, False, True, True],
    ).reset_index(drop=True)
    distribuicao = distribuicao.sort_values("grau").reset_index(drop=True)
    componentes = componentes.sort_values(
        ["n_alimentadores", "n_clientes", "componente_id"], ascending=[False, False, True]
    ).reset_index(drop=True)
    return ResultadoAtlas(resumo, por_ctmt, arestas, distribuicao, componentes, grafo)


def renderizar_markdown(resultado: ResultadoAtlas) -> str:
    """Renderiza o relatório em Markdown."""
    resumo = resultado.resumo
    top_ties = resultado.alimentadores.head(15)
    ilhados = resultado.alimentadores.loc[resultado.alimentadores["grau"] == 0].head(15)
    componentes = resultado.componentes.head(15)

    linhas = [
        "# Atlas de interligações da Light — quem pode socorrer quem",
        "",
        "Atlas gerado por `scripts/atlas_interligacoes.py` a partir de `data/parquet`,",
        "reutilizando a",
        "detecção geométrica de ties de `ingest/interligacoes.py` e o inventário por CTMT.",
        "",
        "## 1. Resumo executivo",
        "",
        f"- Alimentadores analisados: **{_fmt_int(resumo.n_alimentadores)}**.",
        f"- Ties de campo únicos: **{_fmt_int(resumo.n_ties_campo)}**, dos quais "
        f"**{_fmt_int(resumo.n_ties_telecomandadas)}** telecomandados.",
        f"- Pares chave × CTMT vizinho fora de SE: **{_fmt_int(resumo.n_pares_ctmt)}**.",
        f"- Arestas CTMT–CTMT do grafo de socorro: **{_fmt_int(resumo.n_arestas)}**.",
        f"- Alimentadores com grau 0 (sem socorro possível): **{_fmt_int(resumo.n_grau_zero)}**.",
        f"- Componentes conexas: **{_fmt_int(resumo.n_componentes)}** "
        f"(maior componente com **{_fmt_int(resumo.maior_componente)}** CTMT).",
        f"- Clientes em alimentadores de grau 0: **{_fmt_int(resumo.n_clientes_sem_socorro)} / "
        f"{_fmt_int(resumo.n_clientes_total)} = {_fmt_pct(resumo.pct_clientes_sem_socorro)}**.",
        "",
        "A declaração pedida na issue, sem maquiagem, é: "
        f"**{_fmt_pct(resumo.pct_clientes_sem_socorro)} dos clientes estão em alimentadores sem "
        "socorro possível por tie de campo**.",
        "",
        "## 2. Metodologia",
        "",
        "- Tie de campo = chave `UNSEMT` normalmente aberta detectada geometricamente a até 2 m de",
        "  extremidade `SSDMT` de outro CTMT, excluindo `EM_SUB=True` (pátio de subestação).",
        "- O relatório por alimentador usa o inventário real da base:",
        "  clientes = `n_UCBT + n_UCMT`.",
        "- O grafo de socorro é simples (`networkx.Graph`): uma aresta por par CTMT–CTMT, com",
        "  atributos `n_ties_campo`, `n_ties_telecomandadas` e lista de chaves. Ties paralelas são",
        "  preservadas nos atributos e nas tabelas exportadas.",
        "",
        "## 3. Distribuição de grau",
        "",
        _markdown_tabela(
            resultado.distribuicao_grau,
            ["grau", "alimentadores", "pct_alimentadores", "clientes", "pct_clientes"],
        ),
        "",
        "![Histograma do grau do grafo de socorro](dados/grau-socorro-histograma.svg)",
        "",
        "## 4. Componentes conexas",
        "",
        _markdown_tabela(
            componentes,
            [
                "componente_id",
                "n_alimentadores",
                "n_clientes",
                "n_arestas",
                "n_ties_campo",
                "n_subestacoes",
                "amostra_ctmts",
            ],
        ),
        "",
        "## 5. Alimentadores com mais ties de campo",
        "",
        _markdown_tabela(
            top_ties,
            [
                "COD_ID",
                "NOME",
                "SUB",
                "n_clientes",
                "ties_campo",
                "ties_telecomandadas",
                "grau",
                "alimentadores_socorro",
            ],
        ),
        "",
        "## 6. Alimentadores ilhados (grau 0) com mais clientes",
        "",
        _markdown_tabela(
            ilhados,
            ["COD_ID", "NOME", "SUB", "n_clientes", "ties_campo", "grau", "CONJ_NOME"],
        ),
        "",
        "## 7. Arquivos rastreáveis versionados",
        "",
        "- `docs/dados/atlas-interligacoes-alimentadores.csv`: uma linha por CTMT com grau, ties,",
        "  listas de destinos e componente conexa.",
        "- `docs/dados/grafo-socorro-arestas.csv`: arestas CTMT–CTMT com contagens de",
        "  ties por par.",
        "- `docs/dados/grafo-socorro.graphml`: grafo de socorro em formato aberto.",
        "- `docs/dados/grau-socorro-histograma.svg`: histograma em SVG puro.",
        "",
        "## 8. Reprodução",
        "",
        "```bash",
        "uv run python scripts/atlas_interligacoes.py \\",
        "  --parquet-dir data/parquet \\",
        "  --out docs/atlas-interligacoes.md",
        "```",
        "",
    ]
    return "\n".join(linhas)


def gerar_histograma_svg(distribuicao_grau: pd.DataFrame) -> str:
    """Gera um histograma simples em SVG puro."""
    if distribuicao_grau.empty:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="180">'
            '<text x="20" y="40" font-size="18">Sem dados para histograma.</text></svg>'
        )

    largura_plot = LARGURA_SVG - MARGEM_ESQ - MARGEM_DIR
    altura_plot = ALTURA_SVG - MARGEM_SUP - MARGEM_INF
    max_y = max(int(distribuicao_grau["alimentadores"].max()), 1)
    n_barras = len(distribuicao_grau)
    passo = largura_plot / max(n_barras, 1)
    largura_barra = max(passo * 0.7, 8)

    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{LARGURA_SVG}" height="{ALTURA_SVG}" '
        f'viewBox="0 0 {LARGURA_SVG} {ALTURA_SVG}">',
        "<style>text{font-family:Arial,sans-serif;fill:#1f2937}"
        ".grade{stroke:#d1d5db;stroke-width:1}.barra{fill:#2563eb}.eixo{stroke:#111827;stroke-width:1.5}"
        ".rotulo{font-size:12px}.titulo{font-size:20px;font-weight:700}</style>",
        (
            f'<text class="titulo" x="{MARGEM_ESQ}" y="26">'
            "Distribuição de grau do grafo de socorro</text>"
        ),
    ]
    for frac in range(5):
        y_val = round(max_y * frac / 4)
        y = MARGEM_SUP + altura_plot - (y_val / max_y * altura_plot if max_y else 0)
        partes.append(
            f'<line class="grade" x1="{MARGEM_ESQ}" y1="{y:.1f}" x2="{LARGURA_SVG - MARGEM_DIR}" '
            f'y2="{y:.1f}"/>'
        )
        partes.append(
            f'<text class="rotulo" x="{MARGEM_ESQ - 10}" y="{y + 4:.1f}" '
            f'text-anchor="end">{y_val}</text>'
        )
    partes.append(
        f'<line class="eixo" x1="{MARGEM_ESQ}" y1="{MARGEM_SUP}" x2="{MARGEM_ESQ}" '
        f'y2="{MARGEM_SUP + altura_plot}"/>'
    )
    partes.append(
        f'<line class="eixo" x1="{MARGEM_ESQ}" y1="{MARGEM_SUP + altura_plot}" '
        f'x2="{LARGURA_SVG - MARGEM_DIR}" y2="{MARGEM_SUP + altura_plot}"/>'
    )

    for indice, linha in enumerate(distribuicao_grau.itertuples(index=False), start=0):
        altura = 0 if max_y == 0 else (float(linha.alimentadores) / max_y) * altura_plot
        x = MARGEM_ESQ + indice * passo + (passo - largura_barra) / 2
        y = MARGEM_SUP + altura_plot - altura
        cx = x + largura_barra / 2
        partes.append(
            f'<rect class="barra" x="{x:.1f}" y="{y:.1f}" width="{largura_barra:.1f}" '
            f'height="{altura:.1f}" rx="2"/>'
        )
        partes.append(
            f'<text class="rotulo" x="{cx:.1f}" y="{y - 6:.1f}" text-anchor="middle">'
            f"{int(linha.alimentadores)}</text>"
        )
        partes.append(
            f'<text class="rotulo" x="{cx:.1f}" y="{MARGEM_SUP + altura_plot + 18:.1f}" '
            f'text-anchor="middle">{int(linha.grau)}</text>'
        )
    partes.append(
        f'<text class="rotulo" x="{(MARGEM_ESQ + largura_plot / 2):.1f}" y="{ALTURA_SVG - 18}" '
        'text-anchor="middle">Grau (vizinhos distintos com tie de campo)</text>'
    )
    partes.append(
        f'<text class="rotulo" transform="translate(18,{MARGEM_SUP + altura_plot / 2:.1f}) '
        'rotate(-90)" text-anchor="middle">Alimentadores</text>'
    )
    partes.append("</svg>")
    return "".join(partes)


def escrever_resultado(
    resultado: ResultadoAtlas,
    *,
    out_markdown: str | Path,
    out_alimentadores_csv: str | Path,
    out_arestas_csv: str | Path,
    out_graphml: str | Path,
    out_svg: str | Path,
) -> None:
    """Escreve os arquivos versionáveis do atlas."""
    md = Path(out_markdown)
    alimentadores_csv = Path(out_alimentadores_csv)
    arestas_csv = Path(out_arestas_csv)
    graphml = Path(out_graphml)
    svg = Path(out_svg)

    for caminho in (md, alimentadores_csv, arestas_csv, graphml, svg):
        caminho.parent.mkdir(parents=True, exist_ok=True)

    resultado.alimentadores.to_csv(alimentadores_csv, index=False)
    resultado.arestas.to_csv(arestas_csv, index=False)
    nx.write_graphml(resultado.grafo, graphml)
    svg.write_text(gerar_histograma_svg(resultado.distribuicao_grau), encoding="utf-8")
    md.write_text(renderizar_markdown(resultado), encoding="utf-8")


def _carregar_ctmt_extra(fonte: DiretorioParquet) -> pd.DataFrame:
    ctmt = fonte.ler("CTMT", ["COD_ID", "CONJ"]).copy()
    if "CONJ" in ctmt.columns:
        ctmt["CONJ_CODIGO"] = ctmt["CONJ"].map(_codigo_texto)
    else:
        ctmt["CONJ_CODIGO"] = ""
    ctmt = ctmt[["COD_ID", "CONJ_CODIGO"]]
    conj = fonte.ler_se_existir("CONJ", ["COD_ID", "NOME"])
    if conj is None or conj.empty:
        ctmt["CONJ_NOME"] = ""
        return ctmt
    mapa_conj = (
        conj.assign(
            COD_ID=conj["COD_ID"].map(_codigo_texto), NOME=conj["NOME"].fillna("").astype("string")
        )
        .drop_duplicates("COD_ID")
        .set_index("COD_ID")["NOME"]
    )
    faltantes = ctmt["CONJ_CODIGO"].eq("")
    if faltantes.any():
        derivados = _mapa_conjuntos_por_ctmt(fonte)
        ctmt.loc[faltantes, "CONJ_CODIGO"] = ctmt.loc[faltantes, "COD_ID"].map(derivados).fillna("")
    ctmt["CONJ_NOME"] = ctmt["CONJ_CODIGO"].map(mapa_conj).fillna("").astype("string")
    sem_nome = ctmt["CONJ_NOME"].eq("") & ctmt["CONJ_CODIGO"].str.contains(";", regex=False)
    if sem_nome.any():
        ctmt.loc[sem_nome, "CONJ_NOME"] = ctmt.loc[sem_nome, "CONJ_CODIGO"].map(
            lambda valor: ";".join(
                nome for nome in (mapa_conj.get(codigo, "") for codigo in valor.split(";")) if nome
            )
        )
    sem_nome = ctmt["CONJ_NOME"].eq("") & ctmt["CONJ_CODIGO"].ne("")
    ctmt.loc[sem_nome, "CONJ_NOME"] = ctmt.loc[sem_nome, "CONJ_CODIGO"]
    return ctmt


def _mapa_conjuntos_por_ctmt(fonte: DiretorioParquet) -> dict[str, str]:
    contagens: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for camada in ("UCBT_tab", "UCMT_tab", "UNTRMT"):
        if not fonte.tem(camada):
            continue
        colunas = set(fonte.colunas(camada))
        if {"CTMT", "CONJ"} - colunas:
            continue
        for lote in fonte.iterar_lotes(camada, ["CTMT", "CONJ"]):
            if lote.empty:
                continue
            ctmts = lote["CTMT"].map(_texto)
            conjuntos = lote["CONJ"].map(_codigo_texto)
            mascara = ctmts.ne("") & conjuntos.ne("")
            for ctmt, codigo in zip(ctmts[mascara], conjuntos[mascara], strict=False):
                contagens[ctmt][codigo] += 1
    return {
        ctmt: sorted(contador.items(), key=lambda item: (-item[1], item[0]))[0][0]
        for ctmt, contador in contagens.items()
        if contador
    }


def _pares_simetricos_campo(ties_campo: pd.DataFrame) -> pd.DataFrame:
    colunas = ["CTMT", "CTMT_VIZ", "COD_ID", "TLCD"]
    if ties_campo.empty:
        return pd.DataFrame(columns=[*colunas, "DONO"])
    ida = ties_campo[colunas].copy()
    ida["DONO"] = True
    volta = ida.rename(columns={"CTMT": "CTMT_VIZ", "CTMT_VIZ": "CTMT"})
    volta["DONO"] = False
    return pd.concat([ida, volta], ignore_index=True)


def _agrupar_arestas(ties_campo: pd.DataFrame, alimentadores: pd.DataFrame) -> pd.DataFrame:
    colunas = [
        "CTMT_A",
        "CTMT_B",
        "SUB_A",
        "SUB_B",
        "SUB_NOME_A",
        "SUB_NOME_B",
        "CONJ_A",
        "CONJ_B",
        "CONJ_NOME_A",
        "CONJ_NOME_B",
        "n_ties_campo",
        "n_ties_telecomandadas",
        "chaves",
        "chaves_telecomandadas",
    ]
    if ties_campo.empty:
        return pd.DataFrame(columns=colunas)

    mapa = alimentadores.set_index("COD_ID")[
        ["SUB", "SUB_NOME", "CONJ_CODIGO", "CONJ_NOME"]
    ].to_dict(orient="index")
    pares = ties_campo.copy()
    pares["CTMT_A"] = pares[["CTMT", "CTMT_VIZ"]].min(axis=1)
    pares["CTMT_B"] = pares[["CTMT", "CTMT_VIZ"]].max(axis=1)

    registros = []
    for (ctmt_a, ctmt_b), grupo in pares.groupby(["CTMT_A", "CTMT_B"], sort=True):
        sub_a = mapa.get(ctmt_a, {})
        sub_b = mapa.get(ctmt_b, {})
        chaves = sorted(set(grupo["COD_ID"].astype(str)))
        chaves_tlcd = sorted(set(grupo.loc[grupo["TLCD"] == 1, "COD_ID"].astype(str)))
        registros.append(
            {
                "CTMT_A": ctmt_a,
                "CTMT_B": ctmt_b,
                "SUB_A": _texto(sub_a.get("SUB")),
                "SUB_B": _texto(sub_b.get("SUB")),
                "SUB_NOME_A": _texto(sub_a.get("SUB_NOME")),
                "SUB_NOME_B": _texto(sub_b.get("SUB_NOME")),
                "CONJ_A": _texto(sub_a.get("CONJ_CODIGO")),
                "CONJ_B": _texto(sub_b.get("CONJ_CODIGO")),
                "CONJ_NOME_A": _texto(sub_a.get("CONJ_NOME")),
                "CONJ_NOME_B": _texto(sub_b.get("CONJ_NOME")),
                "n_ties_campo": len(chaves),
                "n_ties_telecomandadas": len(chaves_tlcd),
                "chaves": ";".join(chaves),
                "chaves_telecomandadas": ";".join(chaves_tlcd),
            }
        )
    return pd.DataFrame(registros, columns=colunas)


def _montar_grafo(alimentadores: pd.DataFrame, arestas: pd.DataFrame) -> nx.Graph:
    grafo = nx.Graph()
    for _, linha in alimentadores.iterrows():
        grafo.add_node(
            linha["COD_ID"],
            nome=_texto(linha["NOME"]),
            sub=_texto(linha["SUB"]),
            sub_nome=_texto(linha["SUB_NOME"]),
            conj=_texto(linha["CONJ_CODIGO"]),
            conj_nome=_texto(linha["CONJ_NOME"]),
            n_clientes=int(linha["n_clientes"]),
            ties_campo=int(linha.get("NA_interligacao_campo", 0)),
            ties_telecomandadas=int(linha.get("NA_interligacao_campo_telecomandada", 0)),
        )
    for _, linha in arestas.iterrows():
        grafo.add_edge(
            linha["CTMT_A"],
            linha["CTMT_B"],
            n_ties_campo=int(linha["n_ties_campo"]),
            n_ties_telecomandadas=int(linha["n_ties_telecomandadas"]),
            chaves=_texto(linha["chaves"]),
            chaves_telecomandadas=_texto(linha["chaves_telecomandadas"]),
        )
    return grafo


def _componentes_do_grafo(
    grafo: nx.Graph,
    alimentadores: pd.DataFrame,
) -> pd.DataFrame:
    mapa_cli = alimentadores.set_index("COD_ID")["n_clientes"].to_dict()
    mapa_sub = alimentadores.set_index("COD_ID")["SUB"].fillna("").astype(str).to_dict()
    comp_por_no: dict[str, int] = {}
    linhas = []
    for indice, nos in enumerate(
        sorted(nx.connected_components(grafo), key=lambda comp: (-len(comp), sorted(comp)[0])),
        start=1,
    ):
        nos_ordenados = sorted(nos)
        subgrafo = grafo.subgraph(nos_ordenados)
        for no in nos_ordenados:
            comp_por_no[no] = indice
        linhas.append(
            {
                "componente_id": indice,
                "n_alimentadores": len(nos_ordenados),
                "n_clientes": int(sum(int(mapa_cli.get(no, 0)) for no in nos_ordenados)),
                "n_arestas": int(subgrafo.number_of_edges()),
                "n_ties_campo": int(
                    sum(
                        int(dados.get("n_ties_campo", 0))
                        for _, _, dados in subgrafo.edges(data=True)
                    )
                ),
                "n_subestacoes": len(
                    {_texto(mapa_sub.get(no)) for no in nos_ordenados if _texto(mapa_sub.get(no))}
                ),
                "amostra_ctmts": ";".join(nos_ordenados[:10]),
            }
        )
    componentes = pd.DataFrame(linhas)
    if componentes.empty:
        return componentes
    componentes.attrs["comp_por_no"] = comp_por_no
    return componentes


def _consolidar_por_ctmt(
    alimentadores: pd.DataFrame,
    pares: pd.DataFrame,
    grafo: nx.Graph,
    componentes: pd.DataFrame,
) -> pd.DataFrame:
    base = alimentadores.copy()
    comp_por_no = componentes.attrs.get("comp_por_no", {})
    dados_destino = base.set_index("COD_ID")[
        ["SUB", "SUB_NOME", "CONJ_CODIGO", "CONJ_NOME"]
    ].to_dict(orient="index")
    grupos = (
        {ctmt: grupo.copy() for ctmt, grupo in pares.groupby("CTMT")} if not pares.empty else {}
    )

    linhas = []
    for _, linha in base.iterrows():
        ctmt = linha["COD_ID"]
        grupo = grupos.get(ctmt)
        destinos = [] if grupo is None else sorted(set(grupo["CTMT_VIZ"].astype(str)))
        subs_destino = sorted(
            {
                _texto(dados_destino.get(viz, {}).get("SUB"))
                for viz in destinos
                if _texto(dados_destino.get(viz, {}).get("SUB"))
            }
        )
        subs_nomes = sorted(
            {
                _texto(dados_destino.get(viz, {}).get("SUB_NOME"))
                for viz in destinos
                if _texto(dados_destino.get(viz, {}).get("SUB_NOME"))
            }
        )
        conjs = sorted(
            {
                _texto(dados_destino.get(viz, {}).get("CONJ_CODIGO"))
                for viz in destinos
                if _texto(dados_destino.get(viz, {}).get("CONJ_CODIGO"))
            }
        )
        conj_nomes = sorted(
            {
                _texto(dados_destino.get(viz, {}).get("CONJ_NOME"))
                for viz in destinos
                if _texto(dados_destino.get(viz, {}).get("CONJ_NOME"))
            }
        )
        chaves = [] if grupo is None else sorted(set(grupo["COD_ID"].astype(str)))
        chaves_tlcd = (
            []
            if grupo is None
            else sorted(set(grupo.loc[grupo["TLCD"] == 1, "COD_ID"].astype(str)))
        )
        componente_id = int(comp_por_no.get(ctmt, 0))
        tamanho = 1
        if componente_id:
            tamanho = int(
                componentes.loc[
                    componentes["componente_id"] == componente_id, "n_alimentadores"
                ].iloc[0]
            )
        linhas.append(
            {
                **linha.to_dict(),
                "ties_campo": int(linha["NA_interligacao_campo"]),
                "ties_telecomandadas": int(linha["NA_interligacao_campo_telecomandada"]),
                "ties_manuais": int(
                    linha["NA_interligacao_campo"] - linha["NA_interligacao_campo_telecomandada"]
                ),
                "pares_ctmt_vizinho": 0 if grupo is None else int(len(grupo)),
                "grau": int(grafo.degree(ctmt)),
                "sem_socorro": bool(grafo.degree(ctmt) == 0),
                "alimentadores_socorro": ";".join(destinos),
                "subestacoes_socorro": ";".join(subs_destino),
                "subestacoes_socorro_nomes": ";".join(subs_nomes),
                "conjuntos_socorro": ";".join(conjs),
                "conjuntos_socorro_nomes": ";".join(conj_nomes),
                "chaves_campo": ";".join(chaves),
                "chaves_telecomandadas": ";".join(chaves_tlcd),
                "componente_id": componente_id,
                "tamanho_componente": tamanho,
            }
        )
    return pd.DataFrame(linhas)


def _distribuicao_grau(grafo: nx.Graph) -> pd.DataFrame:
    graus = pd.Series(dict(grafo.degree()), name="grau", dtype="int64")
    if graus.empty:
        return pd.DataFrame(
            columns=["grau", "alimentadores", "pct_alimentadores", "clientes", "pct_clientes"]
        )
    clientes = pd.Series(
        nx.get_node_attributes(grafo, "n_clientes"), name="n_clientes", dtype="int64"
    )
    tabela = []
    total_nos = len(graus)
    total_clientes = int(clientes.sum())
    for grau, serie in graus.groupby(graus):
        nos = list(serie.index)
        cli = int(clientes.reindex(nos).fillna(0).sum())
        tabela.append(
            {
                "grau": int(grau),
                "alimentadores": len(nos),
                "pct_alimentadores": _fmt_pct(_percentual(len(nos), total_nos)),
                "clientes": cli,
                "pct_clientes": _fmt_pct(_percentual(cli, total_clientes)),
            }
        )
    return pd.DataFrame(tabela)


def _markdown_tabela(df: pd.DataFrame, colunas: list[str]) -> str:
    if df.empty:
        return "_Sem linhas para esta seção._"
    tabela = df[colunas].copy()
    for coluna in tabela.columns:
        if tabela[coluna].dtype.kind in {"i", "u"}:
            tabela[coluna] = tabela[coluna].map(_fmt_int)
    cabecalho = "| " + " | ".join(colunas) + " |"
    separador = "| " + " | ".join("---" for _ in colunas) + " |"
    linhas = [cabecalho, separador]
    for _, linha in tabela.iterrows():
        valores = [_escapar_markdown(linha[coluna]) for coluna in colunas]
        linhas.append("| " + " | ".join(valores) + " |")
    return "\n".join(linhas)


def _fmt_int(valor: int) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _fmt_pct(valor: float) -> str:
    return f"{valor:.2f} %".replace(".", ",")


def _percentual(parte: int | float, total: int | float) -> float:
    if not total:
        return 0.0
    return float(parte) * 100.0 / float(total)


def _texto(valor: object) -> str:
    if valor is None or pd.isna(valor):
        return ""
    return str(valor).strip()


def _escapar_markdown(valor: object) -> str:
    return _texto(valor).replace("|", r"\|").replace("\n", "<br>")


def _codigo_texto(valor: object) -> str:
    if valor is None or pd.isna(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()
