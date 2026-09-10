"""Testes do servidor MCP (extra `agent` + `twin`): domínio ``SessaoCOD`` no cluster_mini
(inject → locate → isolate → restore_options → propose → set_switch recusado → approve →
set_switch ok, com auditoria verificável), fila de propostas entre processos, camada MCP em
memória e comandos ``bdgd-light mcp --listar`` / ``bdgd-light aprovar``."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytest.importorskip("opendssdirect")
pytest.importorskip("mcp")

from rich.console import Console  # noqa: E402

from bdgd_light.agent.audit import AuditLog  # noqa: E402
from bdgd_light.cli import app  # noqa: E402
from bdgd_light.ingest.recorte import recortar  # noqa: E402
from bdgd_light.mcp_server import (  # noqa: E402
    FilaPropostas,
    RecusadoError,
    SessaoCOD,
    SessaoError,
    ferramentas_da_sessao,
)
from bdgd_light.mcp_server.servidor import (  # noqa: E402
    ERROS_DOMINIO,
    criar_servidor,
    descritores,
)

CLUSTER_MINI = Path("tests/fixtures/dss/cluster_mini")
runner = CliRunner()


@pytest.fixture(scope="module")
def recorte(parquet_mini, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("mcp_feeders")
    resultado = recortar(parquet_mini, ["RJO001", "RJO002"], out, console=Console(quiet=True))
    return resultado.cluster.gpkg


@pytest.fixture
def dss_out(tmp_path) -> Path:
    # cópia: preparar_master_cluster escreve o Master do cluster dentro de dss_out
    destino = tmp_path / "dss"
    shutil.copytree(CLUSTER_MINI, destino)
    return destino


@pytest.fixture
def sessao(recorte, dss_out, tmp_path) -> SessaoCOD:
    s = SessaoCOD(feeders=recorte.parent, dss_out=dss_out, estado_dir=tmp_path / "estado")
    s.load_cluster(str(recorte))
    return s


def registros(sessao: SessaoCOD) -> list[dict]:
    return [json.loads(linha) for linha in sessao.audit.caminho.read_text().splitlines()]


# -- fluxo completo (critério de aceite da issue) -----------------------------------------------


def test_fluxo_flisr_completo_com_hitl(sessao: SessaoCOD):
    topo = sessao.get_topology()
    assert topo["resumo"]["nos"] == 16  # PACs (as 2 fontes não contam)
    assert topo["resumo"]["religadores"] == {"RJO001": "CH008", "RJO002": "CH009"}
    assert len(topo["chaves"]) == 8 and len(topo["ties"]) == 2

    falta = sessao.inject_fault("SEG001")
    assert falta["religador"] == "CH008"
    assert sessao.get_switch_state("CH008")["estado"] == "aberta"
    assert falta["sem_tensao"]["clientes"]["total"] == 5  # zona (1) + jusante restaurável (4)

    loc = sessao.locate_fault()
    assert loc["chaves_com_indicacao"] == ["CH008"] and loc["ultima_indicacao"] == "CH008"
    assert loc["chaves_fronteira"] == ["CH001", "CH008"]
    assert loc["zona"]["trechos"] == ["SEG001"] and loc["zona"]["clientes"]["total"] == 1

    iso = sessao.isolate_fault()
    assert iso["chaves"] == ["CH001", "CH008"]
    assert iso["sequencia"] == [{"acao": "abrir", "chave": "CH001"}]  # CH008 já está aberto
    assert iso["religar_apos_isolar"] is False  # a falta está no tronco, colada no religador
    assert iso["clientes_desligados"]["total"] == 4 and len(iso["desligados"]) == 5

    ops = sessao.restore_options(score=True)
    assert [o["chave"] for o in ops["opcoes"]] == ["CH003", "CH005"]
    melhor = ops["opcoes"][0]
    assert melhor["fonte"] == "RJO002" and melhor["score"]["viavel"] is True
    assert melhor["score"]["margem_disjuntor"] > 0.5
    assert melhor["manobras"] == [
        {"acao": "abrir", "chave": "CH001"},
        {"acao": "fechar", "chave": "CH003"},
    ]

    prop = sessao.propose_plan(chave="CH003", justificativa="maior margem, telecomandada")
    assert prop["id"] == "P-0001" and prop["status"] == "pendente" and prop["token"] is None
    assert prop["proximo_passo"] == {"acao": "abrir", "chave": "CH001"}

    # sem aprovação humana nada é executado
    with pytest.raises(RecusadoError, match="sem token"):
        sessao.set_switch("CH001", "aberta")
    with pytest.raises(RecusadoError, match="sem token"):
        sessao.set_switch("CH001", "aberta", approval_token="token-falso")
    assert sessao.get_switch_state("CH001")["estado"] == "fechada"

    aprovada = sessao.approve("P-0001", operador="operadora")
    token = aprovada["token"]
    assert token and aprovada["status"] == "aprovada"
    assert sessao.get_proposal("P-0001")["token"] == token  # o agente pega o token aqui

    # ordem da proposta é obrigatória: fechar o NA antes de abrir a fronteira é recusado
    with pytest.raises(RecusadoError, match="próximo passo"):
        sessao.set_switch("CH003", "fechada", approval_token=token)

    r1 = sessao.set_switch("CH001", "aberta", approval_token=token)
    assert r1["executado"] is True and (r1["chave"], r1["estado"]) == ("CH001", "aberta")
    assert r1["passo"] == 1 and r1["n_passos"] == 2
    assert r1["proposta_status"] == "aprovada" and r1["aprovada_por"] == "operadora"
    r2 = sessao.set_switch("CH003", "fechada", approval_token=token)
    assert r2["passo"] == 2 and r2["proposta_status"] == "executada"
    assert r2["sem_tensao"]["clientes"]["total"] == 1  # só o cliente da zona em falta
    assert sessao.get_switch_state("CH003")["estado"] == "fechada"

    # token consumido: proposta executada não autoriza mais nada
    with pytest.raises(RecusadoError):
        sessao.set_switch("CH002", "aberta", approval_token=token)

    # auditoria encadeada, com recusas registradas e token nunca em claro
    caminho = sessao.audit.caminho
    assert AuditLog.verificar_arquivo(caminho) == len(registros(sessao))
    tipos = [r["tipo"] for r in registros(sessao)]
    assert tipos.count("mcp.recusa") == 4 and "hitl.aprovacao" in tipos
    assert tipos.count("mcp.chamada") >= 10
    assert token not in caminho.read_text()
    chamada_set = [r for r in registros(sessao) if r["dados"].get("ferramenta") == "set_switch"]
    assert chamada_set[-1]["dados"]["argumentos"]["approval_token"].startswith("sha256:")
    aprovacao = [r for r in registros(sessao) if r["tipo"] == "hitl.aprovacao"][0]
    assert aprovacao["dados"]["resultado"]["token"].startswith("sha256:")


def test_rejeicao_e_expiracao(sessao: SessaoCOD):
    sessao.inject_fault("SEG001")
    sessao.restore_options()
    p1 = sessao.propose_plan(chave="CH003")
    p2 = sessao.propose_plan(chave="CH005")

    sessao.reject(p1["id"], operador="op", motivo="prefiro CH005")
    assert sessao.get_proposal(p1["id"])["status"] == "rejeitada"
    with pytest.raises(SessaoError, match="rejeitada"):
        sessao.approve(p1["id"])

    token = sessao.approve(p2["id"], validade_s=-1)["token"]
    with pytest.raises(RecusadoError, match="venceu"):
        sessao.set_switch("CH001", "aberta", approval_token=token)
    assert sessao.get_proposal(p2["id"])["status"] == "expirada"


def test_proposta_so_isolar_e_religar(sessao: SessaoCOD):
    """Falta a jusante de CH001: isolar e religar o tronco são recupera clientes sem NA."""
    sessao.inject_fault("SEG002")
    iso = sessao.isolate_fault()
    assert iso["chaves"] == ["CH001"] and iso["religar_apos_isolar"] is True
    assert iso["reenergizados_ao_religar"]["clientes"]["total"] >= 1
    assert sessao.restore_options()["opcoes"] == []
    p = sessao.propose_plan()
    assert p["chave"] is None and p["manobras"] == [
        {"acao": "abrir", "chave": "CH001"},
        {"acao": "fechar", "chave": "CH008"},
    ]
    assert sessao.estado()["sem_tensao"]["clientes"]["total"] == 5
    token = sessao.approve(p["id"])["token"]
    sessao.set_switch("CH001", "aberta", approval_token=token)
    r = sessao.set_switch("CH008", "fechada", approval_token=token)
    assert r["proposta_status"] == "executada"
    assert r["sem_tensao"]["clientes"]["total"] == 4  # só a zona em falta segue desligada


def test_sem_falta_nao_ha_o_que_localizar(sessao: SessaoCOD):
    with pytest.raises(SessaoError, match="não há falta"):
        sessao.locate_fault()
    with pytest.raises(SessaoError, match="não há falta"):
        sessao.propose_plan(chave="CH003")
    with pytest.raises(ERROS_DOMINIO):
        sessao.inject_fault("SEG999")


def test_run_powerflow_e_downstream(sessao: SessaoCOD):
    pf = sessao.run_powerflow()
    assert pf["convergiu"] is True and pf["manobras_aplicadas"] == []
    com = sessao.run_powerflow(manobras=[{"acao": "abrir", "chave": "CH001"}])
    assert com["comandos_dss"] and "CH001" in " ".join(com["comandos_dss"])
    with pytest.raises(ERROS_DOMINIO):
        sessao.run_powerflow(manobras=[{"acao": "explodir", "chave": "CH001"}])
    d = sessao.downstream_customers(chave="CH001")
    assert d["clientes"]["total"] == 4 and d["n_nos"] == 5
    with pytest.raises(SessaoError):
        sessao.downstream_customers()


def test_sem_cluster_carregado(recorte, dss_out, tmp_path):
    s = SessaoCOD(feeders=recorte.parent, dss_out=dss_out, estado_dir=None)
    with pytest.raises(SessaoError, match="load_cluster"):
        s.get_topology()
    with pytest.raises(FileNotFoundError):
        s.load_cluster("inexistente")


# -- fila de propostas entre processos ---------------------------------------------------------


def test_fila_aprovada_em_outro_processo(sessao: SessaoCOD):
    sessao.inject_fault("SEG001")
    sessao.restore_options()
    p = sessao.propose_plan(chave="CH003")
    arquivo = sessao.estado_dir / "propostas.json"

    # "outro processo" (CLI aprovar / console) decide no arquivo
    outra = FilaPropostas(arquivo)
    token = outra.aprovar(p["id"], operador="cli").token
    assert sessao.get_proposal(p["id"])["status"] == "aprovada"
    r = sessao.set_switch("CH001", "aberta", approval_token=token)
    assert r["aprovada_por"] == "cli"
    # e a execução volta para o arquivo
    assert json.loads(arquivo.read_text())[0]["executadas"] == 1


def test_fila_ids_e_persistencia(tmp_path):
    arquivo = tmp_path / "p.json"
    fila = FilaPropostas(arquivo, agora=lambda: datetime(2026, 1, 1, tzinfo=UTC))
    a = fila.criar(cluster="c", falta="S1", chave="K", fonte="F", manobras=[], clientes={})
    b = fila.criar(cluster="c", falta="S1", chave=None, fonte="F", manobras=[], clientes={})
    assert (a.id, b.id) == ("P-0001", "P-0002")
    fila.aprovar(a.id, validade_s=60)
    assert fila.obter(a.id).expira_em == "2026-01-01T00:01:00+00:00"
    relida = FilaPropostas(arquivo)
    assert relida.obter(a.id).status == "aprovada" and relida.por_token(fila.obter(a.id).token)
    assert relida.por_token("nada") is None
    with pytest.raises(SessaoError, match="não existe"):
        fila.obter("P-9999")


# -- camada MCP -------------------------------------------------------------------------------


def test_descritores_e_ferramentas():
    nomes = [n for n, _ in ferramentas_da_sessao()]
    assert nomes[:3] == ["load_cluster", "get_topology", "get_switch_state"]
    assert {"inject_fault", "restore_options", "propose_plan", "set_switch"} <= set(nomes)
    assert "approve" not in nomes  # aprovação humana não é ferramenta do modelo
    ds = {d["name"]: d for d in descritores()}
    assert set(ds) == set(nomes)
    assert ds["set_switch"]["parameters"]["required"] == ["chave", "estado"]
    assert "approval_token" in ds["set_switch"]["parameters"]["properties"]
    assert "aprovada por humano" in ds["set_switch"]["description"]


@pytest.mark.anyio
async def test_servidor_mcp_em_memoria(sessao: SessaoCOD):
    from mcp.client.client import Client

    srv = criar_servidor(sessao)
    async with Client(srv) as cliente:
        tools = await cliente.list_tools()
        assert len(tools.tools) == len(ferramentas_da_sessao())
        r = await cliente.call_tool("inject_fault", {"trecho": "SEG001"})
        assert r.is_error is False and r.structured_content["religador"] == "CH008"
        r = await cliente.call_tool("restore_options", {"score": False})
        assert [o["chave"] for o in r.structured_content["opcoes"]] == ["CH003", "CH005"]
        r = await cliente.call_tool("propose_plan", {"chave": "CH003"})
        pid = r.structured_content["id"]
        recusa = await cliente.call_tool(
            "set_switch", {"chave": "CH001", "estado": "aberta", "approval_token": "x"}
        )
        assert recusa.is_error is True and "recusada" in recusa.content[0].text
        token = sessao.approve(pid)["token"]
        ok = await cliente.call_tool(
            "set_switch", {"chave": "CH001", "estado": "aberta", "approval_token": token}
        )
        assert ok.is_error is False and ok.structured_content["passo"] == 1
    assert "mcp.recusa" in [r["tipo"] for r in registros(sessao)]


@pytest.fixture
def anyio_backend():
    return "asyncio"


# -- CLI --------------------------------------------------------------------------------------


def test_cli_mcp_listar():
    r = runner.invoke(app, ["mcp", "--listar"], env={"COLUMNS": "200"})
    assert r.exit_code == 0, r.output
    assert "load_cluster" in r.output and "set_switch" in r.output
    assert "approval_token?" in r.output


def test_cli_mcp_cluster_inexistente(tmp_path):
    r = runner.invoke(app, ["mcp", "--cluster", "nada", "--feeders", str(tmp_path)])
    assert r.exit_code == 1


def test_cli_aprovar(sessao: SessaoCOD, tmp_path):
    estado = str(sessao.estado_dir)
    r = runner.invoke(app, ["aprovar", "--estado", estado])
    assert r.exit_code == 0 and "nenhuma proposta" in r.output

    sessao.inject_fault("SEG001")
    sessao.restore_options()
    sessao.propose_plan(chave="CH003")
    sessao.propose_plan(chave="CH005")

    r = runner.invoke(app, ["aprovar", "--estado", estado], env={"COLUMNS": "200"})
    assert r.exit_code == 0 and "P-0001" in r.output and "pendente" in r.output

    r = runner.invoke(app, ["aprovar", "P-0002", "--estado", estado, "--rejeitar", "--motivo", "x"])
    assert r.exit_code == 0 and "rejeitada" in r.output

    r = runner.invoke(app, ["aprovar", "P-0001", "--estado", estado, "--operador", "ana"])
    assert r.exit_code == 0 and "aprovada por ana" in r.output, r.output
    token = r.output.split("approval_token:")[1].split()[0]
    assert sessao.set_switch("CH001", "aberta", approval_token=token)["aprovada_por"] == "ana"

    r = runner.invoke(app, ["aprovar", "P-0001", "--estado", estado])
    assert r.exit_code == 1 and "aprovada" in r.output

    hitl = Path(estado) / "hitl.jsonl"
    assert AuditLog.verificar_arquivo(hitl) == 2
    assert [json.loads(linha)["tipo"] for linha in hitl.read_text().splitlines()] == [
        "hitl.rejeicao",
        "hitl.aprovacao",
    ]
