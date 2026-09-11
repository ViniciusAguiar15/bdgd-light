"""Matriz adversarial do verificador determinístico usada por testes e documentação."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bdgd_light.agent.orquestrador import Veredito, Verificador
from bdgd_light.mcp_server.sessao import SessaoCOD

TIJUCA = Path("data/feeders/cluster_tijuca.gpkg")
TRECHO_FALTA = "11304252"
CHAVE_ISOLAMENTO = "11035901"
CHAVE_RIMARAES = "974020904"
FONTE_RIMARAES = "ALC9946"
CHAVE_AMALIA = "977361689"
FONTE_AMALIA = "URG29983"
CHAVE_FANTASMA = "CHAVE_FANTASMA"
CHAVE_FORA_DAS_OPCOES = "CHAVE_FORA_DAS_OPCOES"


@dataclass(frozen=True)
class CasoAdversarial:
    """Caso inválido que o verificador precisa reprovar de forma determinística."""

    id: str
    situacao: str
    gate: str
    mensagem: str


CASOS_ADVERSARIAIS: tuple[CasoAdversarial, ...] = (
    CasoAdversarial(
        id="chave-inexistente",
        situacao="Plano usa uma chave que não existe no cluster da Tijuca.",
        gate="chaves_existem",
        mensagem=f"chave(s) inexistente(s) no cluster: {CHAVE_FANTASMA}",
    ),
    CasoAdversarial(
        id="chave-indisponivel",
        situacao="Evento `chave_indisponivel`: a sequência tenta manobrar a tie indisponível.",
        gate="chaves_disponiveis",
        mensagem=f"a sequência usa chave(s) indisponível(is): {CHAVE_RIMARAES}",
    ),
    CasoAdversarial(
        id="restricao-operacional",
        situacao="Rejeição anterior proibiu a mesma chave e o plano insiste nela.",
        gate="restricoes_operacionais",
        mensagem=f"rejeição anterior: usa chave proibida {CHAVE_RIMARAES}",
    ),
    CasoAdversarial(
        id="fecha-antes-de-abrir",
        situacao="A sequência fecha a tie antes de abrir a fronteira da falta.",
        gate="abre_antes_de_fechar",
        mensagem="há fechamento antes de uma abertura na sequência",
    ),
    CasoAdversarial(
        id="opcao-fora-do-restore",
        situacao="A chave escolhida não consta entre as opções correntes de `restore_options`.",
        gate="opcao_em_restore_options",
        mensagem=(f"a chave {CHAVE_FORA_DAS_OPCOES} não está entre as opções de restore_options"),
    ),
    CasoAdversarial(
        id="rota-amalia-inviavel",
        situacao=("Rota por AMALIA/URG29983 deixa o trecho `11051956` em ~180 % de carregamento."),
        gate="sem_sobrecarga_mt",
        mensagem="elemento(s) MT acima de 100 %: Line.smt_11051956",
    ),
    CasoAdversarial(
        id="sem-falta-registrada",
        situacao="Evento sem falta registrada (ex.: `pico_carga`) tenta propor manobra.",
        gate="falta_registrada",
        mensagem="não há falta registrada na sessão; nada a propor",
    ),
    CasoAdversarial(
        id="fronteira-nao-isolada",
        situacao="A proposta não abre toda a fronteira e deixa a falta conectada.",
        gate="fronteira_isolada",
        mensagem=(f"a sequência não abre toda a fronteira da falta: falta(m) {CHAVE_ISOLAMENTO}"),
    ),
)


@dataclass
class EntradaVerificacao:
    """Entradas necessárias para chamar ``Verificador.verificar`` sem LLM."""

    sessao: SessaoCOD
    verificador: Verificador
    chave: str | None
    opcoes: list[dict[str, Any]] | None = None
    isolamento: dict[str, Any] | None = None


def primeiro_gate_reprovado(veredito: Veredito) -> str | None:
    """Nome do primeiro gate reprovado, na ordem em que o verificador roda."""
    return next((nome for nome, ok in veredito.checagens.items() if ok is False), None)


def avaliar_caso(caso_id: str) -> Veredito:
    """Executa um caso adversarial sem LLM, montando o plano diretamente em Python."""
    entrada = montar_caso(caso_id)
    return entrada.verificador.verificar(
        entrada.sessao,
        entrada.chave,
        opcoes=entrada.opcoes,
        isolamento=entrada.isolamento,
    )


def montar_caso(caso_id: str) -> EntradaVerificacao:
    """Cria a sessão e o plano manual correspondente ao caso adversarial."""
    if caso_id == "chave-inexistente":
        return EntradaVerificacao(
            sessao=_sessao_com_falta(),
            verificador=Verificador(exigir_score=False),
            chave=CHAVE_RIMARAES,
            opcoes=[
                _plano_manual(
                    CHAVE_RIMARAES,
                    FONTE_RIMARAES,
                    manobras=[
                        _manobra("abrir", CHAVE_ISOLAMENTO),
                        _manobra("fechar", CHAVE_RIMARAES),
                        _manobra("fechar", CHAVE_FANTASMA),
                    ],
                )
            ],
        )
    if caso_id == "chave-indisponivel":
        return EntradaVerificacao(
            sessao=_sessao_com_falta(),
            verificador=Verificador(exigir_score=False, indisponiveis={CHAVE_RIMARAES}),
            chave=CHAVE_RIMARAES,
            opcoes=[_plano_manual(CHAVE_RIMARAES, FONTE_RIMARAES)],
        )
    if caso_id == "restricao-operacional":
        sessao = _sessao_com_falta()
        sessao.aplicar_restricao({"chaves_proibidas": [CHAVE_RIMARAES]}, motivo="rejeição anterior")
        return EntradaVerificacao(
            sessao=sessao,
            verificador=Verificador(exigir_score=False),
            chave=CHAVE_RIMARAES,
            opcoes=[_plano_manual(CHAVE_RIMARAES, FONTE_RIMARAES)],
        )
    if caso_id == "fecha-antes-de-abrir":
        return EntradaVerificacao(
            sessao=_sessao_com_falta(),
            verificador=Verificador(exigir_score=False),
            chave=CHAVE_RIMARAES,
            opcoes=[
                _plano_manual(
                    CHAVE_RIMARAES,
                    FONTE_RIMARAES,
                    manobras=[
                        _manobra("fechar", CHAVE_RIMARAES),
                        _manobra("abrir", CHAVE_ISOLAMENTO),
                    ],
                )
            ],
        )
    if caso_id == "opcao-fora-do-restore":
        return EntradaVerificacao(
            sessao=_sessao_com_falta(),
            verificador=Verificador(exigir_score=False),
            chave=CHAVE_FORA_DAS_OPCOES,
        )
    if caso_id == "rota-amalia-inviavel":
        return EntradaVerificacao(
            sessao=_sessao_com_falta(),
            verificador=Verificador(),
            chave=CHAVE_AMALIA,
            opcoes=[_plano_manual(CHAVE_AMALIA, FONTE_AMALIA, score=_score_amalia_inviavel())],
        )
    if caso_id == "sem-falta-registrada":
        return EntradaVerificacao(
            sessao=_sessao_tijuca(),
            verificador=Verificador(exigir_score=False),
            chave=None,
        )
    if caso_id == "fronteira-nao-isolada":
        return EntradaVerificacao(
            sessao=_sessao_com_falta(),
            verificador=Verificador(exigir_score=False),
            chave=CHAVE_RIMARAES,
            opcoes=[
                _plano_manual(
                    CHAVE_RIMARAES,
                    FONTE_RIMARAES,
                    manobras=[_manobra("fechar", CHAVE_RIMARAES)],
                )
            ],
        )
    raise KeyError(f"caso adversarial desconhecido: {caso_id}")


def renderizar_markdown(casos: tuple[CasoAdversarial, ...] = CASOS_ADVERSARIAIS) -> str:
    """Renderiza ``docs/verificador.md`` a partir da mesma matriz usada na suíte."""
    linhas = [
        "# Verificador determinístico: planos que precisam ser reprovados",
        "",
        (
            "Este documento é gerado a partir da mesma matriz usada em "
            "`tests/test_verificador_adversarial.py`. Os planos são montados diretamente como "
            "estruturas Python e passados ao `Verificador`, sem qualquer cliente de LLM."
        ),
        "",
        (
            "O gate é determinístico porque depende apenas do estado da `SessaoCOD`, da sequência "
            "de manobras proposta e, quando existe score elétrico, dos campos numéricos já "
            "calculados para a opção. O modelo pode sugerir qualquer plano, mas a aprovação "
            "final continua condicionada a essas checagens booleanas reproduzíveis."
        ),
        "",
        "| Situação | Gate reprovado | Mensagem esperada |",
        "|---|---|---|",
    ]
    for caso in casos:
        linhas.append(f"| {caso.situacao} | `{caso.gate}` | `{caso.mensagem}` |")
    linhas.extend(
        [
            "",
            "Regeneração: `uv run python scripts/gerar_verificador_doc.py`.",
            "",
        ]
    )
    return "\n".join(linhas)


def _sessao_tijuca() -> SessaoCOD:
    sessao = SessaoCOD(estado_dir=None)
    sessao.load_cluster(str(TIJUCA))
    return sessao


def _sessao_com_falta() -> SessaoCOD:
    sessao = _sessao_tijuca()
    sessao.inject_fault(TRECHO_FALTA)
    return sessao


def _manobra(acao: str, chave: str) -> dict[str, str]:
    return {"acao": acao, "chave": chave}


def _plano_manual(
    chave: str,
    fonte: str,
    *,
    manobras: list[dict[str, str]] | None = None,
    score: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "chave": chave,
        "fonte": fonte,
        "manobras": manobras or [_manobra("abrir", CHAVE_ISOLAMENTO), _manobra("fechar", chave)],
        "score": score,
    }


def _score_amalia_inviavel() -> dict[str, Any]:
    return {
        "convergiu": True,
        "vmin_mt_pu": 1.014,
        "vmax_mt_pu": 1.034,
        "i_disjuntor_a": 118.5,
        "i_nominal_a": 132.0,
        "margem_disjuntor": 0.102,
        "sobrecargas_mt": ["Line.smt_11051956"],
        "trechos_carregados_mt": [
            {
                "elemento": "Line.smt_11051956",
                "cod_id": "11051956",
                "i_max_a": 237.6,
                "i_nominal_a": 132.0,
                "carregamento_pct": 180.0,
            }
        ],
        "motivos": ["1 trecho(s) MT acima de 100 % (Line.smt_11051956 180 %)"],
        "viavel": False,
    }
