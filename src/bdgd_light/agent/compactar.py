"""Compactação dos retornos das ferramentas **para o modelo** (pedido da revisão PR-14, #36).

A ``SessaoCOD``/MCP continua devolvendo os dados completos (console, verificador e clientes MCP
precisam deles); só a mensagem ``tool`` que vai ao LLM é reduzida: listas de nós viram contagens,
``restore_options`` traz as ``top_n`` opções detalhadas e um resumo de uma linha das demais,
``get_topology`` traz contagens de chaves em vez da lista, e os números são arredondados. O
orquestrador aplica isto em ``Orquestrador(compactar=True)``; ``--sem-compactar`` mede o "antes".
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

TOP_N_OPCOES = 5
"""Opções de ``restore_options`` enviadas ao modelo com todos os campos; as demais vão resumidas."""

MAX_TIES = 40
"""Acima disto, ``get_topology`` manda ao modelo só a contagem de interligações."""

_CAMPOS_OPCAO = ("chave", "ctmt_chave", "fonte", "tlcd", "externa", "clientes", "manobras")
_CAMPOS_SCORE = (
    "viavel",
    "convergiu",
    "margem_disjuntor",
    "i_disjuntor_a",
    "i_nominal_a",
    "vmin_mt_pu",
    "vmax_mt_pu",
    "carregamento_max_mt_pct",
    "sobrecargas_mt",
    "perdas_kw",
    "motivos",
)
_CAMPOS_TIE = ("chave", "ctmt", "ctmt_viz", "aberta", "tlcd", "externa", "em_sub")
_CAMPOS_FLUXO_FORA = ("comandos_dss", "master", "ajustes", "n_nos_fase")


def arredondar(valor: Any, casas: int = 4) -> Any:
    """Arredonda todos os ``float`` de uma estrutura JSON-like (menos tokens, mesma leitura)."""
    if isinstance(valor, bool) or valor is None:
        return valor
    if isinstance(valor, float):
        return round(valor, casas)
    if isinstance(valor, Mapping):
        return {k: arredondar(v, casas) for k, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [arredondar(v, casas) for v in valor]
    return valor


def _contar_nos(d: dict[str, Any], *campos: str) -> None:
    for campo in campos:
        if isinstance(d.get(campo), list):
            d[f"n_{campo}"] = len(d.pop(campo))


def _clientes(c: Any) -> Any:
    if not isinstance(c, Mapping):
        return c
    return {k: c[k] for k in ("ucbt", "ucmt", "trafos", "kva", "total") if k in c}


def _manobras(m: Any) -> Any:
    if not isinstance(m, list):
        return m
    return [f"{x.get('acao')} {x.get('chave')}" if isinstance(x, Mapping) else x for x in m]


def compactar_topologia(r: Mapping[str, Any]) -> dict[str, Any]:
    saida = {k: v for k, v in r.items() if k not in ("chaves", "ties")}
    chaves = r.get("chaves")
    if isinstance(chaves, list):
        saida["chaves_resumo"] = {
            "total": len(chaves),
            "NA": sum(1 for c in chaves if c.get("normal") == "NA"),
            "NF": sum(1 for c in chaves if c.get("normal") == "NF"),
            "abertas": sum(1 for c in chaves if c.get("estado") == "aberta"),
            "telecomandadas": sum(1 for c in chaves if c.get("tlcd")),
            "nota": "lista omitida; use get_switch_state(chave) para uma chave específica",
        }
    ties = r.get("ties")
    if isinstance(ties, list):
        if len(ties) <= MAX_TIES:
            saida["ties"] = [{k: t.get(k) for k in _CAMPOS_TIE if k in t} for t in ties]
        else:
            saida["ties_resumo"] = {
                "total": len(ties),
                "abertas": sum(1 for t in ties if t.get("aberta")),
                "nota": f"lista omitida ({len(ties)} interligações)",
            }
    return saida


def compactar_zona(r: Mapping[str, Any]) -> dict[str, Any]:
    """``locate_fault``/``isolate_fault``: listas de nós → contagens; manobras em uma linha."""
    saida = dict(r)
    _contar_nos(saida, "zona", "desligados", "reenergizados")
    zona = saida.get("zona")
    if isinstance(zona, Mapping):
        z = dict(zona)
        _contar_nos(z, "nos")
        saida["zona"] = z
    for campo in ("manobras", "sequencia"):
        if campo in saida:
            saida[campo] = _manobras(saida[campo])
    for campo in ("clientes_zona", "clientes_desligados", "clientes"):
        if campo in saida:
            saida[campo] = _clientes(saida[campo])
    return saida


def _opcao_detalhada(o: Mapping[str, Any]) -> dict[str, Any]:
    d = {k: o.get(k) for k in _CAMPOS_OPCAO if k in o}
    d["clientes"] = _clientes(o.get("clientes"))
    d["manobras"] = _manobras(o.get("manobras"))
    score = o.get("score")
    if isinstance(score, Mapping):
        s = {k: score.get(k) for k in _CAMPOS_SCORE if k in score}
        if isinstance(s.get("margem_disjuntor"), int | float):
            s["margem_disjuntor_pct"] = round(100 * s["margem_disjuntor"], 1)
        d["score"] = s
    else:
        d["score"] = score
    return d


def _opcao_resumida(o: Mapping[str, Any]) -> dict[str, Any]:
    score = o.get("score") if isinstance(o.get("score"), Mapping) else {}
    d: dict[str, Any] = {
        "chave": o.get("chave"),
        "fonte": o.get("fonte"),
        "clientes": (o.get("clientes") or {}).get("total"),
    }
    if score:
        d["viavel"] = score.get("viavel")
        if isinstance(score.get("margem_disjuntor"), int | float):
            d["margem_disjuntor_pct"] = round(100 * score["margem_disjuntor"], 1)
        if score.get("motivos"):
            d["motivo"] = score["motivos"][0]
    return d


def compactar_restore_options(r: Mapping[str, Any], top_n: int = TOP_N_OPCOES) -> dict[str, Any]:
    saida = {k: v for k, v in r.items() if k not in ("opcoes", "score")}
    score = r.get("score")
    if isinstance(score, Mapping):
        saida["score"] = {k: v for k, v in score.items() if k != "master"}
    else:
        saida["score"] = score
    opcoes = list(r.get("opcoes") or [])
    saida["opcoes"] = [_opcao_detalhada(o) for o in opcoes[:top_n]]
    if len(opcoes) > top_n:
        saida["outras_opcoes"] = [_opcao_resumida(o) for o in opcoes[top_n:]]
        saida["nota"] = (
            f"{len(opcoes)} opções ordenadas (viáveis → maior margem → clientes); as {top_n} "
            f"primeiras detalhadas, as demais resumidas"
        )
    return saida


def compactar_fluxo(r: Mapping[str, Any]) -> dict[str, Any]:
    saida = {k: v for k, v in r.items() if k not in _CAMPOS_FLUXO_FORA}
    if "manobras_aplicadas" in saida:
        saida["manobras_aplicadas"] = _manobras(saida["manobras_aplicadas"])
    for campo in ("piores_barras", "sobrecargas"):
        lista = saida.get(campo)
        if isinstance(lista, list):
            saida[campo] = [
                {k: v for k, v in item.items() if k not in ("no", "kv_base")} for item in lista[:5]
            ]
    return saida


_POR_FERRAMENTA = {
    "get_topology": compactar_topologia,
    "locate_fault": compactar_zona,
    "isolate_fault": compactar_zona,
    "restore_options": compactar_restore_options,
    "run_powerflow": compactar_fluxo,
}


def compactar(nome: str, resultado: Any, *, top_n: int = TOP_N_OPCOES) -> Any:
    """Versão do resultado de ``nome`` para o modelo; ferramentas sem regra só têm os números
    arredondados. Nunca altera o objeto original."""
    if not isinstance(resultado, Mapping):
        return arredondar(resultado)
    if nome == "restore_options":
        return arredondar(compactar_restore_options(resultado, top_n))
    funcao = _POR_FERRAMENTA.get(nome)
    return arredondar(funcao(resultado) if funcao else dict(resultado))
