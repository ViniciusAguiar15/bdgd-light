"""Impacto estimado de uma manobra em consumidor-minutos e DEC do conjunto.

As fórmulas aqui tratam o ``tempo_reparo_min`` explicitamente como **premissa operacional**:
não é medição realizada do evento, e sim uma estimativa do que a manobra poupa se o reparo
demorar esse tempo.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from bdgd_light.grid.rede import Isolamento, OpcaoRestauracao, Rede

TEMPO_REPARO_PADRAO_MIN = 180.0
TEMPO_MANOBRA_PADRAO_MIN = 5.0


def premissa_impacto(
    tempo_reparo_min: float = TEMPO_REPARO_PADRAO_MIN,
    tempo_manobra_min: float = TEMPO_MANOBRA_PADRAO_MIN,
) -> str:
    """Frase curta para deixar explícita a hipótese do cálculo."""
    return (
        "impacto estimado do evento sob premissa de reparo em "
        f"{tempo_reparo_min:g} min e manobra em {tempo_manobra_min:g} min; "
        "não é medição realizada de DEC"
    )


@dataclass(frozen=True)
class ImpactoDECConjunto:
    """Impacto estimado no DEC de um conjunto elétrico."""

    codigo: str
    nome: str
    total_uc: int
    ucs_restauradas_no_conjunto: int
    dec_horas: float
    dec_minutos: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ImpactoEstimado:
    """Resultado do impacto estimado de uma opção de restauração."""

    tempo_reparo_min: float
    tempo_manobra_min: float
    clientes_restaurados: int
    clientes_sem_tensao_ate_reparo: int
    consumidor_minutos_evitados: float
    premissa: str
    dec_conjunto: ImpactoDECConjunto | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["dec_conjunto"] = None if self.dec_conjunto is None else self.dec_conjunto.to_dict()
        return d


def calcular_impacto_opcao(
    rede: Rede,
    opcao: OpcaoRestauracao,
    *,
    isolamento: Isolamento,
    tempo_reparo_min: float = TEMPO_REPARO_PADRAO_MIN,
    tempo_manobra_min: float = TEMPO_MANOBRA_PADRAO_MIN,
) -> ImpactoEstimado:
    """Calcula o impacto estimado da opção sob a hipótese de tempo de reparo informado."""
    tempo_reparo = _tempo_positivo("tempo_reparo_min", tempo_reparo_min)
    tempo_manobra = _tempo_positivo("tempo_manobra_min", tempo_manobra_min)
    clientes_restaurados = int(opcao.clientes.total)
    clientes_restantes = max(int(isolamento.clientes_desligados.total) - clientes_restaurados, 0)
    minutos_evitar_por_cliente = max(tempo_reparo - tempo_manobra, 0.0)
    consumidor_minutos = float(clientes_restaurados) * minutos_evitar_por_cliente
    dec_conjunto = _impacto_dec_conjunto(rede, opcao.nos, consumidor_minutos)
    return ImpactoEstimado(
        tempo_reparo_min=tempo_reparo,
        tempo_manobra_min=tempo_manobra,
        clientes_restaurados=clientes_restaurados,
        clientes_sem_tensao_ate_reparo=clientes_restantes,
        consumidor_minutos_evitados=consumidor_minutos,
        premissa=premissa_impacto(tempo_reparo, tempo_manobra),
        dec_conjunto=dec_conjunto,
    )


def _tempo_positivo(nome: str, valor: float) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{nome} inválido: {valor!r}") from exc
    if numero < 0:
        raise ValueError(f"{nome} deve ser ≥ 0 min")
    return numero


def _impacto_dec_conjunto(
    rede: Rede, nos: Iterable[str], consumidor_minutos: float
) -> ImpactoDECConjunto | None:
    camadas = rede.camadas
    if camadas.conj is None or camadas.conj.empty:
        return None
    codigo = _resolver_codigo_conjunto(rede, set(nos))
    if codigo is None:
        return None
    total_uc = _total_uc_conjunto(rede, codigo)
    if total_uc <= 0:
        return None
    nome = _nome_conjunto(camadas.conj, codigo)
    restauradas = _clientes_por_conjunto(rede, set(nos)).get(codigo, 0)
    dec_horas = consumidor_minutos / total_uc / 60.0
    return ImpactoDECConjunto(
        codigo=codigo,
        nome=nome,
        total_uc=total_uc,
        ucs_restauradas_no_conjunto=restauradas,
        dec_horas=dec_horas,
        dec_minutos=60.0 * dec_horas,
    )


def _resolver_codigo_conjunto(rede: Rede, nos: set[str]) -> str | None:
    contagens = _clientes_por_conjunto(rede, nos)
    codigo = _modo_unico(contagens)
    if codigo is not None:
        return codigo
    codigo = _modo_unico(_ativos_por_conjunto(rede, nos))
    if codigo is not None:
        return codigo
    ctmts = Counter(
        str(d.get("ctmt"))
        for no, d in rede.grafo.nodes(data=True)
        if no in nos and d.get("ctmt") not in (None, "")
    )
    ctmt = _modo_unico(ctmts)
    if ctmt is None:
        return None
    return _conjunto_do_ctmt(rede, ctmt)


def _modo_unico(contagens: Mapping[str, int]) -> str | None:
    validas = [(codigo, int(total)) for codigo, total in contagens.items() if codigo and total > 0]
    if not validas:
        return None
    validas.sort(key=lambda item: (-item[1], item[0]))
    if len(validas) == 1 or validas[0][1] > validas[1][1]:
        return validas[0][0]
    return None


def _clientes_por_conjunto(rede: Rede, nos: set[str]) -> Counter[str]:
    contagens: Counter[str] = Counter()
    camadas = rede.camadas
    if camadas.ucmt_tab is not None and {"PAC", "CONJ"} <= set(camadas.ucmt_tab.columns):
        ucmt = camadas.ucmt_tab
        sel = ucmt[ucmt["PAC"].isin(nos)]
        contagens.update(_serie_codigos(sel["CONJ"]))
    if (
        camadas.untrmt is not None
        and camadas.ucbt_tab is not None
        and {"COD_ID", "PAC_1"} <= set(camadas.untrmt.columns)
        and {"UNI_TR_MT", "CONJ"} <= set(camadas.ucbt_tab.columns)
    ):
        trafos = set(camadas.untrmt.loc[camadas.untrmt["PAC_1"].isin(nos), "COD_ID"])
        if trafos:
            sel = camadas.ucbt_tab[camadas.ucbt_tab["UNI_TR_MT"].isin(trafos)]
            contagens.update(_serie_codigos(sel["CONJ"]))
    return contagens


def _ativos_por_conjunto(rede: Rede, nos: set[str]) -> Counter[str]:
    contagens: Counter[str] = Counter()
    camadas = rede.camadas
    if camadas.ssdmt is not None and {"PAC_1", "PAC_2", "CONJ"} <= set(camadas.ssdmt.columns):
        trechos = camadas.ssdmt[camadas.ssdmt["PAC_1"].isin(nos) | camadas.ssdmt["PAC_2"].isin(nos)]
        contagens.update(_serie_codigos(trechos["CONJ"]))
    if camadas.unsemt is not None and {"PAC_1", "PAC_2", "CONJ"} <= set(camadas.unsemt.columns):
        chaves = camadas.unsemt[
            camadas.unsemt["PAC_1"].isin(nos) | camadas.unsemt["PAC_2"].isin(nos)
        ]
        contagens.update(_serie_codigos(chaves["CONJ"]))
    if camadas.untrmt is not None and {"PAC_1", "CONJ"} <= set(camadas.untrmt.columns):
        trafos = camadas.untrmt[camadas.untrmt["PAC_1"].isin(nos)]
        contagens.update(_serie_codigos(trafos["CONJ"]))
    return contagens


def _conjunto_do_ctmt(rede: Rede, ctmt: str) -> str | None:
    camadas = rede.camadas
    if camadas.ctmt is not None and {"COD_ID", "CONJ"} <= set(camadas.ctmt.columns):
        linhas = camadas.ctmt.loc[camadas.ctmt["COD_ID"] == ctmt, "CONJ"]
        codigos = list(_serie_codigos(linhas))
        if len(codigos) == 1:
            return codigos[0]
    for camada, coluna in (
        (camadas.ssdmt, "CTMT"),
        (camadas.unsemt, "CTMT"),
        (camadas.untrmt, "CTMT"),
        (camadas.ucmt_tab, "CTMT"),
        (camadas.ucbt_tab, "CTMT"),
    ):
        if camada is None or {coluna, "CONJ"} - set(camada.columns):
            continue
        sel = camada.loc[camada[coluna] == ctmt, "CONJ"]
        codigo = _modo_unico(Counter(_serie_codigos(sel)))
        if codigo is not None:
            return codigo
    return None


def _total_uc_conjunto(rede: Rede, codigo: str) -> int:
    total = 0
    camadas = rede.camadas
    for camada in (camadas.ucbt_tab, camadas.ucmt_tab):
        if camada is None or "CONJ" not in camada.columns:
            continue
        total += int((_normalizar_serie(camada["CONJ"]) == codigo).sum())
    return total


def _nome_conjunto(conj: pd.DataFrame, codigo: str) -> str:
    if "COD_ID" not in conj.columns:
        return codigo
    serie = _normalizar_serie(conj["COD_ID"])
    linha = conj.loc[serie == codigo]
    if linha.empty:
        return codigo
    for coluna in ("NOME", "DESCR"):
        if coluna in linha.columns:
            texto = _texto(linha.iloc[0][coluna])
            if texto:
                return texto
    return codigo


def _serie_codigos(serie: pd.Series) -> list[str]:
    return [codigo for codigo in _normalizar_serie(serie).tolist() if codigo]


def _normalizar_serie(serie: pd.Series) -> pd.Series:
    return serie.map(_texto)


def _texto(valor: Any) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    if pd.isna(valor):
        return ""
    return str(valor).strip()
