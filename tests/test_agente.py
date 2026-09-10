"""Testes do agente orquestrador + verificador HITL (issue #34) sobre o cluster_mini: descritores
das ferramentas expostas ao modelo, exemplos anotados (top-K), checagens do verificador, laço com
``FakeLLMClient`` roteirizado (proposta certa, recusa → replanejamento, uma proposta por execução),
operador fake por tipo de evento, métricas/auditoria e o comando ``bdgd-light agente``."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

if importlib.util.find_spec("opendssdirect") is None:  # não importar: ver twin.powerflow.no_motor
    pytest.skip("opendssdirect não instalado (uv sync --extra twin)", allow_module_level=True)
pytest.importorskip("yaml")

from rich.console import Console  # noqa: E402

from bdgd_light.agent import FakeLLMClient, Text, ToolCall, ToolCalls  # noqa: E402
from bdgd_light.agent.orquestrador import (  # noqa: E402
    EXEMPLOS_PADRAO,
    FERRAMENTAS_MODELO,
    Exemplo,
    Orquestrador,
    Verificador,
    carregar_exemplos,
    especificacoes,
    fake_operador,
    montar_prompt_sistema,
    selecionar_exemplos,
)
from bdgd_light.cli import app  # noqa: E402
from bdgd_light.grid import Cluster  # noqa: E402
from bdgd_light.ingest.recorte import recortar  # noqa: E402
from bdgd_light.mcp_server import SessaoCOD, SessaoError  # noqa: E402
from bdgd_light.sim import CENARIOS, Evento, FilaEventos, Simulador  # noqa: E402

CLUSTER_MINI = Path("tests/fixtures/dss/cluster_mini")
TAQUARA = Path("data/feeders/cluster_TQR0007-TQR33859-TQR33862.gpkg")
runner = CliRunner()


@pytest.fixture(scope="module")
def recorte(parquet_mini, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("agente_feeders")
    resultado = recortar(parquet_mini, ["RJO001", "RJO002"], out, console=Console(quiet=True))
    return resultado.cluster.gpkg


@pytest.fixture(scope="module")
def rede(recorte) -> Cluster:
    return Cluster.from_gpkg(recorte)


@pytest.fixture
def dss_out(tmp_path) -> Path:
    destino = tmp_path / "dss"
    shutil.copytree(CLUSTER_MINI, destino)
    return destino


@pytest.fixture
def sessao(recorte, dss_out, tmp_path) -> SessaoCOD:
    return SessaoCOD(feeders=recorte.parent, dss_out=dss_out, estado_dir=tmp_path / "estado")


@pytest.fixture
def simulador(rede, recorte) -> Simulador:
    return Simulador(rede, recorte.stem, seed=7)


def tc(nome: str, **argumentos) -> ToolCalls:
    return ToolCalls((ToolCall(f"c-{nome}", nome, argumentos),), modelo="fake-roteiro")


def registros(sessao: SessaoCOD) -> list[dict]:
    return [json.loads(linha) for linha in sessao.audit.caminho.read_text().splitlines()]


# -- descritores ------------------------------------------------------------------------------


def test_especificacoes_nao_expoem_set_switch():
    specs = especificacoes()
    nomes = [s.name for s in specs]
    assert nomes == list(FERRAMENTAS_MODELO)
    assert "set_switch" not in nomes and "load_cluster" not in nomes
    assert {"locate_fault", "isolate_fault", "restore_options", "propose_plan"} <= set(nomes)
    por_nome = {s.name: s for s in specs}
    fluxo = por_nome["run_powerflow"].parameters
    assert fluxo["type"] == "object"
    assert fluxo["properties"]["manobras"]["type"] == "array"
    assert fluxo["properties"]["manobras"]["items"]["type"] == "object"
    assert fluxo["properties"]["loadmult"]["type"] == "number"
    assert "required" not in fluxo or "loadmult" not in fluxo["required"]
    assert por_nome["get_proposal"].parameters["required"] == ["proposta_id"]
    assert por_nome["restore_options"].parameters["properties"]["score"]["type"] == "boolean"
    for s in specs:
        assert s.description, s.name
        for prop in s.parameters["properties"].values():
            assert prop.get("description"), s.name


# -- exemplos -----------------------------------------------------------------------------------


def test_exemplos_padrao_carregam_e_selecionam_por_tipo():
    exemplos = carregar_exemplos()
    assert EXEMPLOS_PADRAO.exists() and len(exemplos) >= 10
    ids = [e.id for e in exemplos]
    assert len(set(ids)) == len(ids)
    assert all(e.tarefa and e.justificativa for e in exemplos)
    for tipo in ("falta_permanente", "falta_transitoria", "pico_carga", "chave_indisponivel"):
        escolhidos = selecionar_exemplos(exemplos, "", 3, tipo=tipo)
        assert tipo in escolhidos[0].tags, tipo
    pergunta = selecionar_exemplos(exemplos, "quantos clientes ficam sem tensão se a chave abrir")
    assert pergunta[0].id == "pergunta_clientes_jusante"
    assert selecionar_exemplos(exemplos, "qualquer coisa", 0) == []
    assert carregar_exemplos(Path("/nao/existe.yaml")) == []


def test_carregar_exemplos_aceita_lista_ou_mapa(tmp_path):
    lista = tmp_path / "lista.yaml"
    lista.write_text(
        "- id: a\n  tarefa: t\n  ferramentas: [x]\n  justificativa: j\n  tags: [k]\n"
        "- id: b\n  tarefa: t2\n  ferramentas: []\n  justificativa: j2\n"
    )
    mapa = tmp_path / "mapa.yaml"
    mapa.write_text("exemplos:\n  - id: c\n    tarefa: t\n    ferramentas: [x, y]\n")
    assert [e.id for e in carregar_exemplos(lista)] == ["a", "b"]
    (c,) = carregar_exemplos(mapa)
    assert c.ferramentas == ("x", "y") and c.tags == () and c.justificativa == ""
    ruim = tmp_path / "ruim.yaml"
    ruim.write_text("- id: sem_tarefa\n")
    with pytest.raises(ValueError, match="sem 'tarefa'"):
        carregar_exemplos(ruim)
    ruim.write_text("texto solto\n")
    with pytest.raises(ValueError, match="lista"):
        carregar_exemplos(ruim)


def test_prompt_sistema_inclui_regras_e_exemplos():
    ex = Exemplo("x1", "tarefa X", ("locate_fault",), "porque sim", ("t",))
    prompt = montar_prompt_sistema([ex])
    assert "set_switch" in prompt and "propose_plan" in prompt
    assert "[x1] Tarefa: tarefa X" in prompt and "locate_fault" in prompt
    assert "Exemplos anotados" in prompt and "Exemplos anotados" not in montar_prompt_sistema([])


# -- verificador --------------------------------------------------------------------------------


def test_verificador_sem_falta_recusa(sessao, recorte):
    sessao.load_cluster(str(recorte))
    v = Verificador().verificar(sessao, "CH003")
    assert v.ok is False and v.checagens == {"falta_registrada": False}


def test_verificador_checagens_no_cluster_mini(sessao, recorte):
    sessao.load_cluster(str(recorte))
    sessao.inject_fault("SEG001")
    iso = sessao.isolate_fault()
    ops = sessao.restore_options(score=True)["opcoes"]
    ver = Verificador()

    ok = ver.verificar(sessao, "CH003", opcoes=ops, isolamento=iso)
    assert ok.ok is True and ok.problemas == [] and ok.eletrico is True
    assert all(ok.checagens.values())
    assert {"opcao_em_restore_options", "abre_antes_de_fechar", "fronteira_isolada"} <= set(
        ok.checagens
    )
    assert {"convergiu", "tensao_mt", "corrente_disjuntor", "viavel"} <= set(ok.checagens)

    fora = ver.verificar(sessao, "CH999", opcoes=ops, isolamento=iso)
    assert fora.ok is False and fora.checagens["opcao_em_restore_options"] is False
    assert "CH999" in fora.problemas[0] and "CH003, CH005" in fora.problemas[0]

    indisponivel = Verificador(indisponiveis={"CH003"}).verificar(
        sessao, "CH003", opcoes=ops, isolamento=iso
    )
    assert indisponivel.ok is False and indisponivel.checagens["chaves_disponiveis"] is False

    so_isolar = ver.verificar(sessao, None, opcoes=ops, isolamento=iso)
    assert so_isolar.ok is True and so_isolar.eletrico is False
    assert so_isolar.avisos and "opção viável não usada" in so_isolar.avisos[0]

    # sem resultados prévios, o verificador consulta a sessão sozinho
    assert ver.verificar(sessao, "CH005").ok is True


def test_verificador_sequencia_e_score_sinteticos(sessao, recorte):
    sessao.load_cluster(str(recorte))
    sessao.inject_fault("SEG001")
    iso = sessao.isolate_fault()
    ops = sessao.restore_options(score=True)["opcoes"]
    boa = dict(ops[0])
    ver = Verificador()

    invertida = {**boa, "manobras": list(reversed(boa["manobras"]))}
    v = ver.verificar(sessao, boa["chave"], opcoes=[invertida], isolamento=iso)
    assert v.checagens["abre_antes_de_fechar"] is False

    sem_fronteira = {**boa, "manobras": [m for m in boa["manobras"] if m["acao"] != "abrir"]}
    v = ver.verificar(sessao, boa["chave"], opcoes=[sem_fronteira], isolamento=iso)
    assert v.checagens["fronteira_isolada"] is False and "CH001" in v.problemas[0]

    fantasma = {**boa, "manobras": boa["manobras"] + [{"acao": "fechar", "chave": "CHX"}]}
    v = ver.verificar(sessao, boa["chave"], opcoes=[fantasma], isolamento=iso)
    assert v.checagens["chaves_existem"] is False

    inviavel = {
        **boa,
        "score": {
            **boa["score"],
            "viavel": False,
            "vmin_mt_pu": 0.80,
            "margem_disjuntor": -0.1,
            "sobrecargas_mt": [{"elemento": "Line.x", "carregamento_pct": 140}],
            "motivos": ["disjuntor acima da nominal"],
        },
    }
    v = ver.verificar(sessao, boa["chave"], opcoes=[inviavel], isolamento=iso)
    assert v.ok is False
    assert v.checagens["tensao_mt"] is False and v.checagens["corrente_disjuntor"] is False
    assert v.checagens["sem_sobrecarga_mt"] is False and v.checagens["viavel"] is False

    sem_score = {**boa, "score": None}
    v = ver.verificar(sessao, boa["chave"], opcoes=[sem_score], isolamento=iso)
    assert v.ok is False and v.checagens["score_eletrico"] is False
    v = Verificador(exigir_score=False).verificar(
        sessao, boa["chave"], opcoes=[sem_score], isolamento=iso
    )
    assert v.ok is True and v.eletrico is False

    # opção viável com margem claramente maior vira aviso, não recusa
    melhor = {**ops[1], "score": {**ops[1]["score"], "margem_disjuntor": 0.999}}
    pior = {**boa, "score": {**boa["score"], "margem_disjuntor": 0.5}}
    v = ver.verificar(sessao, boa["chave"], opcoes=[pior, melhor], isolamento=iso)
    assert v.ok is True and any("margem maior" in a for a in v.avisos)


# -- laço roteirizado ---------------------------------------------------------------------------


def test_roteiro_falta_permanente_gera_proposta_certa(sessao, simulador):
    ev = simulador.falta_permanente("SEG001")
    roteiro = [
        tc("locate_fault"),
        tc("isolate_fault"),
        tc("restore_options", score=True),
        tc("propose_plan", chave="CH003", justificativa="maior margem"),
        Text("Proposta P-0001: abrir CH001 e fechar CH003.", modelo="fake-roteiro"),
    ]
    orq = Orquestrador(sessao, FakeLLMClient(roteiro), provider="fake")
    assert "set_switch" not in [f.name for f in orq._ferramentas()]
    assert "inject_fault" in [f.name for f in orq._ferramentas()]

    ex = orq.executar_evento(ev)
    assert ex.sequencia == ["locate_fault", "isolate_fault", "restore_options", "propose_plan"]
    assert ex.proposta["id"] == "P-0001" and ex.proposta["chave"] == "CH003"
    assert ex.proposta["manobras"] == [
        {"acao": "abrir", "chave": "CH001"},
        {"acao": "fechar", "chave": "CH003"},
    ]
    assert ex.proposta["status"] == "pendente" and ex.proposta["token"] is None
    assert ex.veredito["ok"] is True and ex.recusas == []
    assert ex.rodadas == 5 and ex.replanejamentos == 0 and ex.erro is None
    assert ex.modelo == "fake-roteiro" and ex.exemplos and ex.hash_auditoria
    assert ex.tipo == "evento" and ex.evento == ev.to_dict() and ex.cluster == sessao.nome
    assert ex.uso["total_tokens"] == 0 and ex.segundos_total >= ex.segundos_llm >= 0
    assert all("segundos" in f for f in ex.ferramentas)
    d = ex.to_dict()
    assert d["sequencia"] == ex.sequencia and d["n_ferramentas"] == 4

    regs = registros(sessao)
    tipos = [r["tipo"] for r in regs]
    ferramentas = [r["dados"].get("ferramenta") for r in regs if r["tipo"] == "mcp.chamada"]
    assert ferramentas[:2] == ["load_cluster", "inject_fault"]  # preparação do orquestrador
    assert "set_switch" not in ferramentas
    assert "agente.inicio" in tipos and "agente.verificador.ok" in tipos
    assert tipos[-1] == "agente.fim" and regs[-1]["hash"] == ex.hash_auditoria
    assert sessao.audit.verificar() == len(tipos)

    # a falta foi injetada pelo orquestrador, não pelo modelo; nada foi manobrado
    assert sessao.falta == "SEG001"
    assert sessao.get_switch_state("CH001")["estado"] == "fechada"
    assert sessao.get_proposal("P-0001")["status"] == "pendente"


def test_roteiro_recusa_do_verificador_leva_a_replanejar(sessao, simulador):
    ev = simulador.falta_permanente("SEG001")
    roteiro = [
        tc("locate_fault"),
        tc("isolate_fault"),
        tc("restore_options", score=True),
        tc("propose_plan", chave="CH999"),
        tc("propose_plan", chave="CH005", justificativa="segunda opção"),
        tc("propose_plan", chave="CH003"),  # segunda proposta na mesma execução: recusada
        Text("Proposta P-0001 por CH005.", modelo="fake-roteiro"),
    ]
    orq = Orquestrador(sessao, FakeLLMClient(roteiro), provider="fake")
    ex = orq.executar_evento(ev)
    assert ex.sequencia.count("propose_plan") == 3
    assert [r["chave"] for r in ex.recusas] == ["CH999"]
    assert ex.recusas[0]["checagens"]["opcao_em_restore_options"] is False
    assert ex.proposta["id"] == "P-0001" and ex.proposta["chave"] == "CH005"
    assert ex.ferramentas[-1]["ok"] is False and ex.ferramentas[-1]["erro"] == "já há proposta"
    assert len(sessao.propostas.listar()) == 1
    assert "agente.verificador.recusa" in [r["tipo"] for r in registros(sessao)]


def test_roteiro_sem_proposta_pede_replanejamento(sessao, simulador):
    ev = simulador.falta_permanente("SEG001")
    roteiro = [
        tc("locate_fault"),
        Text("Não vejo o que fazer.", modelo="fake-roteiro"),
        tc("isolate_fault"),
        tc("restore_options", score=True),
        tc("propose_plan", chave="CH003"),
        Text("Agora sim: P-0001.", modelo="fake-roteiro"),
    ]
    orq = Orquestrador(sessao, FakeLLMClient(roteiro), provider="fake", replanejamentos=2)
    ex = orq.executar_evento(ev)
    assert ex.replanejamentos == 1 and ex.proposta["id"] == "P-0001"
    assert ex.resposta == "Agora sim: P-0001."

    sessao.load_cluster(str(sessao.gpkg))
    teimoso = FakeLLMClient([Text("nada", modelo="x")] * 5)
    ex2 = Orquestrador(sessao, teimoso, provider="fake", replanejamentos=1).executar_evento(ev)
    assert ex2.proposta is None and ex2.replanejamentos == 1 and ex2.erro
    assert "sem proposta" in ex2.erro


def test_roteiro_esgota_rodadas_registra_erro(sessao, simulador):
    ev = simulador.falta_permanente("SEG001")
    insistente = FakeLLMClient([tc("locate_fault")] * 20)
    orq = Orquestrador(sessao, insistente, provider="fake", max_rodadas=3, replanejamentos=0)
    ex = orq.executar_evento(ev)
    assert ex.erro and ex.proposta is None and ex.rodadas >= 3
    assert [r["tipo"] for r in registros(sessao)][-1] == "agente.fim"


# -- operador fake por tipo de evento --------------------------------------------------------------


def test_fake_operador_falta_permanente(sessao, simulador):
    ev = simulador.falta_permanente("SEG001")
    ex = Orquestrador(sessao, fake_operador(), provider="fake").executar_evento(ev)
    assert ex.sequencia == ["locate_fault", "isolate_fault", "restore_options", "propose_plan"]
    assert ex.proposta["chave"] == "CH003" and ex.proposta["fonte"] == "RJO002"
    assert ex.veredito["ok"] is True and ex.veredito["eletrico"] is True
    assert "Proposta P-0001" in ex.resposta and "bdgd-light aprovar P-0001" in ex.resposta
    assert "Alternativas descartadas: CH005" in ex.resposta


def test_fake_operador_falta_sem_opcao(sessao, simulador):
    ev = simulador.falta_permanente("SEG002")  # a jusante de CH001: sem NA para restaurar
    ex = Orquestrador(sessao, fake_operador(), provider="fake").executar_evento(ev)
    assert ex.proposta is not None and ex.proposta["chave"] is None
    assert ex.veredito["ok"] is True and ex.recusas == []
    assert "sem opção viável" in ex.resposta


def test_fake_operador_chave_indisponivel_bloqueia_plano(sessao, simulador):
    orq = Orquestrador(sessao, fake_operador(), provider="fake")
    ex1 = orq.executar_evento(simulador.chave_indisponivel("CH003"))
    assert ex1.proposta is None and orq.indisponiveis == {"CH003"}
    assert ex1.resposta and ex1.evento["tipo"] == "chave_indisponivel"

    ex2 = orq.executar_evento(simulador.falta_permanente("SEG001"))
    assert [r["chave"] for r in ex2.recusas] == ["CH003"]
    assert ex2.recusas[0]["checagens"]["chaves_disponiveis"] is False
    assert ex2.proposta["chave"] == "CH005"
    assert ex2.sequencia.count("propose_plan") == 2


def test_fake_operador_transitoria_e_pico(sessao, simulador):
    orq = Orquestrador(sessao, fake_operador(), provider="fake")
    ex = orq.executar_evento(simulador.falta_transitoria("SEG003"))
    assert ex.proposta is None and ex.n_ferramentas == 0 and "religou" in ex.resposta.lower()
    assert sessao.falta is None

    pico = simulador.pico_carga("RJO001")
    ex = orq.executar_evento(pico)
    assert ex.sequencia == ["run_powerflow"]
    assert ex.ferramentas[0]["argumentos"]["loadmult"] == pico.detalhes["loadmult"]
    assert "loadmult" in ex.resposta and ex.proposta is None


def test_fake_operador_pergunta_e_evento_como_dict(sessao, recorte, simulador):
    orq = Orquestrador(sessao, fake_operador(), provider="fake")
    ex = orq.responder("quantos km tem o alimentador RJO001?", cluster=str(recorte))
    assert ex.tipo == "pergunta" and ex.sequencia == ["get_topology"]
    assert ex.resposta and ex.proposta is None and "pergunta_topologia" in ex.exemplos

    ev = simulador.falta_permanente("SEG001").to_dict()
    ex2 = orq.executar_evento(ev)
    assert ex2.proposta["id"] == "P-0001" and ex2.evento == ev

    with pytest.raises(SessaoError, match="nenhum cluster"):
        Orquestrador(
            SessaoCOD(feeders=recorte.parent, dss_out=recorte.parent, estado_dir=None),
            fake_operador(),
        ).responder("oi")


# -- CLI ----------------------------------------------------------------------------------------


def _args(recorte: Path, dss_out: Path, tmp_path: Path) -> list[str]:
    return [
        "--provider",
        "fake",
        "--feeders",
        str(recorte.parent),
        "--dss-out",
        str(dss_out),
        "--estado",
        str(tmp_path / "estado"),
    ]


def test_cli_agente_evento_inline_e_json(recorte, dss_out, tmp_path, simulador):
    ev = json.dumps(simulador.falta_permanente("SEG001").to_dict(), ensure_ascii=False)
    r = runner.invoke(
        app, ["agente", "--evento", ev, *_args(recorte, dss_out, tmp_path)], env={"COLUMNS": "200"}
    )
    assert r.exit_code == 0, r.output
    assert "Proposta P-0001" in r.output and "fechar CH003" in r.output
    assert "Verificador: ok" in r.output and "fake-operador" in r.output

    saida = tmp_path / "exec.json"
    r = runner.invoke(
        app,
        ["agente", "--evento", ev, "--json", "--saida", str(saida)]
        + _args(recorte, dss_out, tmp_path),
    )
    assert r.exit_code == 0, r.output
    d = json.loads(saida.read_text())
    assert d["proposta"]["id"] == "P-0002" and d["sequencia"][-1] == "propose_plan"
    assert d["veredito"]["ok"] is True and d["hash_auditoria"]
    assert json.loads(r.output)["proposta"]["id"] == "P-0002"


def test_cli_agente_fila_pergunta_e_erros(recorte, dss_out, tmp_path, simulador):
    fila = tmp_path / "eventos.jsonl"
    ev = FilaEventos(fila).publicar(simulador.pico_carga("RJO002"))
    assert ev.id == "E-0001"
    r = runner.invoke(
        app,
        ["agente", "--evento", ev.id, "--fila", str(fila), *_args(recorte, dss_out, tmp_path)],
    )
    assert r.exit_code == 0, r.output
    assert "run_powerflow" in r.output and "pico_carga" in r.output

    r = runner.invoke(
        app,
        ["agente", "--evento", str(fila), *_args(recorte, dss_out, tmp_path)],
    )
    assert r.exit_code == 0, r.output

    r = runner.invoke(
        app,
        ["agente", "--pergunta", "quantas chaves?", "--cluster", str(recorte)]
        + _args(recorte, dss_out, tmp_path),
    )
    assert r.exit_code == 0, r.output
    assert "get_topology" in r.output

    r = runner.invoke(app, ["agente", *_args(recorte, dss_out, tmp_path)])
    assert r.exit_code == 1 and "exatamente um" in r.output
    r = runner.invoke(app, ["agente", "--pergunta", "oi", *_args(recorte, dss_out, tmp_path)])
    assert r.exit_code == 1 and "--cluster" in r.output
    r = runner.invoke(app, ["agente", "--cenario", "xyz", *_args(recorte, dss_out, tmp_path)])
    assert r.exit_code == 1 and "desconhecido" in r.output
    r = runner.invoke(
        app,
        ["agente", "--evento", "E-9999", "--fila", str(fila)] + _args(recorte, dss_out, tmp_path),
    )
    assert r.exit_code == 1 and "E-9999" in r.output


# -- cenário nomeado com dados reais (só quando o recorte existe localmente) ----------------------


@pytest.mark.skipif(
    not TAQUARA.exists(), reason="recorte de Taquara ausente (data/ não versionado)"
)
def test_cenario_taquara_bocari_com_operador_fake(tmp_path):
    cen = CENARIOS["taquara_bocari"]
    ev = Simulador(None, cen.cluster).cenario("taquara_bocari")
    assert ev.trecho == "11798327"
    sessao = SessaoCOD(feeders=TAQUARA.parent, dss_out=tmp_path, estado_dir=tmp_path / "estado")
    orq = Orquestrador(sessao, fake_operador(), provider="fake", exigir_score=False)
    ex = orq.executar_evento(ev)
    assert ex.sequencia == ["locate_fault", "isolate_fault", "restore_options", "propose_plan"]
    assert ex.proposta["chave"] in {"1007642983", "789941518"}  # PARNAIBA ou CURUMAU
    assert ex.veredito["ok"] is True and ex.veredito["eletrico"] is False


def test_evento_de_dict_preserva_id(simulador):
    ev = simulador.falta_permanente("SEG001")
    assert Evento.de_dict(ev.to_dict()) == ev
