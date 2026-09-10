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
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GENESIS = "0" * 64
ALGORITMO = "sha256"


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
