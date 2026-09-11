"""Benchmark do agente (#36): arquivo de tarefas, métricas, gabarito e execução com o fake."""

from __future__ import annotations

import csv
import importlib.util
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

if importlib.util.find_spec("opendssdirect") is None:  # não importar: ver twin.powerflow.no_motor
    pytest.skip("opendssdirect não instalado (uv sync --extra twin)", allow_module_level=True)
yaml = pytest.importorskip("yaml")

from rich.console import Console  # noqa: E402

from bdgd_light.bench import (  # noqa: E402
    TAREFAS_PADRAO,
    BenchError,
    Benchmark,
    Configuracao,
    Gabarito,
    Rodada,
    Tarefa,
    acerto_resposta,
    acerto_sem_manobra,
    carregar_comparativo,
    carregar_tarefas,
    chamadas_desnecessarias,
    comparativo,
    custo_usd,
    escrever_csv,
    extrair_numeros,
    filtrar,
    ler_campo,
    ler_csv,
    melhor_opcao,
    nome_relatorio,
    ordenacao,
    pass_at_k,
    preco_modelo,
    relatorio_markdown,
    resumir,
    tolerancias,
)
from bdgd_light.cli import app  # noqa: E402
from bdgd_light.ingest.recorte import recortar  # noqa: E402

CLUSTER_MINI = Path("tests/fixtures/dss/cluster_mini")
TAREFAS_MINI = Path("tests/fixtures/bench_mini.yaml")
runner = CliRunner()


@pytest.fixture(scope="module")
def recorte(parquet_mini, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("bench_feeders")
    resultado = recortar(parquet_mini, ["RJO001", "RJO002"], out, console=Console(quiet=True))
    return resultado.cluster.gpkg


@pytest.fixture
def dss_out(tmp_path) -> Path:
    destino = tmp_path / "dss"
    shutil.copytree(CLUSTER_MINI, destino)
    return destino


def _tarefa(**kw) -> Tarefa:
    base = dict(
        id="T1",
        nivel="simple",
        cluster="tijuca",
        pergunta="?",
        referencia=("get_topology",),
        gabarito={"ferramenta": "get_topology", "argumentos": {}, "campo": "resumo.km"},
    )
    base.update(kw)
    return Tarefa(**base)


# -- arquivos de tarefas ---------------------------------------------------------------------------


def test_tarefas_padrao_sao_38_em_tres_niveis_com_ids_unicos():
    tarefas = carregar_tarefas(TAREFAS_PADRAO)
    assert len(tarefas) == 38
    assert {n: sum(1 for t in tarefas if t.nivel == n) for n in ("simple", "medium", "hard")} == {
        "simple": 10,
        "medium": 13,
        "hard": 15,
    }
    assert len({t.id for t in tarefas}) == 38
    assert {t.cluster for t in tarefas} == {"tijuca", "ipanema", "taquara"}
    for t in tarefas:
        if t.verificar == "sem_manobra":
            # eventos sem manobra: nenhuma ferramenta necessária; o gabarito vem do evento
            assert t.evento in ("falta_transitoria", "chave_indisponivel") and not t.referencia
            assert (t.falta or t.chave) and t.gabarito["ferramenta"] == "downstream_customers"
            continue
        assert t.referencia, t.id
        assert t.gabarito["ferramenta"] in t.referencia or t.gabarito["campo"] == "melhor_opcao"
        if t.verificar == "proposta":
            assert t.evento == "falta_permanente" and t.falta, t.id
        else:
            assert t.pergunta, t.id
    # toda tarefa tem 'esperado' registrado para a conferência com --gabarito
    assert all(t.esperado is not None for t in tarefas)
    # as 4 tarefas de Ipanema da issue #52 e os eventos novos do harness
    por_id = {t.id: t for t in tarefas}
    assert {por_id[i].cluster for i in ("M11", "M12", "M13", "H11")} == {"ipanema"}
    assert por_id["M12"].evento == "chave_indisponivel" and por_id["M12"].chave == "10934177"
    assert por_id["M13"].evento == "falta_transitoria" and por_id["M13"].falta == "11409068"
    assert por_id["H11"].verificar == "proposta" and por_id["H11"].esperado == []
    assert por_id["H12"].restricoes[0]["alimentadores_evitar"] == ["ALC9946"]
    assert por_id["H13"].indisponiveis == ("746851189",)
    assert por_id["H14"].rejeicao_previa == {"motivo": "a chave 974020904 está em manutenção"}
    assert por_id["H15"].rejeicao_previa == {"motivo": "a chave 746851189 está em manutenção"}


def test_tarefas_mini_carregam_e_filtram():
    tarefas = carregar_tarefas(TAREFAS_MINI)
    assert [t.id for t in tarefas] == [
        "S01", "S02", "S03", "S04", "M01", "M02", "M03", "M04", "M05", "H01", "H02", "H03", "H04",
    ]  # fmt: skip
    assert [t.id for t in filtrar(tarefas, niveis=["hard"])] == ["H01", "H02", "H03", "H04"]
    assert [t.id for t in filtrar(tarefas, ids=["S02", "M01"])] == ["S02", "M01"]
    assert filtrar(tarefas, clusters=["tijuca"]) == []
    assert filtrar(tarefas, clusters=["CLUSTER_RJO001-RJO002"]) == tarefas


def test_arquivo_de_tarefas_invalido(tmp_path):
    ruim = tmp_path / "t.yaml"
    ruim.write_text("tarefas:\n  - id: X\n    nivel: extremo\n", encoding="utf-8")
    with pytest.raises(BenchError, match="nível"):
        carregar_tarefas(ruim)
    ruim.write_text("tarefas: [{id: X, nivel: simple, campo: a[0]}]", encoding="utf-8")
    with pytest.raises(BenchError, match="YAML"):
        carregar_tarefas(ruim)
    ruim.write_text(
        yaml.safe_dump({"tarefas": [{"id": "A", "nivel": "simple"}, {"id": "A", "nivel": "hard"}]}),
        encoding="utf-8",
    )
    with pytest.raises(BenchError):
        carregar_tarefas(ruim)
    base = {
        "id": "E",
        "nivel": "medium",
        "cluster": "c",
        "gabarito": {"ferramenta": "downstream_customers", "campo": "clientes.ucbt"},
    }
    casos = [
        ({"evento": "pico_carga", "referencia": ["run_powerflow"]}, "não suportado"),
        ({"evento": "chave_indisponivel", "verificar": "sem_manobra"}, "exige 'chave'"),
        ({"evento": "falta_transitoria", "verificar": "sem_manobra"}, "exige 'falta'"),
        ({"pergunta": "?", "verificar": "sem_manobra", "referencia": []}, None),
        ({"pergunta": "?", "referencia": []}, "referencia vazia"),
        ({"evento": "falta_transitoria", "falta": "S", "verificar": "proposta"}, "só com evento"),
        ({"pergunta": "?", "referencia": ["x"], "verificar": "tudo"}, "verificar"),
        (
            {"pergunta": "?", "referencia": ["x"], "rejeicao_previa": {"motivo": "x"}},
            "rejeicao_previa",
        ),
        (
            {
                "evento": "falta_permanente",
                "falta": "S",
                "referencia": ["x"],
                "verificar": "proposta",
                "rejeicao_previa": {},
            },
            "exige 'motivo'",
        ),
    ]
    for extra, erro in casos:
        ruim.write_text(yaml.safe_dump({"tarefas": [base | extra]}), encoding="utf-8")
        if erro is None:
            assert carregar_tarefas(ruim)[0].referencia == ()
        else:
            with pytest.raises(BenchError, match=erro):
                carregar_tarefas(ruim)


# -- métricas --------------------------------------------------------------------------------------


def test_extrair_numeros_pt_br():
    assert extrair_numeros("O alimentador tem 4.036 UCBT e 4,246 km") == [4036.0, 4.036, 4.246]
    assert extrair_numeros("margem 45,98 % e Vmin 0.93 pu; total 1.234,5") == [45.98, 0.93, 1234.5]
    assert extrair_numeros("sem números") == []


def test_ler_campo_caminhos_e_agregacoes():
    dados = {"a": {"b": [{"c": 1}, {"c": 2}], "n": [3, 4, 5]}, "lista": ["x", "y"]}
    assert ler_campo(dados, "a.b[1].c") == 2
    assert ler_campo(dados, "a.b[5].c") is None
    assert ler_campo(dados, "a.x") is None
    assert ler_campo(dados, "len(lista)") == 2
    assert ler_campo(dados, "len(a.b)") == 2
    assert ler_campo(dados, "sum(a.n)") == 12
    assert ler_campo(dados, "max(a.n)") == 5


def test_pass_at_k_e_ordenacao():
    assert pass_at_k(5, 5, 5) == 1.0
    assert pass_at_k(5, 0, 5) == 0.0
    assert pass_at_k(5, 1, 1) == pytest.approx(0.2)
    assert pass_at_k(5, 1, 5) == 1.0
    assert pass_at_k(4, 2, 2) == pytest.approx(1 - 1 / 6)
    ref = ["locate_fault", "isolate_fault", "restore_options", "propose_plan"]
    assert ordenacao(ref, ref) == (1.0, 1.0)
    assert ordenacao(["locate_fault", "restore_options"], ref) == (0.5, 1.0)
    ordem, precisao = ordenacao(["get_topology", "locate_fault", "isolate_fault"], ref)
    assert ordem == 0.5 and precisao == pytest.approx(2 / 3, abs=1e-3)
    assert ordenacao([], ref) == (0.0, 0.0)
    assert chamadas_desnecessarias(ref, ref) == 0
    assert chamadas_desnecessarias(["locate_fault", "restore_options"], ref) == 0
    assert chamadas_desnecessarias(["get_topology", "locate_fault", "isolate_fault"], ref) == 1


def test_tolerancias_e_acerto_resposta():
    contagem = _tarefa()
    assert tolerancias(contagem, 4036) == (0.5, 0.0)  # inteiro: valor exato
    assert tolerancias(contagem, 4.246) == (0.0, 0.02)  # fracionário: ±2 %
    assert acerto_resposta("O alimentador tem 4.036 UCBT.", 4036, contagem) == (True, 4036.0)
    assert acerto_resposta("cerca de 4.000 UCBT", 4036, contagem) == (False, 4000.0)
    assert acerto_resposta("tem 4,2 km de rede", 4.246, contagem) == (True, 4.2)
    assert acerto_resposta("tem 4,0 km de rede", 4.246, contagem) == (False, 4.0)
    assert acerto_resposta("não sei", 4036, contagem) == (False, None)
    pct = _tarefa(escala=100.0, tolerancia_abs=0.5)
    # a fração (0,4598) e a escala (45,98 %) são aceitas quando 'escala' está definida
    assert acerto_resposta("margem de 46 %", 45.98, pct)[0]
    assert acerto_resposta("margem de 0,46", 45.98, pct)[0]
    assert not acerto_resposta("margem de 52 %", 45.98, pct)[0]
    assert acerto_resposta("a chave é 746851189", "746851189", contagem) == (True, "746851189")


def test_acerto_sem_manobra():
    from bdgd_light.agent.orquestrador import Execucao

    def exec_(resposta: str, *ferramentas: str, proposta=None) -> Execucao:
        return Execucao(
            tipo="evento",
            cluster="c",
            evento=None,
            pergunta=None,
            provider="fake",
            modelo=None,
            ferramentas=[{"ferramenta": f} for f in ferramentas],
            proposta=proposta,
            resposta=resposta,
        )

    t = _tarefa(verificar="sem_manobra", referencia=(), evento="falta_transitoria", falta="S")
    assert acerto_sem_manobra(exec_("religou; 1730 UCBT sem tensão no tempo morto"), 1730, t) == (
        True,
        1730.0,
    )
    # consultar é permitido; propor ou manobrar, não
    assert acerto_sem_manobra(exec_("1730 UCBT", "downstream_customers"), 1730, t)[0]
    assert acerto_sem_manobra(exec_("1730 UCBT", "locate_fault", "propose_plan"), 1730, t) == (
        False,
        "chamou propose_plan",
    )
    assert acerto_sem_manobra(exec_("1730", proposta={"id": "P-0001"}), 1730, t) == (
        False,
        "proposta P-0001",
    )
    assert acerto_sem_manobra(exec_("religou, sem manobra"), 1730, t) == (False, None)
    # sem gabarito numérico basta uma resposta não vazia
    assert acerto_sem_manobra(exec_("registrado"), None, t) == (True, None)
    assert acerto_sem_manobra(exec_("  "), None, t) == (False, None)


def test_custo_usd_por_preco_de_lista():
    assert preco_modelo("gemini-2.5-flash") == (0.30, 2.50)
    assert preco_modelo("gpt-4.1-mini-2025-04-14") == (0.40, 1.60)  # prefixo mais longo
    assert preco_modelo("gpt-4.1-2025-04-14") == (2.00, 8.00)
    assert preco_modelo("openai/gpt-4.1-mini") == (0.40, 1.60)  # GitHub Models
    assert preco_modelo("fake-operador") is None and preco_modelo(None) is None
    base = dict(
        tarefa="S01", nivel="simple", cluster="c", repeticao=1, acerto=True, obtido=1, esperado=1,
        sequencia=[], referencia=[], ordem=1.0, precisao=1.0, desnecessarias=0, rodadas=2,
        chars_ferramentas=0, segundos_llm=0.0, segundos_ferramentas=0.0, segundos_total=0.0,
        replanejamentos=0, recusas=0, erro=None, resposta="", provider="gemini", exemplos=True,
        compactado=True, seed=42, data="2026-09-11T00:00:00+00:00",
    )  # fmt: skip
    # Gemini: os tokens de raciocínio (total − prompt) contam como saída
    r = Rodada(**base, modelo="gemini-2.5-flash", tokens_prompt=1_000_000, tokens_completion=1_000,
               tokens_total=1_100_000, tokens_informados=True)  # fmt: skip
    assert custo_usd(r) == pytest.approx(0.30 + 0.1 * 2.50)
    r = Rodada(**base, modelo="gpt-4.1-mini", tokens_prompt=1_000_000, tokens_completion=500_000,
               tokens_total=1_500_000, tokens_informados=True)  # fmt: skip
    assert custo_usd(r) == pytest.approx(0.40 + 0.5 * 1.60)
    sem_uso = Rodada(**base, modelo="gemini-2.5-flash", tokens_prompt=0, tokens_completion=0,
                     tokens_total=0, tokens_informados=False)  # fmt: skip
    assert custo_usd(sem_uso) is None
    res = resumir([r, r], 1)
    assert res["total"]["usd_medio"] == pytest.approx(1.2) and res["total"]["usd_por_pass1"] == 1.2
    # execução sem uso informado (timeout) conta como 0; grupo só de fake/desconhecidos → None
    assert resumir([r, sem_uso], 1)["total"]["usd_medio"] == pytest.approx(0.6)
    assert resumir([sem_uso], 1)["total"]["usd_medio"] is None


def test_melhor_opcao_equivalentes_dentro_da_tolerancia():
    def opcao(chave, margem, total=100, viavel=True):
        return {
            "chave": chave,
            "clientes": {"total": total},
            "score": {"viavel": viavel, "margem_disjuntor": margem},
        }

    # mesmo critério do ranking do gêmeo (viáveis → maior margem) e do verificador (empate a
    # menos de 2 p.p.); inviáveis nunca contam, e só entram as que recuperam os mesmos clientes
    opcoes = [opcao("A", 0.46), opcao("B", 0.45), opcao("C", 0.40), opcao("E", 0.99, viavel=False)]
    assert melhor_opcao({"opcoes": opcoes}) == ["A", "B"]
    assert melhor_opcao({"opcoes": [*opcoes, opcao("D", 0.99, total=50)]}) == ["D"]
    assert melhor_opcao({"opcoes": [*opcoes, opcao("F", 0.455, total=80)]}) == ["A", "B"]
    assert melhor_opcao({"opcoes": [opcao("E", 0.9, viavel=False)]}) == []
    assert melhor_opcao(
        {
            "opcoes": [
                opcao("A", 0.46, total=100) | {"bloqueada": "restrição"},
                opcao("B", 0.45, total=100),
            ]
        }
    ) == ["B"]
    assert melhor_opcao(
        {
            "opcoes": [
                opcao("A", 0.46, total=100, viavel=True)
                | {"manobras": [{"acao": "fechar", "chave": "X"}]},
                opcao("B", 0.45, total=100),
            ]
        },
        indisponiveis=["X"],
    ) == ["B"]
    assert melhor_opcao({}) == []


def _rodada(tarefa, nivel, acerto, tokens=100, seq=None, provider="fake", **kw) -> Rodada:
    base = dict(
        tarefa=tarefa,
        nivel=nivel,
        cluster="tijuca",
        repeticao=1,
        acerto=acerto,
        obtido=1.0 if acerto else 2.0,
        esperado=1.0,
        sequencia=seq or ["get_topology"],
        referencia=["get_topology"],
        ordem=1.0,
        precisao=1.0,
        desnecessarias=0,
        rodadas=1,
        tokens_prompt=tokens,
        tokens_completion=0,
        tokens_total=tokens,
        tokens_informados=tokens > 0,
        chars_ferramentas=400,
        segundos_llm=0.5,
        segundos_ferramentas=0.1,
        segundos_total=0.6,
        replanejamentos=0,
        recusas=0,
        erro=None,
        resposta="1",
        provider=provider,
        modelo="m",
        exemplos=True,
        compactado=True,
        seed=1,
        data="2026-01-01T00:00:00+00:00",
    )
    base.update(kw)
    return Rodada(**base)


def test_resumir_pass_at_k_por_tarefa_e_tokens_por_acerto():
    rodadas = [
        _rodada("S01", "simple", True, repeticao=1),
        _rodada("S01", "simple", True, repeticao=2),
        _rodada("S02", "simple", False, repeticao=1),
        _rodada("S02", "simple", True, repeticao=2),
        _rodada("H01", "hard", False, repeticao=1, tokens=1000),
        _rodada("H01", "hard", False, repeticao=2, tokens=1000),
    ]
    res = resumir(rodadas, k=2)
    assert res["simple"]["tarefas"] == 2 and res["simple"]["execucoes"] == 4
    assert res["simple"]["pass@1"] == 0.75
    assert res["simple"]["pass@2"] == 1.0  # S02 acerta em pelo menos uma das duas amostras
    assert res["hard"]["pass@1"] == 0.0 and res["hard"]["tokens_por_pass1"] is None
    assert res["total"]["pass@1"] == 0.5
    assert res["total"]["tokens_por_pass1"] == pytest.approx(400 / 0.5)
    assert res["total"]["desnecessarias_media"] == 0.0
    assert "medium" not in res


def test_csv_ida_e_volta_relatorio_e_comparativo(tmp_path):
    rodadas = [
        _rodada("S01", "simple", True, seq=["get_topology"]),
        _rodada("H01", "hard", False, obtido=None, esperado=["A", "B"], erro="LLMError: x"),
    ]
    caminho = escrever_csv(rodadas, tmp_path / "2026-01-01-fake.csv")
    with caminho.open(encoding="utf-8") as fh:
        linhas = list(csv.DictReader(fh))
    assert len(linhas) == 2 and linhas[0]["acerto"] == "1" and linhas[1]["acerto"] == "0"
    lidas = ler_csv(caminho)
    assert lidas == rodadas
    # um arquivo antigo do mesmo rótulo não entra no comparativo; outro provedor entra
    escrever_csv(
        [_rodada("S01", "simple", False, data="2025-12-31T00:00:00+00:00")],
        tmp_path / "2025-12-31-fake.csv",
    )
    escrever_csv(
        [_rodada("S01", "simple", True, provider="openai", tokens=2000)],
        tmp_path / "2026-01-01-openai.csv",
    )
    por_rotulo = carregar_comparativo(tmp_path)
    assert set(por_rotulo) == {"fake", "openai"}
    assert all(r.data.startswith("2026") for r in por_rotulo["fake"])
    assert len(por_rotulo["fake"]) == 2
    tabela = comparativo(por_rotulo, k=1)
    assert "| fake |" in tabela and "| openai |" in tabela and "pass@1 hard" in tabela
    assert "ferr. desnec." in tabela
    config = Configuracao(provider="fake", k=1, n=1, seed=1)
    md = relatorio_markdown(
        rodadas,
        config,
        tarefas=carregar_tarefas(TAREFAS_MINI),
        arquivo_tarefas=TAREFAS_MINI,
        csv_path=caminho,
        comparativo_md=tabela,
        k=1,
    )
    assert md.startswith("# Benchmark do agente — fake (2026-01-01)")
    assert "## Métricas por nível" in md and "## Por tarefa" in md and "## Erros" in md
    assert "LLMError: x" in md and "## Comparativo" in md
    assert "ferr. desnec." in md
    assert nome_relatorio(Configuracao(provider="gemini", exemplos=False)).endswith(
        "-gemini-sem-exemplos"
    )
    assert Configuracao(compactar=False, exemplos=False).rotulo == "fake-sem-exemplos-sem-compactar"


# -- execução no cluster de teste ------------------------------------------------------------------


def test_gabarito_no_cluster_mini(recorte, dss_out, tmp_path):
    from bdgd_light.mcp_server import SessaoCOD

    sessao = SessaoCOD(feeders=recorte.parent, dss_out=dss_out, estado_dir=tmp_path / "estado")
    gab = Gabarito(sessao, recorte.parent)
    por_id = {t.id: t for t in carregar_tarefas(TAREFAS_MINI)}
    assert gab.esperado(por_id["S01"]) == pytest.approx(0.674, abs=0.01)
    assert gab.esperado(por_id["M01"]) == 3
    assert gab.esperado(por_id["M02"]) == 1
    assert gab.esperado(por_id["M03"]) == 3
    assert sorted(gab.esperado(por_id["H01"])) == ["CH003", "CH005"]
    assert gab.esperado(por_id["H02"]) == 2
    assert gab.esperado(por_id["H03"]) == pytest.approx(1.0136, abs=0.005)
    assert gab.esperado(por_id["H04"]) == ["CH005"]
    # o gabarito é calculado uma vez por (cluster, falta, ferramenta, campo)
    assert len(gab._cache) == 8
    quebrada = _tarefa(
        cluster="cluster_RJO001-RJO002", gabarito={**por_id["S01"].gabarito, "campo": "resumo.nada"}
    )
    with pytest.raises(BenchError, match="ausente"):
        gab.esperado(quebrada)


def test_benchmark_fake_acerta_todas_as_tarefas_mini(recorte, dss_out, tmp_path):
    config = Configuracao(provider="fake", k=1, n=1, seed=3)
    bench = Benchmark(recorte.parent, dss_out, tmp_path / "estado", config)
    tarefas = carregar_tarefas(TAREFAS_MINI)
    vistos: list[str] = []
    rodadas = bench.rodar(tarefas, progresso=lambda r, i, n: vistos.append(f"{i}/{n}"))
    assert vistos[-1] == "13/13"
    erradas = [
        (r.tarefa, r.obtido, r.esperado, r.resposta, r.erro) for r in rodadas if not r.acerto
    ]
    assert erradas == []
    res = resumir(rodadas, k=1)
    assert res["total"]["pass@1"] == 1.0 and res["total"]["erros"] == 0
    assert res["simple"]["ordem"] == 1.0 and res["hard"]["precisao"] == 0.875
    por_id = {r.tarefa: r for r in rodadas}
    assert por_id["H01"].sequencia == [
        "locate_fault", "isolate_fault", "restore_options", "propose_plan",
    ]  # fmt: skip
    assert por_id["H01"].obtido in ("CH003", "CH005")
    assert por_id["M03"].sequencia == ["locate_fault", "isolate_fault"]
    assert por_id["H03"].sequencia == ["run_powerflow"]
    assert por_id["H04"].sequencia[-2:] == ["restore_options", "propose_plan"]
    assert por_id["H04"].desnecessarias == 2
    assert por_id["H04"].obtido == "CH005"
    # eventos sem manobra: nenhuma ferramenta, resposta cita os clientes do evento, sem proposta
    for tid, texto in (("M04", "2 UCBT a jusante"), ("M05", "4 UCBT ficaram sem tensão")):
        r = por_id[tid]
        assert r.sequencia == [] and (r.ordem, r.precisao) == (1.0, 1.0) and r.obtido == r.esperado
        assert texto in r.resposta, r.resposta
    assert all(r.chars_ferramentas > 0 for r in rodadas if r.tarefa not in ("M04", "M05"))
    assert all(not r.tokens_informados or r.tokens_total == 0 for r in rodadas)
    # a mesma semente reproduz a ordem de execução
    ordem_a = [r.tarefa for r in rodadas]
    ordem_b = [
        r.tarefa for r in Benchmark(recorte.parent, dss_out, tmp_path / "e2", config).rodar(tarefas)
    ]
    assert ordem_a == ordem_b


def test_benchmark_registra_erro_de_tarefa_sem_derrubar_a_rodada(recorte, dss_out, tmp_path):
    config = Configuracao(provider="fake", k=1, n=1)
    bench = Benchmark(recorte.parent, dss_out, tmp_path / "estado", config)
    ruim = _tarefa(id="X1", cluster="cluster_inexistente")
    with pytest.raises(BenchError, match="gabarito impossível"):
        bench.gabarito.esperado(ruim)
    rodada = bench.executar_tarefa(ruim, 1)
    assert not rodada.acerto and "gabarito impossível" in (rodada.erro or "")
    boa = carregar_tarefas(TAREFAS_MINI)[0]
    rodada = bench.executar_tarefa(boa, 1)
    assert rodada.acerto and rodada.erro is None


def _args(recorte: Path, dss_out: Path, tmp_path: Path) -> list[str]:
    return [
        "--tarefas", str(TAREFAS_MINI),
        "--feeders", str(recorte.parent),
        "--dss-out", str(dss_out),
        "--estado", str(tmp_path / "estado"),
    ]  # fmt: skip


def test_cli_bench_gabarito_e_relatorio(recorte, dss_out, tmp_path):
    r = runner.invoke(app, ["bench", "--gabarito", *_args(recorte, dss_out, tmp_path)])
    assert r.exit_code == 0, r.output
    assert "13 gabaritos conferem" in r.output
    saida = tmp_path / "relatorios"
    r = runner.invoke(
        app,
        [
            "bench",
            "--provider",
            "fake",
            "--k",
            "2",
            "--n",
            "1",
            "--seed",
            "1",
            "--ids",
            "S02,M01,H01",
            "--saida",
            str(saida),
            *_args(recorte, dss_out, tmp_path),
        ],  # fmt: skip
    )
    assert r.exit_code == 0, r.output
    assert "3 tarefas × 1 = 3 execuções" in r.output
    csvs = list(saida.glob("*-fake.csv"))
    mds = list(saida.glob("*-fake.md"))
    assert len(csvs) == 1 and len(mds) == 1
    assert len(ler_csv(csvs[0])) == 3
    texto = mds[0].read_text(encoding="utf-8")
    assert "| total | 3 | 3 | 100 % |" in texto and "| fake |" in texto
    # --acrescentar acumula no CSV do dia e o relatório passa a cobrir todas as execuções
    r = runner.invoke(
        app,
        [
            "bench",
            "--provider",
            "fake",
            "--k",
            "2",
            "--n",
            "1",
            "--seed",
            "1",
            "--ids",
            "H02",
            "--saida",
            str(saida),
            "--acrescentar",
            *_args(recorte, dss_out, tmp_path),
        ],  # fmt: skip
    )
    assert r.exit_code == 0, r.output
    assert "acrescentando às 3 execuções" in r.output
    assert len(ler_csv(csvs[0])) == 4
    assert "| total | 4 | 4 | 100 % |" in mds[0].read_text(encoding="utf-8")
    r = runner.invoke(
        app,
        ["bench", "--json", "--sem-relatorio", "--ids", "S01", *_args(recorte, dss_out, tmp_path)],
    )
    assert r.exit_code == 0, r.output
    assert '"pass@1": 1.0' in r.output
    r = runner.invoke(app, ["bench", "--ids", "NAO_EXISTE", *_args(recorte, dss_out, tmp_path)])
    assert r.exit_code != 0 and "nenhuma tarefa" in r.output
