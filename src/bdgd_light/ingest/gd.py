"""Ingestão e consolidação da base pública de MMGD da ANEEL para a Light."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from bdgd_light.ingest.inventario import inventariar
from bdgd_light.ingest.parquet import DiretorioParquet

AGENTE_LIGHT = "LIGHT SERVICOS DE ELETRICIDADE S A"
SIGLA_LIGHT = "LIGHT SESA"
CNPJ_LIGHT = "60444437000146"
UF_LIGHT = "RJ"

COLUNAS_MMGD = (
    "DatGeracaoConjuntoDados",
    "AnmPeriodoReferencia",
    "NumCNPJDistribuidora",
    "SigAgente",
    "NomAgente",
    "CodClasseConsumo",
    "DscClasseConsumo",
    "CodSubGrupoTarifario",
    "DscSubGrupoTarifario",
    "CodUFibge",
    "SigUF",
    "CodRegiao",
    "NomRegiao",
    "CodMunicipioIbge",
    "NomMunicipio",
    "CodCEP",
    "SigTipoConsumidor",
    "NumCPFCNPJ",
    "CodEmpreendimento",
    "DthAtualizaCadastralEmpreend",
    "SigModalidadeEmpreendimento",
    "DscModalidadeHabilitado",
    "QtdUCRecebeCredito",
    "SigTipoGeracao",
    "DscFonteGeracao",
    "DscPorte",
    "MdaPotenciaInstaladaKW",
    "NomSubEstacao",
    "NumCoordESub",
    "NumCoordNSub",
    "NomTitularEmpreendimento",
)
COLUNAS_BDGD_GD = (
    "COD_ID",
    "CEG_GD",
    "CTMT",
    "UNI_TR_MT",
    "CONJ",
    "MUN",
    "POT_INST",
    "DAT_CON",
)


@dataclass(frozen=True)
class ConfiguracaoGd:
    """Parâmetros da consolidação."""

    parquet_dir: Path
    mmgd_path: Path
    distribuidora: str = "light"


@dataclass(frozen=True)
class EvidenciaJuncao:
    """Evidências sobre a chave de junção MMGD ↔ BDGD."""

    chave_mmgd: str
    chave_bdgd: str
    n_mmgd: int
    kw_mmgd: float
    n_mmgd_com_match: int
    kw_mmgd_com_match: float
    n_mmgd_sem_match: int
    kw_mmgd_sem_match: float
    n_bdgd: int
    kw_bdgd: float
    n_bdgd_com_match: int
    kw_bdgd_com_match: float
    n_bdgd_sem_match: int
    kw_bdgd_sem_match: float
    n_bdgd_ceg_vazio: int
    kw_bdgd_ceg_vazio: float
    n_ceg_ambiguos_multictmt: int
    n_ceg_duplicados_mesmo_ctmt: int


@dataclass(frozen=True)
class ResultadoGd:
    """Estrutura consolidada para relatório e artefatos auxiliares."""

    mmgd_filtrado: pd.DataFrame
    bdgd_gd: pd.DataFrame
    comparativo_chave: pd.DataFrame
    alimentadores: pd.DataFrame
    conjuntos: pd.DataFrame
    municipios_sem_chave: pd.DataFrame
    evolucao_anual: pd.DataFrame
    divergencias: pd.DataFrame
    evidencia_juncao: EvidenciaJuncao
    extraido_em: str
    data_geracao_conjunto: str
    periodo_referencia: str
    distribuidora: str
    observacao_data: str


def analisar_gd(config: ConfiguracaoGd) -> ResultadoGd:
    """Consolida a MMGD da ANEEL com a BDGD da Light."""
    fonte = DiretorioParquet(config.parquet_dir)
    mmgd = normalizar_mmgd(carregar_mmgd(config.mmgd_path), distribuidora=config.distribuidora)
    bdgd = carregar_bdgd_gd(fonte)
    comparativo = comparar_por_chave(mmgd, bdgd)
    evidencia = montar_evidencia_juncao(mmgd, bdgd, comparativo)

    inventario = inventariar(config.parquet_dir)
    alimentadores = inventario.tabela.copy()
    conjuntos_ctmt = _mapa_conjuntos_ctmt(fonte)
    alimentadores["CONJ_CODIGO"] = alimentadores["COD_ID"].map(conjuntos_ctmt).fillna("")
    alimentadores["CONJ_NOME"] = (
        alimentadores["CONJ_CODIGO"].map(_mapa_nomes_conjuntos(fonte)).fillna("")
    )
    alimentadores["MUN"] = pd.to_numeric(alimentadores["MUN"], errors="coerce").astype("Int64")

    match_exato = comparativo.loc[comparativo["status_juncao"] == "match_exato"].copy()
    alimentadores_ag = agregar_por_alimentador(match_exato, alimentadores)
    conjuntos_ag = agregar_por_conjunto(alimentadores_ag)
    municipios_sem = agregar_sem_chave_por_municipio(
        comparativo.loc[comparativo["status_juncao"] != "match_exato"], alimentadores
    )
    evolucao = agregar_evolucao_anual(mmgd)
    divergencias = listar_divergencias(match_exato)

    data_geracao = _primeiro_texto(mmgd["data_geracao_conjunto"])
    periodo = _primeiro_texto(mmgd["periodo_referencia"])
    observacao_data = (
        "O dicionário PDF v2.3 expõe como único campo temporal do arquivo "
        "`DthAtualizaCadastralEmpreend`. Apesar do texto descritivo citar 'data da conexão', "
        "não há outra coluna temporal no Parquet; a evolução anual abaixo usa "
        "exatamente esse campo."
    )
    return ResultadoGd(
        mmgd_filtrado=mmgd,
        bdgd_gd=bdgd,
        comparativo_chave=comparativo,
        alimentadores=alimentadores_ag,
        conjuntos=conjuntos_ag,
        municipios_sem_chave=municipios_sem,
        evolucao_anual=evolucao,
        divergencias=divergencias,
        evidencia_juncao=evidencia,
        extraido_em=_carregar_extraido_em(config.mmgd_path),
        data_geracao_conjunto=data_geracao,
        periodo_referencia=periodo,
        distribuidora=AGENTE_LIGHT if config.distribuidora == "light" else config.distribuidora,
        observacao_data=observacao_data,
    )


def carregar_mmgd(caminho: str | Path) -> pd.DataFrame:
    """Lê o recurso de MMGD em Parquet, CSV ou ZIP."""
    caminho = Path(caminho)
    if not caminho.is_file():
        raise FileNotFoundError(
            f"arquivo da MMGD não encontrado: {caminho} "
            "(rode `uv run python scripts/baixar_gd.py` primeiro)"
        )
    if caminho.suffix.lower() == ".parquet":
        return pd.read_parquet(caminho, columns=list(COLUNAS_MMGD))
    if caminho.suffix.lower() == ".zip":
        return pd.read_csv(
            caminho, compression="zip", sep=";", encoding="utf-8", usecols=COLUNAS_MMGD
        )
    if caminho.suffix.lower() == ".csv":
        return pd.read_csv(caminho, sep=";", encoding="utf-8", usecols=COLUNAS_MMGD)
    raise ValueError(f"formato de MMGD não suportado: {caminho.suffix}")


def normalizar_mmgd(bruto: pd.DataFrame, *, distribuidora: str = "light") -> pd.DataFrame:
    """Filtra a distribuidora e normaliza campos relevantes da MMGD."""
    esperado = set(COLUNAS_MMGD)
    faltantes = sorted(esperado - set(bruto.columns))
    if faltantes:
        raise KeyError(f"colunas MMGD ausentes: {', '.join(faltantes)}")
    if distribuidora != "light":
        raise ValueError(f"distribuidora não suportada: {distribuidora}")

    df = bruto.copy()
    for coluna in (
        "NumCNPJDistribuidora",
        "SigAgente",
        "NomAgente",
        "CodClasseConsumo",
        "DscClasseConsumo",
        "CodSubGrupoTarifario",
        "DscSubGrupoTarifario",
        "SigUF",
        "NomRegiao",
        "NomMunicipio",
        "CodCEP",
        "SigTipoConsumidor",
        "NumCPFCNPJ",
        "CodEmpreendimento",
        "SigModalidadeEmpreendimento",
        "DscModalidadeHabilitado",
        "SigTipoGeracao",
        "DscFonteGeracao",
        "DscPorte",
        "NomSubEstacao",
        "NomTitularEmpreendimento",
    ):
        df[coluna] = df[coluna].map(_texto)

    df["DatGeracaoConjuntoDados"] = pd.to_datetime(
        df["DatGeracaoConjuntoDados"], errors="coerce"
    ).dt.date
    df["DthAtualizaCadastralEmpreend"] = pd.to_datetime(
        df["DthAtualizaCadastralEmpreend"], errors="coerce", dayfirst=False
    )
    for coluna in ("CodUFibge", "CodRegiao", "CodMunicipioIbge"):
        df[coluna] = pd.to_numeric(df[coluna], errors="coerce").astype("Int64")
    for coluna in ("QtdUCRecebeCredito",):
        df[coluna] = pd.to_numeric(df[coluna], errors="coerce").astype("Int64")
    for coluna in ("MdaPotenciaInstaladaKW", "NumCoordESub", "NumCoordNSub"):
        df[coluna] = pd.to_numeric(df[coluna], errors="coerce")

    filtro = (
        df["NumCNPJDistribuidora"].eq(CNPJ_LIGHT)
        & df["SigUF"].eq(UF_LIGHT)
        & df["NomAgente"].eq(AGENTE_LIGHT)
    )
    df = df.loc[filtro].copy()
    df["ano_conexao"] = df["DthAtualizaCadastralEmpreend"].dt.year.astype("Int64")
    df["fonte_normalizada"] = df.apply(_fonte_normalizada, axis=1)
    df["classe_normalizada"] = df.apply(_classe_normalizada, axis=1)
    df["subgrupo_normalizado"] = df["DscSubGrupoTarifario"].where(
        df["DscSubGrupoTarifario"].ne(""), "sem subgrupo"
    )
    df = df.rename(
        columns={
            "DatGeracaoConjuntoDados": "data_geracao_conjunto",
            "AnmPeriodoReferencia": "periodo_referencia",
            "NumCNPJDistribuidora": "cnpj_distribuidora",
            "SigAgente": "sigla_agente",
            "NomAgente": "nome_agente",
            "CodClasseConsumo": "cod_classe_consumo",
            "DscClasseConsumo": "classe_consumo",
            "CodSubGrupoTarifario": "cod_subgrupo_tarifario",
            "DscSubGrupoTarifario": "subgrupo_tarifario",
            "CodUFibge": "cod_uf_ibge",
            "SigUF": "uf",
            "CodRegiao": "cod_regiao",
            "NomRegiao": "regiao",
            "CodMunicipioIbge": "cod_municipio_ibge",
            "NomMunicipio": "municipio",
            "CodCEP": "cep",
            "SigTipoConsumidor": "tipo_consumidor",
            "NumCPFCNPJ": "cpf_cnpj_titular",
            "CodEmpreendimento": "cod_empreendimento",
            "DthAtualizaCadastralEmpreend": "data_atualizacao_cadastral",
            "SigModalidadeEmpreendimento": "sigla_modalidade",
            "DscModalidadeHabilitado": "modalidade",
            "QtdUCRecebeCredito": "qtd_uc_recebe_credito",
            "SigTipoGeracao": "sig_tipo_geracao",
            "DscFonteGeracao": "fonte_geracao",
            "DscPorte": "porte",
            "MdaPotenciaInstaladaKW": "potencia_kw",
            "NomSubEstacao": "subestacao",
            "NumCoordESub": "coord_e_sub",
            "NumCoordNSub": "coord_n_sub",
            "NomTitularEmpreendimento": "titular",
        }
    )
    return df.sort_values(["municipio", "cod_empreendimento"]).reset_index(drop=True)


def carregar_bdgd_gd(fonte: DiretorioParquet) -> pd.DataFrame:
    """Normaliza as tabelas `UGBT_tab` e `UGMT_tab` da BDGD."""
    tabelas = []
    for camada in ("UGBT_tab", "UGMT_tab"):
        df = fonte.ler(camada, COLUNAS_BDGD_GD).copy()
        if "UNI_TR_MT" not in df.columns:
            df["UNI_TR_MT"] = ""
        df["camada_bdgd"] = camada
        tabelas.append(df)
    bdgd = pd.concat(tabelas, ignore_index=True)
    for coluna in ("COD_ID", "CEG_GD", "CTMT", "UNI_TR_MT", "DAT_CON"):
        bdgd[coluna] = bdgd[coluna].map(_texto)
    bdgd["CONJ"] = bdgd["CONJ"].map(_codigo_texto)
    bdgd["MUN"] = pd.to_numeric(bdgd["MUN"], errors="coerce").astype("Int64")
    bdgd["POT_INST"] = pd.to_numeric(bdgd["POT_INST"], errors="coerce").fillna(0.0)
    bdgd["data_conexao_bdgd"] = pd.to_datetime(bdgd["DAT_CON"], errors="coerce", dayfirst=True)
    bdgd = bdgd.rename(
        columns={
            "COD_ID": "cod_id_bdgd",
            "CEG_GD": "ceg_gd",
            "CTMT": "ctmt",
            "UNI_TR_MT": "uni_tr_mt",
            "CONJ": "conj",
            "MUN": "cod_municipio_bdgd",
            "POT_INST": "potencia_kw_bdgd",
        }
    )
    bdgd["linhas_origem_duplicadas"] = bdgd.groupby(
        ["ceg_gd", "ctmt", "cod_id_bdgd"], dropna=False
    )["cod_id_bdgd"].transform("size")
    bdgd = bdgd.sort_values(["ceg_gd", "camada_bdgd"]).drop_duplicates(
        ["ceg_gd", "ctmt", "cod_id_bdgd"], keep="first"
    )
    return bdgd.reset_index(drop=True)


def comparar_por_chave(mmgd: pd.DataFrame, bdgd: pd.DataFrame) -> pd.DataFrame:
    """Compara MMGD e BDGD por `CodEmpreendimento ↔ CEG_GD`."""
    bdgd_chave = bdgd.loc[bdgd["ceg_gd"].ne("")].copy()
    agrupado = bdgd_chave.groupby("ceg_gd", sort=True)
    mapa = agrupado.agg(
        ctmt=("ctmt", _unicos_ordenados_texto),
        n_ctmt=("ctmt", "nunique"),
        conj=("conj", _unicos_ordenados_texto),
        cod_municipio_bdgd=("cod_municipio_bdgd", _primeiro_int),
        potencia_kw_bdgd=("potencia_kw_bdgd", "sum"),
        camadas_bdgd=("camada_bdgd", _unicos_ordenados_texto),
        codigos_bdgd=("cod_id_bdgd", _unicos_ordenados_texto),
    ).reset_index()
    mapa["duplicado_mesmo_ctmt"] = agrupado.size().reindex(mapa["ceg_gd"]).to_numpy() > 1
    comparativo = mmgd.merge(mapa, left_on="cod_empreendimento", right_on="ceg_gd", how="left")
    comparativo["status_juncao"] = "sem_match"
    comparativo.loc[comparativo["ceg_gd"].notna(), "status_juncao"] = "match_exato"
    comparativo.loc[comparativo["n_ctmt"].fillna(0) > 1, "status_juncao"] = "match_ambiguo"
    comparativo["delta_kw_mmgd_menos_bdgd"] = (
        comparativo["potencia_kw"] - comparativo["potencia_kw_bdgd"].fillna(0.0)
    ).round(6)
    return comparativo.sort_values(
        ["status_juncao", "municipio", "cod_empreendimento"]
    ).reset_index(drop=True)


def montar_evidencia_juncao(
    mmgd: pd.DataFrame, bdgd: pd.DataFrame, comparativo: pd.DataFrame
) -> EvidenciaJuncao:
    """Resume a evidência de junção e de ausência de chaves alternativas."""
    bdgd_match = bdgd["ceg_gd"].isin(set(mmgd["cod_empreendimento"]))
    mmgd_match = comparativo["status_juncao"] == "match_exato"
    n_amb = int((comparativo["status_juncao"] == "match_ambiguo").sum())
    bdgd_vazio = bdgd["ceg_gd"].eq("")
    ceg_duplicado_mesmo_ctmt = int(
        bdgd.loc[
            bdgd["ceg_gd"].ne("") & bdgd["linhas_origem_duplicadas"].fillna(1).gt(1),
            "ceg_gd",
        ].nunique()
    )
    return EvidenciaJuncao(
        chave_mmgd="CodEmpreendimento",
        chave_bdgd="CEG_GD",
        n_mmgd=int(len(mmgd)),
        kw_mmgd=float(mmgd["potencia_kw"].sum()),
        n_mmgd_com_match=int(mmgd_match.sum()),
        kw_mmgd_com_match=float(comparativo.loc[mmgd_match, "potencia_kw"].sum()),
        n_mmgd_sem_match=int((comparativo["status_juncao"] == "sem_match").sum()),
        kw_mmgd_sem_match=float(
            comparativo.loc[comparativo["status_juncao"] == "sem_match", "potencia_kw"].sum()
        ),
        n_bdgd=int(len(bdgd)),
        kw_bdgd=float(bdgd["potencia_kw_bdgd"].sum()),
        n_bdgd_com_match=int(bdgd_match.sum()),
        kw_bdgd_com_match=float(bdgd.loc[bdgd_match, "potencia_kw_bdgd"].sum()),
        n_bdgd_sem_match=int((~bdgd_match).sum()),
        kw_bdgd_sem_match=float(bdgd.loc[~bdgd_match, "potencia_kw_bdgd"].sum()),
        n_bdgd_ceg_vazio=int(bdgd_vazio.sum()),
        kw_bdgd_ceg_vazio=float(bdgd.loc[bdgd_vazio, "potencia_kw_bdgd"].sum()),
        n_ceg_ambiguos_multictmt=n_amb,
        n_ceg_duplicados_mesmo_ctmt=ceg_duplicado_mesmo_ctmt,
    )


def agregar_por_alimentador(match_exato: pd.DataFrame, alimentadores: pd.DataFrame) -> pd.DataFrame:
    """Agrega MMGD por alimentador usando só os matches exatos."""
    resumo = (
        match_exato.groupby("ctmt", sort=True)
        .apply(_resumo_grupo_match, include_groups=False)
        .reset_index()
        .rename(columns={"ctmt": "COD_ID"})
    )
    tabela = alimentadores.merge(resumo, on="COD_ID", how="left")
    for coluna in (
        "empreendimentos_mmgd",
        "potencia_kw_mmgd",
        "potencia_kw_bdgd_mesmas_chaves",
        "diferenca_kw_mmgd_menos_bdgd_mesmas_chaves",
    ):
        tabela[coluna] = tabela[coluna].fillna(
            0.0 if "potencia" in coluna or "diferenca" in coluna else 0
        )
    tabela["empreendimentos_mmgd"] = tabela["empreendimentos_mmgd"].fillna(0).astype("int64")
    tabela["fonte_predominante"] = tabela["fonte_predominante"].fillna("")
    tabela["classe_predominante"] = tabela["classe_predominante"].fillna("")
    tabela["subgrupo_predominante"] = tabela["subgrupo_predominante"].fillna("")
    tabela["periodo_primeira_data"] = tabela["periodo_primeira_data"].fillna("")
    tabela["periodo_ultima_data"] = tabela["periodo_ultima_data"].fillna("")
    tabela["penetracao_gd_pct"] = tabela.apply(
        lambda linha: _percentual(linha["potencia_kw_mmgd"], linha["kVA_instalado"]), axis=1
    )
    tabela["cobertura_vs_bdgd_pct"] = tabela.apply(
        lambda linha: (
            _percentual(linha["potencia_kw_mmgd"], linha["kW_DER"])
            if float(linha["kW_DER"]) > 0
            else 0.0
        ),
        axis=1,
    )
    tabela["diferenca_kw_mmgd_menos_bdgd_total"] = (
        tabela["potencia_kw_mmgd"] - tabela["kW_DER"]
    ).round(6)
    tabela["CONJ_CODIGO"] = tabela["CONJ_CODIGO"].fillna("")
    tabela["CONJ_NOME"] = tabela["CONJ_NOME"].fillna("")
    colunas = [
        "COD_ID",
        "NOME",
        "SUB",
        "SUB_NOME",
        "MUN",
        "CONJ_CODIGO",
        "CONJ_NOME",
        "kVA_instalado",
        "kW_DER",
        "n_DER",
        "empreendimentos_mmgd",
        "potencia_kw_mmgd",
        "potencia_kw_bdgd_mesmas_chaves",
        "diferenca_kw_mmgd_menos_bdgd_mesmas_chaves",
        "diferenca_kw_mmgd_menos_bdgd_total",
        "penetracao_gd_pct",
        "cobertura_vs_bdgd_pct",
        "fonte_predominante",
        "classe_predominante",
        "subgrupo_predominante",
        "periodo_primeira_data",
        "periodo_ultima_data",
    ]
    tabela = tabela[colunas].sort_values(
        ["potencia_kw_mmgd", "penetracao_gd_pct", "COD_ID"], ascending=[False, False, True]
    )
    return tabela.reset_index(drop=True)


def agregar_por_conjunto(alimentadores: pd.DataFrame) -> pd.DataFrame:
    """Agrega os matches exatos por conjunto."""
    base = alimentadores.loc[alimentadores["CONJ_CODIGO"].ne("")].copy()
    if base.empty:
        return pd.DataFrame(
            columns=[
                "CONJ_CODIGO",
                "CONJ_NOME",
                "alimentadores",
                "empreendimentos_mmgd",
                "potencia_kw_mmgd",
                "potencia_kw_bdgd_total",
                "kVA_instalado_total",
                "penetracao_gd_pct",
                "fonte_predominante",
            ]
        )
    linhas = []
    for (codigo, nome), grupo in base.groupby(["CONJ_CODIGO", "CONJ_NOME"], sort=True):
        linhas.append(
            {
                "CONJ_CODIGO": codigo,
                "CONJ_NOME": nome,
                "alimentadores": int(len(grupo)),
                "empreendimentos_mmgd": int(grupo["empreendimentos_mmgd"].sum()),
                "potencia_kw_mmgd": float(grupo["potencia_kw_mmgd"].sum()),
                "potencia_kw_bdgd_total": float(grupo["kW_DER"].sum()),
                "kVA_instalado_total": float(grupo["kVA_instalado"].sum()),
                "penetracao_gd_pct": _percentual(
                    float(grupo["potencia_kw_mmgd"].sum()), float(grupo["kVA_instalado"].sum())
                ),
                "fonte_predominante": _moda_ponderada(
                    grupo["fonte_predominante"], grupo["potencia_kw_mmgd"]
                ),
            }
        )
    return (
        pd.DataFrame(linhas)
        .sort_values(
            ["potencia_kw_mmgd", "penetracao_gd_pct", "CONJ_CODIGO"],
            ascending=[False, False, True],
        )
        .reset_index(drop=True)
    )


def agregar_sem_chave_por_municipio(
    sem_chave: pd.DataFrame, alimentadores: pd.DataFrame
) -> pd.DataFrame:
    """Agrega por município o saldo sem chave direta para alimentador."""
    candidatos = (
        alimentadores.groupby("MUN", sort=True)
        .agg(alimentadores_bdgd=("COD_ID", "nunique"), conjuntos_bdgd=("CONJ_CODIGO", "nunique"))
        .reset_index()
        .rename(columns={"MUN": "cod_municipio_ibge"})
    )
    sem = (
        sem_chave.groupby(["cod_municipio_ibge", "municipio"], sort=True)
        .agg(
            empreendimentos_sem_chave=("cod_empreendimento", "nunique"),
            potencia_kw_sem_chave=("potencia_kw", "sum"),
        )
        .reset_index()
    )
    sem = sem.merge(candidatos, on="cod_municipio_ibge", how="left")
    sem["alimentadores_bdgd"] = sem["alimentadores_bdgd"].fillna(0).astype("int64")
    sem["conjuntos_bdgd"] = sem["conjuntos_bdgd"].fillna(0).astype("int64")
    return sem.sort_values(
        ["potencia_kw_sem_chave", "empreendimentos_sem_chave", "municipio"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def agregar_evolucao_anual(mmgd: pd.DataFrame) -> pd.DataFrame:
    """Conta empreendimentos e potência por ano do único campo temporal disponível."""
    base = mmgd.loc[mmgd["ano_conexao"].notna()].copy()
    if base.empty:
        return pd.DataFrame(columns=["ano", "empreendimentos", "potencia_kw"])
    tabela = (
        base.groupby("ano_conexao", sort=True)
        .agg(empreendimentos=("cod_empreendimento", "nunique"), potencia_kw=("potencia_kw", "sum"))
        .reset_index()
        .rename(columns={"ano_conexao": "ano"})
    )
    return tabela.sort_values("ano").reset_index(drop=True)


def listar_divergencias(match_exato: pd.DataFrame, limite: int = 25) -> pd.DataFrame:
    """Lista as maiores divergências de potência entre MMGD e BDGD na mesma chave."""
    colunas = [
        "cod_empreendimento",
        "municipio",
        "ctmt",
        "potencia_kw",
        "potencia_kw_bdgd",
        "delta_kw_mmgd_menos_bdgd",
    ]
    base = match_exato.loc[match_exato["delta_kw_mmgd_menos_bdgd"].abs() > 0.001, colunas].copy()
    if base.empty:
        return base
    base = base.rename(
        columns={
            "cod_empreendimento": "CodEmpreendimento",
            "municipio": "Municipio",
            "ctmt": "CTMT",
            "potencia_kw": "PotenciaKW_MMGD",
            "potencia_kw_bdgd": "PotenciaKW_BDGD",
            "delta_kw_mmgd_menos_bdgd": "DeltaKW_MMGD_menos_BDGD",
        }
    )
    base["abs_delta_kw"] = base["DeltaKW_MMGD_menos_BDGD"].abs()
    base = base.sort_values(["abs_delta_kw", "CodEmpreendimento"], ascending=[False, True]).head(
        limite
    )
    return base.drop(columns=["abs_delta_kw"]).reset_index(drop=True)


def renderizar_markdown(resultado: ResultadoGd) -> str:
    """Renderiza `docs/gd-light.md` em Markdown."""
    evid = resultado.evidencia_juncao
    top_alimentadores = resultado.alimentadores.head(20).copy()
    top_conjuntos = resultado.conjuntos.head(15).copy()
    saldo_municipios = resultado.municipios_sem_chave.head(15).copy()
    divergencias = resultado.divergencias.head(15).copy()
    top_alimentadores["penetracao_gd_pct"] = top_alimentadores["penetracao_gd_pct"].map(_fmt_pct)
    top_alimentadores["cobertura_vs_bdgd_pct"] = top_alimentadores["cobertura_vs_bdgd_pct"].map(
        _fmt_pct
    )
    top_conjuntos["penetracao_gd_pct"] = top_conjuntos["penetracao_gd_pct"].map(_fmt_pct)

    linhas = [
        "# GD na Light a partir da MMGD ANEEL",
        "",
        "Relatório gerado por `scripts/gerar_gd_light.py` a partir da MMGD pública da ANEEL e de",
        "`data/parquet` da BDGD Light.",
        "",
        "## 1. Fonte usada nesta execução",
        "",
        (f"- Extraído em (`data/gd/metadata.json`): **{resultado.extraido_em or '—'}**."),
        (
            f"- Distribuidora filtrada: **{resultado.distribuidora}** "
            f"(`NumCNPJDistribuidora = {CNPJ_LIGHT}`, `SigUF = {UF_LIGHT}`)."
        ),
        (
            "- Data de geração do conjunto MMGD (`DatGeracaoConjuntoDados`): "
            f"**{resultado.data_geracao_conjunto or '—'}**."
        ),
        (
            "- Período de referência (`AnmPeriodoReferencia`): "
            f"**{resultado.periodo_referencia or '—'}**."
        ),
        (
            f"- Linhas MMGD Light filtradas: **{_fmt_int(evid.n_mmgd)}** empreendimentos, "
            f"**{_fmt_num(evid.kw_mmgd)} kW**."
        ),
        "",
        "Campos do dicionário PDF v2.3 efetivamente usados no pipeline:",
        "",
        "- junção: `CodEmpreendimento` (MMGD) ↔ `CEG_GD` (BDGD `UGBT_tab` / `UGMT_tab`);",
        "- potência: `MdaPotenciaInstaladaKW` (MMGD) e `POT_INST` (BDGD);",
        "- classe/subgrupo: `DscClasseConsumo`, `DscSubGrupoTarifario`;",
        "- fonte: `SigTipoGeracao`, `DscFonteGeracao`;",
        "- campo temporal disponível: `DthAtualizaCadastralEmpreend`.",
        "",
        f"> {resultado.observacao_data}",
        "",
        "## 2. Chave de junção encontrada — e onde ela não basta",
        "",
        "- **Há chave direta** para boa parte da base: `CodEmpreendimento` ↔ `CEG_GD`.",
        (
            f"- Matches exatos MMGD → BDGD: **{_fmt_int(evid.n_mmgd_com_match)} / "
            f"{_fmt_int(evid.n_mmgd)} = "
            f"{_fmt_pct(_percentual(evid.n_mmgd_com_match, evid.n_mmgd))}**, "
            f"cobrindo **{_fmt_num(evid.kw_mmgd_com_match)} / {_fmt_num(evid.kw_mmgd)} "
            f"kW = {_fmt_pct(_percentual(evid.kw_mmgd_com_match, evid.kw_mmgd))}**."
        ),
        (
            f"- Sem match direto na MMGD: **{_fmt_int(evid.n_mmgd_sem_match)}** "
            f"empreendimentos e **{_fmt_num(evid.kw_mmgd_sem_match)} kW**."
        ),
        (
            f"- Linhas BDGD sem `CEG_GD` preenchido: **{_fmt_int(evid.n_bdgd_ceg_vazio)}**, "
            f"somando **{_fmt_num(evid.kw_bdgd_ceg_vazio)} kW**."
        ),
        (
            "- CEGs repetidos no mesmo CTMT "
            f"(anomalia BT/MT da própria BDGD): **{_fmt_int(evid.n_ceg_duplicados_mesmo_ctmt)}**."
        ),
        f"- CEGs apontando para mais de um CTMT: **{_fmt_int(evid.n_ceg_ambiguos_multictmt)}**.",
        "",
        "Evidência negativa importante: o arquivo MMGD **não traz** `CTMT`, `UNI_TR_MT`,",
        "código da UC beneficiária ou outro identificador elétrico fino. Quando",
        "`CodEmpreendimento` não casa com `CEG_GD`, a agregação honesta restante é",
        "**por município**; qualquer rateio por alimentador",
        "seria inventar precisão que o dado não oferece.",
        "",
        "## 3. Divergência global entre MMGD e BDGD",
        "",
        (
            "- BDGD (`UGBT_tab` + `UGMT_tab`, após deduplicar repetição idêntica BT/MT): "
            f"**{_fmt_int(evid.n_bdgd)}** linhas, **{_fmt_num(evid.kw_bdgd)} kW**."
        ),
        (
            "- BDGD com `CEG_GD` presente também na MMGD: "
            f"**{_fmt_int(evid.n_bdgd_com_match)}** linhas, "
            f"**{_fmt_num(evid.kw_bdgd_com_match)} kW**."
        ),
        (
            "- BDGD sem correspondência na MMGD (inclui `CEG_GD` vazio): "
            f"**{_fmt_int(evid.n_bdgd_sem_match)}** linhas, "
            f"**{_fmt_num(evid.kw_bdgd_sem_match)} kW**."
        ),
        "",
        "Essa divergência é, ela própria, um resultado sobre defasagem e qualidade",
        "cadastral entre a",
        "foto anual da BDGD e a base MMGD mais recente.",
        "",
        "## 4. Potência por alimentador (somente matches exatos)",
        "",
        "A tabela abaixo mostra onde a junção é direta. `penetração_gd_pct = potência MMGD exata ÷",
        "carga instalada do alimentador (kVA_instalado da BDGD)`.",
        "",
        _markdown_tabela(
            top_alimentadores,
            [
                "COD_ID",
                "NOME",
                "CONJ_NOME",
                "empreendimentos_mmgd",
                "potencia_kw_mmgd",
                "kW_DER",
                "penetracao_gd_pct",
                "fonte_predominante",
            ],
        ),
        "",
        "## 5. Potência por conjunto (somente matches exatos)",
        "",
        _markdown_tabela(
            top_conjuntos,
            [
                "CONJ_CODIGO",
                "CONJ_NOME",
                "alimentadores",
                "empreendimentos_mmgd",
                "potencia_kw_mmgd",
                "potencia_kw_bdgd_total",
                "penetracao_gd_pct",
                "fonte_predominante",
            ],
        ),
        "",
        "## 6. Evolução anual pelo campo temporal disponível",
        "",
        _markdown_tabela(resultado.evolucao_anual, ["ano", "empreendimentos", "potencia_kw"]),
        "",
        "## 7. Saldo sem chave direta — agregado só onde o dado permite",
        "",
        _markdown_tabela(
            saldo_municipios,
            [
                "cod_municipio_ibge",
                "municipio",
                "empreendimentos_sem_chave",
                "potencia_kw_sem_chave",
                "alimentadores_bdgd",
                "conjuntos_bdgd",
            ],
        ),
        "",
        "## 8. Maiores divergências de potência na mesma chave",
        "",
        _markdown_tabela(
            divergencias,
            [
                "CodEmpreendimento",
                "Municipio",
                "CTMT",
                "PotenciaKW_MMGD",
                "PotenciaKW_BDGD",
                "DeltaKW_MMGD_menos_BDGD",
            ],
        ),
        "",
        "## 9. Arquivos auxiliares versionados",
        "",
        "- `docs/dados/gd-light-alimentadores.csv`",
        "- `docs/dados/gd-light-conjuntos.csv`",
        "- `docs/dados/gd-light-evolucao-anual.csv`",
        "- `docs/dados/gd-light-municipios-sem-chave.csv`",
        "- `docs/dados/gd-light-divergencias.csv`",
        "",
        "## 10. Reprodução",
        "",
        "```bash",
        "uv run python scripts/baixar_gd.py",
        "uv run python scripts/gerar_gd_light.py \\",
        "  --mmgd data/gd/empreendimento-geracao-distribuida.parquet \\",
        "  --parquet-dir data/parquet \\",
        "  --out docs/gd-light.md",
        "```",
        "",
    ]
    return "\n".join(linhas)


def escrever_resultado(
    resultado: ResultadoGd,
    *,
    out_markdown: Path,
    out_alimentadores_csv: Path,
    out_conjuntos_csv: Path,
    out_evolucao_csv: Path,
    out_municipios_sem_chave_csv: Path,
    out_divergencias_csv: Path,
) -> None:
    """Escreve o relatório Markdown e os CSVs auxiliares."""
    artefatos = (
        (out_markdown, renderizar_markdown(resultado)),
        (out_alimentadores_csv, resultado.alimentadores.to_csv(index=False)),
        (out_conjuntos_csv, resultado.conjuntos.to_csv(index=False)),
        (out_evolucao_csv, resultado.evolucao_anual.to_csv(index=False)),
        (out_municipios_sem_chave_csv, resultado.municipios_sem_chave.to_csv(index=False)),
        (out_divergencias_csv, resultado.divergencias.to_csv(index=False)),
    )
    for caminho, conteudo in artefatos:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(conteudo, encoding="utf-8")


def _resumo_grupo_match(grupo: pd.DataFrame) -> pd.Series:
    dados = grupo.copy()
    dados = dados.drop_duplicates("cod_empreendimento")
    inicio = dados["data_atualizacao_cadastral"].min()
    fim = dados["data_atualizacao_cadastral"].max()
    return pd.Series(
        {
            "empreendimentos_mmgd": int(dados["cod_empreendimento"].nunique()),
            "potencia_kw_mmgd": float(dados["potencia_kw"].sum()),
            "potencia_kw_bdgd_mesmas_chaves": float(dados["potencia_kw_bdgd"].sum()),
            "diferenca_kw_mmgd_menos_bdgd_mesmas_chaves": float(
                dados["potencia_kw"].sum() - dados["potencia_kw_bdgd"].sum()
            ),
            "fonte_predominante": _moda_ponderada(dados["fonte_normalizada"], dados["potencia_kw"]),
            "classe_predominante": _moda_ponderada(
                dados["classe_normalizada"], dados["potencia_kw"]
            ),
            "subgrupo_predominante": _moda_ponderada(
                dados["subgrupo_normalizado"], dados["potencia_kw"]
            ),
            "periodo_primeira_data": _fmt_data(inicio),
            "periodo_ultima_data": _fmt_data(fim),
        }
    )


def _mapa_conjuntos_ctmt(fonte: DiretorioParquet) -> dict[str, str]:
    contagens: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for camada in ("UCBT_tab", "UCMT_tab", "UGBT_tab", "UGMT_tab", "UNTRMT"):
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
            for ctmt, conjunto in zip(ctmts[mascara], conjuntos[mascara], strict=False):
                contagens[ctmt][conjunto] += 1
    return {
        ctmt: sorted(contador.items(), key=lambda item: (-item[1], item[0]))[0][0]
        for ctmt, contador in contagens.items()
        if contador
    }


def _mapa_nomes_conjuntos(fonte: DiretorioParquet) -> dict[str, str]:
    conj = fonte.ler_se_existir("CONJ", ["COD_ID", "NOME"])
    if conj is None or conj.empty:
        return {}
    return (
        conj.assign(COD_ID=conj["COD_ID"].map(_codigo_texto), NOME=conj["NOME"].map(_texto))
        .drop_duplicates("COD_ID")
        .set_index("COD_ID")["NOME"]
        .to_dict()
    )


def _fonte_normalizada(linha: pd.Series) -> str:
    sigla = _texto(linha.get("SigTipoGeracao"))
    descricao = _texto(linha.get("DscFonteGeracao"))
    if sigla and descricao:
        return f"{sigla} — {descricao}"
    return sigla or descricao or "não informada"


def _classe_normalizada(linha: pd.Series) -> str:
    classe = _texto(linha.get("DscClasseConsumo"))
    codigo = _texto(linha.get("CodClasseConsumo"))
    if classe and codigo:
        return f"{classe} ({codigo})"
    return classe or codigo or "não informada"


def _moda_ponderada(valores: pd.Series, pesos: pd.Series) -> str:
    acumulado: Counter[str] = Counter()
    for valor, peso in zip(valores.fillna("").astype(str), pesos.fillna(0.0), strict=False):
        valor = valor.strip()
        if not valor:
            continue
        acumulado[valor] += float(peso)
    if not acumulado:
        return ""
    return sorted(acumulado.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _markdown_tabela(df: pd.DataFrame, colunas: list[str]) -> str:
    if df.empty:
        return "_Sem linhas para mostrar._"
    cabecalho = "| " + " | ".join(colunas) + " |"
    separador = "|" + "|".join(["---"] * len(colunas)) + "|"
    linhas = [cabecalho, separador]
    for _, linha in df[colunas].iterrows():
        valores = [_fmt_valor_tabela(linha[coluna]) for coluna in colunas]
        linhas.append("| " + " | ".join(valores) + " |")
    return "\n".join(linhas)


def _fmt_valor_tabela(valor: object) -> str:
    if valor is None or pd.isna(valor):
        return ""
    if isinstance(valor, float):
        return _fmt_num(valor)
    return str(valor).replace("|", r"\|").replace("\n", "<br>")


def _fmt_int(valor: int | float) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _fmt_num(valor: float) -> str:
    return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_pct(valor: float) -> str:
    return f"{float(valor):.2f} %".replace(".", ",")


def _fmt_data(valor: object) -> str:
    if valor is None or pd.isna(valor):
        return ""
    try:
        return pd.Timestamp(valor).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return _texto(valor)


def _percentual(parte: float | int, total: float | int) -> float:
    if not total:
        return 0.0
    return float(parte) * 100.0 / float(total)


def _texto(valor: object) -> str:
    if valor is None or pd.isna(valor):
        return ""
    return str(valor).strip()


def _codigo_texto(valor: object) -> str:
    if valor is None or pd.isna(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def _unicos_ordenados_texto(valores: pd.Series) -> str:
    itens = sorted({_texto(valor) for valor in valores if _texto(valor)})
    return ";".join(itens)


def _primeiro_texto(valores: pd.Series) -> str:
    for valor in valores:
        texto = _texto(valor)
        if texto:
            return texto
    return ""


def _primeiro_int(valores: pd.Series) -> int | pd.NA:
    for valor in valores:
        if valor is None or pd.isna(valor):
            continue
        return int(valor)
    return pd.NA


def _carregar_extraido_em(caminho_mmgd: Path) -> str:
    metadata_path = Path(caminho_mmgd).parent / "metadata.json"
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            metadata = {}
        extraido_em = _texto(metadata.get("extraido_em"))
        if extraido_em:
            return extraido_em
    return pd.Timestamp(Path(caminho_mmgd).stat().st_mtime, unit="s").isoformat(timespec="seconds")
