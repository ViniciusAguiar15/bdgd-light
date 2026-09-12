"""Gera `docs/gd-gemeo.md` com comparação com/sem GD no gêmeo OpenDSS."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from rich.console import Console

from bdgd_light.ingest.recorte import recortar
from bdgd_light.twin import (
    ConfiguracaoGd,
    converter_ctmt,
    listar_ctmts,
    montar_master_cluster,
    run_powerflow,
)

console = Console()
INSTANCIAS = (
    ("madrugada", 2),
    ("meio_dia", 12),
    ("ponta_noite", 19),
)
CLUSTERS = {
    "tijuca": Path("data/feeders/cluster_tijuca.gpkg"),
    "ipanema": Path("data/feeders/cluster_ipanema.gpkg"),
    "taquara": Path("data/feeders/cluster_TQR0007-TQR33859-TQR33862.gpkg"),
}
ALIMENTADORES_COMPARADOS = {
    "ALC9925": "cluster Tijuca — CABOFRIO",
    "RCP9882": "cluster Tijuca — AMALIA",
    "URG29983": "cluster Tijuca — BURLE MARX",
    "PTS9924": "cluster Ipanema — alimentador convergente",
    "PTS4022": "cluster Ipanema — alimentador convergente",
    "GDN0022": "alta penetração convergente na #97",
    "TRS003": "alta penetração convergente na #97",
}
ALIMENTADORES_MAIOR_PENETRACAO = {
    "BRI001": "maior penetração da #97/#35",
    "SRD002": "segunda maior penetração da #97/#35",
}


@dataclass(frozen=True)
class CasoAlimentador:
    ctmt: str
    origem: str
    gpkg: Path


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--parquet-dir", type=Path, default=Path("data/parquet"))
    p.add_argument(
        "--mmgd",
        type=Path,
        default=Path("data/gd/empreendimento-geracao-distribuida.parquet"),
    )
    p.add_argument("--feeders-dir", type=Path, default=Path("data/feeders"))
    p.add_argument("--dss-out", type=Path, default=Path("data/dss/gpkg_issue98"))
    p.add_argument("--mes", type=int, default=9)
    p.add_argument("--dia", default="DU")
    p.add_argument("--out", type=Path, default=Path("docs/gd-gemeo.md"))
    p.add_argument(
        "--out-feeders",
        type=Path,
        default=Path("docs/dados/gd-gemeo-alimentadores.csv"),
    )
    p.add_argument(
        "--out-clusters",
        type=Path,
        default=Path("docs/dados/gd-gemeo-clusters.csv"),
    )
    p.add_argument(
        "--out-alocacao",
        type=Path,
        default=Path("docs/dados/gd-gemeo-alocacao.csv"),
    )
    return p


def _garantir_recorte(ctmt: str, parquet_dir: Path, feeders_dir: Path) -> Path:
    gpkg = feeders_dir / f"{ctmt}.gpkg"
    if gpkg.exists():
        return gpkg
    console.print(f"[cyan]Recortando {ctmt}…[/]")
    resultado = recortar(parquet_dir, [ctmt], feeders_dir, console=Console(quiet=True))
    return resultado.recortes[0].gpkg


def _fluxo_saida(resultado) -> tuple[str, float]:
    kw = float(resultado.potencia_kw)
    sentido = "reverso" if kw < 0 else "SE→rede"
    return sentido, kw


def _medidas_validas(convergiu: bool, vmax_mt_pu: float, kw_saida: float, perdas_kw: float) -> bool:
    return (
        convergiu
        and math.isfinite(vmax_mt_pu)
        and math.isfinite(kw_saida)
        and math.isfinite(perdas_kw)
        and 0.0 < vmax_mt_pu <= 2.0
    )


def _status_cenario(convergiu: bool, vmax_mt_pu: float, kw_saida: float, perdas_kw: float) -> str:
    if not convergiu:
        return "não convergiu"
    if not _medidas_validas(convergiu, vmax_mt_pu, kw_saida, perdas_kw):
        return "instável numericamente"
    return "ok"


def _resumo_fluxo(caso: str, grupo: str, instante: str, hora: int, com_gd: bool, resultado) -> dict:
    mt = resultado.tensoes_mt()
    vmax = mt.nlargest(1, "v_pu").iloc[0] if not mt.empty else None
    sentido, kw_fonte = _fluxo_saida(resultado)
    barras_sobre = 0 if mt.empty else int(mt.loc[mt["v_pu"] > 1.05, "barra"].nunique())
    vmax_mt_pu = float(vmax["v_pu"]) if vmax is not None else float("nan")
    perdas_kw = float(resultado.perdas_kw)
    return {
        "grupo": grupo,
        "caso": caso,
        "instante": instante,
        "hora": hora,
        "com_gd": com_gd,
        "convergiu": bool(resultado.convergiu),
        "status": _status_cenario(bool(resultado.convergiu), vmax_mt_pu, kw_fonte, perdas_kw),
        "vmax_mt_pu": vmax_mt_pu,
        "barra_vmax_mt": str(vmax["barra"]) if vmax is not None else "",
        "barras_mt_acima_1_05": barras_sobre,
        "sentido_fonte": sentido,
        "kw_fonte": kw_fonte,
        "perdas_kw": perdas_kw,
        "potencia_kw": float(resultado.potencia_kw),
        "ajustes": ",".join(resultado.ajustes),
    }


def _delta_por_instante(tabela: pd.DataFrame) -> pd.DataFrame:
    base = (
        tabela[~tabela["com_gd"]]
        .drop(columns=["com_gd"])
        .rename(
            columns={
                "convergiu": "convergiu_sem_gd",
                "status": "status_sem_gd",
                "vmax_mt_pu": "vmax_sem_gd_pu",
                "barra_vmax_mt": "barra_vmax_sem_gd",
                "barras_mt_acima_1_05": "barras_mt_acima_1_05_sem_gd",
                "sentido_fonte": "sentido_sem_gd",
                "kw_fonte": "kw_fonte_sem_gd",
                "perdas_kw": "perdas_sem_gd_kw",
                "potencia_kw": "potencia_sem_gd_kw",
                "ajustes": "ajustes_sem_gd",
            }
        )
    )
    gd = (
        tabela[tabela["com_gd"]]
        .drop(columns=["com_gd"])
        .rename(
            columns={
                "convergiu": "convergiu_com_gd",
                "status": "status_com_gd",
                "vmax_mt_pu": "vmax_com_gd_pu",
                "barra_vmax_mt": "barra_vmax_com_gd",
                "barras_mt_acima_1_05": "barras_mt_acima_1_05_com_gd",
                "sentido_fonte": "sentido_com_gd",
                "kw_fonte": "kw_fonte_com_gd",
                "perdas_kw": "perdas_com_gd_kw",
                "potencia_kw": "potencia_com_gd_kw",
                "ajustes": "ajustes_com_gd",
            }
        )
    )
    chaves = ["grupo", "caso", "instante", "hora"]
    merge = base.merge(gd, on=chaves, how="inner")
    merge["delta_vmax_pu"] = merge["vmax_com_gd_pu"] - merge["vmax_sem_gd_pu"]
    merge["delta_barras_mt_acima_1_05"] = (
        merge["barras_mt_acima_1_05_com_gd"] - merge["barras_mt_acima_1_05_sem_gd"]
    )
    merge["delta_kw_fonte"] = merge["kw_fonte_com_gd"] - merge["kw_fonte_sem_gd"]
    merge["delta_perdas_kw"] = merge["perdas_com_gd_kw"] - merge["perdas_sem_gd_kw"]
    merge["comparacao_valida"] = (merge["status_sem_gd"] == "ok") & (merge["status_com_gd"] == "ok")
    return merge


def _rodar_caso_alimentador(
    caso: CasoAlimentador,
    dss_out: Path,
    dia: str,
    mes: int,
    gd_cfg: ConfiguracaoGd,
) -> tuple[list[dict], dict]:
    conv = converter_ctmt(caso.gpkg, caso.ctmt, dss_out, dias=[dia], meses=[mes], gd=gd_cfg)
    if conv.gd is None:
        raise RuntimeError(f"{caso.ctmt}: conversão não produziu arquivo GD_BT")
    master_base = montar_master_cluster(
        [conv.pasta],
        dss_out / caso.ctmt / f"Master_{dia}{mes:02d}_base_issue98.dss",
        dia=dia,
        mes=mes,
        nome=caso.ctmt,
    )
    master_gd = montar_master_cluster(
        [conv.pasta],
        dss_out / caso.ctmt / f"Master_{dia}{mes:02d}_gd_issue98.dss",
        dia=dia,
        mes=mes,
        nome=caso.ctmt,
        gd=True,
    )
    linhas: list[dict] = []
    for instante, hora in INSTANCIAS:
        r_base = run_powerflow(master_base, modo="daily", comandos_extra=[f"set hour={hora}"])
        r_gd = run_powerflow(master_gd, modo="daily", comandos_extra=[f"set hour={hora}"])
        linhas.append(_resumo_fluxo(caso.ctmt, "alimentador", instante, hora, False, r_base))
        linhas.append(_resumo_fluxo(caso.ctmt, "alimentador", instante, hora, True, r_gd))
    resumo_alocacao = {
        "ctmt": caso.ctmt,
        "origem": caso.origem,
        "n_elementos_gd": conv.gd.n_elementos,
        "n_empreendimentos_exatos": conv.gd.n_empreendimentos_exatos,
        "potencia_exata_kw": conv.gd.potencia_exata_kw,
        "n_empreendimentos_agregados": conv.gd.n_empreendimentos_agregados,
        "potencia_agregada_kw": conv.gd.potencia_agregada_kw,
        "criterio_agregado": conv.gd.criterio_agregado or "",
        "grupos_agregados": "; ".join(conv.gd.grupos_agregados),
    }
    return linhas, resumo_alocacao


def _rodar_cluster(
    nome: str,
    gpkg: Path,
    dss_out: Path,
    dia: str,
    mes: int,
    gd_cfg: ConfiguracaoGd,
) -> list[dict]:
    ctmts = listar_ctmts(gpkg)
    pastas = [
        converter_ctmt(
            gpkg,
            ctmt,
            dss_out / f"cluster_{nome}",
            dias=[dia],
            meses=[mes],
            gd=gd_cfg,
        ).pasta
        for ctmt in ctmts
    ]
    master_base = montar_master_cluster(
        pastas,
        dss_out / f"cluster_{nome}" / f"Master_{dia}{mes:02d}_base_issue98.dss",
        dia=dia,
        mes=mes,
        nome=f"cluster_{nome}",
    )
    master_gd = montar_master_cluster(
        pastas,
        dss_out / f"cluster_{nome}" / f"Master_{dia}{mes:02d}_gd_issue98.dss",
        dia=dia,
        mes=mes,
        nome=f"cluster_{nome}",
        gd=True,
    )
    linhas: list[dict] = []
    for instante, hora in INSTANCIAS:
        r_base = run_powerflow(master_base, modo="daily", comandos_extra=[f"set hour={hora}"])
        r_gd = run_powerflow(master_gd, modo="daily", comandos_extra=[f"set hour={hora}"])
        linhas.append(_resumo_fluxo(nome, "cluster", instante, hora, False, r_base))
        linhas.append(_resumo_fluxo(nome, "cluster", instante, hora, True, r_gd))
    return linhas


def _fmt_num(valor: float, casas: int = 3) -> str:
    return f"{valor:.{casas}f}"


def _markdown_tabela(df: pd.DataFrame, colunas: list[tuple[str, str]]) -> list[str]:
    cabecalho = "| " + " | ".join(rotulo for _, rotulo in colunas) + " |"
    separador = "| " + " | ".join("---" for _ in colunas) + " |"
    linhas = [cabecalho, separador]
    for _, row in df.iterrows():
        valores = []
        for coluna, _ in colunas:
            valor = row[coluna]
            if isinstance(valor, float):
                valor = _fmt_num(valor, 3)
            valores.append(str(valor))
        linhas.append("| " + " | ".join(valores) + " |")
    return linhas


def _renderizar(
    dia: str,
    mes: int,
    alimentadores: pd.DataFrame,
    diagnosticos: pd.DataFrame,
    clusters: pd.DataFrame,
    alocacao: pd.DataFrame,
    escolhidos: list[CasoAlimentador],
    limites: list[CasoAlimentador],
) -> str:
    linhas = [
        "# GD no gêmeo da Light",
        "",
        "Relatório gerado por `scripts/gerar_gd_gemeo.py` com fluxo OpenDSS em `mode=daily`.",
        "",
        "## 1. Premissas desta rodada",
        "",
        f"- Dia/mês do Master: **{dia}{mes:02d}**.",
        (
            "- Instantes representativos: **02:00** (madrugada), **12:00** (meio-dia) "
            "e **19:00** (ponta da noite)."
        ),
        (
            "- Carga segue as curvas `CRVCRG` já usadas pelo conversor; a GD solar entra "
            "como `PVSystem` com shape diário sintético de 0→1→0, e as fontes não solares "
            "entram como `Generator` com shape plano (1,0 nas 24 h)."
        ),
        (
            "- A **flag de GD permanece desligada por padrão**: os Masters base continuam "
            "sem `Redirect` de `GD_BT`; a comparação com GD usa um Master de cenário "
            "montado com `--gd`."
        ),
        (
            "- Quando a MMGD tem chave direta (`CodEmpreendimento ↔ CEG_GD`), a injeção "
            "entra no **PAC da unidade geradora** (`UGBT_tab` / `UGMT_tab`)."
        ),
        (
            "- Quando a MMGD da Light não tem chave direta, o saldo é agregado **apenas por "
            "município** (limite já documentado na #97) e rateado: 1) entre CTMTs do "
            "município, proporcionalmente à carga cadastrada; 2) dentro do CTMT, por "
            "transformador BT e PAC MT."
        ),
        "",
        "## 2. Casos rodados",
        "",
        "- Alimentadores comparados com números versionados:",
    ]
    for caso in escolhidos:
        linhas.append(f"  - `{caso.ctmt}` — {caso.origem}")
    linhas.append("- Alimentadores de maior penetração rodados como diagnóstico de estabilidade:")
    for caso in limites:
        linhas.append(f"  - `{caso.ctmt}` — {caso.origem}")
    linhas += [
        "- Clusters completos: `tijuca`, `ipanema`, `taquara`.",
        "",
        "## 3. Alocação da GD por alimentador",
        "",
    ]
    linhas += _markdown_tabela(
        alocacao,
        [
            ("ctmt", "CTMT"),
            ("origem", "origem"),
            ("n_empreendimentos_exatos", "empreend. exatos"),
            ("potencia_exata_kw", "kW exatos"),
            ("n_empreendimentos_agregados", "empreend. agregados"),
            ("potencia_agregada_kw", "kW agregados"),
            ("criterio_agregado", "critério"),
            ("grupos_agregados", "grupo agregado"),
        ],
    )
    linhas += [
        "",
        "## 4. Comparação com/sem GD — alimentadores versionados",
        "",
    ]
    linhas += _markdown_tabela(
        alimentadores[alimentadores["comparacao_valida"]],
        [
            ("caso", "CTMT"),
            ("instante", "instante"),
            ("vmax_sem_gd_pu", "Vmax MT sem GD"),
            ("barra_vmax_sem_gd", "barra sem GD"),
            ("vmax_com_gd_pu", "Vmax MT com GD"),
            ("barra_vmax_com_gd", "barra com GD"),
            ("barras_mt_acima_1_05_sem_gd", "barras >1,05 sem GD"),
            ("barras_mt_acima_1_05_com_gd", "barras >1,05 com GD"),
            ("sentido_sem_gd", "sentido sem GD"),
            ("sentido_com_gd", "sentido com GD"),
            ("perdas_sem_gd_kw", "perdas sem GD kW"),
            ("perdas_com_gd_kw", "perdas com GD kW"),
            ("delta_perdas_kw", "Δ perdas kW"),
        ],
    )
    linhas += [
        "",
        "## 5. Maiores penetrações e clusters — estabilidade do modelo",
        "",
    ]
    linhas += _markdown_tabela(
        pd.concat([diagnosticos, clusters], ignore_index=True),
        [
            ("grupo", "grupo"),
            ("caso", "caso"),
            ("instante", "instante"),
            ("status_sem_gd", "status sem GD"),
            ("status_com_gd", "status com GD"),
            ("vmax_sem_gd_pu", "Vmax MT sem GD"),
            ("vmax_com_gd_pu", "Vmax MT com GD"),
            ("delta_kw_fonte", "Δ kW na saída"),
        ],
    )
    linhas += [
        "",
        "## 6. Leitura",
        "",
    ]
    alimentadores_validos = alimentadores[alimentadores["comparacao_valida"]].copy()
    meio_dia = alimentadores_validos[alimentadores_validos["instante"] == "meio_dia"].copy()
    relevantes = meio_dia[
        (meio_dia["barras_mt_acima_1_05_com_gd"] > 0)
        | (meio_dia["sentido_com_gd"] == "reverso")
        | (meio_dia["delta_vmax_pu"] > 0.01)
    ]
    if relevantes.empty:
        linhas.append(
            "- Nesta rodada, a GD alterou perdas e carregamento, mas **não** gerou "
            "sobretensão MT > 1,05 pu nem fluxo reverso nos alimentadores versionados."
        )
    else:
        linhas.append(
            "- A GD já importa hoje nos seguintes alimentadores ao meio-dia: "
            + ", ".join(f"`{ctmt}`" for ctmt in relevantes["caso"])
            + "."
        )
    maiores = meio_dia.sort_values("delta_vmax_pu", ascending=False).head(3)
    linhas.append(
        "- Maiores elevações de Vmax MT ao meio-dia: "
        + "; ".join(
            f"`{r.caso}` +{r.delta_vmax_pu:.3f} pu ({r.barra_vmax_com_gd})"
            for r in maiores.itertuples(index=False)
        )
        + "."
    )
    reversos = meio_dia[meio_dia["sentido_com_gd"] == "reverso"]
    if reversos.empty:
        linhas.append(
            "- Nenhum dos alimentadores versionados inverteu o fluxo no disjuntor de "
            "saída neste recorte temporal."
        )
    else:
        linhas.append(
            "- Houve fluxo reverso no disjuntor de saída em: "
            + ", ".join(
                f"`{r.caso}` ({r.kw_fonte_com_gd:.1f} kW)" for r in reversos.itertuples(index=False)
            )
            + "."
        )
    instaveis = pd.concat([diagnosticos, clusters], ignore_index=True)
    instaveis = instaveis[
        (instaveis["status_sem_gd"] != "ok") | (instaveis["status_com_gd"] != "ok")
    ]
    if not instaveis.empty:
        linhas.append(
            "- Casos ainda instáveis nesta base: "
            + ", ".join(
                f"`{r.caso}`/{r.instante} ({r.status_sem_gd} → {r.status_com_gd})"
                for r in instaveis.itertuples(index=False)
            )
            + "."
        )
    linhas += [
        (
            "- Limitação importante: o saldo sem chave direta da MMGD continua sendo "
            "**municipal**, não por CTMT. Isso evita inventar precisão inexistente, mas "
            "ainda pode suavizar picos locais dentro do município."
        ),
        "",
        "## 7. Reprodução",
        "",
        "```bash",
        "uv run python scripts/gerar_gd_gemeo.py \\",
        "  --parquet-dir data/parquet \\",
        "  --mmgd data/gd/empreendimento-geracao-distribuida.parquet \\",
        "  --out docs/gd-gemeo.md",
        "```",
        "",
    ]
    return "\n".join(linhas)


def main() -> None:
    args = _parser().parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out_feeders.parent.mkdir(parents=True, exist_ok=True)
    args.dss_out.mkdir(parents=True, exist_ok=True)
    gd_cfg = ConfiguracaoGd(parquet_dir=args.parquet_dir, mmgd_path=args.mmgd)
    casos = [
        CasoAlimentador(
            ctmt=ctmt,
            origem=origem,
            gpkg=_garantir_recorte(ctmt, args.parquet_dir, args.feeders_dir),
        )
        for ctmt, origem in ALIMENTADORES_COMPARADOS.items()
    ]
    casos_limite = [
        CasoAlimentador(
            ctmt=ctmt,
            origem=origem,
            gpkg=_garantir_recorte(ctmt, args.parquet_dir, args.feeders_dir),
        )
        for ctmt, origem in ALIMENTADORES_MAIOR_PENETRACAO.items()
    ]

    linhas_alimentadores: list[dict] = []
    linhas_alocacao: list[dict] = []
    for caso in casos:
        console.print(f"[cyan]Rodando alimentador {caso.ctmt}…[/]")
        linhas, aloc = _rodar_caso_alimentador(caso, args.dss_out, args.dia, args.mes, gd_cfg)
        linhas_alimentadores.extend(linhas)
        linhas_alocacao.append(aloc)

    linhas_diagnostico: list[dict] = []
    for caso in casos_limite:
        console.print(f"[cyan]Rodando alimentador diagnóstico {caso.ctmt}…[/]")
        linhas, aloc = _rodar_caso_alimentador(caso, args.dss_out, args.dia, args.mes, gd_cfg)
        linhas_diagnostico.extend(linhas)
        linhas_alocacao.append(aloc)

    linhas_clusters: list[dict] = []
    for nome, gpkg in CLUSTERS.items():
        console.print(f"[cyan]Rodando cluster {nome}…[/]")
        linhas_clusters.extend(_rodar_cluster(nome, gpkg, args.dss_out, args.dia, args.mes, gd_cfg))

    bruto_alimentadores = pd.DataFrame(linhas_alimentadores)
    bruto_diagnostico = pd.DataFrame(linhas_diagnostico)
    bruto_clusters = pd.DataFrame(linhas_clusters)
    delta_alimentadores = _delta_por_instante(bruto_alimentadores)
    delta_diagnostico = _delta_por_instante(bruto_diagnostico)
    delta_clusters = _delta_por_instante(bruto_clusters)
    alocacao = pd.DataFrame(linhas_alocacao)

    delta_alimentadores.to_csv(args.out_feeders, index=False)
    delta_clusters.to_csv(args.out_clusters, index=False)
    alocacao.to_csv(args.out_alocacao, index=False)
    args.out.write_text(
        _renderizar(
            args.dia,
            args.mes,
            delta_alimentadores,
            delta_diagnostico,
            delta_clusters,
            alocacao,
            casos,
            casos_limite,
        ),
        encoding="utf-8",
    )
    console.print(f"[green]✔[/] relatório gravado em [bold]{args.out}[/]")


if __name__ == "__main__":
    main()
