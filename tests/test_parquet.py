"""Testes de ``bdgd_light.ingest.parquet`` (leitor das camadas exportadas)."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest

from bdgd_light.ingest.parquet import CamadaAusenteError, DiretorioParquet, filtro_in


@pytest.fixture(scope="module")
def fonte(parquet_mini) -> DiretorioParquet:
    return DiretorioParquet(parquet_mini)


def test_camadas_tipo_e_colunas(fonte):
    assert {"CTMT", "SSDMT", "UCBT_tab", "PONNOT"} <= set(fonte.camadas())
    assert fonte.tem("SSDMT") and not fonte.tem("NAO_EXISTE")
    assert fonte.eh_geografica("SSDMT") and not fonte.eh_geografica("CTMT")
    assert {"COD_ID", "CTMT", "PAC_1", "PAC_2", "geometry"} <= set(fonte.colunas("SSDMT"))


def test_ler_geografica_e_tabela_com_colunas_e_filtro(fonte):
    trechos = fonte.ler("SSDMT", ["COD_ID", "CTMT", "NAO_EXISTE"], filtro_in("CTMT", ["RJO003"]))
    assert isinstance(trechos, gpd.GeoDataFrame) and trechos.crs.to_epsg() == 4674
    assert list(trechos.columns) == ["COD_ID", "CTMT", "geometry"]  # coluna inexistente ignorada
    assert trechos["COD_ID"].tolist() == ["SEG009"]
    ctmt = fonte.ler("CTMT", ["COD_ID", "NOME"], filtro_in("COD_ID", ["RJO002", "RJO001"]))
    assert isinstance(ctmt, pd.DataFrame) and not isinstance(ctmt, gpd.GeoDataFrame)
    assert sorted(ctmt["COD_ID"]) == ["RJO001", "RJO002"]


def test_filtro_in_vazio_devolve_camada_vazia_com_schema(fonte):
    # regressão: conjunto vazio era inferido como ``null`` pelo pyarrow ("Array type doesn't match
    # type of values set") — acontecia no recorte de CTMT sem UNREMT ao filtrar EQRE
    trechos = fonte.ler("SSDMT", filtros=filtro_in("CTMT", []))
    assert isinstance(trechos, gpd.GeoDataFrame) and trechos.empty
    assert trechos.crs.to_epsg() == 4674 and list(trechos.columns) == fonte.colunas("SSDMT")
    ucs = fonte.ler("UCBT_tab", ["COD_ID", "UNI_TR_MT"], filtro_in("UNI_TR_MT", set()))
    assert ucs.empty and list(ucs.columns) == ["COD_ID", "UNI_TR_MT"]
    assert fonte.ler("CTMT", filtros=filtro_in("COD_ID", ["NAO_EXISTE"])).empty


def test_ler_se_existir_e_erro_de_camada_ausente(fonte, tmp_path):
    assert fonte.ler_se_existir("NAO_EXISTE") is None
    with pytest.raises(CamadaAusenteError, match="NAO_EXISTE"):
        fonte.ler("NAO_EXISTE")
    with pytest.raises(FileNotFoundError, match="não encontrado"):
        DiretorioParquet(tmp_path / "nada")


def test_iterar_lotes(fonte):
    lotes = list(fonte.iterar_lotes("UCBT_tab", ["COD_ID", "ENE_01", "NAO_EXISTE"], tamanho=3))
    assert [len(lote) for lote in lotes] == [3, 3, 1]
    assert all(list(lote.columns) == ["COD_ID", "ENE_01"] for lote in lotes)
    assert sorted(pd.concat(lotes)["COD_ID"])[0] == "UC00001"
    with pytest.raises(CamadaAusenteError):
        list(fonte.iterar_lotes("NAO_EXISTE"))
