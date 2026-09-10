"""Testes do gêmeo OpenDSS (extra `twin`): fluxo de potência no IEEE 13 barras e utilitários de
conversão. Pulados se o opendssdirect não estiver instalado (`uv sync --extra twin`)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytest.importorskip("opendssdirect")

from bdgd_light.cli import app  # noqa: E402
from bdgd_light.twin import (  # noqa: E402
    ESTABILIZADORES,
    PowerFlowResult,
    converter,
    escolher_master,
    listar_masters,
    localizar_pasta,
    run_powerflow,
)

runner = CliRunner()
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
IEEE13 = Path("tests/fixtures/dss/ieee13/IEEE13_Master.dss")
TQR0007 = Path("data/dss/sub__10385871/TQR0007/Master_DU01_202608382_TQR0007_------1-----.dss")


def saida(resultado) -> str:
    return _ANSI.sub("", resultado.output)


def compacto(resultado) -> str:
    return re.sub(r"[\s\u2500-\u259f]+", "", saida(resultado))


@pytest.fixture(scope="module")
def ieee13() -> PowerFlowResult:
    return run_powerflow(IEEE13)


# --- run_powerflow -------------------------------------------------------------------------------


def test_ieee13_converge(ieee13):
    assert ieee13.convergiu
    assert ieee13.ajustes == []
    assert 0 < ieee13.iteracoes <= 15
    assert ieee13.circuito == "ieee13"
    assert (ieee13.n_barras, ieee13.n_nos) == (16, 41)
    assert (ieee13.n_linhas, ieee13.n_trafos, ieee13.n_cargas) == (12, 5, 15)
    assert ieee13.n_desenergizados == 0
    assert ieee13.tempo_s < 5


def test_ieee13_tensoes_e_perdas(ieee13):
    # valores de referência do alimentador de teste IEEE 13 barras (regulador em 1,056 pu)
    assert 0.95 < ieee13.v_min_pu < 0.97
    assert 1.05 < ieee13.v_max_pu < 1.06
    assert ieee13.perdas_kw == pytest.approx(112, abs=5)
    assert ieee13.potencia_kw == pytest.approx(3567, abs=50)
    assert ieee13.potencia_kw > ieee13.perdas_kw > 0
    assert list(ieee13.tensoes.columns) == ["barra", "no", "fase", "kv_base", "v_pu"]
    assert set(ieee13.tensoes["fase"]) <= {1, 2, 3}
    assert ieee13.tensoes.loc[ieee13.tensoes["barra"] == "sourcebus", "kv_base"].iloc[0] == (
        pytest.approx(115 / 3**0.5, rel=1e-3)
    )


def test_ieee13_violacoes(ieee13):
    v = ieee13.violacoes
    assert list(v["tipo"]) == ["sobre", "sobre"]
    assert set(v["barra"]) == {"rg60"}
    assert set(v["no"]) == {"rg60.1", "rg60.3"}
    assert ieee13.resumo()["n_subtensao"] == 0
    assert ieee13.resumo()["n_sobretensao"] == 2
    # faixa mais apertada gera subtensões
    apertado = run_powerflow(IEEE13, vmin=0.97, vmax=1.10)
    assert (apertado.violacoes["tipo"] == "sub").sum() > 0
    assert (apertado.violacoes["tipo"] == "sobre").sum() == 0


def test_ieee13_correntes_e_sobrecargas(ieee13):
    c = ieee13.correntes
    assert list(c.columns) == ["elemento", "tipo", "i_max_a", "i_nominal_a", "carregamento_pct"]
    assert set(c["tipo"]) >= {"Line", "Transformer"}
    s = ieee13.sobrecargas
    assert s["elemento"].iloc[0] == "Line.650632"
    assert s["carregamento_pct"].iloc[0] == pytest.approx(148, abs=3)
    assert s["i_nominal_a"].iloc[0] == pytest.approx(400, abs=1)
    assert "Transformer.xfm1" in set(s["elemento"])
    assert s["carregamento_pct"].is_monotonic_decreasing
    assert ieee13.piores_barras(3)["no"].iloc[0] == "611.3"


def test_resumo_serializavel(ieee13):
    r = ieee13.resumo()
    json.dumps(r)
    assert r["convergiu"] is True
    assert r["n_nos_fase"] == 41
    assert r["n_sobrecargas"] == len(ieee13.sobrecargas)


def test_cwd_restaurado():
    antes = os.getcwd()
    run_powerflow(IEEE13)
    assert os.getcwd() == antes


def test_master_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_powerflow(tmp_path / "nao_existe.dss")


def test_comandos_extra_loadmult():
    leve = run_powerflow(IEEE13, comandos_extra=["set loadmult=0.5"])
    cheio = run_powerflow(IEEE13)
    assert leve.convergiu
    assert leve.potencia_kw < 0.6 * cheio.potencia_kw
    assert leve.perdas_kw < cheio.perdas_kw
    assert leve.v_min_pu > cheio.v_min_pu


def test_estabilizadores_em_cascata():
    # com 2 iterações o método padrão não converge; a cascata deve destravar já no 1º degrau
    sem = run_powerflow(IEEE13, comandos_extra=["set maxiterations=2"], estabilizar=False)
    assert not sem.convergiu
    assert sem.ajustes == []
    com = run_powerflow(IEEE13, comandos_extra=["set maxiterations=2"])
    assert com.convergiu
    assert com.ajustes == [ESTABILIZADORES[0][0]] == ["maxiterations=100"]


def test_comando_invalido_da_erro_claro():
    from bdgd_light.twin.powerflow import ErroOpenDSS

    with pytest.raises(ErroOpenDSS, match="xyz"):
        run_powerflow(IEEE13, comandos_extra=["xyz comando inexistente"])


# --- convert -------------------------------------------------------------------------------------


def _pasta_fake(tmp_path: Path, ctmt: str = "TQR0007") -> Path:
    pasta = tmp_path / "sub__10385871" / ctmt
    pasta.mkdir(parents=True)
    for nome in ("Master_DU01_x.dss", "Master_SA03_x.dss", "Master_DO12_x.dss", "SegmentosMT.dss"):
        (pasta / nome).write_text("! fake\n")
    return pasta


def test_localizar_e_listar_masters(tmp_path):
    pasta = _pasta_fake(tmp_path)
    assert localizar_pasta(tmp_path, "TQR0007") == pasta
    assert localizar_pasta(tmp_path, "OUTRO") is None
    assert [m.name for m in listar_masters(pasta)] == [
        "Master_DO12_x.dss",
        "Master_DU01_x.dss",
        "Master_SA03_x.dss",
    ]


def test_escolher_master(tmp_path):
    pasta = _pasta_fake(tmp_path)
    assert escolher_master(pasta).name == "Master_DU01_x.dss"
    assert escolher_master(pasta, "sa", 3).name == "Master_SA03_x.dss"
    assert escolher_master(pasta, "DO", 12).name == "Master_DO12_x.dss"
    with pytest.raises(FileNotFoundError, match="DU02"):
        escolher_master(pasta, "DU", 2)
    with pytest.raises(ValueError):
        escolher_master(pasta, "XX")
    with pytest.raises(FileNotFoundError, match="nenhum Master"):
        escolher_master(tmp_path)


def test_converter_reaproveita_pasta_existente(tmp_path):
    pasta = _pasta_fake(tmp_path)
    assert converter(tmp_path / "qualquer.gdb", "TQR0007", tmp_path) == (pasta, 0.0)


def test_converter_exige_gdb(tmp_path):
    with pytest.raises(FileNotFoundError, match=".gdb"):
        converter(tmp_path / "nao_existe.gdb", "TQR0007", tmp_path / "out")


# --- CLI -----------------------------------------------------------------------------------------


def test_cli_dss_master(tmp_path):
    js = tmp_path / "fluxo.json"
    r = runner.invoke(app, ["dss", "--master", str(IEEE13), "--json", str(js), "--top", "2"])
    assert r.exit_code == 0, r.output
    texto = compacto(r)
    assert "Convergiusim" in texto
    assert "16barras" in texto and "15cargas" in texto
    assert "0sub,2sobre" in texto
    assert "Line.650632" in texto
    dados = json.loads(js.read_text())
    assert dados["convergiu"] is True
    assert len(dados["sobrecargas"]) == 2
    assert dados["piores_barras"][0]["no"] == "611.3"


def test_cli_dss_nao_convergiu_sai_com_2():
    r = runner.invoke(
        app,
        ["dss", "--master", str(IEEE13), "--comando", "set maxiterations=2", "--sem-estabilizar"],
    )
    assert r.exit_code == 2
    assert "NÃO" in saida(r)


def test_cli_dss_sem_argumentos():
    r = runner.invoke(app, ["dss"])
    assert r.exit_code == 1
    assert "--ctmt" in saida(r) and "--master" in saida(r)
    r = runner.invoke(app, ["dss", "--ctmt", "TQR0007"])
    assert r.exit_code == 1
    assert "--gdb" in saida(r)


def test_cli_dss_sem_fluxo_reaproveita_conversao(tmp_path):
    _pasta_fake(tmp_path)
    r = runner.invoke(
        app,
        ["dss", "--ctmt", "TQR0007", "--gdb", str(tmp_path), "--out", str(tmp_path), "--sem-fluxo"],
    )
    assert r.exit_code == 0, r.output
    assert "já existia" in saida(r)
    assert "Master_DU01_x.dss" in saida(r)


@pytest.mark.skipif(not TQR0007.exists(), reason="Master real de TQR0007 ausente (bdgd-light dss)")
def test_fumaca_tqr0007_real():
    r = run_powerflow(TQR0007)
    assert r.convergiu
    assert r.n_trafos == 82
    assert r.n_cargas > 12_000
    mt = r.tensoes[r.tensoes["kv_base"] > 5]
    assert 1.0 < mt["v_pu"].min() <= mt["v_pu"].max() <= 1.05
