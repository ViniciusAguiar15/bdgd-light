"""Master OpenDSS de um cluster de alimentadores + manobras vindas do grafo.

O bdgd2opendss gera um circuito por CTMT, cada um com a própria ``Circuit`` (Vsource) e com as
chaves NA comentadas. Para simular transferência de carga (FLISR) precisamos dos CTMT vizinhos no
**mesmo** circuito: este módulo escreve um ``Master_cluster_*.dss`` que declara a ``Circuit`` no
barramento do primeiro CTMT, uma ``Vsource`` por CTMT adicional (mesma SE, 13,2 kV, 1,045 pu) e
redireciona os arquivos de elementos de todos; em seguida aplica as manobras do grafo
(``bdgd_light.grid``): ``abrir`` → ``open line.cmt_<chave>``; ``fechar`` de uma chave NA → ``New
Line`` da chave mais um jumper até o ``PAC_VIZ`` da tie geométrica (as ties não compartilham PAC).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from bdgd_light.grid.rede import ABRIR, FECHAR, TIE, ChaveInexistenteError, Rede

# arquivos de elementos redirecionados de cada CTMT, na ordem do Master original
_ARQUIVOS = (
    "CodCondutor",
    "TransformadorMTMTMTBT",
    "SegmentosMT",
    "ChavesMT",
    "SegmentosBT",
    "ChavesBT",
    "RamaisBT",
    "Medidores",
    "CurvaCarga",
)
# o bdgd2opendss gera GD_BT mas NÃO o inclui no Master; com ele, TQR33859/TQR33862 divergem
_ARQUIVO_GD = "GD_BT"
_RE_CIRCUITO = re.compile(
    r'New\s+"?Circuit\.(?P<nome>[^"\s]+)"?\s+(?P<params>.*)$', re.IGNORECASE | re.MULTILINE
)
_RE_BUS1 = re.compile(r'bus1="?(?P<bus>[^"\s]+)"?', re.IGNORECASE)
_RE_VBASES = re.compile(r"Set\s+Voltagebases\s*=\s*\[(?P<v>[^\]]*)\]", re.IGNORECASE)
_CHAVE_DSS = "r1=0.001 r0=0.001 x1=0.0 x0=0.0 c1=0.0 c0=0.0 switch=T length=0.001 units=km"


def _arquivo(pasta: Path, prefixo: str, dia: str = "", mes: int = 0) -> Path | None:
    sufixo = f"{dia.upper()}{mes:02d}_" if dia else ""
    achados = sorted(pasta.glob(f"{prefixo}_{sufixo}*.dss"))
    return achados[0] if achados else None


def _circuito(pasta: Path) -> tuple[str, str, str]:
    """(nome, bus1, parâmetros) da ``Circuit`` do CircuitoMT do CTMT."""
    arq = _arquivo(pasta, "CircuitoMT")
    if arq is None:
        raise FileNotFoundError(f"CircuitoMT_*.dss não encontrado em {pasta}")
    m = _RE_CIRCUITO.search(arq.read_text(encoding="utf-8", errors="replace"))
    if not m:
        raise ValueError(f"nenhum `New Circuit` em {arq}")
    b = _RE_BUS1.search(m["params"])
    if not b:
        raise ValueError(f"Circuit sem bus1 em {arq}")
    return m["nome"], b["bus"], m["params"].strip()


def _voltagebases(pastas: Iterable[Path]) -> list[float]:
    bases: set[float] = set()
    for pasta in pastas:
        master = next(iter(sorted(pasta.glob("Master_*.dss"))), None)
        if master is None:
            continue
        m = _RE_VBASES.search(master.read_text(encoding="utf-8", errors="replace"))
        if m:
            bases |= {float(x) for x in re.split(r"[\s,]+", m["v"].strip()) if x}
    return sorted(bases) or [0.22, 13.2]


def comandos_manobras(rede: Rede, manobras: Sequence[Mapping]) -> list[str]:
    """Traduz passos ``{"acao": abrir|fechar, "chave": COD_ID}`` em comandos OpenDSS.

    Chaves NF existem no modelo como ``Line.CMT_<COD_ID>`` (``open``/``close``). Chaves NA saem
    comentadas do bdgd2opendss: ``fechar`` cria a ``Line`` entre os PAC da chave e, para cada tie
    geométrica ligada a um desses PAC no grafo, um jumper ``Line.TIE_<COD_ID>_<n>`` até o
    ``PAC_VIZ``.
    """
    comandos: list[str] = []
    for passo in manobras:
        acao, chave = passo["acao"], passo["chave"]
        if chave not in rede.chaves:
            raise ChaveInexistenteError(chave)
        a, b = rede.chaves[chave]
        dados = rede.grafo.edges[a, b]
        if acao == ABRIR:
            if dados["normal"] == "NA":
                continue  # já está fora do modelo
            comandos.append(f"open line.cmt_{chave} term=1")
        elif acao == FECHAR:
            if dados["normal"] == "NF":
                comandos.append(f"close line.cmt_{chave} term=1")
                continue
            comandos.append(
                f'New "Line.CMT_{chave}" phases=3 bus1="{a}.1.2.3" bus2="{b}.1.2.3" {_CHAVE_DSS}'
            )
            n = 0
            for ponta in (a, b):
                for viz, d in rede.grafo.adj[ponta].items():
                    if d["tipo"] == TIE and not viz.startswith("EXT:"):
                        n += 1
                        comandos.append(
                            f'New "Line.TIE_{chave}_{n}" phases=3 bus1="{ponta}.1.2.3" '
                            f'bus2="{viz}.1.2.3" {_CHAVE_DSS}'
                        )
        else:
            raise ValueError(f"ação desconhecida: {acao!r}")
    return comandos


def montar_master_cluster(
    pastas: Sequence[Path],
    out: Path,
    *,
    dia: str = "DU",
    mes: int = 1,
    comandos: Sequence[str] = (),
    nome: str | None = None,
    gd: bool = False,
) -> Path:
    """Escreve um Master único com os CTMT de ``pastas`` (saídas do bdgd2opendss) e o devolve.

    A ``Circuit`` fica no barramento do primeiro CTMT; os demais entram como ``Vsource`` na mesma
    tensão/pu. ``comandos`` (ex.: de ``comandos_manobras``) são escritos antes de
    ``Calcvoltagebases``. ``gd=True`` inclui os geradores de ``GD_BT`` (o Master do bdgd2opendss não
    os inclui; com eles o fluxo dos alimentadores TQR diverge).
    """
    pastas = [Path(p).resolve() for p in pastas]
    if not pastas:
        raise ValueError("informe ao menos uma pasta de CTMT")
    circuitos = [_circuito(p) for p in pastas]
    nome = nome or "cluster_" + "-".join(c[0] for c in circuitos)
    linhas = ["clear", "Set DefaultBaseFrequency=60", ""]
    _, _, params = circuitos[0]
    linhas.append(f'New "Circuit.{nome}" {params}')
    # linecodes/loadshapes repetem entre CTMT (mesma definição) e a Light tem GD com COD_ID em
    # branco (`generator. `) em mais de um CTMT; sem AllowDuplicates o compile aborta no aviso #266
    linhas.append("Set AllowDuplicates=yes")
    for ctmt, bus1, params in circuitos[1:]:
        # mesma SE: mesma tensão e pu da Circuit; só troca o barramento
        p = _RE_BUS1.sub(f'bus1="{bus1}"', params)
        linhas.append(f'New "Vsource.{ctmt}" {p}')
    linhas.append("")
    for (ctmt, _, _), pasta in zip(circuitos, pastas, strict=True):
        linhas.append(f"! ---- {ctmt} ({pasta.name})")
        for prefixo in _ARQUIVOS + ((_ARQUIVO_GD,) if gd else ()):
            arq = _arquivo(pasta, prefixo)
            if arq is not None:
                linhas.append(f'Redirect "{arq}"')
        for prefixo in ("CargasBT", "CargasMT"):
            arq = _arquivo(pasta, prefixo, dia, mes)
            if arq is not None:
                linhas.append(f'Redirect "{arq}"')
            elif prefixo == "CargasBT" and _arquivo(pasta, prefixo) is not None:
                # há CargasBT de outro dia/mês: o pedido está errado (CargasMT só existe com UCMT)
                raise FileNotFoundError(
                    f"{prefixo}_{dia.upper()}{mes:02d}_*.dss ausente em {pasta}"
                )
        if _arquivo(pasta, "CargasBT") is None and _arquivo(pasta, "CargasMT") is None:
            # circuito expresso/reserva (0 UCBT/UCMT): só a fonte e a rede, sem carga
            linhas.append(f"! {ctmt}: sem CargasBT/CargasMT (circuito sem carga)")
        linhas.append("")
    if comandos:
        linhas.append("! ---- manobras")
        linhas.extend(comandos)
        linhas.append("")
    bases = " ".join(f"{b:g}" for b in _voltagebases(pastas))
    linhas += [f"Set Voltagebases=[{bases}]", "Calcvoltagebases", "Set mode=snapshot", ""]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(linhas), encoding="utf-8")
    return out
