"""Conversor direto GeoPackage → OpenDSS (``bdgd_light.twin.gpkg2dss``)."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point
from typer.testing import CliRunner

if importlib.util.find_spec("opendssdirect") is None:  # não importar: ver twin.powerflow.no_motor
    pytest.skip("opendssdirect não instalado (uv sync --extra twin)", allow_module_level=True)

from rich.console import Console  # noqa: E402

from bdgd_light.cli import app  # noqa: E402
from bdgd_light.grid import Cluster  # noqa: E402
from bdgd_light.ingest.recorte import recortar  # noqa: E402
from bdgd_light.twin import (  # noqa: E402
    DIAS,
    ConversaoGpkg,
    GpkgInvalidoError,
    comandos_manobras,
    converter_ctmt,
    converter_gpkg,
    dias_por_tipo,
    escolher_master,
    listar_ctmts,
    montar_master_cluster,
    run_powerflow,
)

runner = CliRunner()
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
FIXTURE = Path("tests/fixtures/bdgd_mini.gpkg")
TQR0007_GPKG = Path("data/feeders/TQR0007.gpkg")
TQR0007_REF = Path("data/dss/sub__10385871/TQR0007")


def saida(resultado) -> str:
    return _ANSI.sub("", resultado.output)


def compacto(resultado) -> str:
    """Saída sem espaços/quebras (o Rich quebra linhas longas no terminal do CliRunner)."""
    return re.sub(r"[\s\u2500-\u259f]+", "", saida(resultado))


def _texto(pasta: Path, prefixo: str) -> str:
    (arquivo,) = pasta.glob(f"{prefixo}_gpkg_*.dss")
    return arquivo.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def convertido(tmp_path_factory) -> dict[str, ConversaoGpkg]:
    out = tmp_path_factory.mktemp("gpkg_dss")
    return {c.ctmt: c for c in converter_gpkg(FIXTURE, out)}


@pytest.fixture(scope="module")
def recorte_mini(parquet_mini, tmp_path_factory) -> Path:
    """GeoPackage do recorte (cluster RJO001+RJO002), com o grafo das manobras."""
    out = tmp_path_factory.mktemp("recorte")
    resultado = recortar(parquet_mini, ["RJO001", "RJO002"], out, console=Console(quiet=True))
    return resultado.cluster.gpkg


@pytest.fixture(scope="module")
def cluster_mini(recorte_mini) -> Cluster:
    return Cluster.from_gpkg(recorte_mini)


def test_dias_por_tipo_igual_ao_bdgd2opendss():
    from bdgd2opendss.model import Count_days

    Count_days.count_day_type(2026)
    esperado = {
        "DU": {int(m): int(v) for m, v in Count_days.du.items()},
        "SA": {int(m): int(v) for m, v in Count_days.sa.items()},
        "DO": {int(m): int(v) for m, v in Count_days.do.items()},
    }
    assert dias_por_tipo(2026) == esperado
    # 2026: 1º/jan (qui), Carnaval 17/fev (ter) e 21/abr (ter) saem de DU e entram em DO
    dias = dias_por_tipo(2026)
    assert dias["DU"][1] == 21 and dias["DO"][1] == 5 and dias["SA"][1] == 5
    assert dias["DU"][2] == 19 and dias["DO"][2] == 5
    assert all(sum(d[m] for d in dias.values()) in (28, 30, 31) for m in range(1, 13))


def test_listar_ctmts_e_erros(tmp_path):
    assert listar_ctmts(FIXTURE) == ["RJO001", "RJO002", "RJO003"]
    with pytest.raises(GpkgInvalidoError, match="RJO999"):
        converter_ctmt(FIXTURE, "RJO999", tmp_path)
    with pytest.raises(ValueError, match="dia"):
        converter_ctmt(FIXTURE, "RJO001", tmp_path, dias=["XX"])
    with pytest.raises(ValueError, match="mes"):
        converter_ctmt(FIXTURE, "RJO001", tmp_path, meses=[13])
    with pytest.raises(FileNotFoundError):
        converter_ctmt(tmp_path / "nao_existe.gpkg", "RJO001", tmp_path)
    sem_ctmt = tmp_path / "sem_ctmt.gpkg"
    gpd.GeoDataFrame({"COD_ID": ["S1"]}, geometry=[Point(0, 0)], crs=4674).to_file(
        sem_ctmt, layer="SSDMT", driver="GPKG"
    )
    with pytest.raises(GpkgInvalidoError, match="CTMT"):
        listar_ctmts(sem_ctmt)


def test_estrutura_e_contagens(convertido):
    assert set(convertido) == {"RJO001", "RJO002", "RJO003"}
    for ctmt, conv in convertido.items():
        assert conv.pasta.name == ctmt
        assert [m.name for m in conv.masters] == [f"Master_{d}01_gpkg_{ctmt}.dss" for d in DIAS]
        assert all(m.is_file() for m in conv.masters)
        assert escolher_master(conv.pasta, "SA", 1) == conv.masters[1]
    n = convertido["RJO001"].contagem
    assert n["SSDMT"] == 4 and n["UNSEMT"] == 4 and n["UNSEMT_NA"] == 2
    assert n["UNTRMT"] == 2 and n["unidades_trafo"] == 2
    assert n["UCBT_tab"] == 3 and n["isolados_UCBT_tab"] == 1 and n["UCMT_tab"] == 1
    assert n["curvas"] == 6  # 2 tipos de curva (RES/COM) × 3 tipos de dia
    assert any("1 elementos sem caminho até RJO001_MT_0" in a for a in convertido["RJO001"].avisos)
    # RJO003: o PAC_INI do CTMT não pertence a nenhum elemento → aviso, nada é tratado como isolado
    avisos = " ".join(convertido["RJO003"].avisos)
    assert "PAC_INI" in avisos and "sem medidor" in avisos
    assert not any(k.startswith("isolados_") for k in convertido["RJO003"].contagem)


def test_suspeitos_ramais_longos_e_trafos_de_fase_unica(convertido, tmp_path, monkeypatch):
    """Ramais > RAMAL_LONGO_M e trafos com >= 90 % das UC monofásicas na mesma fase saem em
    `avisos`/`contagem` (issue #44); a fixture (ramais de 15 m, trafos com <= 2 UC 1F) não
    dispara nada com os limiares padrão."""
    from bdgd_light.twin import gpkg2dss

    n = convertido["RJO001"].contagem
    assert n["ramais_longos"] == 0 and n["trafos_fase_unica"] == 0
    assert not any("RAMLIG" in a or "fase" in a for a in convertido["RJO001"].avisos)

    monkeypatch.setattr(gpkg2dss, "RAMAL_LONGO_M", 10.0)
    monkeypatch.setattr(gpkg2dss, "FASE_UNICA_MIN_UC", 2)
    conv = converter_ctmt(FIXTURE, "RJO001", tmp_path, dias=["DU"])
    assert conv.contagem["ramais_longos"] == 1  # RM001 (15 m) é o único RAMLIG de RJO001
    assert conv.contagem["trafos_fase_unica"] == 1  # TR001: 2 UC "AN" (+ 1 "ABN", bifásica)
    avisos = "\n".join(conv.avisos)
    assert "1 ramais RAMLIG com mais de 10 m (maior: RM001, 15 m, 1 UC)" in avisos
    assert "1 trafos com >= 90% das UC monofásicas na mesma fase" in avisos
    assert "(TR001 (2 de 2 UC monofásicas em A))" in avisos
    # o modelo em si não muda: mesmas cargas, mesmo FAS_CON
    assert _texto(conv.pasta, "CargasBT_DU01") == _texto(
        convertido["RJO001"].pasta, "CargasBT_DU01"
    )


def test_conteudo_dss_como_bdgd2opendss(convertido):
    pasta = convertido["RJO001"].pasta
    assert _texto(pasta, "CircuitoMT").strip() == (
        'New "Circuit.RJO001" basekv=13.2 pu=1.045 bus1="RJO001_MT_0" r1=0.0 x1=0.0001'
    )
    chaves = _texto(pasta, "ChavesMT")
    assert 'New "Line.CMT_CH001" phases=3 bus1="RJO001_MT_2.1.2.3"' in chaves
    assert '\n!New "Line.CMT_CH003"' in chaves and '\n!New "Line.CMT_CH006"' in chaves  # NA
    assert chaves.count("switch = T length=0.00100") == 4
    trafos = _texto(pasta, "TransformadorMTMTMTBT")
    assert (
        'New "Transformer.TRF_TR001A" phases=3 windings=2 buses=["RJO001_MT_4.1.2.3" '
        '"TR001_BT_0.1.2.3.4"] conns=[Delta Wye] kvs=[13.2 0.22]  kvas=[75 75] '
        "%loadloss=1.100000 %noloadloss=0.300000"
    ) in trafos  # kVA pelo código TPOTAPRT da EQTRMT ("16" → 75); perdas PER_TOT/PER_FER
    assert 'New "Reactor.TRF_TR001A_R" phases=1 bus1=TR001_BT_0.4 R=15 X=0 basefreq=60' in trafos
    assert "kvas=[45 45]" in trafos
    assert _texto(pasta, "Medidores").strip() == (
        'New "Energymeter.M_RJO001" element="Line.CMT_CH008" terminal=1'
    )
    codigos = _texto(pasta, "CodCondutor")
    assert 'New "Linecode.CAB001_3" nphases=3 basefreq=60 r1=0.1900 x1=0.3800 units=km' in codigos
    assert 'New "Line.SMT_SEG001" phases=3 bus1="RJO001_MT_1.1.2.3" bus2="RJO001_MT_2.1.2.3" ' in (
        _texto(pasta, "SegmentosMT")
    )
    assert "length=0.102500000 units=km" in _texto(pasta, "SegmentosMT")
    cargas = _texto(pasta, "CargasBT_DU01")
    assert (
        'New "Load.BT_RM001_M1" bus1="TR001_BT_1.1.4" phases=1 conn=Wye model=2 kv=0.127017059 '
        'kw = 0.1086955 pf=0.92 status=variable vmaxpu=1.5 vminpu=0.5 daily="RES-Tipo3_DU"'
    ) in cargas
    assert 'New "Load.BT_RM001_M2" bus1="TR001_BT_1.1.4" phases=1 conn=Wye model=3' in cargas
    assert '!New "Load.BT_RM003_M1"' in cargas  # sem caminho até a fonte → comentada
    mt = _texto(pasta, "CargasMT_SA01")
    assert (
        'New "Load.MT_PN201_M1" bus1="RJO001_MT_3.1.2.3" phases=3 conn=Delta model=2 kv=13.2'
        in (mt)
    )
    assert 'daily="COM-Tipo1_SA"' in mt
    curvas = _texto(pasta, "CurvaCarga")
    assert curvas.count('New "Loadshape.') == 6
    assert 'New "Loadshape.RES-Tipo3_DO" 24 1 mult=(' in curvas
    master = convertido["RJO001"].masters[0].read_text(encoding="utf-8").splitlines()
    assert master[0] == "clear" and master[1] == 'Redirect "CircuitoMT_gpkg_RJO001.dss"'
    assert 'Redirect "CargasBT_DU01_gpkg_RJO001.dss"' in master
    assert master[-5:] == [
        "Set mode = daily",
        "Set Voltagebases = [0.22 13.2]",
        "Calc Voltagebases",
        "Set tolerance = 0.0001",
        "Set maxcontroliter = 10",
    ]


def test_fluxo_converge(convertido):
    r = run_powerflow(convertido["RJO001"].masters[0])
    assert r.convergiu and r.ajustes == []
    assert r.n_trafos == 2 and r.n_cargas == 6  # (RM001 + RM002 + PN201) × M1/M2; RM003 isolada
    assert 100 < r.potencia_kw < 130  # PN201 ≈ 108,7 kW + BT + perdas
    mt = r.tensoes_mt()
    assert set(mt["ctmt"]) == {"RJO001"} and mt["v_pu"].min() > 1.03
    assert r.n_desenergizados == 0


def test_cluster_com_manobras(convertido, cluster_mini, tmp_path):
    pastas = [convertido["RJO001"].pasta, convertido["RJO002"].pasta]
    base = run_powerflow(montar_master_cluster(pastas, tmp_path / "base.dss"))
    assert base.convergiu and base.n_trafos == 3
    fontes = base.fontes.set_index("fonte")["kw"]
    assert set(fontes.index) == {"source", "rjo002"} and fontes["rjo002"] > 0

    opcao = next(o for o in cluster_mini.restore_options("SEG001") if o.chave == "CH003")
    cmds = comandos_manobras(cluster_mini, opcao.manobras)
    assert cmds[:2] == ["open line.cmt_CH001 term=1", "open line.cmt_CH008 term=1"]
    rest = run_powerflow(montar_master_cluster(pastas, tmp_path / "rest.dss", comandos=cmds))
    assert rest.convergiu
    fontes = rest.fontes.set_index("fonte")["kw"]
    assert fontes["source"] == pytest.approx(0, abs=0.01)  # RJO001 todo transferido/isolado
    assert fontes["rjo002"] > base.fontes.set_index("fonte")["kw"]["rjo002"] + 100
    t = rest.tensoes
    zerados = set(t.loc[(t["fase"] < 4) & (t["v_pu"] == 0), "barra"].str.upper())
    assert {"RJO001_MT_1", "RJO001_MT_2"} <= zerados and "RJO001_MT_4" not in zerados


def test_cli_dss_modo_gpkg(recorte_mini, tmp_path):
    out = tmp_path / "dss"
    js = tmp_path / "fluxo.json"
    r = runner.invoke(
        app,
        ["dss", "--gpkg", str(FIXTURE), "--ctmt", "RJO001", "--out", str(out), "--json", str(js)],
    )
    assert r.exit_code == 0, r.output
    texto = compacto(r)
    assert "RJO001convertidodoGeoPackage" in texto and "3Masters" in texto
    assert "4trechosMT,4chavesMT,2trafos,2trechosBT,3cargasBT,1cargasMT" in texto
    assert (out / "RJO001" / "Master_DU01_gpkg_RJO001.dss").is_file()
    assert json.loads(js.read_text())["n_trafos"] == 2

    # segunda vez reaproveita; --reconverter regenera; sem --ctmt converte todos e monta o cluster
    r = runner.invoke(app, ["dss", "--gpkg", str(FIXTURE), "--ctmt", "RJO001", "--out", str(out),
                            "--sem-fluxo"])  # fmt: skip
    assert r.exit_code == 0 and "jáexistia" in compacto(r)
    r = runner.invoke(app, ["dss", "--gpkg", str(FIXTURE), "--ctmt", "RJO001", "--out", str(out),
                            "--sem-fluxo", "--reconverter"])  # fmt: skip
    assert r.exit_code == 0 and "convertidodoGeoPackage" in compacto(r)
    r = runner.invoke(app, ["dss", "--gpkg", str(FIXTURE), "--out", str(out), "--sem-fluxo"])
    assert r.exit_code == 0, r.output
    assert "CTMTdoGeoPackage:RJO001,RJO002,RJO003" in compacto(r)
    assert (out / "cluster_RJO001-RJO002-RJO003" / "Master_DU01_base.dss").is_file()
    # falha + restauração direto do GPKG do recorte (grafo + modelo), sem conversão prévia
    r = runner.invoke(app, ["dss", "--gpkg", str(recorte_mini), "--out", str(tmp_path / "novo"),
                            "--falha", "SEG001", "--restaurar", "CH003", "--json", str(js)],
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    assert "CTMTdoGeoPackage:RJO001,RJO002" in compacto(r)
    assert "abrirCH001,CH008;fecharCH003" in compacto(r)
    dados = json.loads(js.read_text())
    assert (
        dados["fontes"]["source"] == pytest.approx(0, abs=0.1) and dados["fontes"]["rjo002"] > 100
    )


@pytest.mark.skipif(
    not (TQR0007_GPKG.exists() and TQR0007_REF.exists()),
    reason="recorte e modelo bdgd2opendss de TQR0007 ausentes",
)
def test_paridade_tqr0007_real(tmp_path):
    conv = converter_ctmt(TQR0007_GPKG, "TQR0007", tmp_path, dias=["DU"])
    assert conv.contagem["UCBT_tab"] == 4917 and conv.contagem["PIP"] == 1235
    for prefixo in ("SegmentosMT", "ChavesMT", "SegmentosBT", "ChavesBT", "RamaisBT",
                    "TransformadorMTMTMTBT", "CargasBT_DU01", "CargasMT_DU01"):  # fmt: skip
        meu = [x.strip() for x in _texto(conv.pasta, prefixo).splitlines() if x.strip()]
        (ref,) = TQR0007_REF.glob(f"{prefixo}_*.dss")
        linhas_ref = [x.strip() for x in ref.read_text().splitlines()]
        linhas_ref = [x for x in linhas_ref if x and not x.startswith("!Chave")]
        assert sorted(meu) == sorted(linhas_ref), prefixo
    meu = run_powerflow(conv.masters[0])
    referencia = run_powerflow(escolher_master(TQR0007_REF, "DU", 1))
    assert meu.convergiu and referencia.convergiu
    assert meu.n_cargas == referencia.n_cargas == 12312
    assert meu.perdas_kw == pytest.approx(referencia.perdas_kw, rel=1e-3)
    a = meu.tensoes_mt().set_index(["barra", "fase"])["v_pu"]
    b = referencia.tensoes_mt().set_index(["barra", "fase"])["v_pu"]
    assert (a - b).abs().max() < 1e-6
