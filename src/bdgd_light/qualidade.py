"""Perfil de qualidade do cadastro BDGD a partir das camadas exportadas em Parquet."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from bdgd_light.ingest.parquet import DiretorioParquet

MONOFASICAS = frozenset({"A", "B", "C", "AN", "BN", "CN", "AX", "BX", "CX"})
LIMITE_RAMAL_M = 300.0
LIMITE_PN_CON_M = 2_000.0
MAX_EXEMPLOS = 5
CAMADAS_FAS_CON = (
    "SSDMT",
    "SSDBT",
    "RAMLIG",
    "UNSEMT",
    "UNSEBT",
    "UCBT_tab",
    "UCMT_tab",
    "UGBT_tab",
    "UGMT_tab",
)
CAMADAS_TIP_CND = ("SSDMT", "SSDBT", "RAMLIG")
CAMADAS_COM_CTMT = (
    "SSDMT",
    "SSDBT",
    "UNSEMT",
    "UNSEBT",
    "UNTRMT",
    "UNREMT",
    "UNCRMT",
    "RAMLIG",
    "UCBT_tab",
    "UCMT_tab",
    "UGBT_tab",
    "UGMT_tab",
    "PIP",
)
CAMADAS_TLCD = ("UNSEMT", "UNSEBT")
ORIGENS_PAC_MT = (
    ("CTMT", "PAC_INI", "COD_ID"),
    ("SSDMT", "PAC_1", "COD_ID"),
    ("SSDMT", "PAC_2", "COD_ID"),
    ("UNSEMT", "PAC_1", "COD_ID"),
    ("UNSEMT", "PAC_2", "COD_ID"),
    ("UNTRMT", "PAC_1", "COD_ID"),
    ("UNTRMT", "PAC_2", "COD_ID"),
    ("UNTRMT", "PAC_3", "COD_ID"),
    ("UCMT_tab", "PAC", "COD_ID"),
    ("UGMT_tab", "PAC", "COD_ID"),
)


@dataclass(frozen=True)
class ConfiguracaoQualidade:
    """Parâmetros da análise de qualidade."""

    parquet_dir: Path
    limite_ramal_m: float = LIMITE_RAMAL_M
    limite_pn_con_m: float = LIMITE_PN_CON_M
    max_exemplos: int = MAX_EXEMPLOS


@dataclass(frozen=True)
class FonteMetadados:
    """Metadados básicos da base analisada."""

    distribuidora: int | None
    data_inicio: str
    data_fim: str
    data_extracao: str
    descricao: str
    parquet_dir: Path


@dataclass(frozen=True)
class ExemploDistancia:
    """Exemplo de referência geográfica distante."""

    cod_id: str
    ctmt: str
    distancia_m: float


@dataclass(frozen=True)
class ExemploPac:
    """Exemplo de PAC associado a mais de um alimentador."""

    pac: str
    ctmts: tuple[str, ...]
    camada: str
    cod_id: str


@dataclass(frozen=True)
class ResultadoQualidade:
    """Estrutura consolidada da análise para renderização."""

    fonte: FonteMetadados
    fas_con: dict[str, Any]
    ramlig: dict[str, Any]
    pn_con: dict[str, Any]
    tip_cnd: dict[str, Any]
    ctmt: dict[str, Any]
    pac: dict[str, Any]
    geometria: dict[str, Any]
    bbox: dict[str, Any]
    tlcd: dict[str, Any]
    perguntas: tuple[str, ...]


def analisar_qualidade(config: ConfiguracaoQualidade) -> ResultadoQualidade:
    """Executa as nove verificações de qualidade sobre o diretório Parquet informado."""
    fonte = DiretorioParquet(config.parquet_dir)
    metadados = carregar_metadados(fonte)
    mapa_trafo_ctmt = carregar_mapa_trafo_ctmt(fonte)
    fas_con = analisar_fas_con(fonte, mapa_trafo_ctmt, config.max_exemplos)
    ramlig = analisar_ramlig(fonte, config.limite_ramal_m, config.max_exemplos)
    pn_con = analisar_pn_con(fonte, mapa_trafo_ctmt, config.limite_pn_con_m, config.max_exemplos)
    tip_cnd = analisar_tip_cnd(fonte, config.max_exemplos)
    ctmt = analisar_ctmt(fonte, config.max_exemplos)
    pac = analisar_pacs_multiplos(fonte, config.max_exemplos)
    geometria, bbox = analisar_geometrias_e_bbox(fonte, config.max_exemplos)
    tlcd = analisar_tlcd(fonte, config.max_exemplos)
    perguntas = gerar_perguntas(pn_con, tip_cnd, ctmt, pac, tlcd)
    return ResultadoQualidade(
        fonte=metadados,
        fas_con=fas_con,
        ramlig=ramlig,
        pn_con=pn_con,
        tip_cnd=tip_cnd,
        ctmt=ctmt,
        pac=pac,
        geometria=geometria,
        bbox=bbox,
        tlcd=tlcd,
        perguntas=perguntas,
    )


def carregar_metadados(fonte: DiretorioParquet) -> FonteMetadados:
    """Lê os metadados básicos da camada BASE."""
    base = fonte.ler_se_existir("BASE")
    if base is None or base.empty:
        return FonteMetadados(None, "—", "—", "—", "BASE ausente", fonte.caminho)
    linha = base.iloc[0]
    return FonteMetadados(
        distribuidora=_inteiro_ou_none(linha.get("DIST")),
        data_inicio=_texto_unico(linha.get("DAT_INC")),
        data_fim=_texto_unico(linha.get("DAT_FNL")),
        data_extracao=_texto_unico(linha.get("DAT_EXT")),
        descricao=_texto_unico(linha.get("DESCR")),
        parquet_dir=fonte.caminho,
    )


def carregar_mapa_trafo_ctmt(fonte: DiretorioParquet) -> pd.Series:
    """Mapeia ``UNTRMT.COD_ID`` para ``CTMT`` com strings normalizadas."""
    if not fonte.tem("UNTRMT"):
        return pd.Series(dtype="string")
    trafos = fonte.ler("UNTRMT", ["COD_ID", "CTMT"])
    if trafos.empty:
        return pd.Series(dtype="string")
    trafos = trafos.copy()
    trafos["COD_ID"] = _normalizar_serie_texto(trafos["COD_ID"])
    trafos["CTMT"] = _normalizar_serie_texto(trafos["CTMT"])
    trafos = trafos.dropna(subset=["COD_ID"]).drop_duplicates("COD_ID")
    return trafos.set_index("COD_ID")["CTMT"]


def analisar_fas_con(
    fonte: DiretorioParquet, mapa_trafo_ctmt: pd.Series, max_exemplos: int
) -> dict[str, Any]:
    """Distribuição de ``FAS_CON`` por camada e concentração monofásica por alimentador."""
    total_informado = 0
    total_monofasico = 0
    resumo_camadas: list[dict[str, Any]] = []
    topo_alimentadores: list[dict[str, Any]] = []

    for camada in CAMADAS_FAS_CON:
        if not fonte.tem(camada) or "FAS_CON" not in fonte.colunas(camada):
            continue
        contagem_total: Counter[str] = Counter()
        total = 0
        informado = 0
        monofasico = 0
        total_por_ctmt: defaultdict[str, int] = defaultdict(int)
        mono_por_ctmt: defaultdict[str, int] = defaultdict(int)
        colunas = ["COD_ID", "FAS_CON", "CTMT", "UNI_TR_MT"]
        for lote in fonte.iterar_lotes(camada, colunas):
            if lote.empty:
                continue
            lote = lote.copy()
            lote["FAS_CON"] = _normalizar_serie_texto(lote.get("FAS_CON"))
            total += len(lote)
            validos = lote["FAS_CON"].dropna()
            informado += len(validos)
            monofasico += int(validos.isin(MONOFASICAS).sum())
            contagem_total.update(validos.value_counts().to_dict())

            ctmts = _resolver_ctmt_lote(lote, mapa_trafo_ctmt)
            mascara_ctmt = ctmts.notna() & lote["FAS_CON"].notna()
            if mascara_ctmt.any():
                total_ctmt = ctmts[mascara_ctmt].value_counts()
                mono_ctmt = ctmts[mascara_ctmt & lote["FAS_CON"].isin(MONOFASICAS)].value_counts()
                for ctmt, valor in total_ctmt.items():
                    total_por_ctmt[str(ctmt)] += int(valor)
                for ctmt, valor in mono_ctmt.items():
                    mono_por_ctmt[str(ctmt)] += int(valor)

        total_informado += informado
        total_monofasico += monofasico
        top_valores = ", ".join(
            f"{fas}={qtd}" for fas, qtd in sorted(contagem_total.items(), key=_chave_counter)[:5]
        )
        resumo_camadas.append(
            {
                "camada": camada,
                "registros": total,
                "informados": informado,
                "monofasicos": monofasico,
                "pct_monofasico": _percentual(monofasico, informado),
                "top_fas_con": top_valores or "—",
            }
        )
        candidatos = []
        for ctmt, total_ctmt in total_por_ctmt.items():
            if total_ctmt == 0:
                continue
            mono_ctmt = mono_por_ctmt.get(ctmt, 0)
            candidatos.append(
                {
                    "camada": camada,
                    "ctmt": ctmt,
                    "registros": total_ctmt,
                    "monofasicos": mono_ctmt,
                    "pct_monofasico": _percentual(mono_ctmt, total_ctmt),
                }
            )
        topo_alimentadores.extend(
            sorted(
                [c for c in candidatos if c["registros"] >= 20],
                key=lambda item: (-item["pct_monofasico"], -item["monofasicos"], item["ctmt"]),
            )[: max_exemplos * 2]
        )

    topo_alimentadores = sorted(
        topo_alimentadores,
        key=lambda item: (
            -item["pct_monofasico"],
            -item["monofasicos"],
            item["camada"],
            item["ctmt"],
        ),
    )[:max_exemplos]
    return {
        "contagem": total_monofasico,
        "universo": total_informado,
        "percentual": _percentual(total_monofasico, total_informado),
        "exemplos": tuple(item["ctmt"] for item in topo_alimentadores[:max_exemplos]),
        "camadas": sorted(resumo_camadas, key=lambda item: item["camada"]),
        "alimentadores": topo_alimentadores,
        "impacto": (
            "Concentração monofásica elevada pressiona o equilíbrio de fases e foi um dos gatilhos "
            "para estabilizações específicas no OpenDSS (ex.: vminpu=0.9 em circuitos BT)."
        ),
        "limitacoes": (),
    }


def analisar_ramlig(
    fonte: DiretorioParquet, limite_ramal_m: float, max_exemplos: int
) -> dict[str, Any]:
    """Ramais com comprimento excessivo."""
    if not fonte.tem("RAMLIG"):
        return _sem_camada("RAMLIG")
    total = 0
    validos = 0
    longos = 0
    comprimentos: list[np.ndarray] = []
    exemplos: list[dict[str, Any]] = []
    for lote in fonte.iterar_lotes("RAMLIG", ["COD_ID", "CTMT", "COMP"]):
        if lote.empty:
            continue
        total += len(lote)
        comp = pd.to_numeric(lote.get("COMP"), errors="coerce")
        mascara_valida = comp.notna()
        mascara_longa = mascara_valida & (comp > limite_ramal_m)
        validos += int(mascara_valida.sum())
        longos += int(mascara_longa.sum())
        if mascara_valida.any():
            comprimentos.append(comp[mascara_valida].to_numpy(dtype=float, copy=False))
        if mascara_longa.any():
            recorte = lote.loc[mascara_longa, ["COD_ID", "CTMT"]].copy()
            recorte["COMP"] = comp[mascara_longa].astype(float)
            exemplos.extend(recorte.to_dict(orient="records"))
            exemplos = sorted(exemplos, key=lambda item: (-item["COMP"], str(item["COD_ID"])))[:20]
    p99 = float(np.percentile(np.concatenate(comprimentos), 99)) if comprimentos else float("nan")
    top = exemplos[:max_exemplos]
    return {
        "contagem": longos,
        "universo": validos,
        "percentual": _percentual(longos, validos),
        "p99_m": p99,
        "exemplos": tuple(_texto_unico(item["COD_ID"]) for item in top),
        "exemplos_detalhados": [
            {
                "cod_id": _texto_unico(item["COD_ID"]),
                "ctmt": _texto_unico(item["CTMT"]),
                "comprimento_m": float(item["COMP"]),
            }
            for item in top
        ],
        "impacto": (
            "Ramais muito longos tendem a indicar circuito BT modelado como RAMLIG, o que distorce "
            "comprimento, perdas e o gêmeo elétrico BT."
        ),
        "limitacoes": (),
    }


def analisar_pn_con(
    fonte: DiretorioParquet,
    mapa_trafo_ctmt: pd.Series,
    limite_pn_con_m: float,
    max_exemplos: int,
) -> dict[str, Any]:
    """Postes ``PN_CON`` distantes do transformador da UC."""
    if not fonte.tem("UCBT_tab") or not fonte.tem("PONNOT") or not fonte.tem("UNTRMT"):
        return _sem_camada("UCBT_tab/PONNOT/UNTRMT")

    postes = fonte.ler("PONNOT", ["COD_ID", "geometry"])
    trafos = fonte.ler("UNTRMT", ["COD_ID", "CTMT", "geometry"])
    postes = postes.dropna(subset=["geometry"]).copy()
    trafos = trafos.dropna(subset=["geometry"]).copy()
    if postes.empty or trafos.empty:
        return _sem_camada("PONNOT/UNTRMT com geometria")

    postes["COD_ID"] = _normalizar_serie_texto(postes["COD_ID"])
    trafos["COD_ID"] = _normalizar_serie_texto(trafos["COD_ID"])
    postes_3857 = postes.to_crs("EPSG:3857")
    trafos_3857 = trafos.to_crs("EPSG:3857")
    postes_x = pd.Series(postes_3857.geometry.x.to_numpy(), index=postes["COD_ID"])
    postes_y = pd.Series(postes_3857.geometry.y.to_numpy(), index=postes["COD_ID"])
    trafos_x = pd.Series(trafos_3857.geometry.x.to_numpy(), index=trafos["COD_ID"])
    trafos_y = pd.Series(trafos_3857.geometry.y.to_numpy(), index=trafos["COD_ID"])

    total = 0
    mensuraveis = 0
    longes = 0
    exemplos: list[ExemploDistancia] = []
    for lote in fonte.iterar_lotes("UCBT_tab", ["COD_ID", "PN_CON", "UNI_TR_MT", "CTMT"]):
        if lote.empty:
            continue
        lote = lote.copy()
        lote["COD_ID"] = _normalizar_serie_texto(lote["COD_ID"])
        lote["PN_CON"] = _normalizar_serie_texto(lote["PN_CON"])
        lote["UNI_TR_MT"] = _normalizar_serie_texto(lote["UNI_TR_MT"])
        total += len(lote)
        mascara_base = lote["PN_CON"].notna() & lote["UNI_TR_MT"].notna()
        if not mascara_base.any():
            continue
        pn = lote.loc[mascara_base, "PN_CON"]
        tr = lote.loc[mascara_base, "UNI_TR_MT"]
        xs_poste = pn.map(postes_x)
        ys_poste = pn.map(postes_y)
        xs_trafo = tr.map(trafos_x)
        ys_trafo = tr.map(trafos_y)
        mascara_medida = xs_poste.notna() & ys_poste.notna() & xs_trafo.notna() & ys_trafo.notna()
        mensuraveis += int(mascara_medida.sum())
        if not mascara_medida.any():
            continue
        distancias = np.hypot(
            xs_poste[mascara_medida].to_numpy() - xs_trafo[mascara_medida].to_numpy(),
            ys_poste[mascara_medida].to_numpy() - ys_trafo[mascara_medida].to_numpy(),
        )
        medido = lote.loc[mascara_base, ["COD_ID", "CTMT"]].loc[mascara_medida].copy()
        medido["distancia_m"] = distancias
        mascara_longa = medido["distancia_m"] > limite_pn_con_m
        longes += int(mascara_longa.sum())
        if mascara_longa.any():
            medido = medido.loc[mascara_longa]
            medido["CTMT"] = _resolver_ctmt_lote(medido, mapa_trafo_ctmt).fillna(
                _normalizar_serie_texto(medido.get("CTMT"))
            )
            exemplos.extend(
                ExemploDistancia(
                    cod_id=_texto_unico(item["COD_ID"]),
                    ctmt=_texto_unico(item["CTMT"]),
                    distancia_m=float(item["distancia_m"]),
                )
                for item in medido.to_dict(orient="records")
            )
            exemplos = sorted(
                exemplos, key=lambda item: (-item.distancia_m, item.cod_id, item.ctmt)
            )[:20]

    limitacoes = []
    if fonte.tem("UCMT_tab"):
        colunas_ucmt = set(fonte.colunas("UCMT_tab"))
        if "UNI_TR_MT" not in colunas_ucmt:
            limitacoes.append(
                "UCMT_tab não traz UNI_TR_MT nem outro vínculo direto com transformador "
                "de distribuição; a checagem de 2 km ficou restrita a UCBT_tab na "
                "Light 2025."
            )
    return {
        "contagem": longes,
        "universo": mensuraveis,
        "percentual": _percentual(longes, mensuraveis),
        "cobertura": {"total_ucbt": total, "mensuraveis": mensuraveis},
        "exemplos": tuple(item.cod_id for item in exemplos[:max_exemplos]),
        "exemplos_detalhados": [
            {
                "cod_id": item.cod_id,
                "ctmt": item.ctmt,
                "distancia_m": item.distancia_m,
            }
            for item in exemplos[:max_exemplos]
        ],
        "impacto": (
            "PN_CON distante infla bbox de recortes e tiles e já motivou filtro "
            "geográfico para evitar postes a dezenas de km do alimentador."
        ),
        "limitacoes": tuple(limitacoes),
    }


def analisar_tip_cnd(fonte: DiretorioParquet, max_exemplos: int) -> dict[str, Any]:
    """Trechos com ``TIP_CND`` vazio ou sem correspondência em ``SEGCON``."""
    if not fonte.tem("SEGCON"):
        return _sem_camada("SEGCON")
    segcon = fonte.ler("SEGCON", ["COD_ID"])
    catalogo = set(_normalizar_serie_texto(segcon["COD_ID"]).dropna())
    total = 0
    problemas = 0
    resumo_camadas: list[dict[str, Any]] = []
    exemplos: list[dict[str, Any]] = []

    for camada in CAMADAS_TIP_CND:
        if not fonte.tem(camada) or "TIP_CND" not in fonte.colunas(camada):
            continue
        camada_total = 0
        camada_problemas = 0
        camada_vazios = 0
        camada_sem_catalogo = 0
        for lote in fonte.iterar_lotes(camada, ["COD_ID", "TIP_CND"]):
            if lote.empty:
                continue
            lote = lote.copy()
            lote["TIP_CND"] = _normalizar_serie_texto(lote.get("TIP_CND"))
            camada_total += len(lote)
            vazio = lote["TIP_CND"].isna()
            sem_catalogo = lote["TIP_CND"].notna() & ~lote["TIP_CND"].isin(catalogo)
            problema = vazio | sem_catalogo
            camada_problemas += int(problema.sum())
            camada_vazios += int(vazio.sum())
            camada_sem_catalogo += int(sem_catalogo.sum())
            if problema.any():
                recorte = lote.loc[problema, ["COD_ID", "TIP_CND"]].copy()
                recorte["camada"] = camada
                exemplos.extend(recorte.to_dict(orient="records"))
                exemplos = sorted(
                    exemplos,
                    key=lambda item: (
                        item["camada"],
                        "" if pd.isna(item["TIP_CND"]) else str(item["TIP_CND"]),
                        str(item["COD_ID"]),
                    ),
                )[:20]
        total += camada_total
        problemas += camada_problemas
        resumo_camadas.append(
            {
                "camada": camada,
                "registros": camada_total,
                "problemas": camada_problemas,
                "vazios": camada_vazios,
                "sem_catalogo": camada_sem_catalogo,
                "percentual": _percentual(camada_problemas, camada_total),
            }
        )
    return {
        "contagem": problemas,
        "universo": total,
        "percentual": _percentual(problemas, total),
        "exemplos": tuple(_texto_unico(item["COD_ID"]) for item in exemplos[:max_exemplos]),
        "exemplos_detalhados": [
            {
                "cod_id": _texto_unico(item["COD_ID"]),
                "camada": item["camada"],
                "tip_cnd": _texto_unico(item["TIP_CND"]) or "(vazio)",
            }
            for item in exemplos[:max_exemplos]
        ],
        "camadas": sorted(resumo_camadas, key=lambda item: item["camada"]),
        "impacto": (
            "Sem SEGCON compatível o conversor monta linhas apontando para linecodes "
            "inexistentes, o que vira ruído de engenharia e risco de quebra na "
            "conversão BDGD→OpenDSS."
        ),
        "limitacoes": (),
    }


def analisar_ctmt(fonte: DiretorioParquet, max_exemplos: int) -> dict[str, Any]:
    """Referências a ``CTMT`` ausente e alimentadores sem nenhuma referência."""
    if not fonte.tem("CTMT"):
        return _sem_camada("CTMT")
    ctmt = fonte.ler("CTMT", ["COD_ID"])
    cadastrados = set(_normalizar_serie_texto(ctmt["COD_ID"]).dropna())
    total_refs = 0
    refs_invalidas = 0
    referencias_validas: set[str] = set()
    exemplos_invalidos: list[dict[str, Any]] = []
    resumo_camadas: list[dict[str, Any]] = []

    for camada in CAMADAS_COM_CTMT:
        if not fonte.tem(camada) or "CTMT" not in fonte.colunas(camada):
            continue
        camada_total = 0
        camada_invalidas = 0
        for lote in fonte.iterar_lotes(camada, ["COD_ID", "CTMT"]):
            if lote.empty:
                continue
            lote = lote.copy()
            lote["CTMT"] = _normalizar_serie_texto(lote.get("CTMT"))
            camada_total += int(lote["CTMT"].notna().sum())
            invalida = lote["CTMT"].notna() & ~lote["CTMT"].isin(cadastrados)
            camada_invalidas += int(invalida.sum())
            refs_invalidas += int(invalida.sum())
            total_refs += int(lote["CTMT"].notna().sum())
            referencias_validas |= set(lote.loc[lote["CTMT"].isin(cadastrados), "CTMT"])
            if invalida.any():
                recorte = lote.loc[invalida, ["COD_ID", "CTMT"]].copy()
                recorte["camada"] = camada
                exemplos_invalidos.extend(recorte.to_dict(orient="records"))
                exemplos_invalidos = sorted(
                    exemplos_invalidos,
                    key=lambda item: (item["camada"], str(item["CTMT"]), str(item["COD_ID"])),
                )[:20]
        resumo_camadas.append(
            {
                "camada": camada,
                "referencias": camada_total,
                "ausentes": camada_invalidas,
                "percentual": _percentual(camada_invalidas, camada_total),
            }
        )

    sem_referencia = sorted(cadastrados - referencias_validas)
    return {
        "contagem": refs_invalidas,
        "universo": total_refs,
        "percentual": _percentual(refs_invalidas, total_refs),
        "exemplos": tuple(
            _texto_unico(item["COD_ID"]) for item in exemplos_invalidos[:max_exemplos]
        ),
        "exemplos_detalhados": [
            {
                "cod_id": _texto_unico(item["COD_ID"]),
                "camada": item["camada"],
                "ctmt": _texto_unico(item["CTMT"]),
            }
            for item in exemplos_invalidos[:max_exemplos]
        ],
        "camadas": sorted(resumo_camadas, key=lambda item: item["camada"]),
        "ctmt_sem_referencia": {
            "contagem": len(sem_referencia),
            "universo": len(cadastrados),
            "percentual": _percentual(len(sem_referencia), len(cadastrados)),
            "exemplos": tuple(sem_referencia[:max_exemplos]),
        },
        "impacto": (
            "Referência quebrada de CTMT contamina inventário, recortes e agregações "
            "por alimentador; o inverso pode indicar alimentador cadastro-reserva ou "
            "camada faltante no pipeline."
        ),
        "limitacoes": (),
    }


def analisar_pacs_multiplos(fonte: DiretorioParquet, max_exemplos: int) -> dict[str, Any]:
    """PACs de MT associados a mais de um alimentador."""
    primeiro_ctmt: dict[str, str] = {}
    total_pacs: set[str] = set()
    conflitos: dict[str, set[str]] = defaultdict(set)
    detalhes: dict[str, ExemploPac] = {}

    for camada, coluna_pac, coluna_id in ORIGENS_PAC_MT:
        if not fonte.tem(camada):
            continue
        colunas = set(fonte.colunas(camada))
        if coluna_pac not in colunas or coluna_id not in colunas:
            continue
        if camada != "CTMT" and "CTMT" not in colunas:
            continue
        for lote in fonte.iterar_lotes(camada, [coluna_id, coluna_pac, "CTMT"]):
            if lote.empty:
                continue
            lote = lote.copy()
            lote[coluna_pac] = _normalizar_serie_texto(lote.get(coluna_pac))
            if camada == "CTMT":
                ctmts = _normalizar_serie_texto(lote.get(coluna_id))
            else:
                ctmts = _normalizar_serie_texto(lote.get("CTMT"))
            ids = _normalizar_serie_texto(lote.get(coluna_id))
            for pac, ctmt, cod_id in zip(lote[coluna_pac], ctmts, ids, strict=False):
                if pd.isna(pac) or pd.isna(ctmt):
                    continue
                pac_txt = str(pac)
                ctmt_txt = str(ctmt)
                total_pacs.add(pac_txt)
                if pac_txt not in primeiro_ctmt:
                    primeiro_ctmt[pac_txt] = ctmt_txt
                    continue
                if primeiro_ctmt[pac_txt] == ctmt_txt:
                    continue
                conflitos[pac_txt].update({primeiro_ctmt[pac_txt], ctmt_txt})
                detalhes.setdefault(
                    pac_txt,
                    ExemploPac(
                        pac=pac_txt,
                        ctmts=tuple(
                            sorted(conflitos[pac_txt] or {primeiro_ctmt[pac_txt], ctmt_txt})
                        ),
                        camada=camada,
                        cod_id=_texto_unico(cod_id),
                    ),
                )
                detalhes[pac_txt] = ExemploPac(
                    pac=pac_txt,
                    ctmts=tuple(sorted(conflitos[pac_txt])),
                    camada=camada,
                    cod_id=_texto_unico(cod_id),
                )
    exemplos = sorted(detalhes.values(), key=lambda item: (-len(item.ctmts), item.pac, item.cod_id))
    return {
        "contagem": len(conflitos),
        "universo": len(total_pacs),
        "percentual": _percentual(len(conflitos), len(total_pacs)),
        "exemplos": tuple(item.cod_id for item in exemplos[:max_exemplos]),
        "exemplos_detalhados": [
            {
                "cod_id": item.cod_id,
                "pac": item.pac,
                "camada": item.camada,
                "ctmts": ", ".join(item.ctmts),
            }
            for item in exemplos[:max_exemplos]
        ],
        "impacto": (
            "O grafo usa PAC como nó interno do alimentador; PAC compartilhado entre "
            "CTMTs enfraquece a premissa de unicidade e pode mascarar interligações "
            "ou erros de modelagem."
        ),
        "limitacoes": (
            "A contagem cobre PACs de MT usados pelo pipeline elétrico (CTMT, SSDMT, "
            "UNSEMT, UNTRMT, UCMT_tab e UGMT_tab), não os PACs BT por transformador.",
        ),
    }


def analisar_geometrias_e_bbox(
    fonte: DiretorioParquet, max_exemplos: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Geometrias inválidas/vazias e coordenadas fora da bbox da área de atuação."""
    camadas_geograficas = [camada for camada in fonte.camadas() if fonte.eh_geografica(camada)]
    bbox_arat = None
    if fonte.tem("ARAT"):
        arat = fonte.ler("ARAT", ["geometry"])
        if isinstance(arat, gpd.GeoDataFrame) and not arat.empty:
            bbox_arat = tuple(float(v) for v in arat.total_bounds.tolist())

    total_geo = 0
    problemas_geo = 0
    exemplos_geo: list[dict[str, Any]] = []
    resumo_geo: list[dict[str, Any]] = []

    total_bbox = 0
    problemas_bbox = 0
    exemplos_bbox: list[dict[str, Any]] = []
    resumo_bbox: list[dict[str, Any]] = []

    for camada in sorted(camadas_geograficas):
        gdf = fonte.ler(camada, ["COD_ID", "geometry"])
        if not isinstance(gdf, gpd.GeoDataFrame) or gdf.empty:
            resumo_geo.append(
                {
                    "camada": camada,
                    "registros": 0,
                    "problemas": 0,
                    "percentual": 0.0,
                }
            )
            resumo_bbox.append(
                {
                    "camada": camada,
                    "registros": 0,
                    "problemas": 0,
                    "percentual": 0.0,
                }
            )
            continue
        codigos = (
            _normalizar_serie_texto(gdf["COD_ID"])
            if "COD_ID" in gdf
            else pd.Series([pd.NA] * len(gdf), dtype="string")
        )
        geoms = gdf.geometry.array
        missing = shapely.is_missing(geoms)
        empty = shapely.is_empty(geoms)
        invalid = (~missing) & (~empty) & (~shapely.is_valid(geoms))
        problema_geo = missing | empty | invalid
        total_geo += len(gdf)
        problemas_geo += int(problema_geo.sum())
        resumo_geo.append(
            {
                "camada": camada,
                "registros": len(gdf),
                "problemas": int(problema_geo.sum()),
                "percentual": _percentual(int(problema_geo.sum()), len(gdf)),
            }
        )
        if problema_geo.any():
            recorte = pd.DataFrame({"COD_ID": codigos[problema_geo], "camada": camada})
            exemplos_geo.extend(recorte.to_dict(orient="records"))
            exemplos_geo = sorted(
                exemplos_geo, key=lambda item: (item["camada"], _texto_unico(item["COD_ID"]))
            )[:20]

        if bbox_arat is None:
            resumo_bbox.append(
                {
                    "camada": camada,
                    "registros": len(gdf),
                    "problemas": 0,
                    "percentual": 0.0,
                }
            )
            continue
        bounds = shapely.bounds(geoms)
        mensuravel = (~missing) & (~empty)
        fora = np.zeros(len(gdf), dtype=bool)
        if mensuravel.any():
            fora = mensuravel & (
                (bounds[:, 0] < bbox_arat[0])
                | (bounds[:, 1] < bbox_arat[1])
                | (bounds[:, 2] > bbox_arat[2])
                | (bounds[:, 3] > bbox_arat[3])
            )
        total_bbox += int(mensuravel.sum())
        problemas_bbox += int(fora.sum())
        resumo_bbox.append(
            {
                "camada": camada,
                "registros": int(mensuravel.sum()),
                "problemas": int(fora.sum()),
                "percentual": _percentual(int(fora.sum()), int(mensuravel.sum())),
            }
        )
        if fora.any():
            recorte = pd.DataFrame({"COD_ID": codigos[fora], "camada": camada})
            exemplos_bbox.extend(recorte.to_dict(orient="records"))
            exemplos_bbox = sorted(
                exemplos_bbox, key=lambda item: (item["camada"], _texto_unico(item["COD_ID"]))
            )[:20]

    geometria = {
        "contagem": problemas_geo,
        "universo": total_geo,
        "percentual": _percentual(problemas_geo, total_geo),
        "exemplos": tuple(_texto_unico(item["COD_ID"]) for item in exemplos_geo[:max_exemplos]),
        "exemplos_detalhados": [
            {"cod_id": _texto_unico(item["COD_ID"]), "camada": item["camada"]}
            for item in exemplos_geo[:max_exemplos]
        ],
        "camadas": resumo_geo,
        "impacto": (
            "Geometria vazia ou inválida quebra consultas espaciais, recortes, tiles "
            "e qualquer análise baseada em área, comprimento ou distância."
        ),
        "limitacoes": (),
    }
    bbox = {
        "contagem": problemas_bbox,
        "universo": total_bbox,
        "percentual": _percentual(problemas_bbox, total_bbox),
        "bbox_arat": bbox_arat,
        "exemplos": tuple(_texto_unico(item["COD_ID"]) for item in exemplos_bbox[:max_exemplos]),
        "exemplos_detalhados": [
            {"cod_id": _texto_unico(item["COD_ID"]), "camada": item["camada"]}
            for item in exemplos_bbox[:max_exemplos]
        ],
        "camadas": resumo_bbox,
        "impacto": (
            "Coordenadas fora da bbox da concessão puxam mapa, bbox de recorte e "
            "verificações espaciais para fora do território esperado."
        ),
        "limitacoes": () if bbox_arat is not None else ("ARAT ausente: bbox não pôde ser medida.",),
    }
    return geometria, bbox


def analisar_tlcd(fonte: DiretorioParquet, max_exemplos: int) -> dict[str, Any]:
    """Chaves com ``TLCD`` nulo, vazio ou fora do domínio esperado."""
    total = 0
    problemas = 0
    resumo_camadas: list[dict[str, Any]] = []
    exemplos: list[dict[str, Any]] = []
    for camada in CAMADAS_TLCD:
        if not fonte.tem(camada) or "TLCD" not in fonte.colunas(camada):
            continue
        dados = fonte.ler(camada, ["COD_ID", "TLCD"])
        if dados.empty:
            continue
        total += len(dados)
        bruto = dados.get("TLCD")
        texto = _normalizar_serie_texto(bruto)
        numerico = pd.to_numeric(texto, errors="coerce")
        nulo = texto.isna()
        indefinido = numerico.notna() & ~numerico.isin([0, 1])
        problema = nulo | indefinido
        problemas += int(problema.sum())
        resumo_camadas.append(
            {
                "camada": camada,
                "registros": len(dados),
                "problemas": int(problema.sum()),
                "nulos": int(nulo.sum()),
                "indefinidos": int(indefinido.sum()),
                "percentual": _percentual(int(problema.sum()), len(dados)),
            }
        )
        if problema.any():
            recorte = dados.loc[problema, ["COD_ID"]].copy()
            recorte["camada"] = camada
            recorte["TLCD"] = texto[problema].fillna("(nulo)")
            exemplos.extend(recorte.to_dict(orient="records"))
            exemplos = sorted(
                exemplos,
                key=lambda item: (item["camada"], str(item["TLCD"]), str(item["COD_ID"])),
            )[:20]
    return {
        "contagem": problemas,
        "universo": total,
        "percentual": _percentual(problemas, total),
        "exemplos": tuple(_texto_unico(item["COD_ID"]) for item in exemplos[:max_exemplos]),
        "exemplos_detalhados": [
            {
                "cod_id": _texto_unico(item["COD_ID"]),
                "camada": item["camada"],
                "tlcd": _texto_unico(item["TLCD"]),
            }
            for item in exemplos[:max_exemplos]
        ],
        "camadas": sorted(resumo_camadas, key=lambda item: item["camada"]),
        "impacto": (
            "TLCD inconsistente distorce o inventário de telecomando e a priorização "
            "operacional de ties e chaves de manobra remota."
        ),
        "limitacoes": (),
    }


def gerar_perguntas(
    pn_con: dict[str, Any],
    tip_cnd: dict[str, Any],
    ctmt: dict[str, Any],
    pac: dict[str, Any],
    tlcd: dict[str, Any],
) -> tuple[str, ...]:
    """Lista objetiva de perguntas para a distribuidora."""
    perguntas = [
        (
            "A concentração massiva de `FAS_CON` monofásico em alguns alimentadores "
            "representa rede bifilar real ou convenção de cadastro usada como default?"
        ),
        (
            "Os `RAMLIG` acima de 300 m são de fato ramais de ligação ou trechos de "
            "circuito BT classificados na camada errada?"
        ),
        (
            "Qual é a regra oficial para o `PN_CON` de UCs BT quando o poste "
            "cadastrado fica a quilômetros do transformador? Há um campo mais "
            "confiável para o ponto de conexão físico?"
        ),
        (
            "Existe tabela de domínio ou catálogo complementar para os `TIP_CND` "
            "usados nos trechos sem correspondência em `SEGCON`?"
        ),
        (
            "Os `CTMT` referenciados fora da camada `CTMT` e os `CTMT` sem nenhuma "
            "referência representam alimentadores planejados, desativados, reserva "
            "fria ou erro de extração?"
        ),
        (
            "PACs compartilhados entre mais de um alimentador são casos intencionais "
            "de barramento/subestação ou inconsistência de identificação? Qual regra "
            "deve prevalecer no tratamento dessas exceções?"
        ),
        (
            "`TLCD` nulo significa chave não telecomandada, dado desconhecido ou "
            "outro estado operacional? O domínio correto continua restrito a 0/1?"
        ),
    ]
    if pn_con.get("limitacoes"):
        perguntas.append(
            "Para `UCMT_tab`, qual campo liga a UC ao equipamento/localização física "
            "que deve ser usado para validar a coerência do `PN_CON`?"
        )
    if tip_cnd.get("contagem", 0) == 0:
        perguntas = [p for p in perguntas if "TIP_CND" not in p]
    if ctmt.get("contagem", 0) == 0 and ctmt.get("ctmt_sem_referencia", {}).get("contagem", 0) == 0:
        perguntas = [p for p in perguntas if "CTMT" not in p]
    if pac.get("contagem", 0) == 0:
        perguntas = [p for p in perguntas if not p.startswith("PACs")]
    if tlcd.get("contagem", 0) == 0:
        perguntas = [p for p in perguntas if "`TLCD`" not in p]
    return tuple(perguntas)


def renderizar_markdown(resultado: ResultadoQualidade) -> str:
    """Renderiza o relatório determinístico em Markdown."""
    fonte = resultado.fonte
    linhas = [
        "# Qualidade do cadastro BDGD Light 2025",
        "",
        "_Arquivo gerado por `uv run python scripts/qualidade_bdgd.py`._",
        "",
        "## Fontes",
        "",
        f"- diretório analisado: `{_relativo_repo(fonte.parquet_dir)}`",
        f"- distribuidora: `{fonte.distribuidora if fonte.distribuidora is not None else '—'}`",
        f"- data-base informada em `BASE`: `{fonte.data_inicio}` a `{fonte.data_fim}`",
        f"- data de extração informada em `BASE`: `{fonte.data_extracao}`",
        f"- descrição da base: {fonte.descricao}",
        "",
        "## 1. `FAS_CON` por camada e por alimentador",
        "",
        _resumo(resultado.fas_con),
        "",
        _tabela(
            ["camada", "registros", "FAS_CON informado", "monofásicos", "% mono", "top 5 valores"],
            [
                [
                    item["camada"],
                    _fmt_int(item["registros"]),
                    _fmt_int(item["informados"]),
                    _fmt_int(item["monofasicos"]),
                    _fmt_pct(item["pct_monofasico"]),
                    item["top_fas_con"],
                ]
                for item in resultado.fas_con["camadas"]
            ],
        ),
        "",
        "### Alimentadores com maior concentração monofásica",
        "",
        _tabela(
            ["camada", "CTMT", "registros", "monofásicos", "% mono"],
            [
                [
                    item["camada"],
                    item["ctmt"],
                    _fmt_int(item["registros"]),
                    _fmt_int(item["monofasicos"]),
                    _fmt_pct(item["pct_monofasico"]),
                ]
                for item in resultado.fas_con["alimentadores"]
            ]
            or [["—", "—", "0", "0", "0,00%"]],
        ),
        "",
        f"- exemplos: {_lista_exemplos(resultado.fas_con['exemplos'])}",
        "",
        f"Impacto no pipeline: {_texto_impacto(resultado.fas_con)}",
        "",
        "## 2. `RAMLIG` acima de 300 m",
        "",
        _resumo(resultado.ramlig),
        "",
        f"- percentil 99 de `COMP`: **{_fmt_num(resultado.ramlig.get('p99_m'))} m**",
        f"- exemplos: {_lista_exemplos(resultado.ramlig['exemplos'])}",
        "",
        _tabela(
            ["COD_ID", "CTMT", "comprimento (m)"],
            [
                [item["cod_id"], item["ctmt"], _fmt_num(item["comprimento_m"])]
                for item in resultado.ramlig["exemplos_detalhados"]
            ]
            or [["—", "—", "—"]],
        ),
        "",
        f"Impacto no pipeline: {_texto_impacto(resultado.ramlig)}",
        "",
        "## 3. `PN_CON` de UCBT/UCMT a mais de 2 km do transformador da UC",
        "",
        _resumo(resultado.pn_con),
        "",
        (
            f"- cobertura mensurável em `UCBT_tab`: "
            f"**{_fmt_int(resultado.pn_con['cobertura']['mensuraveis'])}** "
            f"de **{_fmt_int(resultado.pn_con['cobertura']['total_ucbt'])}** registros"
        ),
        f"- exemplos: {_lista_exemplos(resultado.pn_con['exemplos'])}",
        "",
        _tabela(
            ["COD_ID", "CTMT", "distância (m)"],
            [
                [item["cod_id"], item["ctmt"], _fmt_num(item["distancia_m"])]
                for item in resultado.pn_con["exemplos_detalhados"]
            ]
            or [["—", "—", "—"]],
        ),
        *(_linhas_limitacoes(resultado.pn_con)),
        "",
        f"Impacto no pipeline: {_texto_impacto(resultado.pn_con)}",
        "",
        "## 4. Trechos sem `TIP_CND` correspondente em `SEGCON`",
        "",
        _resumo(resultado.tip_cnd),
        "",
        _tabela(
            ["camada", "registros", "problemas", "vazios", "sem catálogo", "% problema"],
            [
                [
                    item["camada"],
                    _fmt_int(item["registros"]),
                    _fmt_int(item["problemas"]),
                    _fmt_int(item["vazios"]),
                    _fmt_int(item["sem_catalogo"]),
                    _fmt_pct(item["percentual"]),
                ]
                for item in resultado.tip_cnd["camadas"]
            ]
            or [["—", "0", "0", "0", "0", "0,00%"]],
        ),
        "",
        f"- exemplos: {_lista_exemplos(resultado.tip_cnd['exemplos'])}",
        _tabela(
            ["COD_ID", "camada", "TIP_CND"],
            [
                [item["cod_id"], item["camada"], item["tip_cnd"]]
                for item in resultado.tip_cnd["exemplos_detalhados"]
            ]
            or [["—", "—", "—"]],
        ),
        "",
        f"Impacto no pipeline: {_texto_impacto(resultado.tip_cnd)}",
        "",
        "## 5. `CTMT` referenciado por feições mas ausente da camada `CTMT` (e o inverso)",
        "",
        _resumo(resultado.ctmt),
        "",
        _tabela(
            ["camada", "referências", "ausentes", "% ausente"],
            [
                [
                    item["camada"],
                    _fmt_int(item["referencias"]),
                    _fmt_int(item["ausentes"]),
                    _fmt_pct(item["percentual"]),
                ]
                for item in resultado.ctmt["camadas"]
            ]
            or [["—", "0", "0", "0,00%"]],
        ),
        "",
        (
            "- `CTMT` presentes em `CTMT` mas sem nenhuma referência nas camadas verificadas: "
            f"**{_fmt_int(resultado.ctmt['ctmt_sem_referencia']['contagem'])}** de "
            f"**{_fmt_int(resultado.ctmt['ctmt_sem_referencia']['universo'])}** "
            f"({_fmt_pct(resultado.ctmt['ctmt_sem_referencia']['percentual'])})"
        ),
        f"- exemplos de feições com `CTMT` ausente: {_lista_exemplos(resultado.ctmt['exemplos'])}",
        (
            "- exemplos de `CTMT` sem referência: "
            f"{_lista_exemplos(resultado.ctmt['ctmt_sem_referencia']['exemplos'])}"
        ),
        _tabela(
            ["COD_ID", "camada", "CTMT"],
            [
                [item["cod_id"], item["camada"], item["ctmt"]]
                for item in resultado.ctmt["exemplos_detalhados"]
            ]
            or [["—", "—", "—"]],
        ),
        "",
        f"Impacto no pipeline: {_texto_impacto(resultado.ctmt)}",
        "",
        "## 6. PACs que aparecem em mais de um alimentador",
        "",
        _resumo(resultado.pac),
        "",
        f"- exemplos: {_lista_exemplos(resultado.pac['exemplos'])}",
        _tabela(
            ["COD_ID", "camada", "PAC", "CTMTs"],
            [
                [item["cod_id"], item["camada"], item["pac"], item["ctmts"]]
                for item in resultado.pac["exemplos_detalhados"]
            ]
            or [["—", "—", "—", "—"]],
        ),
        *(_linhas_limitacoes(resultado.pac)),
        "",
        f"Impacto no pipeline: {_texto_impacto(resultado.pac)}",
        "",
        "## 7. Geometria inválida ou vazia, por camada",
        "",
        _resumo(resultado.geometria),
        "",
        _tabela(
            ["camada", "registros", "problemas", "% problema"],
            [
                [
                    item["camada"],
                    _fmt_int(item["registros"]),
                    _fmt_int(item["problemas"]),
                    _fmt_pct(item["percentual"]),
                ]
                for item in resultado.geometria["camadas"]
            ],
        ),
        "",
        f"- exemplos: {_lista_exemplos(resultado.geometria['exemplos'])}",
        _tabela(
            ["COD_ID", "camada"],
            [
                [item["cod_id"], item["camada"]]
                for item in resultado.geometria["exemplos_detalhados"]
            ]
            or [["—", "—"]],
        ),
        "",
        f"Impacto no pipeline: {_texto_impacto(resultado.geometria)}",
        "",
        "## 8. Coordenadas fora da bbox da área de concessão",
        "",
        _resumo(resultado.bbox),
        "",
        (
            "- bbox de `ARAT`: "
            + (
                "`[" + ", ".join(_fmt_num(v, 6) for v in resultado.bbox["bbox_arat"]) + "]`"
                if resultado.bbox.get("bbox_arat")
                else "não disponível"
            )
        ),
        _tabela(
            ["camada", "registros mensuráveis", "fora da bbox", "% fora"],
            [
                [
                    item["camada"],
                    _fmt_int(item["registros"]),
                    _fmt_int(item["problemas"]),
                    _fmt_pct(item["percentual"]),
                ]
                for item in resultado.bbox["camadas"]
            ],
        ),
        "",
        f"- exemplos: {_lista_exemplos(resultado.bbox['exemplos'])}",
        _tabela(
            ["COD_ID", "camada"],
            [[item["cod_id"], item["camada"]] for item in resultado.bbox["exemplos_detalhados"]]
            or [["—", "—"]],
        ),
        *(_linhas_limitacoes(resultado.bbox)),
        "",
        f"Impacto no pipeline: {_texto_impacto(resultado.bbox)}",
        "",
        "## 9. Chaves com `TLCD` nulo/indefinido",
        "",
        _resumo(resultado.tlcd),
        "",
        _tabela(
            ["camada", "registros", "problemas", "nulos", "indefinidos", "% problema"],
            [
                [
                    item["camada"],
                    _fmt_int(item["registros"]),
                    _fmt_int(item["problemas"]),
                    _fmt_int(item["nulos"]),
                    _fmt_int(item["indefinidos"]),
                    _fmt_pct(item["percentual"]),
                ]
                for item in resultado.tlcd["camadas"]
            ]
            or [["—", "0", "0", "0", "0", "0,00%"]],
        ),
        "",
        f"- exemplos: {_lista_exemplos(resultado.tlcd['exemplos'])}",
        _tabela(
            ["COD_ID", "camada", "TLCD"],
            [
                [item["cod_id"], item["camada"], item["tlcd"]]
                for item in resultado.tlcd["exemplos_detalhados"]
            ]
            or [["—", "—", "—"]],
        ),
        "",
        f"Impacto no pipeline: {_texto_impacto(resultado.tlcd)}",
        "",
        "## Perguntas para a distribuidora",
        "",
        *[f"- {pergunta}" for pergunta in resultado.perguntas],
        "",
    ]
    return "\n".join(linhas)


def _resolver_ctmt_lote(lote: pd.DataFrame, mapa_trafo_ctmt: pd.Series) -> pd.Series:
    if "CTMT" in lote:
        ctmt = _normalizar_serie_texto(lote.get("CTMT"))
    else:
        ctmt = pd.Series(pd.NA, index=lote.index, dtype="string")
    if "UNI_TR_MT" not in lote:
        return ctmt
    uni_tr_mt = _normalizar_serie_texto(lote.get("UNI_TR_MT"))
    via_trafo = uni_tr_mt.map(mapa_trafo_ctmt)
    if len(via_trafo) != len(ctmt):
        via_trafo = pd.Series(via_trafo, index=lote.index, dtype="string")
    return via_trafo.fillna(ctmt)


def _normalizar_serie_texto(serie: pd.Series | None) -> pd.Series:
    if serie is None:
        return pd.Series(dtype="string")
    resultado = pd.Series(serie, copy=False).astype("string").str.strip()
    return resultado.replace("", pd.NA)


def _texto_unico(valor: object) -> str:
    if valor is None or valor is pd.NA:
        return ""
    if isinstance(valor, float) and np.isnan(valor):
        return ""
    return str(valor).strip()


def _inteiro_ou_none(valor: object) -> int | None:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    return numero


def _sem_camada(nome: str) -> dict[str, Any]:
    return {
        "contagem": 0,
        "universo": 0,
        "percentual": 0.0,
        "exemplos": (),
        "exemplos_detalhados": [],
        "camadas": [],
        "impacto": "nenhum — verificação não executada.",
        "limitacoes": (f"Camada(s) necessária(s) ausente(s): {nome}.",),
    }


def _percentual(numerador: int, denominador: int) -> float:
    return 0.0 if denominador == 0 else 100.0 * numerador / denominador


def _chave_counter(item: tuple[str, int]) -> tuple[int, str]:
    chave, valor = item
    return (-valor, chave)


def _tabela(cabecalho: list[str], linhas: list[list[str]]) -> str:
    return "\n".join(
        [
            "| " + " | ".join(cabecalho) + " |",
            "|" + "|".join("---" for _ in cabecalho) + "|",
            *["| " + " | ".join(str(c) for c in linha) + " |" for linha in linhas],
        ]
    )


def _resumo(dados: dict[str, Any]) -> str:
    return (
        f"- contagem: **{_fmt_int(dados['contagem'])}**\n"
        f"- universo: **{_fmt_int(dados['universo'])}**\n"
        f"- percentual: **{_fmt_pct(dados['percentual'])}**"
    )


def _linhas_limitacoes(dados: dict[str, Any]) -> list[str]:
    if not dados.get("limitacoes"):
        return []
    return ["", "Limitações/adaptações:", *[f"- {item}" for item in dados["limitacoes"]]]


def _fmt_int(valor: object) -> str:
    try:
        return f"{int(valor):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"


def _fmt_pct(valor: float | None) -> str:
    if valor is None:
        return "—"
    casas = 4 if 0 < abs(valor) < 0.01 else 2
    return f"{valor:.{casas}f}%".replace(".", ",")


def _fmt_num(valor: float | None, casas: int = 2) -> str:
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return "—"
    return f"{valor:.{casas}f}".replace(".", ",")


def _lista_exemplos(exemplos: tuple[str, ...]) -> str:
    return ", ".join(f"`{item}`" for item in exemplos) if exemplos else "—"


def _texto_impacto(dados: dict[str, Any]) -> str:
    if dados.get("contagem", 0) == 0:
        return "nenhum — não houve ocorrência nessa checagem."
    return str(dados.get("impacto", "nenhum"))


def _relativo_repo(caminho: Path) -> str:
    try:
        return str(caminho.relative_to(Path.cwd()))
    except ValueError:
        return str(caminho)


__all__ = [
    "ConfiguracaoQualidade",
    "ResultadoQualidade",
    "analisar_qualidade",
    "renderizar_markdown",
]
