"""Testes da ingestão de MMGD da ANEEL cruzada com a BDGD Light."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

from bdgd_light.ingest.gd import (
    AGENTE_LIGHT,
    CNPJ_LIGHT,
    SIGLA_LIGHT,
    ConfiguracaoGd,
    analisar_gd,
    normalizar_mmgd,
    renderizar_markdown,
)


def escrever_mmgd_sintetica(destino: Path) -> Path:
    dados = [
        {
            "DatGeracaoConjuntoDados": "2026-09-11",
            "AnmPeriodoReferencia": "09/2026",
            "NumCNPJDistribuidora": CNPJ_LIGHT,
            "SigAgente": SIGLA_LIGHT,
            "NomAgente": AGENTE_LIGHT,
            "CodClasseConsumo": "RE",
            "DscClasseConsumo": "Residencial",
            "CodSubGrupoTarifario": "B1",
            "DscSubGrupoTarifario": "B1",
            "CodUFibge": "33",
            "SigUF": "RJ",
            "CodRegiao": "3301",
            "NomRegiao": "Metropolitana",
            "CodMunicipioIbge": "3304557",
            "NomMunicipio": "Rio de Janeiro",
            "CodCEP": "20000000",
            "SigTipoConsumidor": "PF",
            "NumCPFCNPJ": "***",
            "CodEmpreendimento": "GD.RJ.UGBT001",
            "DthAtualizaCadastralEmpreend": "2022-05-01",
            "SigModalidadeEmpreendimento": "",
            "DscModalidadeHabilitado": "Geracao na propria UC",
            "QtdUCRecebeCredito": 1,
            "SigTipoGeracao": "UFV",
            "DscFonteGeracao": "Radiação solar",
            "DscPorte": "Microgeracao",
            "MdaPotenciaInstaladaKW": 5.0,
            "NomSubEstacao": "SE001",
            "NumCoordESub": -43.2,
            "NumCoordNSub": -22.9,
            "NomTitularEmpreendimento": "***",
        },
        {
            "DatGeracaoConjuntoDados": "2026-09-11",
            "AnmPeriodoReferencia": "09/2026",
            "NumCNPJDistribuidora": CNPJ_LIGHT,
            "SigAgente": SIGLA_LIGHT,
            "NomAgente": AGENTE_LIGHT,
            "CodClasseConsumo": "CO",
            "DscClasseConsumo": "Comercial",
            "CodSubGrupoTarifario": "B3",
            "DscSubGrupoTarifario": "B3",
            "CodUFibge": "33",
            "SigUF": "RJ",
            "CodRegiao": "3301",
            "NomRegiao": "Metropolitana",
            "CodMunicipioIbge": "3304557",
            "NomMunicipio": "Rio de Janeiro",
            "CodCEP": "20000000",
            "SigTipoConsumidor": "PJ",
            "NumCPFCNPJ": "***",
            "CodEmpreendimento": "GD.RJ.UGMT001",
            "DthAtualizaCadastralEmpreend": "2022-05-01",
            "SigModalidadeEmpreendimento": "",
            "DscModalidadeHabilitado": "Geracao na propria UC",
            "QtdUCRecebeCredito": 1,
            "SigTipoGeracao": "UFV",
            "DscFonteGeracao": "Radiação solar",
            "DscPorte": "Minigeracao",
            "MdaPotenciaInstaladaKW": 500.0,
            "NomSubEstacao": "SE001",
            "NumCoordESub": -43.2,
            "NumCoordNSub": -22.9,
            "NomTitularEmpreendimento": "EMPRESA A",
        },
        {
            "DatGeracaoConjuntoDados": "2026-09-11",
            "AnmPeriodoReferencia": "09/2026",
            "NumCNPJDistribuidora": CNPJ_LIGHT,
            "SigAgente": SIGLA_LIGHT,
            "NomAgente": AGENTE_LIGHT,
            "CodClasseConsumo": "RE",
            "DscClasseConsumo": "Residencial",
            "CodSubGrupoTarifario": "B1",
            "DscSubGrupoTarifario": "B1",
            "CodUFibge": "33",
            "SigUF": "RJ",
            "CodRegiao": "3301",
            "NomRegiao": "Metropolitana",
            "CodMunicipioIbge": "3304557",
            "NomMunicipio": "Rio de Janeiro",
            "CodCEP": "20000000",
            "SigTipoConsumidor": "PF",
            "NumCPFCNPJ": "***",
            "CodEmpreendimento": "GD.RJ.UGBT002",
            "DthAtualizaCadastralEmpreend": "2022-05-01",
            "SigModalidadeEmpreendimento": "",
            "DscModalidadeHabilitado": "Geracao na propria UC",
            "QtdUCRecebeCredito": 1,
            "SigTipoGeracao": "UFV",
            "DscFonteGeracao": "Radiação solar",
            "DscPorte": "Microgeracao",
            "MdaPotenciaInstaladaKW": 10.0,
            "NomSubEstacao": "SE001",
            "NumCoordESub": -43.2,
            "NumCoordNSub": -22.9,
            "NomTitularEmpreendimento": "***",
        },
        {
            "DatGeracaoConjuntoDados": "2026-09-11",
            "AnmPeriodoReferencia": "09/2026",
            "NumCNPJDistribuidora": CNPJ_LIGHT,
            "SigAgente": SIGLA_LIGHT,
            "NomAgente": AGENTE_LIGHT,
            "CodClasseConsumo": "RE",
            "DscClasseConsumo": "Residencial",
            "CodSubGrupoTarifario": "B1",
            "DscSubGrupoTarifario": "B1",
            "CodUFibge": "33",
            "SigUF": "RJ",
            "CodRegiao": "3301",
            "NomRegiao": "Metropolitana",
            "CodMunicipioIbge": "3304557",
            "NomMunicipio": "Rio de Janeiro",
            "CodCEP": "20000000",
            "SigTipoConsumidor": "PF",
            "NumCPFCNPJ": "***",
            "CodEmpreendimento": "GD.RJ.SEM.MATCH",
            "DthAtualizaCadastralEmpreend": "2024-07-10",
            "SigModalidadeEmpreendimento": "",
            "DscModalidadeHabilitado": "Geracao na propria UC",
            "QtdUCRecebeCredito": 1,
            "SigTipoGeracao": "UFV",
            "DscFonteGeracao": "Radiação solar",
            "DscPorte": "Microgeracao",
            "MdaPotenciaInstaladaKW": 7.5,
            "NomSubEstacao": "",
            "NumCoordESub": None,
            "NumCoordNSub": None,
            "NomTitularEmpreendimento": "***",
        },
        {
            "DatGeracaoConjuntoDados": "2026-09-11",
            "AnmPeriodoReferencia": "09/2026",
            "NumCNPJDistribuidora": "00000000000000",
            "SigAgente": "OUTRA",
            "NomAgente": "OUTRA DISTRIBUIDORA",
            "CodClasseConsumo": "RE",
            "DscClasseConsumo": "Residencial",
            "CodSubGrupoTarifario": "B1",
            "DscSubGrupoTarifario": "B1",
            "CodUFibge": "33",
            "SigUF": "RJ",
            "CodRegiao": "3301",
            "NomRegiao": "Metropolitana",
            "CodMunicipioIbge": "3304557",
            "NomMunicipio": "Rio de Janeiro",
            "CodCEP": "20000000",
            "SigTipoConsumidor": "PF",
            "NumCPFCNPJ": "***",
            "CodEmpreendimento": "GD.RJ.FORA",
            "DthAtualizaCadastralEmpreend": "2024-07-10",
            "SigModalidadeEmpreendimento": "",
            "DscModalidadeHabilitado": "Geracao na propria UC",
            "QtdUCRecebeCredito": 1,
            "SigTipoGeracao": "UFV",
            "DscFonteGeracao": "Radiação solar",
            "DscPorte": "Microgeracao",
            "MdaPotenciaInstaladaKW": 99.0,
            "NomSubEstacao": "",
            "NumCoordESub": None,
            "NumCoordNSub": None,
            "NomTitularEmpreendimento": "***",
        },
    ]
    caminho = destino / "mmgd.parquet"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(dados).to_parquet(caminho, index=False)
    return caminho


def carregar_script(nome: str) -> object:
    spec = importlib.util.spec_from_file_location(nome, Path("scripts") / f"{nome}.py")
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_normaliza_e_filtra_light(tmp_path):
    caminho = escrever_mmgd_sintetica(tmp_path)
    bruto = pd.read_parquet(caminho)

    filtrado = normalizar_mmgd(bruto)

    assert len(filtrado) == 4
    assert set(filtrado["cod_empreendimento"]) == {
        "GD.RJ.SEM.MATCH",
        "GD.RJ.UGBT001",
        "GD.RJ.UGBT002",
        "GD.RJ.UGMT001",
    }
    assert filtrado["potencia_kw"].sum() == 522.5
    assert filtrado["fonte_normalizada"].nunique() == 1
    assert filtrado["classe_normalizada"].str.contains("Residencial").any()


def test_analisa_juncao_e_agregacoes(parquet_mini: Path, tmp_path):
    mmgd = escrever_mmgd_sintetica(tmp_path)

    resultado = analisar_gd(ConfiguracaoGd(parquet_dir=parquet_mini, mmgd_path=mmgd))

    assert resultado.evidencia_juncao.n_mmgd == 4
    assert resultado.evidencia_juncao.n_mmgd_com_match == 3
    assert resultado.evidencia_juncao.n_mmgd_sem_match == 1
    assert resultado.evidencia_juncao.kw_mmgd_sem_match == 7.5

    alimentadores = resultado.alimentadores.set_index("COD_ID")
    assert alimentadores.loc["RJO001", "empreendimentos_mmgd"] == 2
    assert alimentadores.loc["RJO001", "potencia_kw_mmgd"] == 505.0
    assert alimentadores.loc["RJO002", "potencia_kw_mmgd"] == 10.0
    assert alimentadores.loc["RJO003", "potencia_kw_mmgd"] == 0.0
    assert alimentadores.loc["RJO001", "fonte_predominante"] == "UFV — Radiação solar"

    assert list(resultado.evolucao_anual["ano"]) == [2022, 2024]
    assert resultado.municipios_sem_chave.loc[0, "empreendimentos_sem_chave"] == 1


def test_renderizacao_markdown_deterministica(parquet_mini: Path, tmp_path):
    mmgd = escrever_mmgd_sintetica(tmp_path)
    resultado = analisar_gd(ConfiguracaoGd(parquet_dir=parquet_mini, mmgd_path=mmgd))

    md1 = renderizar_markdown(resultado)
    md2 = renderizar_markdown(resultado)

    assert md1 == md2
    assert "CodEmpreendimento" in md1
    assert "arquivo MMGD **não traz** `CTMT`, `UNI_TR_MT`" in md1
    assert "GD.RJ.SEM.MATCH" not in md1


def test_scripts_geram_artefatos(parquet_mini: Path, tmp_path, monkeypatch):
    mmgd = escrever_mmgd_sintetica(tmp_path / "dados")
    gerar = carregar_script("gerar_gd_light")
    baixar = carregar_script("baixar_gd")

    out_md = tmp_path / "docs" / "gd-light.md"
    out_dados = tmp_path / "docs" / "dados"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "gerar_gd_light.py",
            "--parquet-dir",
            str(parquet_mini),
            "--mmgd",
            str(mmgd),
            "--out",
            str(out_md),
            "--out-alimentadores",
            str(out_dados / "alimentadores.csv"),
            "--out-conjuntos",
            str(out_dados / "conjuntos.csv"),
            "--out-evolucao",
            str(out_dados / "evolucao.csv"),
            "--out-municipios-sem-chave",
            str(out_dados / "municipios.csv"),
            "--out-divergencias",
            str(out_dados / "divergencias.csv"),
        ],
    )
    gerar.main()

    assert out_md.exists()
    assert (out_dados / "alimentadores.csv").exists()
    assert (out_dados / "conjuntos.csv").exists()
    assert (out_dados / "evolucao.csv").exists()
    assert (out_dados / "municipios.csv").exists()
    assert (out_dados / "divergencias.csv").exists()

    metadados = baixar.coletar_metadados_dado(mmgd)
    assert metadados["data_geracao_conjunto"] == ["2026-09-11"]
    assert metadados["periodo_referencia"] == ["09/2026"]
