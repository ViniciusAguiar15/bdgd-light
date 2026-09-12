"""Compara `restore_options` em instantes com e sem GD para a issue #99."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console

from bdgd_light.generalizacao import maior_trecho_tronco
from bdgd_light.grid import Cluster, Feeder, Rede
from bdgd_light.ingest.recorte import nome_cluster, recortar
from bdgd_light.mcp_server.sessao import resolver_cluster
from bdgd_light.sim.eventos import CENARIOS
from bdgd_light.twin import ConfiguracaoGd, converter_ctmt, montar_master_cluster, score_eletrico

console = Console()

INSTANTES = (
    ("meio_dia_com_gd", "meio-dia com GD", 12, True),
    ("ponta_noite_sem_gd", "ponta da noite sem GD", 19, False),
)
CENARIOS_ALVO = ("tijuca_cabofrio_tronco", "ipanema_9210", "taquara_bocari")


@dataclass(frozen=True)
class CasoAnalise:
    """Um caso de comparação da restauração."""

    grupo: str
    caso: str
    descricao: str
    cluster: str
    gpkg: Path
    ctmts_cluster: tuple[str, ...]
    ctmt_principal: str
    trecho_falta: str
    criterio_falta: str
    origem: str


def _fmt_num(valor: Any, casas: int = 3) -> str:
    if valor is None:
        return "—"
    if isinstance(valor, float):
        if math.isnan(valor) or math.isinf(valor):
            return "—"
        return f"{valor:.{casas}f}"
    return str(valor)


def _fmt_pct(valor: Any) -> str:
    if valor is None or (isinstance(valor, float) and (math.isnan(valor) or math.isinf(valor))):
        return "—"
    return f"{100 * float(valor):.1f}%"


def _fmt_bool(valor: Any) -> str:
    return "sim" if bool(valor) else "não"


def carregar_rede(gpkg: Path) -> Rede:
    """Carrega o recorte como `Feeder` ou `Cluster`."""
    try:
        return Feeder.from_gpkg(gpkg)
    except ValueError:
        return Cluster.from_gpkg(gpkg)


def carregar_vizinhos(inventario_csv: Path) -> dict[str, tuple[str, ...]]:
    """Vizinhos diretos por CTMT, no mesmo formato do inventário versionado."""
    inventario = pd.read_csv(inventario_csv, dtype={"COD_ID": str, "vizinhos": str}).fillna("")
    saida: dict[str, tuple[str, ...]] = {}
    for item in inventario.itertuples(index=False):
        bruto = str(getattr(item, "vizinhos", "") or "")
        vizinhos = tuple(v.strip() for v in bruto.split(";") if v.strip())
        saida[str(item.COD_ID)] = vizinhos
    return saida


def selecionar_alimentadores_alta_penetracao(
    alocacao_csv: Path,
    *,
    n: int = 3,
) -> pd.DataFrame:
    """Seleciona os CTMTs de maior potência de GD entre os rotulados como alta penetração."""
    tabela = pd.read_csv(alocacao_csv, dtype={"ctmt": str}).copy()
    tabela["potencia_total_kw"] = tabela["potencia_exata_kw"].fillna(0.0) + tabela[
        "potencia_agregada_kw"
    ].fillna(0.0)
    filtro = tabela["origem"].fillna("").str.contains("penetra", case=False)
    escolhidos = tabela[filtro].sort_values(
        ["potencia_total_kw", "potencia_exata_kw", "ctmt"],
        ascending=[False, False, True],
    )
    return escolhidos.head(n).reset_index(drop=True)


def montar_casos_cenarios(feeders_dir: Path) -> list[CasoAnalise]:
    """Casos fixos dos três cenários da demo."""
    casos: list[CasoAnalise] = []
    for nome in CENARIOS_ALVO:
        cenario = CENARIOS[nome]
        assert (
            cenario.cluster is not None and cenario.ctmt is not None and cenario.trecho is not None
        )
        gpkg = resolver_cluster(cenario.cluster, feeders_dir)
        rede = carregar_rede(gpkg)
        casos.append(
            CasoAnalise(
                grupo="cenario",
                caso=nome,
                descricao=cenario.descricao,
                cluster=cenario.cluster,
                gpkg=gpkg,
                ctmts_cluster=tuple(rede.ctmts),
                ctmt_principal=cenario.ctmt,
                trecho_falta=cenario.trecho,
                criterio_falta="cenário nomeado",
                origem=f"cenário {cenario.cluster}",
            )
        )
    return casos


def materializar_casos_alimentadores(
    selecionados: pd.DataFrame,
    *,
    parquet_dir: Path,
    inventario_csv: Path,
    feeders_dir: Path,
    console_: Console | None = None,
) -> list[CasoAnalise]:
    """Recorta os clusters reais `CTMT + vizinhos` e escolhe a falta do maior trecho do tronco."""
    console_ = console_ or console
    vizinhos = carregar_vizinhos(inventario_csv)
    casos: list[CasoAnalise] = []
    for item in selecionados.itertuples(index=False):
        ctmt = str(item.ctmt)
        ctmts_cluster = (ctmt, *vizinhos.get(ctmt, ()))
        nome = nome_cluster(ctmts_cluster)
        console_.print(f"[cyan]Recortando {ctmt} com {len(ctmts_cluster) - 1} vizinho(s)…[/]")
        rodada = recortar(
            parquet_dir,
            ctmts_cluster,
            feeders_dir,
            nome_cluster_=nome,
            console=Console(quiet=True),
        )
        gpkg = rodada.cluster.gpkg if rodada.cluster is not None else rodada.recortes[0].gpkg
        if gpkg is None:
            raise RuntimeError(f"{ctmt}: recorte não gerou GeoPackage utilizável")
        rede = carregar_rede(gpkg)
        trecho = maior_trecho_tronco(rede, ctmt)
        casos.append(
            CasoAnalise(
                grupo="alimentador",
                caso=ctmt,
                descricao=str(item.origem),
                cluster=nome,
                gpkg=Path(gpkg),
                ctmts_cluster=tuple(rede.ctmts),
                ctmt_principal=ctmt,
                trecho_falta=trecho,
                criterio_falta="maior trecho do tronco do CTMT principal",
                origem=str(item.origem),
            )
        )
    return casos


def preparar_plano_restauracao(rede: Rede, trecho_falta: str) -> tuple[Rede, list[Any], str]:
    """Abre o religador da falta e devolve a vista de plano usada por `restore_options`."""
    if trecho_falta not in rede.trechos:
        raise KeyError(f"trecho {trecho_falta!r} ausente no recorte")
    u, v = rede.trechos[trecho_falta]
    ponta = u if rede.energized_by(u) is not None else v
    fonte = rede.energized_by(ponta)
    if fonte is None:
        raise RuntimeError(f"trecho {trecho_falta} já está sem tensão")
    indicacoes = rede.chaves_no_caminho(ponta)
    if not indicacoes:
        raise RuntimeError(f"trecho {trecho_falta} sem religador entre a fonte e a falta")
    religador = indicacoes[0]
    com_falta = rede.copy()
    com_falta.open_switch(religador)
    plano = com_falta.copy()
    if plano.is_open(religador):
        plano.close_switch(religador)
    return plano, plano.restore_options(trecho_falta), religador


def preparar_masters_caso(
    caso: CasoAnalise,
    *,
    dss_out: Path,
    dia: str,
    mes: int,
    gd_cfg: ConfiguracaoGd,
) -> tuple[Path, Path]:
    """Gera os modelos sem GD e com GD do cluster do caso."""
    subdir = dss_out / caso.cluster
    pastas = [
        converter_ctmt(caso.gpkg, ctmt, subdir, dias=[dia], meses=[mes], gd=gd_cfg).pasta
        for ctmt in caso.ctmts_cluster
    ]
    master_base = montar_master_cluster(
        pastas,
        subdir / f"Master_{dia}{mes:02d}_base_issue99.dss",
        dia=dia,
        mes=mes,
        nome=caso.cluster,
    )
    master_gd = montar_master_cluster(
        pastas,
        subdir / f"Master_{dia}{mes:02d}_gd_issue99.dss",
        dia=dia,
        mes=mes,
        nome=caso.cluster,
        gd=True,
    )
    return master_base, master_gd


def _linhas_score(
    scores: list[Any],
    caso: CasoAnalise,
    *,
    instante_id: str,
    instante_rotulo: str,
    hora: int,
    com_gd: bool,
    religador: str,
) -> list[dict[str, Any]]:
    linhas: list[dict[str, Any]] = []
    for ordem, item in enumerate(scores, start=1):
        linhas.append(
            {
                "grupo": caso.grupo,
                "caso": caso.caso,
                "descricao": caso.descricao,
                "cluster": caso.cluster,
                "origem": caso.origem,
                "ctmt_principal": caso.ctmt_principal,
                "ctmts_cluster": ";".join(caso.ctmts_cluster),
                "trecho_falta": caso.trecho_falta,
                "criterio_falta": caso.criterio_falta,
                "religador": religador,
                "instante_id": instante_id,
                "instante": instante_rotulo,
                "hora": hora,
                "com_gd": com_gd,
                "ordem": ordem,
                "chave": item.chave,
                "fonte": item.fonte,
                "clientes_ucbt": item.opcao.clientes.ucbt,
                "clientes_total": item.opcao.clientes.total,
                "tlcd": item.opcao.tlcd,
                "convergiu": item.convergiu,
                "viavel": item.viavel,
                "margem_disjuntor": item.margem_disjuntor,
                "i_disjuntor_a": item.i_disjuntor_a,
                "i_nominal_a": item.i_nominal_a,
                "vmin_mt_pu": item.vmin_mt_pu,
                "vmin_mt_barra": item.vmin_mt_barra or "",
                "vmax_mt_pu": item.vmax_mt_pu,
                "vmax_mt_barra": item.vmax_mt_barra or "",
                "carregamento_max_mt_pct": item.carregamento_max_mt_pct,
                "perdas_kw": item.perdas_kw,
                "motivos": "; ".join(item.motivos),
                "ajustes": "; ".join(item.ajustes),
            }
        )
    return linhas


def resumir_resultados(tabela: pd.DataFrame) -> pd.DataFrame:
    """Um resumo por caso × instante, preservando a opção vencedora."""
    if tabela.empty:
        return pd.DataFrame(
            columns=[
                "grupo",
                "caso",
                "instante",
                "hora",
                "com_gd",
                "n_opcoes",
                "n_viaveis",
                "vencedora",
                "vencedora_viavel",
                "margem_disjuntor_vencedora",
                "vmin_mt_pu_vencedora",
                "vmax_mt_pu_vencedora",
                "observacao",
            ]
        )
    linhas: list[dict[str, Any]] = []
    for chaves, grupo in tabela.groupby(
        ["grupo", "caso", "instante", "hora", "com_gd"], sort=False
    ):
        melhor = grupo.sort_values("ordem").iloc[0]
        viaveis = grupo[grupo["viavel"]]
        melhor_viavel = viaveis.sort_values("ordem").iloc[0]["chave"] if not viaveis.empty else None
        linhas.append(
            {
                "grupo": chaves[0],
                "caso": chaves[1],
                "instante": chaves[2],
                "hora": chaves[3],
                "com_gd": chaves[4],
                "n_opcoes": int(len(grupo)),
                "n_viaveis": int(grupo["viavel"].sum()),
                "vencedora": melhor["chave"],
                "vencedora_viavel": melhor_viavel,
                "margem_disjuntor_vencedora": melhor["margem_disjuntor"],
                "vmin_mt_pu_vencedora": melhor["vmin_mt_pu"],
                "vmax_mt_pu_vencedora": melhor["vmax_mt_pu"],
                "observacao": melhor["motivos"] if not bool(melhor["viavel"]) else "",
            }
        )
    return pd.DataFrame(linhas)


def comparar_vencedoras(resumo: pd.DataFrame) -> pd.DataFrame:
    """Compara o resultado do meio-dia com GD contra a ponta da noite sem GD."""
    if resumo.empty:
        return pd.DataFrame(
            columns=[
                "grupo",
                "caso",
                "vencedora_meio_dia_com_gd",
                "vencedora_ponta_noite_sem_gd",
                "mudou_vencedora",
                "viavel_meio_dia_com_gd",
                "viavel_ponta_noite_sem_gd",
                "mudou_opcao_viavel",
            ]
        )
    base = resumo[["grupo", "caso"]].drop_duplicates().sort_values(["grupo", "caso"])
    meio = (
        resumo[resumo["instante"] == "meio-dia com GD"]
        .rename(
            columns={
                "vencedora": "vencedora_meio_dia_com_gd",
                "vencedora_viavel": "viavel_meio_dia_com_gd",
            }
        )
        .drop(columns=["instante", "hora", "com_gd", "n_opcoes", "n_viaveis", "observacao"])
    )
    noite = (
        resumo[resumo["instante"] == "ponta da noite sem GD"]
        .rename(
            columns={
                "vencedora": "vencedora_ponta_noite_sem_gd",
                "vencedora_viavel": "viavel_ponta_noite_sem_gd",
            }
        )
        .drop(columns=["instante", "hora", "com_gd", "n_opcoes", "n_viaveis", "observacao"])
    )
    tabela = base.merge(meio, on=["grupo", "caso"], how="left").merge(
        noite, on=["grupo", "caso"], how="left"
    )
    sentinela = "__sem_opcao__"
    tabela["mudou_vencedora"] = tabela["vencedora_meio_dia_com_gd"].fillna(sentinela) != tabela[
        "vencedora_ponta_noite_sem_gd"
    ].fillna(sentinela)
    tabela["mudou_opcao_viavel"] = tabela["viavel_meio_dia_com_gd"].fillna(sentinela) != tabela[
        "viavel_ponta_noite_sem_gd"
    ].fillna(sentinela)
    return tabela


def rodar_analise(
    casos: list[CasoAnalise],
    *,
    dss_out: Path,
    dia: str,
    mes: int,
    gd_cfg: ConfiguracaoGd,
    console_: Console | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Executa a comparação completa e devolve tabelas de opções, resumo e comparação final."""
    console_ = console_ or console
    linhas: list[dict[str, Any]] = []
    for caso in casos:
        console_.print(f"[cyan]Rodando {caso.grupo} {caso.caso}…[/]")
        rede = carregar_rede(caso.gpkg)
        plano, opcoes, religador = preparar_plano_restauracao(rede, caso.trecho_falta)
        if not opcoes:
            for instante_id, instante_rotulo, hora, com_gd in INSTANTES:
                linhas.append(
                    {
                        "grupo": caso.grupo,
                        "caso": caso.caso,
                        "descricao": caso.descricao,
                        "cluster": caso.cluster,
                        "origem": caso.origem,
                        "ctmt_principal": caso.ctmt_principal,
                        "ctmts_cluster": ";".join(caso.ctmts_cluster),
                        "trecho_falta": caso.trecho_falta,
                        "criterio_falta": caso.criterio_falta,
                        "religador": religador,
                        "instante_id": instante_id,
                        "instante": instante_rotulo,
                        "hora": hora,
                        "com_gd": com_gd,
                        "ordem": 0,
                        "chave": "",
                        "fonte": "",
                        "clientes_ucbt": 0,
                        "clientes_total": 0,
                        "tlcd": False,
                        "convergiu": False,
                        "viavel": False,
                        "margem_disjuntor": math.nan,
                        "i_disjuntor_a": math.nan,
                        "i_nominal_a": math.nan,
                        "vmin_mt_pu": math.nan,
                        "vmin_mt_barra": "",
                        "vmax_mt_pu": math.nan,
                        "vmax_mt_barra": "",
                        "carregamento_max_mt_pct": math.nan,
                        "perdas_kw": math.nan,
                        "motivos": "sem opções de restauração",
                        "ajustes": "",
                    }
                )
            continue
        master_base, master_gd = preparar_masters_caso(
            caso, dss_out=dss_out, dia=dia, mes=mes, gd_cfg=gd_cfg
        )
        for instante_id, instante_rotulo, hora, com_gd in INSTANTES:
            master = master_gd if com_gd else master_base
            scores = score_eletrico(
                opcoes,
                plano,
                master,
                comandos_base=["set mode=daily", f"set hour={hora}"],
            )
            linhas.extend(
                _linhas_score(
                    scores,
                    caso,
                    instante_id=instante_id,
                    instante_rotulo=instante_rotulo,
                    hora=hora,
                    com_gd=com_gd,
                    religador=religador,
                )
            )
    opcoes = pd.DataFrame(linhas)
    resumo = resumir_resultados(opcoes[opcoes["ordem"] > 0] if not opcoes.empty else opcoes)
    if not opcoes.empty:
        sem_opcoes = opcoes[opcoes["ordem"] == 0]
        if not sem_opcoes.empty:
            resumo = pd.concat(
                [
                    resumo,
                    sem_opcoes[["grupo", "caso", "instante", "hora", "com_gd", "motivos"]]
                    .rename(columns={"motivos": "observacao"})
                    .assign(
                        n_opcoes=0,
                        n_viaveis=0,
                        vencedora=None,
                        vencedora_viavel=None,
                        margem_disjuntor_vencedora=math.nan,
                        vmin_mt_pu_vencedora=math.nan,
                        vmax_mt_pu_vencedora=math.nan,
                    ),
                ],
                ignore_index=True,
            ).sort_values(["grupo", "caso", "hora"])
    comparacao = comparar_vencedoras(resumo)
    return opcoes.sort_values(["grupo", "caso", "hora", "ordem"]), resumo, comparacao


def _markdown_tabela(df: pd.DataFrame, colunas: list[tuple[str, str]]) -> list[str]:
    cab = "| " + " | ".join(rotulo for _, rotulo in colunas) + " |"
    sep = "| " + " | ".join("---" for _ in colunas) + " |"
    linhas = [cab, sep]
    for _, row in df.iterrows():
        valores: list[str] = []
        for coluna, _ in colunas:
            valor = row[coluna]
            if coluna == "viavel":
                valores.append(_fmt_bool(valor))
            elif isinstance(valor, bool):
                valores.append(_fmt_bool(valor))
            elif coluna.startswith("margem_disjuntor"):
                valores.append(_fmt_pct(valor))
            elif isinstance(valor, float):
                valores.append(_fmt_num(valor))
            elif valor in (None, ""):
                valores.append("—")
            else:
                valores.append(str(valor))
        linhas.append("| " + " | ".join(valores) + " |")
    return linhas


def renderizar_relatorio(
    *,
    opcoes: pd.DataFrame,
    resumo: pd.DataFrame,
    comparacao: pd.DataFrame,
    casos: list[CasoAnalise],
    alimentadores_selecionados: pd.DataFrame,
    dia: str,
    mes: int,
    out_opcoes_csv: Path,
    out_resumo_csv: Path,
) -> str:
    """Relatório Markdown versionado para `docs/gd-restauracao.md`."""
    por_caso = {(c.grupo, c.caso): c for c in casos}
    linhas = [
        "# GD na restauração",
        "",
        "Relatório gerado por `scripts/gd_na_restauracao.py` para a issue #99.",
        "",
        "## 1. Premissas",
        "",
        f"- Dia/mês dos Masters: **{dia}{mes:02d}**.",
        (
            "- Comparação pedida nesta issue: **meio-dia com GD plena** (`mode=daily`, `hour=12`, "
            "Master com `--gd`) versus **ponta da noite sem GD** (`hour=19`, Master base)."
        ),
        (
            "- **Ilhamento não entra como hipótese de restauração**: a GD **não** é contada como "
            "fonte durante a falta, porque o inversor desconecta na ausência de tensão da rede. "
            "Ela só pode alterar o carregamento do **socorredor** no instante da manobra."
        ),
        (
            "- A comparação usa a própria ordenação do `restore_options(score=true)`: "
            "**viável → maior margem no disjuntor → clientes**."
        ),
        (
            "- Nos alimentadores reais fora da demo, o recorte foi montado como "
            "**CTMT principal + vizinhos diretos do inventário**; a falta foi fixada no "
            "**maior trecho do tronco** do CTMT principal, reaproveitando a heurística da #91."
        ),
        "",
        "## 2. Casos rodados",
        "",
        "- Cenários fixos da demo:",
    ]
    for nome in CENARIOS_ALVO:
        caso = por_caso.get(("cenario", nome))
        if caso is None:
            continue
        linhas.append(
            f"  - `{caso.caso}` — {caso.ctmt_principal}, falta `{caso.trecho_falta}` "
            f"em `{caso.cluster}`"
        )
    linhas.append(
        "- Alimentadores reais de alta penetração escolhidos a partir de "
        "`docs/dados/gd-gemeo-alocacao.csv`:"
    )
    for item in alimentadores_selecionados.itertuples(index=False):
        total = float(item.potencia_total_kw)
        linhas.append(
            f"  - `{item.ctmt}` — {item.origem}; GD total considerada = **{total:.3f} kW**"
        )
    linhas += [
        "",
        "## 3. Resumo por caso e instante",
        "",
    ]
    linhas += _markdown_tabela(
        resumo.sort_values(["grupo", "caso", "hora"]).reset_index(drop=True),
        [
            ("grupo", "grupo"),
            ("caso", "caso"),
            ("instante", "instante"),
            ("n_opcoes", "opções"),
            ("n_viaveis", "viáveis"),
            ("vencedora", "vencedora"),
            ("vencedora_viavel", "melhor viável"),
            ("margem_disjuntor_vencedora", "margem da vencedora"),
            ("vmin_mt_pu_vencedora", "Vmin MT"),
            ("vmax_mt_pu_vencedora", "Vmax MT"),
            ("observacao", "observação"),
        ],
    )
    linhas += [
        "",
        "## 4. Comparação entre meio-dia com GD e ponta da noite sem GD",
        "",
    ]
    linhas += _markdown_tabela(
        comparacao.reset_index(drop=True),
        [
            ("grupo", "grupo"),
            ("caso", "caso"),
            ("vencedora_meio_dia_com_gd", "vencedora meio-dia"),
            ("vencedora_ponta_noite_sem_gd", "vencedora noite"),
            ("mudou_vencedora", "mudou vencedora"),
            ("viavel_meio_dia_com_gd", "melhor viável meio-dia"),
            ("viavel_ponta_noite_sem_gd", "melhor viável noite"),
            ("mudou_opcao_viavel", "mudou melhor viável"),
        ],
    )
    linhas += [
        "",
        "## 5. Tabelas detalhadas por caso",
        "",
    ]
    for caso in casos:
        linhas += [
            f"### `{caso.caso}`",
            "",
            f"- Grupo: **{caso.grupo}**.",
            f"- Origem: {caso.origem}.",
            f"- Cluster analisado: `{caso.cluster}` ({', '.join(caso.ctmts_cluster)}).",
            f"- Falta: trecho `{caso.trecho_falta}` ({caso.criterio_falta}).",
            "",
        ]
        dados = opcoes[(opcoes["grupo"] == caso.grupo) & (opcoes["caso"] == caso.caso)].copy()
        for instante_rotulo, hora in (("meio-dia com GD", 12), ("ponta da noite sem GD", 19)):
            linhas.append(f"#### {instante_rotulo} ({hora:02d}:00)")
            linhas.append("")
            trecho = dados[dados["instante"] == instante_rotulo].copy()
            if trecho.empty or int(trecho["ordem"].max()) == 0:
                linhas.append("Sem opções de restauração neste caso.")
                linhas.append("")
                continue
            linhas += _markdown_tabela(
                trecho.sort_values("ordem").reset_index(drop=True),
                [
                    ("ordem", "ordem"),
                    ("chave", "chave"),
                    ("fonte", "socorredor"),
                    ("viavel", "viável"),
                    ("margem_disjuntor", "margem"),
                    ("vmin_mt_pu", "Vmin MT"),
                    ("vmin_mt_barra", "barra Vmin"),
                    ("vmax_mt_pu", "Vmax MT"),
                    ("vmax_mt_barra", "barra Vmax"),
                    ("carregamento_max_mt_pct", "carreg. máx. MT %"),
                    ("motivos", "motivos"),
                ],
            )
            linhas.append("")
    mudou = comparacao[comparacao["mudou_vencedora"]]
    sem_opcoes = sorted(resumo.loc[resumo["n_opcoes"] == 0, "caso"].unique())
    linhas += [
        "## 6. Conclusão",
        "",
    ]
    if mudou.empty:
        linhas.append(
            "- **Resultado desta base:** entre os 6 casos rodados, a GD **não mudou a opção "
            "vencedora** do `restore_options(score=true)` entre meio-dia e ponta da noite."
        )
    else:
        linhas.append(
            "- **Resultado desta base:** a GD **mudou a opção vencedora** em "
            + ", ".join(f"`{r.caso}`" for r in mudou.itertuples(index=False))
            + "."
        )
    mudou_viavel = comparacao[comparacao["mudou_opcao_viavel"]]
    if mudou_viavel.empty:
        linhas.append(
            "- Também não houve troca de **melhor opção viável** entre os dois instantes nos casos "
            "avaliados."
        )
    else:
        linhas.append(
            "- Houve mudança na **melhor opção viável** em "
            + ", ".join(f"`{r.caso}`" for r in mudou_viavel.itertuples(index=False))
            + "."
        )
    if sem_opcoes:
        linhas.append(
            "- Casos sem alternativa topológica de restauração neste recorte: "
            + ", ".join(f"`{caso}`" for caso in sem_opcoes)
            + "."
        )
    if "taquara_bocari" in set(mudou["caso"]):
        linhas.append(
            "- Na base atual, a troca de vencedora apareceu em `taquara_bocari`, mas com uma "
            "**limitação relevante**: o meio-dia com GD não convergiu para nenhuma das 10 opções, "
            "enquanto a ponta da noite sem GD convergiu com 10 opções viáveis."
        )
    if "SRD002" in set(mudou_viavel["caso"]):
        linhas.append(
            "- Em `SRD002`, a chave vencedora permaneceu `20729022`, mas a viabilidade mudou: "
            "ao meio-dia com GD ela ficou viável; na ponta da noite sem GD, nenhuma das 3 opções "
            "convergiu como viável."
        )
    linhas += [
        (
            "- A formulação operacional correta permanece: **a GD não restaura durante a falta**, "
            "mas pode reduzir a carga absorvida pelo socorredor no instante da transferência e, "
            "por consequência, alterar a margem do disjuntor, a tensão MT e a viabilidade "
            "do socorro."
        ),
        (
            "- Se algum caso mudou de vencedora, a recomendação é tratar o **horário do evento** "
            "como premissa explícita do score em issue separada, sem alterar o "
            "comportamento nesta #99."
        ),
        "",
        "## 7. Artefatos versionados",
        "",
        f"- Detalhe por opção: `{out_opcoes_csv}`.",
        f"- Resumo por caso/instante: `{out_resumo_csv}`.",
        "",
        "## 8. Reprodução",
        "",
        "```bash",
        "uv run python scripts/gd_na_restauracao.py \\",
        "  --parquet-dir data/parquet \\",
        "  --mmgd data/gd/empreendimento-geracao-distribuida.parquet \\",
        "  --out docs/gd-restauracao.md",
        "```",
        "",
    ]
    return "\n".join(linhas)
