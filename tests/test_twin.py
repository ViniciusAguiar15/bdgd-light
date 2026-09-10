"""Testes do gêmeo OpenDSS (extra `twin`): fluxo de potência no IEEE 13 barras e utilitários de
conversão. Pulados se o opendssdirect não estiver instalado (`uv sync --extra twin`)."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytest.importorskip("opendssdirect")

from rich.console import Console  # noqa: E402

from bdgd_light.cli import app  # noqa: E402
from bdgd_light.grid import (  # noqa: E402
    ABRIR,
    FECHAR,
    ChaveInexistenteError,
    Cluster,
    Feeder,
    manobra,
)
from bdgd_light.ingest.recorte import recortar  # noqa: E402
from bdgd_light.twin import (  # noqa: E402
    ESTABILIZADORES,
    PowerFlowResult,
    comandos_manobras,
    converter,
    escolher_master,
    listar_masters,
    localizar_pasta,
    montar_master_cluster,
    run_powerflow,
)

runner = CliRunner()
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
IEEE13 = Path("tests/fixtures/dss/ieee13/IEEE13_Master.dss")
CLUSTER_MINI = Path("tests/fixtures/dss/cluster_mini")
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


def test_cli_dss_sem_argumentos(tmp_path):
    r = runner.invoke(app, ["dss"])
    assert r.exit_code == 1
    assert "--ctmt" in saida(r) and "--master" in saida(r)
    # sem --gdb e sem modelo convertido em --out (vazio, para não depender de data/dss local)
    r = runner.invoke(app, ["dss", "--ctmt", "TQR0007", "--out", str(tmp_path)])
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


# --- cluster + manobras do grafo -----------------------------------------------------------------


@pytest.fixture(scope="module")
def grafos(parquet_mini, tmp_path_factory) -> dict[str, Path]:
    out = tmp_path_factory.mktemp("twin_grid")
    resultado = recortar(parquet_mini, ["RJO001", "RJO002"], out, console=Console(quiet=True))
    return {r.nome: r.gpkg for r in resultado.recortes} | {"cluster": resultado.cluster.gpkg}


@pytest.fixture
def cluster_mini(grafos) -> Cluster:
    return Cluster.from_gpkg(grafos["cluster"])


def _nos_zerados(r: PowerFlowResult) -> set[str]:
    t = r.tensoes
    return set(t.loc[(t["fase"] < 4) & (t["v_pu"] == 0), "barra"].str.upper())


def test_comandos_manobras(cluster_mini: Cluster, grafos):
    opcao = next(o for o in cluster_mini.restore_options("SEG001") if o.chave == "CH003")
    cmds = comandos_manobras(cluster_mini, opcao.manobras)
    assert cmds[:2] == ["open line.cmt_CH001 term=1", "open line.cmt_CH008 term=1"]
    # NA sai comentada do bdgd2opendss: fechar = criar a Line da chave + jumper até o PAC_VIZ da tie
    assert cmds[2].startswith('New "Line.CMT_CH003" phases=3 bus1="RJO001_MT_')
    assert 'bus1="RJO001_MT_5.1.2.3" bus2="RJO001_MT_7.1.2.3"' in cmds[2] or (
        'bus1="RJO001_MT_7.1.2.3" bus2="RJO001_MT_5.1.2.3"' in cmds[2]
    )
    assert "switch=T" in cmds[2]
    assert cmds[3].startswith('New "Line.TIE_CH003_1" phases=3 bus1="RJO001_MT_7.1.2.3" ')
    assert 'bus2="RJO002_MT_5.1.2.3"' in cmds[3]
    assert len(cmds) == 4
    # NF fechada explicitamente → close; abrir uma NA não gera nada (já está fora do modelo)
    assert comandos_manobras(cluster_mini, [manobra(FECHAR, "CH001")]) == [
        "close line.cmt_CH001 term=1"
    ]
    assert comandos_manobras(cluster_mini, [manobra(ABRIR, "CH003")]) == []
    with pytest.raises(ChaveInexistenteError):
        comandos_manobras(cluster_mini, [manobra(ABRIR, "CH999")])
    with pytest.raises(ValueError, match="religar"):
        comandos_manobras(cluster_mini, [{"acao": "religar", "chave": "CH001"}])
    # num Feeder isolado o vizinho é um nó EXT: → sem jumper (não existe no modelo do CTMT)
    feeder = Feeder.from_gpkg(grafos["RJO001"])
    so_chave = comandos_manobras(feeder, [manobra(FECHAR, "CH003")])
    assert len(so_chave) == 1 and so_chave[0].startswith('New "Line.CMT_CH003"')


def test_montar_master_cluster_texto(tmp_path):
    pastas = [CLUSTER_MINI / "RJO001", CLUSTER_MINI / "RJO002"]
    out = montar_master_cluster(pastas, tmp_path / "m.dss", comandos=["open line.cmt_CH001 term=1"])
    texto = out.read_text()
    linhas = texto.splitlines()
    assert linhas[0] == "clear"
    assert 'New "Circuit.cluster_RJO001-RJO002" basekv=13.2' in texto
    assert 'bus1="RJO001_MT_0"' in texto and 'New "Vsource.RJO002" basekv=13.2' in texto
    assert 'bus1="RJO002_MT_0"' in texto
    assert texto.index("Set AllowDuplicates=yes") > texto.index('New "Circuit.')
    redirects = [ln for ln in linhas if ln.startswith("Redirect")]
    assert len(redirects) == 13  # 7 de RJO001 (com CargasMT) + 6 de RJO002 (sem UCMT)
    assert sum("CargasMT_DU01" in ln for ln in redirects) == 1
    assert not any("GD_BT" in ln for ln in redirects)
    assert not any("Master_" in ln or "CircuitoMT" in ln for ln in redirects)
    assert texto.index("open line.cmt_CH001 term=1") < texto.index("Calcvoltagebases")
    assert "Set Voltagebases=[0.22 13.2]" in texto and linhas[-1] == "Set mode=snapshot"

    com_gd = montar_master_cluster(pastas, tmp_path / "gd.dss", gd=True, nome="teste").read_text()
    assert 'New "Circuit.teste"' in com_gd and com_gd.count("GD_BT") == 2
    with pytest.raises(FileNotFoundError, match="CargasBT_SA02"):
        montar_master_cluster(pastas, tmp_path / "x.dss", dia="SA", mes=2)
    with pytest.raises(ValueError):
        montar_master_cluster([], tmp_path / "x.dss")
    with pytest.raises(FileNotFoundError, match="CircuitoMT"):
        montar_master_cluster([tmp_path], tmp_path / "x.dss")


def test_flisr_no_gemeo(cluster_mini: Cluster, tmp_path):
    pastas = [CLUSTER_MINI / "RJO001", CLUSTER_MINI / "RJO002"]
    base = run_powerflow(montar_master_cluster(pastas, tmp_path / "base.dss"))
    assert base.convergiu and base.ajustes == []
    assert base.n_desenergizados == 0 and base.n_trafos == 3 and base.n_cargas == 4
    fontes = base.fontes.set_index("fonte")["kw"]
    assert set(fontes.index) == {"source", "rjo002"}
    assert fontes["source"] == pytest.approx(302, abs=2)  # RJO001: 30 + 50 kW BT + 200 kW UCMT
    assert fontes["rjo002"] == pytest.approx(83, abs=2)
    mt = base.tensoes_mt()
    assert set(mt["ctmt"]) == {"RJO001", "RJO002"} and mt["v_pu"].min() > 1.04
    # o GD_BT com `generator. ` (nome em branco) repetido só compila com AllowDuplicates
    com_gd = run_powerflow(montar_master_cluster(pastas, tmp_path / "gd.dss", gd=True))
    assert com_gd.convergiu and com_gd.potencia_kw < base.potencia_kw

    opcao = next(o for o in cluster_mini.restore_options("SEG001") if o.chave == "CH003")
    isolamento = comandos_manobras(cluster_mini, opcao.manobras[:-1])
    iso_master = montar_master_cluster(pastas, tmp_path / "iso.dss", comandos=isolamento)
    isolado = run_powerflow(iso_master)
    assert isolado.convergiu
    zerados = _nos_zerados(isolado)
    assert {f"RJO001_MT_{i}" for i in (1, 2, 3, 4, 5, 6)} <= zerados
    assert "RJO001_MT_0" not in zerados and not any(b.startswith("RJO002") for b in zerados)
    assert isolado.fontes.set_index("fonte")["kw"]["source"] == pytest.approx(0, abs=0.01)

    restauracao = comandos_manobras(cluster_mini, opcao.manobras)
    rest = run_powerflow(montar_master_cluster(pastas, tmp_path / "rest.dss", comandos=restauracao))
    assert rest.convergiu
    zerados = _nos_zerados(rest)
    assert zerados == {"RJO001_MT_1", "RJO001_MT_2", "TR003_BT_1"}  # só a zona da falta (SEG001)
    fontes = rest.fontes.set_index("fonte")["kw"]
    assert fontes["source"] == pytest.approx(0, abs=0.01)
    # RJO002 assume TR001 (50 kW) e a UCMT (200 kW) além dos seus 80 kW; só TR003 fica sem energia
    assert 83 + 50 + 200 < fontes["rjo002"] < base.potencia_kw - 30
    assert rest.tensoes_mt().query("ctmt == 'RJO001'")["v_pu"].min() > 1.03
    assert rest.sobrecargas.empty  # tronco de 200 A: os ~15 A transferidos não sobrecarregam
    correntes = rest.correntes.set_index("elemento")["i_max_a"]  # nomes em minúsculas (OpenDSS)
    assert correntes["Line.cmt_ch009"] > correntes["Line.cmt_ch008"] == pytest.approx(0, abs=0.01)
    assert correntes["Line.tie_ch003_1"] == pytest.approx(correntes["Line.cmt_ch003"], rel=0.01)
    assert correntes["Line.cmt_ch003"] > 10  # ~250 kW a 13,2 kV


def test_cli_dss_cluster_com_falha_e_restauracao(grafos, tmp_path):
    out = tmp_path / "dss"
    shutil.copytree(CLUSTER_MINI, out)  # modelos "já convertidos" em <out>/<CTMT>/
    js = tmp_path / "fluxo.json"
    r = runner.invoke(
        app,
        [
            "dss", "--ctmt", "RJO001,RJO002", "--out", str(out), "--gpkg", str(grafos["cluster"]),
            "--falha", "SEG001", "--restaurar", "CH003", "--json", str(js),
        ],
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    texto = saida(r)
    assert "já existia" in texto and "Master_DU01_falha_SEG001_via_CH003.dss" in texto
    assert "abrir CH001, CH008; fechar CH003" in texto
    assert "open line.cmt_CH001 term=1" in texto and 'New "Line.TIE_CH003_1"' in texto
    assert "Por fonte" in texto and "rjo002" in texto and "Tensão MT por alimentador" in texto
    dados = json.loads(js.read_text())
    assert dados["fontes"]["source"] == pytest.approx(0, abs=0.1)
    assert dados["fontes"]["rjo002"] > 330
    assert (out / "cluster_RJO001-RJO002" / "Master_DU01_falha_SEG001_via_CH003.dss").exists()

    # sem --gdb e sem modelo convertido → erro claro; chave que não restaura → erro claro
    r = runner.invoke(app, ["dss", "--ctmt", "RJO009", "--out", str(out)])
    assert r.exit_code == 1 and "--gdb" in saida(r)
    r = runner.invoke(
        app,
        ["dss", "--ctmt", "RJO001", "--out", str(out), "--gpkg", str(grafos["cluster"]),
         "--falha", "SEG001", "--restaurar", "CH002"],
    )  # fmt: skip
    assert r.exit_code == 1 and "não restaura" in saida(r)
    r = runner.invoke(app, ["dss", "--master", str(IEEE13), "--falha", "SEG001"])
    assert r.exit_code == 1 and "--gpkg" in saida(r)
    # manobras avulsas num único CTMT: Master próprio com o cenário "manobras"
    r = runner.invoke(
        app,
        ["dss", "--ctmt", "RJO001", "--out", str(out), "--gpkg", str(grafos["RJO001"]),
         "--abrir", "CH001", "--sem-fluxo"],
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    assert "RJO001/Master_DU01_manobras.dss" in compacto(r)


@pytest.mark.skipif(not TQR0007.exists(), reason="Master real de TQR0007 ausente (bdgd-light dss)")
def test_fumaca_tqr0007_real():
    r = run_powerflow(TQR0007)
    assert r.convergiu
    assert r.n_trafos == 82
    assert r.n_cargas > 12_000
    mt = r.tensoes[r.tensoes["kv_base"] > 5]
    assert 1.0 < mt["v_pu"].min() <= mt["v_pu"].max() <= 1.05
