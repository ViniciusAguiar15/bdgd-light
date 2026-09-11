"""Log de auditoria só de acréscimo (ADR-001, decisão 6).

Formato: **JSON Lines**, um registro por linha, cada um com número de sequência, carimbo de tempo
UTC, tipo, dados livres, o hash SHA-256 do registro anterior e o próprio hash — uma cadeia em que
alterar, remover ou reordenar qualquer linha invalida todas as seguintes (``verificar``).

Uso típico::

    log = AuditLog(Path("data/audit/llm.jsonl"))
    log.registrar("llm.rodada", rodada=1, modelo="gpt-4.1-mini", ...)
    AuditLog.verificar_arquivo(Path("data/audit/llm.jsonl"))  # → nº de registros válidos

O hash cobre ``{seq, ts, tipo, dados, hash_anterior}`` serializados de forma canônica (chaves
ordenadas, sem espaços, ``ensure_ascii=False``); o primeiro registro aponta para ``GENESIS``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GENESIS = "0" * 64
ALGORITMO = "sha256"
_RE_EVENTO = re.compile(r"\bE-\d{4}\b")
_RE_PROPOSTA = re.compile(r"\bP-\d{4}\b")
_TIPOS_PREPARO_EVENTO = frozenset({"load_cluster", "inject_fault"})
_TIPOS_HITL = frozenset({"hitl.aprovacao", "hitl.rejeicao", "hitl.passo"})


class AuditError(Exception):
    """Cadeia inválida (hash não bate, sequência quebrada ou linha ilegível)."""


@dataclass(frozen=True)
class Registro:
    seq: int
    ts: str
    tipo: str
    dados: Mapping[str, Any]
    hash_anterior: str
    hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "tipo": self.tipo,
            "dados": dict(self.dados),
            "hash_anterior": self.hash_anterior,
            "hash": self.hash,
        }

    def to_json(self) -> str:
        return _canonico(self.to_dict())

    @classmethod
    def de_dict(cls, d: Mapping[str, Any]) -> Registro:
        try:
            return cls(
                int(d["seq"]),
                str(d["ts"]),
                str(d["tipo"]),
                dict(d["dados"]),
                str(d["hash_anterior"]),
                str(d["hash"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AuditError(f"registro malformado: {exc}") from exc


@dataclass(frozen=True)
class RegistroArquivo:
    """Registro da auditoria acompanhado do arquivo de origem."""

    arquivo: str
    registro: Registro

    def to_dict(self) -> dict[str, Any]:
        return {"arquivo": self.arquivo, **self.registro.to_dict()}


def _canonico(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def calcular_hash(
    seq: int, ts: str, tipo: str, dados: Mapping[str, Any], hash_anterior: str
) -> str:
    corpo = _canonico(
        {"seq": seq, "ts": ts, "tipo": tipo, "dados": dados, "hash_anterior": hash_anterior}
    )
    return hashlib.new(ALGORITMO, corpo.encode("utf-8")).hexdigest()


def _agora_utc() -> datetime:
    return datetime.now(UTC)


class AuditLog:
    """Cadeia de registros; com ``caminho`` cada registro é anexado ao arquivo imediatamente
    (``flush``) e, se o arquivo já existir, a cadeia continua do último hash gravado."""

    def __init__(
        self,
        caminho: Path | str | None = None,
        *,
        agora: Callable[[], datetime] = _agora_utc,
    ):
        self.caminho = None if caminho is None else Path(caminho)
        self._agora = agora
        self._registros: list[Registro] = []
        self._ultimo_hash = GENESIS
        if self.caminho is not None and self.caminho.exists():
            existentes = list(ler(self.caminho))
            self._registros = existentes
            if existentes:
                self._ultimo_hash = existentes[-1].hash

    # -- leitura ------------------------------------------------------------------------------
    @property
    def registros(self) -> list[Registro]:
        return list(self._registros)

    @property
    def ultimo_hash(self) -> str:
        return self._ultimo_hash

    def __len__(self) -> int:
        return len(self._registros)

    def __iter__(self) -> Iterator[Registro]:
        return iter(self._registros)

    # -- escrita ------------------------------------------------------------------------------
    def registrar(self, tipo: str, /, **dados: Any) -> Registro:
        """Anexa um registro do ``tipo`` com ``dados`` (JSON-serializáveis; o resto vira str)."""
        dados_limpos = json.loads(_canonico(dados))  # garante serializável e estável
        seq = len(self._registros) + 1
        ts = self._agora().astimezone(UTC).isoformat(timespec="milliseconds")
        h = calcular_hash(seq, ts, tipo, dados_limpos, self._ultimo_hash)
        reg = Registro(seq, ts, tipo, dados_limpos, self._ultimo_hash, h)
        if self.caminho is not None:
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
            with self.caminho.open("a", encoding="utf-8") as f:
                f.write(reg.to_json() + "\n")
                f.flush()
        self._registros.append(reg)
        self._ultimo_hash = h
        return reg

    # -- verificação --------------------------------------------------------------------------
    def verificar(self) -> int:
        """Confere a cadeia em memória; devolve o nº de registros ou levanta ``AuditError``."""
        return verificar_registros(self._registros)

    @staticmethod
    def verificar_arquivo(caminho: Path | str) -> int:
        """Lê e confere um arquivo JSON Lines; devolve o nº de registros válidos."""
        return verificar_registros(list(ler(caminho)))


def listar_arquivos(origem: Path | str) -> list[Path]:
    """Lista arquivos JSONL de auditoria a partir de um arquivo ou diretório."""
    caminho = Path(origem)
    if not caminho.exists():
        raise FileNotFoundError(f"{caminho} não existe.")
    if caminho.is_file():
        return [caminho]
    arquivos = sorted(p for p in caminho.rglob("*.jsonl") if p.is_file())
    if not arquivos:
        raise FileNotFoundError(f"nenhum arquivo .jsonl encontrado em {caminho}")
    return arquivos


def ler(caminho: Path | str) -> Iterator[Registro]:
    """Itera os registros de um arquivo (sem verificar a cadeia)."""
    with Path(caminho).open(encoding="utf-8") as f:
        for n, linha in enumerate(f, start=1):
            linha = linha.strip()
            if not linha:
                continue
            try:
                yield Registro.de_dict(json.loads(linha))
            except json.JSONDecodeError as exc:
                raise AuditError(f"linha {n} ilegível: {exc}") from exc


def verificar_origem(origem: Path | str, arquivos: list[Path] | None = None) -> dict[str, Any]:
    """Verifica todos os arquivos JSONL de uma origem e resume a primeira divergência."""
    lista = arquivos or listar_arquivos(origem)
    relatorio = []
    primeira = None
    for arquivo in lista:
        try:
            n = AuditLog.verificar_arquivo(arquivo)
            relatorio.append(
                {"arquivo": str(arquivo), "integra": True, "registros": n, "erro": None}
            )
        except AuditError as exc:
            info = {
                "arquivo": str(arquivo),
                "integra": False,
                "registros": None,
                "erro": str(exc),
            }
            relatorio.append(info)
            if primeira is None:
                primeira = {"arquivo": str(arquivo), "erro": str(exc)}
    return {"integra": primeira is None, "primeira_divergencia": primeira, "arquivos": relatorio}


def reconstruir_evento(evento_id: str, origem: Path | str) -> dict[str, Any]:
    """Reconstrói a linha do tempo de um evento a partir dos arquivos JSONL de auditoria."""
    arquivos = listar_arquivos(origem)
    registros_por_arquivo = {arquivo: list(ler(arquivo)) for arquivo in arquivos}
    relevantes: dict[tuple[str, int], RegistroArquivo] = {}

    def adicionar(arquivo: Path, indice: int) -> None:
        registro = registros_por_arquivo[arquivo][indice]
        relevantes[(str(arquivo), registro.seq)] = RegistroArquivo(str(arquivo), registro)

    for arquivo, registros in registros_por_arquivo.items():
        for i, registro in enumerate(registros):
            if registro.tipo == "agente.inicio" and evento_id in extrair_ids_evento(registro.dados):
                inicio = i
                while (
                    inicio > 0
                    and registros[inicio - 1].tipo in {"mcp.chamada", "mcp.recusa", "mcp.erro"}
                    and registros[inicio - 1].dados.get("ferramenta") in _TIPOS_PREPARO_EVENTO
                ):
                    inicio -= 1
                fim = i
                while fim + 1 < len(registros) and registros[fim].tipo != "agente.fim":
                    fim += 1
                for j in range(inicio, min(fim + 1, len(registros))):
                    adicionar(arquivo, j)
            elif evento_id in extrair_ids_evento(registro.dados):
                adicionar(arquivo, i)

    if not relevantes:
        raise AuditError(f"evento {evento_id} não encontrado em {origem}")

    mudou = True
    while mudou:
        ids_proposta = {
            proposta
            for item in relevantes.values()
            for proposta in extrair_ids_proposta(item.registro.to_dict())
        }
        mudou = False
        for arquivo, registros in registros_por_arquivo.items():
            for _i, registro in enumerate(registros):
                chave = (str(arquivo), registro.seq)
                if chave in relevantes:
                    continue
                if evento_id in extrair_ids_evento(registro.dados) or (
                    ids_proposta and ids_proposta & extrair_ids_proposta(registro.to_dict())
                ):
                    relevantes[chave] = RegistroArquivo(str(arquivo), registro)
                    mudou = True

    lista_relevantes = sorted(relevantes.values(), key=_ordenar_registro_arquivo)
    evento = next(
        (
            item.registro.dados.get("evento")
            for item in lista_relevantes
            if item.registro.tipo == "agente.inicio"
            and isinstance(item.registro.dados.get("evento"), Mapping)
        ),
        None,
    )
    cadeia = verificar_origem(origem, arquivos=sorted({Path(r.arquivo) for r in lista_relevantes}))
    linha = montar_linha_do_tempo(lista_relevantes)
    return {
        "evento_id": evento_id,
        "evento": dict(evento) if isinstance(evento, Mapping) else None,
        "origem": str(origem),
        "arquivos": sorted({r.arquivo for r in lista_relevantes}),
        "cadeia": cadeia,
        "linha_do_tempo": linha,
        "registros": [r.to_dict() for r in lista_relevantes],
        "resposta_final": next(
            (item.get("resposta") for item in reversed(linha) if item["tipo"] == "encerramento"),
            None,
        ),
    }


def verificar_registros(registros: list[Registro]) -> int:
    anterior = GENESIS
    for esperado, r in enumerate(registros, start=1):
        if r.seq != esperado:
            raise AuditError(f"sequência quebrada: esperado seq={esperado}, encontrado {r.seq}")
        if r.hash_anterior != anterior:
            raise AuditError(f"seq={r.seq}: hash_anterior não bate com o registro anterior")
        recalculado = calcular_hash(r.seq, r.ts, r.tipo, r.dados, r.hash_anterior)
        if recalculado != r.hash:
            raise AuditError(f"seq={r.seq}: hash não bate (registro alterado)")
        anterior = r.hash
    return len(registros)


def extrair_ids_evento(obj: Any) -> set[str]:
    """Encontra ids de evento ``E-0001`` dentro de uma estrutura JSON-like."""
    return _extrair_ids(obj, _RE_EVENTO)


def extrair_ids_proposta(obj: Any) -> set[str]:
    """Encontra ids de proposta ``P-0001`` dentro de uma estrutura JSON-like."""
    return _extrair_ids(obj, _RE_PROPOSTA)


def _extrair_ids(obj: Any, regex: re.Pattern[str]) -> set[str]:
    ids: set[str] = set()
    if isinstance(obj, str):
        ids.update(regex.findall(obj))
        return ids
    if isinstance(obj, Mapping):
        for valor in obj.values():
            ids.update(_extrair_ids(valor, regex))
        return ids
    if isinstance(obj, list | tuple):
        for valor in obj:
            ids.update(_extrair_ids(valor, regex))
    return ids


def _ordenar_registro_arquivo(item: RegistroArquivo) -> tuple[str, int, str, int]:
    prioridade = 0 if Path(item.arquivo).name == "hitl.jsonl" else 1
    return (
        item.registro.ts,
        prioridade,
        item.arquivo,
        item.registro.seq,
    )


def montar_linha_do_tempo(registros: list[RegistroArquivo]) -> list[dict[str, Any]]:
    """Converte registros brutos numa linha do tempo sem duplicar o log humano."""
    incluir_hitl_canonico = any(Path(r.arquivo).name == "hitl.jsonl" for r in registros)
    linha: list[dict[str, Any]] = []
    for item in registros:
        entrada = _registro_para_linha(item, incluir_hitl_canonico)
        if entrada is not None:
            linha.append(entrada)
    return linha


def _registro_para_linha(
    item: RegistroArquivo, incluir_hitl_canonico: bool
) -> dict[str, Any] | None:
    registro = item.registro
    dados = dict(registro.dados)
    base = {
        "ts": registro.ts,
        "seq": registro.seq,
        "arquivo": item.arquivo,
        "registro_tipo": registro.tipo,
    }
    if (
        incluir_hitl_canonico
        and registro.tipo in _TIPOS_HITL
        and Path(item.arquivo).name != "hitl.jsonl"
    ):
        return None
    if registro.tipo == "agente.inicio":
        return {
            **base,
            "tipo": "evento",
            "titulo": "Agente recebeu o evento",
            "execucao_tipo": dados.get("tipo"),
            "cluster": dados.get("cluster"),
            "evento": dados.get("evento"),
        }
    if registro.tipo == "mcp.chamada":
        ferramenta = str(dados.get("ferramenta"))
        resultado = dados.get("resultado")
        entrada = {
            **base,
            "tipo": "ferramenta",
            "titulo": _titulo_ferramenta(ferramenta),
            "ferramenta": ferramenta,
            "argumentos": dados.get("argumentos"),
            "resultado": resultado,
            "resultado_sha256": dados.get("resultado_sha256"),
            "duracao_ms": dados.get("ms"),
        }
        if ferramenta == "restore_options" and isinstance(resultado, Mapping):
            entrada["tipo"] = "opcoes"
            entrada["opcoes"] = list(resultado.get("opcoes") or [])
            entrada["outras_opcoes"] = list(resultado.get("outras_opcoes") or [])
        return entrada
    if registro.tipo in {"mcp.recusa", "mcp.erro"}:
        return {
            **base,
            "tipo": "ferramenta_erro",
            "titulo": (
                "Ferramenta recusada" if registro.tipo == "mcp.recusa" else "Ferramenta falhou"
            ),
            "ferramenta": dados.get("ferramenta"),
            "argumentos": dados.get("argumentos"),
            "erro": dados.get("erro"),
            "duracao_ms": dados.get("ms"),
        }
    if registro.tipo in {"agente.verificador.ok", "agente.verificador.recusa"}:
        checagens = dict(dados.get("checagens") or {})
        return {
            **base,
            "tipo": "verificador",
            "titulo": "Verificador aprovou a proposta"
            if registro.tipo.endswith(".ok")
            else "Verificador recusou a proposta",
            "status": "ok" if registro.tipo.endswith(".ok") else "recusa",
            "proposta": dados.get("proposta"),
            "chave": dados.get("chave"),
            "eletrico": dados.get("eletrico"),
            "gates_ok": [nome for nome, valor in checagens.items() if valor],
            "gates_falhos": [nome for nome, valor in checagens.items() if not valor],
            "problemas": list(dados.get("problemas") or []),
            "avisos": list(dados.get("avisos") or []),
            "checagens": checagens,
        }
    if registro.tipo == "agente.replanejamento":
        return {
            **base,
            "tipo": "replanejamento",
            "titulo": "Replanejamento após rejeição humana",
            "proposta_id": dados.get("proposta_id"),
            "motivo": dados.get("motivo"),
            "restricao": dados.get("restricao"),
            "n_replanejamento": dados.get("n_replanejamento"),
            "evento": dados.get("evento"),
        }
    if registro.tipo == "hitl.aprovacao":
        proposta = _proposta_humana(dados)
        resultado = dados.get("resultado")
        aprovada_por = (
            (resultado or {}).get("aprovada_por") if isinstance(resultado, Mapping) else None
        )
        operador = dados.get("operador") or (proposta or {}).get("aprovada_por") or aprovada_por
        return {
            **base,
            "tipo": "aprovacao",
            "titulo": "Aprovação humana",
            "operador": operador,
            "proposta": (proposta or {}).get("id"),
            "executar": dados.get("executar", True),
            "detalhes": proposta,
        }
    if registro.tipo == "hitl.rejeicao":
        proposta = _proposta_humana(dados)
        resultado = dados.get("resultado")
        aprovada_por = (
            (resultado or {}).get("aprovada_por") if isinstance(resultado, Mapping) else None
        )
        operador = dados.get("operador") or (proposta or {}).get("aprovada_por") or aprovada_por
        return {
            **base,
            "tipo": "rejeicao",
            "titulo": "Rejeição humana",
            "operador": operador,
            "proposta": (proposta or {}).get("id"),
            "motivo": dados.get("motivo") or (proposta or {}).get("motivo"),
            "detalhes": proposta,
        }
    if registro.tipo == "hitl.passo":
        return {
            **base,
            "tipo": "passo_humano",
            "titulo": "Execução passo a passo",
            "operador": dados.get("operador"),
            "proposta": dados.get("proposta_id"),
            "manobra": dados.get("manobra"),
            "passo": dados.get("passo"),
            "n_passos": dados.get("n_passos"),
            "erro": dados.get("erro"),
        }
    if registro.tipo == "agente.fim":
        return {
            **base,
            "tipo": "encerramento",
            "titulo": "Agente encerrou a execução",
            "execucao_tipo": dados.get("tipo"),
            "proposta": dados.get("proposta"),
            "veredito": dados.get("veredito"),
            "sequencia": list(dados.get("sequencia") or []),
            "rodadas": dados.get("rodadas"),
            "replanejamentos": dados.get("replanejamentos"),
            "recusas": dados.get("recusas"),
            "resposta": dados.get("resposta"),
            "erro": dados.get("erro"),
            "uso": dados.get("uso"),
        }
    return None


def _titulo_ferramenta(nome: str) -> str:
    return {
        "load_cluster": "Cluster carregado",
        "inject_fault": "Evento injetado",
        "locate_fault": "Falta localizada",
        "isolate_fault": "Isolamento calculado",
        "restore_options": "Opções de restauração avaliadas",
        "propose_plan": "Proposta registrada",
        "set_switch": "Manobra executada",
        "run_powerflow": "Fluxo de potência executado",
        "get_topology": "Topologia consultada",
        "get_switch_state": "Estado de chave consultado",
        "downstream_customers": "Clientes a jusante consultados",
        "get_proposal": "Proposta consultada",
    }.get(nome, f"Ferramenta {nome}")


def _proposta_humana(dados: Mapping[str, Any]) -> dict[str, Any] | None:
    proposta = dados.get("proposta")
    if isinstance(proposta, Mapping):
        return dict(proposta)
    resultado = dados.get("resultado")
    if isinstance(resultado, Mapping):
        if isinstance(resultado.get("proposta"), Mapping):
            return dict(resultado["proposta"])
        if "id" in resultado:
            return dict(resultado)
    return None
