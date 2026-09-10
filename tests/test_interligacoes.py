"""Testes da detecção geométrica de interligações (``bdgd_light.ingest.interligacoes``)."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import MultiLineString, Point

from bdgd_light.ingest.interligacoes import (
    COLUNAS_INTERLIGACAO,
    contar_por_ctmt,
    crs_metrico,
    detectar_interligacoes,
    extremidades,
    vizinhos_de,
)


@pytest.fixture(scope="module")
def camadas(bdgd_mini):
    ler = lambda camada: gpd.read_file(bdgd_mini, layer=camada, engine="pyogrio")  # noqa: E731
    return {"UNSEMT": ler("UNSEMT"), "SSDMT": ler("SSDMT"), "SUB": ler("SUB")}


def test_fixture_nao_compartilha_pac_entre_ctmt(camadas):
    """A interligação não aparece por PAC: cada CTMT numera os seus (como na Light)."""
    trechos = camadas["SSDMT"]
    pacs_por_ctmt = {ctmt: set(g["PAC_1"]) | set(g["PAC_2"]) for ctmt, g in trechos.groupby("CTMT")}
    for a in pacs_por_ctmt:
        for b in pacs_por_ctmt:
            if a != b:
                assert not pacs_por_ctmt[a] & pacs_por_ctmt[b]
    na = camadas["UNSEMT"].query("P_N_OPE == 'A'")
    for _, chave in na.iterrows():
        outros = set().union(*(p for c, p in pacs_por_ctmt.items() if c != chave["CTMT"]))
        assert chave["PAC_1"] not in outros and chave["PAC_2"] not in outros


def test_detecta_ties_a_ate_2m_de_extremidade_de_outro_ctmt(camadas):
    ties = detectar_interligacoes(camadas["UNSEMT"], camadas["SSDMT"], sub=camadas["SUB"])
    assert list(ties.columns) == [*COLUNAS_INTERLIGACAO, "geometry"]
    assert ties.crs.to_epsg() == 4674
    esperado = pd.DataFrame(
        {
            "COD_ID": ["CH003", "CH005", "CH007"],
            "CTMT": ["RJO001", "RJO002", "RJO002"],
            "CTMT_VIZ": ["RJO002", "RJO001", "RJO001"],
            "SSDMT_VIZ": ["SEG007", "SEG006", "SEG001"],
            "PAC_VIZ": ["RJO002_MT_5", "RJO001_MT_6", "RJO001_MT_1"],
            "TLCD": [1, 0, 1],
            "TIP_UNID": ["32", "19", "29"],
            "EM_SUB": [False, False, True],
        }
    )
    pd.testing.assert_frame_equal(
        ties[esperado.columns].reset_index(drop=True), esperado, check_dtype=False
    )
    assert ties["DIST_M"].tolist() == pytest.approx([1.03, 1.11, 1.03], abs=0.05)
    assert (ties["P_N_OPE"] == "A").all()
    # a geometria é a da chave
    chaves = camadas["UNSEMT"].set_index("COD_ID")
    for _, tie in ties.iterrows():
        assert tie.geometry.equals(chaves.loc[tie["COD_ID"], "geometry"])


def test_na_sem_vizinho_e_nf_nao_sao_interligacao(camadas):
    ties = detectar_interligacoes(camadas["UNSEMT"], camadas["SSDMT"])
    assert "CH006" not in set(ties["COD_ID"])  # NA telecomandada, mas longe de outro CTMT
    assert not set(ties["COD_ID"]) & {"CH001", "CH002", "CH004"}  # NF
    assert ties["EM_SUB"].tolist() == [False, False, False]  # sem SUB, ninguém está "na SE"


def test_raio_controla_a_deteccao(camadas):
    assert detectar_interligacoes(camadas["UNSEMT"], camadas["SSDMT"], raio_m=0.5).empty
    assert len(detectar_interligacoes(camadas["UNSEMT"], camadas["SSDMT"], raio_m=1.05)) == 2
    # com 50 m a CH006 (a ~22 m do fim de SEG008, de RJO002) passaria a contar — daí o raio de 2 m
    largo = detectar_interligacoes(camadas["UNSEMT"], camadas["SSDMT"], raio_m=50)
    assert sorted(largo["COD_ID"]) == ["CH003", "CH005", "CH006", "CH007"]


def test_um_candidato_por_par_chave_vizinho_com_a_extremidade_mais_proxima():
    ssdmt = gpd.GeoDataFrame(
        {
            "COD_ID": ["A1", "B1", "B2", "C1"],
            "CTMT": ["A", "B", "B", "C"],
            "PAC_1": ["A_MT_1", "B_MT_1", "B_MT_2", "C_MT_1"],
            "PAC_2": ["A_MT_2", "B_MT_9", "B_MT_3", "C_MT_2"],
            "geometry": [
                MultiLineString([[(0, 0), (100, 0)]]),
                MultiLineString([[(100.0000, 1.5), (200, 50)]]),  # início a 1,5 m da chave
                MultiLineString([[(200, 60), (100.0, 0.5)]]),  # fim a 0,5 m (mais próximo)
                MultiLineString([[(100.0, -1.0), (100, -80)]]),  # outro vizinho, a 1 m
            ],
        },
        crs="EPSG:31983",
    )
    unsemt = gpd.GeoDataFrame(
        {
            "COD_ID": ["CH"],
            "CTMT": ["A"],
            "P_N_OPE": ["A"],
            "TLCD": [1],
            "TIP_UNID": ["19"],
            "geometry": [Point(100, 0)],
        },
        crs="EPSG:31983",
    )
    ties = detectar_interligacoes(unsemt, ssdmt)
    assert ties.crs.to_epsg() == 31983  # já métrico: não reprojeta
    assert ties[["CTMT_VIZ", "SSDMT_VIZ", "PAC_VIZ", "DIST_M"]].values.tolist() == [
        ["B", "B2", "B_MT_3", 0.5],
        ["C", "C1", "C_MT_1", 1.0],
    ]
    resumo = contar_por_ctmt(ties)
    assert resumo.loc["A", "NA_interligacao"] == 1  # a mesma chave conta uma vez
    assert resumo.loc["A", "n_vizinhos"] == 2 and resumo.loc["A", "vizinhos"] == "B;C"
    assert resumo.loc["B", "NA_interligacao"] == resumo.loc["C", "NA_interligacao"] == 1


def test_contagens_por_ctmt_sao_simetricas(camadas):
    ties = detectar_interligacoes(camadas["UNSEMT"], camadas["SSDMT"], sub=camadas["SUB"])
    resumo = contar_por_ctmt(ties)
    assert set(resumo.index) == {"RJO001", "RJO002"}  # RJO003 não aparece
    for ctmt, vizinho in (("RJO001", "RJO002"), ("RJO002", "RJO001")):
        linha = resumo.loc[ctmt]
        assert linha["NA_interligacao"] == 3
        assert linha["NA_interligacao_telecomandada"] == 2
        assert linha["NA_interligacao_SE"] == 1
        # de campo = fora do polígono SUB: CH003 (TLCD) e CH005 (manual); CH007 é disjuntor na SE
        assert linha["NA_interligacao_campo"] == 2
        assert linha["NA_interligacao_campo_telecomandada"] == 1
        assert linha["n_vizinhos"] == 1 and linha["vizinhos"] == vizinho


def test_vizinhos_de_lista_ties_dos_dois_lados(camadas):
    ties = detectar_interligacoes(camadas["UNSEMT"], camadas["SSDMT"], sub=camadas["SUB"])
    de_1 = vizinhos_de(ties, "RJO001")
    assert de_1.to_dict("records") == [
        {
            "CTMT_VIZ": "RJO002",
            "ties": 3,
            "ties_telecomandadas": 2,
            "ties_manuais": 1,
            "ties_em_SE": 1,
            "ties_proprias": 1,
            "ties_do_vizinho": 2,
            "chaves": "CH003;CH005;CH007",
        }
    ]
    de_2 = vizinhos_de(ties, "RJO002").iloc[0]
    assert (de_2["ties"], de_2["ties_proprias"], de_2["ties_do_vizinho"]) == (3, 2, 1)
    assert vizinhos_de(ties, "RJO003").empty


def test_vizinhos_de_sem_se_desconta_disjuntores_da_subestacao(camadas):
    ties = detectar_interligacoes(camadas["UNSEMT"], camadas["SSDMT"], sub=camadas["SUB"])
    campo = vizinhos_de(ties, "RJO001", sem_se=True)
    assert campo.to_dict("records") == [
        {
            "CTMT_VIZ": "RJO002",
            "ties": 2,
            "ties_telecomandadas": 1,
            "ties_manuais": 1,
            "ties_em_SE": 1,  # CH007 continua visível, mas fora das demais contagens
            "ties_proprias": 1,
            "ties_do_vizinho": 1,
            "chaves": "CH003;CH005",
        }
    ]
    # vizinho ligado só por chave na SE continua listado, com ties = 0
    so_se = vizinhos_de(ties[ties["COD_ID"] == "CH007"], "RJO001", sem_se=True)
    assert so_se.to_dict("records") == [
        {
            "CTMT_VIZ": "RJO002",
            "ties": 0,
            "ties_telecomandadas": 0,
            "ties_manuais": 0,
            "ties_em_SE": 1,
            "ties_proprias": 0,
            "ties_do_vizinho": 0,
            "chaves": "",
        }
    ]
    assert vizinhos_de(ties, "RJO003", sem_se=True).empty


def test_entradas_vazias_devolvem_tabelas_vazias_com_colunas(camadas):
    so_rjo003 = camadas["UNSEMT"].query("CTMT == 'RJO003'")
    ties = detectar_interligacoes(so_rjo003, camadas["SSDMT"])
    assert ties.empty and list(ties.columns) == [*COLUNAS_INTERLIGACAO, "geometry"]
    resumo = contar_por_ctmt(ties)
    assert resumo.empty and "NA_interligacao" in resumo.columns
    assert vizinhos_de(ties, "RJO001").empty
    assert detectar_interligacoes(camadas["UNSEMT"].iloc[0:0], camadas["SSDMT"]).empty


def test_extremidades_e_crs_metrico(camadas):
    trechos = camadas["SSDMT"]
    pontos, atributos = extremidades(trechos)
    assert len(pontos) == len(atributos) == 2 * len(trechos)
    inicio = atributos.iloc[0]
    assert (inicio["SSDMT_VIZ"], inicio["CTMT_VIZ"], inicio["PAC_VIZ"]) == (
        "SEG001",
        "RJO001",
        "RJO001_MT_1",
    )
    fim = atributos.iloc[len(trechos)]
    assert (fim["SSDMT_VIZ"], fim["PAC_VIZ"]) == ("SEG001", "RJO001_MT_2")
    assert crs_metrico(trechos).to_epsg() == 31983  # SIRGAS 2000 / UTM 23S para o Rio
    assert crs_metrico(trechos.to_crs(31983)).to_epsg() == 31983
