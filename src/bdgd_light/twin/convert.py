"""Conversão BDGD → OpenDSS via ``bdgd2opendss`` (extra ``twin``).

O bdgd2opendss lê o GDB inteiro (18 tabelas, inclusive BASE, PIP e as *_tab) e escreve, para cada
CTMT, ``<out>/sub_<SUB>/<CTMT>/`` com 36 Masters — um por tipo de dia (DU, SA, DO) e mês — mais os
arquivos de segmentos, chaves, transformadores, cargas e curvas. Aqui só orquestramos a chamada e
localizamos o Master desejado.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

_DIAS = ("DU", "SA", "DO")
_RE_MASTER = re.compile(r"^Master_(?P<dia>DU|SA|DO)(?P<mes>\d{2})_", re.IGNORECASE)
# unidade de banco escrita pelo bdgd2opendss como trifásica (phases=3) com barras de 2 nós
_RE_UNIDADE_BANCO = re.compile(
    r'^(?P<ini>New\s+"?Transformer\.[^"\s]+"?\s+)phases=3(?P<meio>\s+windings=2\s+'
    r'buses=\[\s*"?[^"\s.]+\.\d\.\d"?\s+"?[^"\s.]+\.\d\.\d"?\s*\][^\n]*?kvs=\[)'
    r"(?P<kv1>[\d.]+)\s+(?P<kv2>[\d.]+)\]",
    re.IGNORECASE,
)


def corrigir_bancos_monofasicos(pasta: str | Path) -> int:
    """Corrige, nos ``TransformadorMTMTMTBT_*.dss`` de ``pasta``, as unidades de bancos de
    transformadores monofásicos (``UNTRMT.TIP_TRAFO`` ``DF``/``DA``) e devolve quantas mudou.

    O bdgd2opendss escreve cada unidade (``TRF_<cod>A/B/C``) como ``phases=3 windings=2`` com
    barras de **dois** nós (``MT.2.3`` / ``BT.2.4``) e ``kvs=[13.2 0.22]``. Num elemento trifásico
    o OpenDSS liga o terceiro condutor ao nó 0 (terra), o que aterra um vértice do delta: no cluster
    Tijuca isso dava 64 % de perdas, 0,2 pu na BT e trafos a 1.100 % de carga. Uma unidade ligada
    entre duas fases MT e fase–neutro BT é ``phases=1`` com ``kvs=[13.2 0.127]`` (tensão do
    enrolamento). A função é idempotente e mantém o resto da linha.
    """
    n = 0
    for arquivo in sorted(Path(pasta).glob("TransformadorMTMTMTBT_*.dss")):
        texto = arquivo.read_text(encoding="utf-8", errors="replace")

        def _troca(m: re.Match) -> str:
            nonlocal n
            n += 1
            kv2 = float(m["kv2"]) / 3**0.5
            return f"{m['ini']}phases=1{m['meio']}{m['kv1']} {kv2:.3f}]"

        novo = "\n".join(_RE_UNIDADE_BANCO.sub(_troca, ln) for ln in texto.split("\n"))
        if novo != texto:
            arquivo.write_text(novo, encoding="utf-8")
    return n


def localizar_pasta(out: str | Path, ctmt: str) -> Path | None:
    """Pasta ``<out>/sub_*/<ctmt>`` gerada pelo bdgd2opendss (ou ``None`` se não existir)."""
    out = Path(out)
    candidatos = sorted(p for p in out.glob(f"sub_*/{ctmt}") if p.is_dir())
    if not candidatos and (out / ctmt).is_dir():
        return out / ctmt
    return candidatos[-1] if candidatos else None


def listar_masters(pasta: str | Path) -> list[Path]:
    return sorted(p for p in Path(pasta).glob("Master_*.dss") if p.is_file())


def escolher_master(pasta: str | Path, dia: str = "DU", mes: int = 1) -> Path:
    """Master do tipo de dia (DU/SA/DO) e mês pedidos; erro claro se não existir."""
    dia = dia.upper()
    if dia not in _DIAS:
        raise ValueError(f"dia deve ser um de {_DIAS}, não {dia!r}")
    masters = listar_masters(pasta)
    if not masters:
        raise FileNotFoundError(f"nenhum Master_*.dss em {pasta}")
    for m in masters:
        g = _RE_MASTER.match(m.name)
        if g and g["dia"].upper() == dia and int(g["mes"]) == mes:
            return m
    raise FileNotFoundError(
        f"Master {dia}{mes:02d} não encontrado em {pasta}; disponíveis: "
        + ", ".join(m.name for m in masters[:6])
        + (" …" if len(masters) > 6 else "")
    )


def converter(gdb: str | Path, ctmt: str, out: str | Path) -> tuple[Path, float]:
    """Roda ``bdgd2opendss.run`` para um CTMT e devolve (pasta do alimentador, segundos).

    Exige um ``.gdb`` (o bdgd2opendss lista o diretório para detectar o tipo de BDGD); GPKG e
    Parquet não são aceitos. Reutiliza a pasta se já houver Masters (idempotente): apague-a para
    reconverter.
    """
    gdb = Path(gdb)
    out = Path(out)
    existente = localizar_pasta(out, ctmt)
    if existente and listar_masters(existente):
        corrigir_bancos_monofasicos(existente)  # idempotente: conserta conversões antigas
        return existente, 0.0
    if not gdb.is_dir():
        raise FileNotFoundError(f"{gdb} não é um diretório .gdb")
    try:
        import bdgd2opendss
    except ImportError as exc:  # pragma: no cover - depende do extra
        raise ImportError("bdgd2opendss não instalado; rode `uv sync --extra twin`.") from exc

    out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    bdgd2opendss.run(str(gdb), str(out), all_feeders=False, lst_feeders=[ctmt])
    pasta = localizar_pasta(out, ctmt)
    if pasta is None or not listar_masters(pasta):
        raise RuntimeError(
            f"bdgd2opendss terminou sem gerar Master para {ctmt} em {out} "
            "(CTMT inexistente na BDGD ou tabela obrigatória ausente; veja o log acima)."
        )
    corrigir_bancos_monofasicos(pasta)
    return pasta, time.perf_counter() - t0
