"""Testes de ``bdgd_light.grid`` (grafo do alimentador) e do comando ``bdgd-light grafo``.

Topologia MT da fixture (``tests/fixtures/gerar_fixture.py``), nós = PAC:

RJO001: MT_0 (PAC_INI, SE) ─CH008 NF─ MT_1 ─SEG001─ MT_2 ─CH001 NF─ MT_3 ─SEG002─ MT_4 ─SEG003─ MT_5
        MT_4 ─SEG006─ MT_6; anel interno CH006 NA (MT_5—MT_6); tie CH003 NA TLCD (MT_5—MT_7) cuja
        ponta MT_7 encosta em RJO002_MT_5; a chave CH005 NA de RJO002 encosta em RJO001_MT_6; CH007
        NA de RJO002 toca RJO001_MT_1 mas está dentro da SE (EM_SUB) e é ignorada por padrão.
        Clientes: TR001@MT_4 (3 UCBT, 75 kVA), TR003@MT_2 (1 UCBT, 45 kVA), UCMT001@MT_3.
RJO002: MT_0 ─CH009 NF─ MT_1 ─SEG004─ MT_2 ─CH002 NF─ MT_3 ─SEG005─ MT_4 … TR002@MT_4 (2 UCBT).
RJO003: sem disjuntor em PAC_INI (fonte cai no PAC mais próximo da SE002); TR004 + UCMT002 @MT_2.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from bdgd_light.cli import app
from bdgd_light.grid import (
    ABRIR,
    CHAVE,
    FECHAR,
    TIE,
    TRECHO,
    ChaveInexistenteError,
    Clientes,
    Cluster,
    Feeder,
    Rede,
    TrechoInexistenteError,
    estado_geojson,
    manobra,
)
from bdgd_light.ingest.recorte import recortar

runner = CliRunner()
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
TQR0007 = Path("data/feeders/TQR0007.gpkg")


def saida(resultado) -> str:
    return _ANSI.sub("", resultado.output)


def compacto(resultado) -> str:
    """Saída sem espaços nem bordas de tabela (rich quebra células em 80 colunas)."""
    return re.sub(r"[\s\u2500-\u259f]+", "", saida(resultado))


def nos(ctmt: str, *indices: int) -> set[str]:
    return {f"{ctmt}_MT_{i}" for i in indices}


@pytest.fixture(scope="module")
def feeders(parquet_mini, tmp_path_factory):
    out = tmp_path_factory.mktemp("grid")
    resultado = recortar(
        parquet_mini, ["RJO001", "RJO002", "RJO003"], out, console=Console(quiet=True)
    )
    return {r.nome: r for r in resultado.recortes} | {"cluster": resultado.cluster}


@pytest.fixture
def rjo001(feeders) -> Feeder:
    return Feeder.from_gpkg(feeders["RJO001"].gpkg)


@pytest.fixture
def cluster(feeders) -> Cluster:
    return Cluster.from_gpkg(feeders["cluster"].gpkg)


# --- construção -------------------------------------------------------------------------------


def test_feeder_topologia(rjo001: Feeder):
    assert rjo001.ctmt == "RJO001"
    assert rjo001.fonte == "RJO001_MT_0"  # PAC_INI = PAC_1 do disjuntor CH008
    assert rjo001.avisos == []
    assert set(rjo001.nos()) == nos("RJO001", 0, 1, 2, 3, 4, 5, 6, 7)
    assert set(rjo001.trechos) == {"SEG001", "SEG002", "SEG003", "SEG006"}
    assert set(rjo001.chaves) == {"CH001", "CH003", "CH005", "CH006", "CH008"}
    assert rjo001.km() == pytest.approx(0.374, abs=0.001)  # soma de COMP (m) / 1000
    por_tipo = {}
    for u, v, d in rjo001.grafo.edges(data=True):
        por_tipo.setdefault(d["tipo"], set()).add(frozenset((u, v)))
    assert len(por_tipo[TRECHO]) == 4
    assert frozenset(("RJO001_MT_3", "RJO001_MT_4")) in por_tipo[TRECHO]
    # ponta de fora da tie própria (MT_7) liga ao nó externo do vizinho, que não está carregado
    assert por_tipo[TIE] == {frozenset(("RJO001_MT_7", "EXT:RJO002"))}
    # chave NA do vizinho (CH005) entra como chave externa entre o nosso PAC e o nó externo
    assert frozenset(("RJO001_MT_6", "EXT:RJO002")) in por_tipo[CHAVE]
    aresta = rjo001.grafo.edges["RJO001_MT_6", "EXT:RJO002"]
    assert aresta["cod"] == "CH005" and aresta["externa"] and aresta["aberta"]
    assert rjo001.externos == ["RJO002"]
    disjuntor = rjo001.grafo.edges[rjo001.chaves["CH008"]]
    assert disjuntor["normal"] == "NF" and not disjuntor["aberta"] and disjuntor["tlcd"]
    assert disjuntor["tip_unid"] == "29"


def test_ties_por_padrao_ignoram_chaves_na_se(rjo001: Feeder, feeders):
    ties = rjo001.tie_switches()
    assert ties["chave"].tolist() == ["CH003", "CH005"]
    propria = ties.set_index("chave").loc["CH003"]
    assert propria["ctmt"] == "RJO001" and propria["ctmt_viz"] == "RJO002"
    assert propria["pac"] == "RJO001_MT_7" and propria["pac_viz"] == "RJO002_MT_5"
    assert bool(propria["tlcd"]) and not bool(propria["externa"]) and bool(propria["aberta"])
    externa = ties.set_index("chave").loc["CH005"]
    assert externa["ctmt"] == "RJO002" and bool(externa["externa"])
    assert externa["pac"] == "RJO001_MT_6"
    com_se = Feeder.from_gpkg(feeders["RJO001"].gpkg, ties_na_se=True)
    assert com_se.tie_switches()["chave"].tolist() == ["CH003", "CH005", "CH007"]


def test_clientes_por_no(rjo001: Feeder):
    assert rjo001.trafos == {"TR001": "RJO001_MT_4", "TR003": "RJO001_MT_2"}
    assert rjo001.clientes["RJO001_MT_4"] == Clientes(ucbt=3, ucmt=0, trafos=1, kva=75.0)
    assert rjo001.clientes["RJO001_MT_2"] == Clientes(ucbt=1, ucmt=0, trafos=1, kva=45.0)
    assert rjo001.clientes["RJO001_MT_3"] == Clientes(ucbt=0, ucmt=1, trafos=0, kva=0.0)
    total = rjo001.customers(rjo001.nos())
    assert total == Clientes(ucbt=4, ucmt=1, trafos=2, kva=120.0) and total.total == 5


def test_fonte_alternativa_quando_pac_ini_nao_esta_no_grafo(feeders):
    rjo003 = Feeder.from_gpkg(feeders["RJO003"].gpkg)
    assert rjo003.fonte == "RJO003_MT_1"
    assert len(rjo003.avisos) == 1 and "PAC_INI" in rjo003.avisos[0]
    assert rjo003.energized_nodes() == nos("RJO003", 1, 2, 3)


def test_feeder_exige_um_ctmt_e_rede_aceita_camadas_em_memoria(feeders):
    with pytest.raises(ValueError, match="exatamente um CTMT"):
        Feeder.from_gpkg(feeders["cluster"].gpkg)
    rede = Rede.from_camadas(feeders["RJO001"].camadas)
    assert set(rede.nos()) == nos("RJO001", 0, 1, 2, 3, 4, 5, 6, 7)
    with pytest.raises(ValueError, match="obrigat"):
        Rede.from_camadas({"CTMT": feeders["RJO001"].camadas["CTMT"]})


# --- energização e chaves -----------------------------------------------------------------------


def test_energizacao_normal_e_manobras(rjo001: Feeder):
    assert rjo001.energized_nodes() == nos("RJO001", 0, 1, 2, 3, 4, 5, 6, 7)
    assert rjo001.energized_by("RJO001_MT_4") == "RJO001"
    # MT_7 é a ponta de fora da tie: recebe tensão do vizinho (nó externo)
    assert rjo001.energized_by("RJO001_MT_7") == "RJO002"
    assert not rjo001.is_open("CH001") and rjo001.is_open("CH003")

    rjo001.open_switch("CH001")
    assert rjo001.energized_nodes() == nos("RJO001", 0, 1, 2, 7)
    assert rjo001.energized_by("RJO001_MT_4") is None
    rjo001.close_switch("CH003")  # transfere a jusante para RJO002 pela tie
    assert rjo001.energized_nodes() == nos("RJO001", 0, 1, 2, 3, 4, 5, 6, 7)
    assert rjo001.energized_by("RJO001_MT_4") == "RJO002"
    assert rjo001.energized_by("RJO001_MT_1") == "RJO001"

    rjo001.reset_switches()
    assert not rjo001.is_open("CH001") and rjo001.is_open("CH003")
    assert rjo001.energized_by("RJO001_MT_4") == "RJO001"
    with pytest.raises(ChaveInexistenteError):
        rjo001.open_switch("CH999")


def test_downstream_e_clientes_a_jusante(rjo001: Feeder):
    assert rjo001.downstream("RJO001_MT_4") == nos("RJO001", 4, 5, 6)
    assert rjo001.customers_downstream("RJO001_MT_4") == Clientes(3, 0, 1, 75.0)
    assert rjo001.downstream("RJO001_MT_1") == nos("RJO001", 1, 2, 3, 4, 5, 6)
    assert rjo001.downstream("RJO001_MT_0") == nos("RJO001", 0, 1, 2, 3, 4, 5, 6)
    rjo001.close_switch("CH006")  # anel interno: MT_5 e MT_6 passam a ter dois caminhos
    assert rjo001.downstream("RJO001_MT_5") == {"RJO001_MT_5"}
    assert rjo001.downstream("RJO001_MT_4") == nos("RJO001", 4, 5, 6)


def test_copy_nao_compartilha_estado(rjo001: Feeder):
    copia = rjo001.copy()
    copia.open_switch("CH001")
    assert not rjo001.is_open("CH001")
    assert len(rjo001.energized_nodes()) == 8 and len(copia.energized_nodes()) == 4


# --- isolamento e restauração -------------------------------------------------------------------


def test_isolar_trecho_a_jusante_da_ultima_chave_nao_desliga_ninguem(rjo001: Feeder):
    for trecho in ["SEG002", "SEG003", "SEG006"]:
        iso = rjo001.isolate_segment(trecho)
        assert iso.chaves == ["CH001"]
        assert iso.zona == nos("RJO001", 3, 4, 5, 6)
        assert iso.desligados == set()
        assert iso.clientes_zona == Clientes(3, 1, 1, 75.0)
        assert rjo001.restore_options(trecho) == []
    with pytest.raises(TrechoInexistenteError):
        rjo001.isolate_segment("SEG999")


def test_isolar_trecho_de_tronco_e_restaurar_pela_tie(rjo001: Feeder):
    iso = rjo001.isolate_segment("SEG001")
    assert iso.chaves == ["CH001", "CH008"]  # primeira chave fechada em cada direção
    assert iso.zona == nos("RJO001", 1, 2)
    assert iso.clientes_zona == Clientes(1, 0, 1, 45.0)
    assert iso.desligados == nos("RJO001", 3, 4, 5, 6)
    assert iso.clientes_desligados == Clientes(3, 1, 1, 75.0)
    assert not rjo001.is_open("CH001")  # sem aplicar=True o estado não muda

    opcoes = rjo001.restore_options("SEG001")
    assert [o.chave for o in opcoes] == ["CH003", "CH005"]  # TLCD primeiro; CH006 não ajuda
    propria, externa = opcoes
    assert propria.ctmt_chave == "RJO001" and propria.fonte == "RJO002"
    assert propria.tlcd and not propria.externa
    assert propria.nos == nos("RJO001", 3, 4, 5, 6)
    assert propria.clientes == Clientes(3, 1, 1, 75.0)
    assert externa.ctmt_chave == "RJO002" and externa.fonte == "RJO002" and externa.externa
    assert not externa.tlcd and externa.nos == propria.nos

    aplicado = rjo001.isolate_segment("SEG001", aplicar=True)
    assert aplicado.chaves == iso.chaves
    assert rjo001.is_open("CH001") and rjo001.is_open("CH008")
    assert rjo001.energized_nodes() == nos("RJO001", 0, 7)
    rjo001.close_switch("CH003")
    assert rjo001.energized_nodes() == nos("RJO001", 0, 3, 4, 5, 6, 7)
    assert rjo001.energized_by("RJO001_MT_4") == "RJO002"


def test_to_dict_serializavel_e_sequencia_de_manobras(rjo001: Feeder):
    iso = rjo001.isolate_segment("SEG001")
    d = iso.to_dict()
    json.dumps(d)
    assert d["chaves"] == ["CH001", "CH008"]
    assert d["zona"] == sorted(nos("RJO001", 1, 2))
    assert d["desligados"] == sorted(nos("RJO001", 3, 4, 5, 6))
    assert d["clientes_desligados"] == {"ucbt": 3, "ucmt": 1, "trafos": 1, "kva": 75.0, "total": 4}
    assert d["manobras"] == iso.manobras == [manobra(ABRIR, "CH001"), manobra(ABRIR, "CH008")]

    opcoes = rjo001.restore_options("SEG001")
    assert opcoes[0].manobras == [
        {"acao": "abrir", "chave": "CH001"},
        {"acao": "abrir", "chave": "CH008"},
        {"acao": "fechar", "chave": "CH003"},
    ]
    o = opcoes[0].to_dict()
    json.dumps(o)
    assert o["nos"] == sorted(nos("RJO001", 3, 4, 5, 6))
    assert o["clientes"]["total"] == 4 and o["clientes_fonte"]["total"] == 0
    assert o["manobras"][-1] == {"acao": FECHAR, "chave": "CH003"}
    # executar a sequência reproduz o estado previsto
    for passo in opcoes[0].manobras:
        (rjo001.open_switch if passo["acao"] == ABRIR else rjo001.close_switch)(passo["chave"])
    assert rjo001.energized_nodes() == nos("RJO001", 0, 3, 4, 5, 6, 7)
    assert Clientes.from_dict(o["clientes"]) == opcoes[0].clientes
    with pytest.raises(ValueError):
        manobra("religar", "CH001")

    r = rjo001.resumo()
    json.dumps(r)
    assert r["clientes"]["ucbt"] == 4 and r["clientes"]["total"] == 5


# --- cluster -----------------------------------------------------------------------------------


def test_cluster_liga_ties_pelos_pac_reais(cluster: Cluster):
    assert cluster.ctmts == ["RJO001", "RJO002", "RJO003"]
    assert cluster.fontes == {
        "RJO001": "RJO001_MT_0",
        "RJO002": "RJO002_MT_0",
        "RJO003": "RJO003_MT_1",
    }
    assert cluster.externos == []
    ties = {frozenset((u, v)) for u, v, d in cluster.grafo.edges(data=True) if d["tipo"] == TIE}
    assert ties == {
        frozenset(("RJO001_MT_7", "RJO002_MT_5")),
        frozenset(("RJO001_MT_6", "RJO002_MT_7")),
    }
    assert cluster.chaves["CH005"] in (
        ("RJO002_MT_6", "RJO002_MT_7"),
        ("RJO002_MT_7", "RJO002_MT_6"),
    )
    assert not cluster.grafo.edges[cluster.chaves["CH005"]]["externa"]
    # CH007 (EM_SUB) fica fora das ties: seus PAC não tocam a rede → ilha sem tensão
    assert set(cluster.nos()) - cluster.energized_nodes() == nos("RJO002", 8, 9)
    assert cluster.tie_switches()["chave"].tolist() == ["CH003", "CH005"]
    assert cluster.energized_by("RJO002_MT_7") == "RJO001"  # ponta de fora da CH005
    assert cluster.energized_by("RJO001_MT_7") == "RJO002"


def test_cluster_restauracao_informa_carga_ja_na_fonte(cluster: Cluster):
    iso = cluster.isolate_segment("SEG001")
    assert iso.chaves == ["CH001", "CH008"]
    assert iso.desligados == nos("RJO001", 3, 4, 5, 6) | {"RJO002_MT_7"}
    opcoes = cluster.restore_options("SEG001")
    assert [(o.chave, o.fonte, o.externa) for o in opcoes] == [
        ("CH003", "RJO002", False),
        ("CH005", "RJO002", False),
    ]
    assert opcoes[0].clientes == Clientes(3, 1, 1, 75.0)
    assert opcoes[0].clientes_fonte == Clientes(2, 0, 1, 112.5)  # TR002 já em RJO002


def test_cluster_com_ties_na_se_e_from_gpkgs(feeders, cluster: Cluster):
    com_se = Cluster.from_gpkg(feeders["cluster"].gpkg, ties_na_se=True)
    assert com_se.tie_switches()["chave"].tolist() == ["CH003", "CH005", "CH007"]
    assert com_se.energized_nodes() == set(com_se.nos()) - {"RJO002_MT_8"}
    separados = Cluster.from_gpkgs(feeders[c].gpkg for c in ["RJO001", "RJO002", "RJO003"])
    assert set(separados.nos()) == set(cluster.nos())
    assert separados.fontes == cluster.fontes
    assert sorted(separados.trechos) == sorted(cluster.trechos)
    assert sorted(separados.chaves) == sorted(cluster.chaves)


# --- GeoJSON ------------------------------------------------------------------------------------


def test_estado_geojson(rjo001: Feeder, tmp_path):
    rjo001.isolate_segment("SEG001", aplicar=True)
    caminho = tmp_path / "estado.geojson"
    colecao = estado_geojson(rjo001, caminho)
    assert json.loads(caminho.read_text()) == colecao
    assert colecao["type"] == "FeatureCollection"
    por_camada: dict[str, dict[str, dict]] = {}
    for f in colecao["features"]:
        por_camada.setdefault(f["properties"]["camada"], {})[f["properties"]["COD_ID"]] = f
    assert {c: len(v) for c, v in por_camada.items()} == {"SSDMT": 4, "UNSEMT": 5, "UNTRMT": 2}
    seg001, seg002 = por_camada["SSDMT"]["SEG001"], por_camada["SSDMT"]["SEG002"]
    assert seg001["geometry"]["type"] == "MultiLineString"
    lon, lat = seg001["geometry"]["coordinates"][0][0]
    assert -43.3 < lon < -43.1 and -23.0 < lat < -22.8  # EPSG:4326
    assert seg001["properties"]["energizado"] is False
    assert seg002["properties"]["energizado"] is False and seg002["properties"]["fonte"] is None
    assert seg001["properties"]["COMP"] == pytest.approx(102.5, abs=0.01)
    ch001 = por_camada["UNSEMT"]["CH001"]["properties"]
    assert ch001["aberta"] is True and ch001["normal"] == "NF" and ch001["tie"] is False
    ch003 = por_camada["UNSEMT"]["CH003"]["properties"]
    assert ch003["tie"] is True and ch003["TLCD"] is True and ch003["externa"] is False
    ch005 = por_camada["UNSEMT"]["CH005"]["properties"]
    assert ch005["externa"] is True and ch005["CTMT"] == "RJO002"
    assert por_camada["UNSEMT"]["CH005"]["geometry"]["type"] == "Point"
    tr001 = por_camada["UNTRMT"]["TR001"]["properties"]
    assert tr001["n_UCBT"] == 3 and tr001["energizado"] is False and tr001["POT_NOM"] == 75


# --- CLI -----------------------------------------------------------------------------------------


def test_cli_grafo_com_falha_e_geojson(feeders, tmp_path):
    geojson = tmp_path / "estado.geojson"
    resultado = runner.invoke(
        app,
        [
            "grafo",
            "--gpkg",
            str(feeders["RJO001"].gpkg),
            "--falha",
            "SEG001",
            "--geojson",
            str(geojson),
        ],
    )
    assert resultado.exit_code == 0, resultado.output
    texto = compacto(resultado)
    assert "GrafodeRJO001" in texto and "RJO001:RJO001_MT_0" in texto
    assert "Ties(2)" in texto and "CH005(externa)" in texto
    assert "FaltaemSEG001→abrirCH001,CH008" in texto
    assert "Opçõesderestauração(2)" in texto
    assert texto.index("CH003") < texto.index("Opçõesderestauração") < texto.rindex("CH003")
    assert geojson.exists()
    energizados = {
        f["properties"]["COD_ID"]: f["properties"]["energizado"]
        for f in json.loads(geojson.read_text())["features"]
        if f["properties"]["camada"] == "SSDMT"
    }
    assert energizados == {"SEG001": False, "SEG002": False, "SEG003": False, "SEG006": False}


def test_cli_grafo_abrir_fechar_e_erros(feeders, tmp_path):
    gpkg = str(feeders["RJO001"].gpkg)
    argumentos = ["grafo", "--gpkg", gpkg, "--abrir", "CH001", "--fechar", "CH003"]
    resultado = runner.invoke(app, argumentos)
    assert resultado.exit_code == 0, resultado.output
    texto = compacto(resultado)
    assert "Nósenergizados8de8" in texto and "CH003" in texto

    resultado = runner.invoke(app, ["grafo", "--gpkg", str(feeders["RJO001"].gpkg), "--abrir", "X"])
    assert resultado.exit_code == 1 and "X" in saida(resultado)
    resultado = runner.invoke(
        app, ["grafo", "--gpkg", str(feeders["RJO001"].gpkg), "--falha", "SEG999"]
    )
    assert resultado.exit_code == 1 and "SEG999" in saida(resultado)
    resultado = runner.invoke(app, ["grafo", "--gpkg", str(tmp_path / "nao_existe.gpkg")])
    assert resultado.exit_code == 1


def test_cli_grafo_cluster(feeders):
    resultado = runner.invoke(app, ["grafo", "--gpkg", str(feeders["cluster"].gpkg)])
    assert resultado.exit_code == 0, resultado.output
    texto = compacto(resultado)
    assert "GrafodeRJO001,RJO002,RJO003" in texto
    assert "Nósenergizados19de21" in texto
    assert "PAC_INI" in texto  # aviso da fonte alternativa de RJO003


# --- fumaça com dados reais ---------------------------------------------------------------------


@pytest.mark.skipif(not TQR0007.exists(), reason="recorte real data/feeders/TQR0007.gpkg ausente")
def test_fumaca_tqr0007():
    feeder = Feeder.from_gpkg(TQR0007)
    assert feeder.ctmt == "TQR0007"
    assert feeder.fonte == "TQR0007_MT_52737"  # PAC_INI = PAC_1 do disjuntor 358368825
    assert feeder.avisos == []
    assert feeder.energized_nodes() == set(feeder.nos())
    ties = feeder.tie_switches()
    assert set(ties["ctmt_viz"]) | set(ties["ctmt"]) >= {"TQR0007", "TQR33859", "TQR33862"}
    assert not ties["em_sub"].any()
    disjuntor = feeder.grafo.edges[feeder.chaves["358368825"]]
    assert disjuntor["tip_unid"] == "29" and disjuntor["normal"] == "NF"
    # trecho ligado ao disjuntor: isolar derruba o alimentador inteiro, e as ties restauram
    iso = feeder.isolate_segment("310743928")
    assert "358368825" in iso.chaves
    assert iso.clientes_desligados.ucbt > 6000
    opcoes = feeder.restore_options("310743928")
    assert opcoes and opcoes[0].tlcd and opcoes[0].clientes == iso.clientes_desligados
    assert {o.fonte for o in opcoes} >= {"TQR33859", "TQR33862"}
    colecao = estado_geojson(feeder)
    assert len(colecao["features"]) == len(feeder.trechos) + len(feeder.trafos) + len(
        [d for _, _, d in feeder.grafo.edges(data=True) if d["tipo"] == CHAVE]
    )
