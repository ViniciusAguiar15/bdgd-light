"""Testes de ``bdgd_light.ingest.tiles`` e do comando ``bdgd-light tiles``.

O tippecanoe é um binário externo: a parte GeoJSON (atributos derivados, ``tippecanoe.minzoom``,
bbox) é testada sempre; a geração do ``.pmtiles`` de verdade só roda se ele estiver no PATH.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pyogrio
import pytest
from rich.console import Console
from typer.testing import CliRunner

from bdgd_light.cli import app
from bdgd_light.ingest import tiles
from bdgd_light.ingest.recorte import recortar
from bdgd_light.ingest.tiles import (
    CAMADAS_TILES,
    TippecanoeAusenteError,
    TippecanoeError,
    comando_tippecanoe,
    escrever_geojson,
    gerar_tiles,
)

runner = CliRunner()
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
CLUSTER = ["RJO001", "RJO002"]
TEM_TIPPECANOE = shutil.which("tippecanoe") is not None


def saida(resultado) -> str:
    return _ANSI.sub("", resultado.output)


def ler_geojsonl(caminho: Path) -> list[dict]:
    return [json.loads(linha) for linha in caminho.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def cluster_gpkg(parquet_mini, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("feeders")
    r = recortar(parquet_mini, CLUSTER, out, console=Console(quiet=True))
    assert r.cluster is not None and r.cluster.gpkg is not None
    return r.cluster.gpkg


@pytest.fixture(scope="module")
def geojson_cluster(cluster_gpkg, tmp_path_factory):
    pasta = tmp_path_factory.mktemp("geojson")
    avisos: list[str] = []
    arquivos, contagem, bbox = escrever_geojson(cluster_gpkg, pasta, avisos=avisos)
    return arquivos, contagem, bbox, avisos


def test_camadas_declaradas_sao_coerentes():
    nomes = [c.nome for c in CAMADAS_TILES]
    assert len(nomes) == len(set(nomes))
    assert {"SSDMT", "UNSEMT", "UNTRMT", "INTERLIGACOES", "UCBT", "PONNOT"} <= set(nomes)
    # a camada derivada UCBT lê os postes (PONNOT) e agrega UCBT_tab por PN_CON
    ucbt = next(c for c in CAMADAS_TILES if c.nome == "UCBT")
    assert ucbt.camada_gpkg == "PONNOT"
    # o tronco MT aparece antes (zoom menor) do que as unidades consumidoras
    minzoom = {c.nome: c.minzoom for c in CAMADAS_TILES}
    assert minzoom["SSDMT"] < minzoom["UNSEMT"] < minzoom["UNTRMT"] < minzoom["UCBT"]


AVISO_UC00007 = "UCBT: 1 postes de UCBT_tab.PN_CON sem PONNOT no recorte"  # PN107, issue #40


def test_geojson_por_camada_em_4326_com_minzoom(geojson_cluster):
    arquivos, contagem, bbox, avisos = geojson_cluster
    assert avisos == [AVISO_UC00007]
    assert set(arquivos) == {
        "SUB",
        "UNTRAT",
        "SSDMT",
        "INTERLIGACOES",
        "UNSEMT",
        "UNTRMT",
        "UNCRMT",
        "SSDBT",
        "UNSEBT",
        "UCBT",
        "PONNOT",
    }
    assert contagem["SSDMT"] == 8 and contagem["UNSEMT"] == 8 and contagem["UNTRMT"] == 3
    assert contagem["INTERLIGACOES"] == 3
    assert bbox is not None
    lon_min, lat_min, lon_max, lat_max = bbox
    assert -43.3 < lon_min < lon_max < -43.1 and -23.0 < lat_min < lat_max < -22.8
    for nome, caminho in arquivos.items():
        assert caminho.name == f"{nome}.geojsonl"
        feicoes = ler_geojsonl(caminho)
        assert len(feicoes) == contagem[nome]
        cam = next(c for c in CAMADAS_TILES if c.nome == nome)
        for f in feicoes:
            assert f["type"] == "Feature"
            assert f["tippecanoe"] == {"minzoom": cam.minzoom, "layer": nome}
            assert set(f["properties"]) <= set(cam.colunas)
            x, y = _primeira_coordenada(f["geometry"])
            assert -44 < x < -43 and -23.1 < y < -22.8  # graus, não metros


def _primeira_coordenada(geometria: dict) -> tuple[float, float]:
    coords = geometria["coordinates"]
    while isinstance(coords[0], list):
        coords = coords[0]
    return coords[0], coords[1]


def test_ssdmt_recebe_tensao_e_nome_do_ctmt(geojson_cluster):
    arquivos = geojson_cluster[0]
    props = [f["properties"] for f in ler_geojsonl(arquivos["SSDMT"])]
    assert {p["TEN_KV"] for p in props} == {13.2}  # TEN_NOM "46" → 13,2 kV
    assert {p["NOME_CTMT"] for p in props} == {"LDA SINTETICO 01", "LDA SINTETICO 02"}
    assert all(p["COMP"] > 0 for p in props)


def test_unsemt_marca_ties_e_vizinho(geojson_cluster):
    arquivos = geojson_cluster[0]
    por_id = {f["properties"]["COD_ID"]: f["properties"] for f in ler_geojsonl(arquivos["UNSEMT"])}
    assert {k for k, p in por_id.items() if p["TIE"]} == {"CH003", "CH005", "CH007"}
    assert por_id["CH003"]["CTMT_VIZ"] == "RJO002" and por_id["CH003"]["EM_SUB"] is False
    assert por_id["CH007"]["CTMT_VIZ"] == "RJO001" and por_id["CH007"]["EM_SUB"] is True
    assert por_id["CH001"]["TIE"] is False and por_id["CH001"]["CTMT_VIZ"] is None
    assert por_id["CH001"]["TIPO"] == "chave fusível"  # TIP_UNID 22 traduzido
    assert por_id["CH003"]["P_N_OPE"] == "A" and por_id["CH003"]["TLCD"] == 1


def test_untrmt_conta_ucbt_e_ucbt_e_agregada_por_poste(geojson_cluster):
    arquivos = geojson_cluster[0]
    trafos = {f["properties"]["COD_ID"]: f["properties"] for f in ler_geojsonl(arquivos["UNTRMT"])}
    assert trafos["TR001"]["N_UCBT"] == 3
    assert trafos["TR002"]["N_UCBT"] == 2
    assert trafos["TR003"]["N_UCBT"] == 1
    ucbt = ler_geojsonl(arquivos["UCBT"])
    assert sum(f["properties"]["N_UC"] for f in ucbt) == 5  # UC00007 sem poste no recorte
    assert all(f["geometry"]["type"] == "Point" for f in ucbt)
    assert {f["properties"]["CTMT"] for f in ucbt} == set(CLUSTER)
    assert all(f["properties"]["PN_CON"].startswith("PN") for f in ucbt)


def test_postes_fora_do_bbox_da_rede_ficam_fora_dos_tiles(parquet_mini, tmp_path):
    # recorte gerado sem o filtro da issue #40 (ou anterior a ele): PN107 a ~40 km entra no GPKG
    r = recortar(
        parquet_mini, CLUSTER, tmp_path / "f", folga_bbox_m=None, console=Console(quiet=True)
    )
    gpkg = r.cluster.gpkg
    assert pyogrio.read_info(gpkg, layer="PONNOT")["features"] == 26

    avisos: list[str] = []
    arquivos, contagem, bbox = escrever_geojson(gpkg, tmp_path / "gj", avisos=avisos)
    assert contagem["PONNOT"] == 25 and contagem["UCBT"] == 5
    assert avisos == [  # na ordem de CAMADAS_TILES
        "UCBT: 1 feição(ões) fora do bbox da rede descartada(s) dos tiles",
        "PONNOT: 1 feição(ões) fora do bbox da rede descartada(s) dos tiles",
    ]
    assert -43.22 < bbox[0] and bbox[1] > -22.93  # sem o poste longe, o bbox é o da rede
    assert "PN107" not in {f["properties"]["COD_ID"] for f in ler_geojsonl(arquivos["PONNOT"])}

    sem_filtro: list[str] = []
    _, contagem2, bbox2 = escrever_geojson(
        gpkg, tmp_path / "gj2", avisos=sem_filtro, folga_bbox_m=None
    )
    assert sem_filtro == [] and contagem2["PONNOT"] == 26 and contagem2["UCBT"] == 6
    assert bbox2[0] == pytest.approx(-43.6) and bbox2[1] == pytest.approx(-23.0)


def test_camadas_ausentes_geram_aviso_e_nao_quebram(bdgd_mini, tmp_path):
    # a fixture bruta não tem INTERLIGACOES nem CTMT.TEN_NOM ausente → UNSEMT sem ties, mas segue
    avisos: list[str] = []
    arquivos, contagem, _ = escrever_geojson(bdgd_mini, tmp_path, avisos=avisos)
    assert "INTERLIGACOES" not in arquivos
    assert all(f["properties"]["TIE"] is False for f in ler_geojsonl(arquivos["UNSEMT"]))
    assert contagem["UCBT"] > 0


def test_comando_tippecanoe():
    cmd = comando_tippecanoe(
        Path("saida/x.pmtiles"),
        {"SSDMT": Path("g/SSDMT.geojsonl"), "UCBT": Path("g/UCBT.geojsonl")},
        nome="x",
        zoom_min=8,
        zoom_max=15,
        executavel="/opt/bin/tippecanoe",
    )
    assert cmd[:3] == ["/opt/bin/tippecanoe", "-o", "saida/x.pmtiles"]
    assert "--minimum-zoom=8" in cmd and "--maximum-zoom=15" in cmd
    assert "--name=x" in cmd and "--force" in cmd and "--generate-ids" in cmd
    assert cmd[-4:] == ["-L", "SSDMT:g/SSDMT.geojsonl", "-L", "UCBT:g/UCBT.geojsonl"]


def test_apenas_geojson_nao_exige_tippecanoe(cluster_gpkg, tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda *_a, **_k: None)
    r = gerar_tiles(cluster_gpkg, tmp_path / "x.pmtiles", apenas_geojson=True)
    assert r.pmtiles is None and r.bytes == 0
    assert set(r.geojson) == set(r.feicoes)
    assert r.geojson["SSDMT"] == tmp_path / "x_geojson" / "SSDMT.geojsonl"
    assert r.geojson["SSDMT"].exists()


def test_tippecanoe_ausente_e_erro_claro(cluster_gpkg, tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda *_a, **_k: None)
    with pytest.raises(TippecanoeAusenteError, match="brew install tippecanoe"):
        gerar_tiles(cluster_gpkg, tmp_path / "x.pmtiles")
    # e nada de GeoJSON é escrito antes de falhar
    assert not (tmp_path / "x_geojson").exists()

    r = runner.invoke(
        app, ["tiles", "--gpkg", str(cluster_gpkg), "--out", str(tmp_path / "x.pmtiles")]
    )
    assert r.exit_code == 1
    assert "Erro: tippecanoe não encontrado" in saida(r)
    assert "--geojson-only" in saida(r)


def test_tippecanoe_com_falha_e_reportado(cluster_gpkg, tmp_path, monkeypatch):
    falso = tmp_path / "tippecanoe"
    falso.write_text("#!/bin/sh\necho 'boom: layer inválida' >&2\nexit 3\n")
    falso.chmod(0o755)
    monkeypatch.setattr(shutil, "which", lambda *_a, **_k: str(falso))
    with pytest.raises(TippecanoeError, match=r"falhou \(3\).*boom"):
        gerar_tiles(cluster_gpkg, tmp_path / "x.pmtiles")


def test_gpkg_sem_camadas_geograficas(tmp_path):
    import geopandas as gpd
    import pandas as pd

    vazio = tmp_path / "vazio.gpkg"
    gpd.GeoDataFrame(pd.DataFrame({"COD_ID": ["a"]}), geometry=[None], crs="EPSG:4674").to_file(
        vazio, layer="CRVCRG", driver="GPKG"
    )
    with pytest.raises(ValueError, match="nenhuma camada geográfica"):
        gerar_tiles(vazio, tmp_path / "x.pmtiles", apenas_geojson=True)


def test_cli_tiles_geojson_only(cluster_gpkg, tmp_path):
    out = tmp_path / "tiles" / "cluster.pmtiles"
    r = runner.invoke(
        app,
        ["tiles", "--gpkg", str(cluster_gpkg), "--out", str(out), "--geojson-only"],
    )
    assert r.exit_code == 0, r.output
    texto = saida(r)
    assert "SSDMT" in texto and "8" in texto
    assert "UCBT" in texto
    assert (tmp_path / "tiles" / "cluster_geojson" / "SSDMT.geojsonl").exists()
    assert not out.exists()


@pytest.mark.skipif(not TEM_TIPPECANOE, reason="tippecanoe não instalado")
def test_gera_pmtiles_de_verdade(cluster_gpkg, tmp_path):
    out = tmp_path / "cluster.pmtiles"
    r = gerar_tiles(cluster_gpkg, out, pasta_geojson=tmp_path / "gj", zoom_min=9, zoom_max=14)
    assert r.pmtiles == out and out.exists()
    assert r.bytes == out.stat().st_size > 1000
    assert out.read_bytes()[:7] == b"PMTiles"
    assert r.feicoes["SSDMT"] == 8 and r.avisos == [AVISO_UC00007]
    assert (tmp_path / "gj" / "SSDMT.geojsonl").exists()


@pytest.mark.skipif(not TEM_TIPPECANOE, reason="tippecanoe não instalado")
def test_cli_tiles_completo(cluster_gpkg, tmp_path):
    out = tmp_path / "cluster.pmtiles"
    r = runner.invoke(app, ["tiles", "--gpkg", str(cluster_gpkg), "--out", str(out)])
    assert r.exit_code == 0, r.output
    assert out.exists()
    texto = saida(r)
    assert str(out) in texto and "MB" in texto


def test_cli_help_lista_tiles():
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0
    assert "tiles" in saida(r)
    r = runner.invoke(app, ["tiles", "--help"])
    assert r.exit_code == 0
    assert "--geojson-only" in saida(r) and "--zoom-min" in saida(r)


def test_modulo_exposto_no_pacote():
    assert tiles.ZOOM_MIN_PADRAO < tiles.ZOOM_MAX_PADRAO
    assert tiles.CRS_TILES == "EPSG:4326"
