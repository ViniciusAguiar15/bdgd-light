"""Fluxo de potência com OpenDSSDirect sobre um Master .dss.

O Master gerado pelo bdgd2opendss vem em ``mode=daily`` e sem ``Solve``; aqui sempre resolvemos um
snapshot (patamar de pico das curvas CRVCRG, ``kw`` = demanda máxima) e, se o método padrão não
convergir, aplicamos uma cascata documentada de estabilizadores (ver ``ESTABILIZADORES``),
registrando no resultado quais foram necessários.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

# Cascata de estabilizadores, aplicada em ordem até convergir; cada item é (rótulo, comandos).
#   1. mais iterações — resolve a maioria dos casos "quase" convergidos;
#   2. vminpu=0,9 — abaixo de 0,9 pu as cargas passam a impedância constante (recomendação do
#      próprio OpenDSS para cargas de corrente/potência constante em barras muito deprimidas);
#   3. impedância constante em todas as cargas — sempre converge; é o último recurso e subestima a
#      carga nas barras deprimidas.
ESTABILIZADORES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("maxiterations=100", ("set maxiterations=100",)),
    ("vminpu=0.9", ("batchedit load..* vminpu=0.9",)),
    ("model=2", ("batchedit load..* model=2",)),
)

_NEUTRO = 4  # convenção do bdgd2opendss: condutor .4 é o neutro aterrado por reator


class ErroOpenDSS(RuntimeError):
    """Erro devolvido pelo motor OpenDSS ao compilar ou resolver o circuito."""


@dataclass
class PowerFlowResult:
    """Resultado de um fluxo de potência snapshot."""

    master: Path
    circuito: str
    convergiu: bool
    iteracoes: int
    ajustes: list[str]
    vmin_ref: float
    vmax_ref: float
    n_barras: int
    n_nos: int
    n_linhas: int
    n_trafos: int
    n_cargas: int
    tensoes: pd.DataFrame  # barra, no, fase, kv_base, v_pu
    correntes: pd.DataFrame  # elemento, tipo, i_max_a, i_nominal_a, carregamento_pct
    fontes: pd.DataFrame  # fonte (Vsource), barra, kw, kvar fornecidos
    perdas_kw: float
    perdas_kvar: float
    potencia_kw: float
    potencia_kvar: float
    tempo_s: float
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def fases(self) -> pd.DataFrame:
        """Nós de fase (1–3) energizados; exclui neutro e nós a 0 pu."""
        t = self.tensoes
        return t[(t["fase"] < _NEUTRO) & (t["v_pu"] > 0.0)]

    @property
    def n_desenergizados(self) -> int:
        t = self.tensoes
        return int(((t["fase"] < _NEUTRO) & (t["v_pu"] <= 0.0)).sum())

    @property
    def v_min_pu(self) -> float:
        f = self.fases
        return float(f["v_pu"].min()) if len(f) else float("nan")

    @property
    def v_max_pu(self) -> float:
        f = self.fases
        return float(f["v_pu"].max()) if len(f) else float("nan")

    @property
    def violacoes(self) -> pd.DataFrame:
        """Nós de fase fora da faixa [vmin_ref, vmax_ref], com coluna ``tipo`` (sub/sobre)."""
        f = self.fases
        v = f[(f["v_pu"] < self.vmin_ref) | (f["v_pu"] > self.vmax_ref)].copy()
        v["tipo"] = v["v_pu"].map(lambda x: "sub" if x < self.vmin_ref else "sobre")
        return v.sort_values("v_pu").reset_index(drop=True)

    @property
    def sobrecargas(self) -> pd.DataFrame:
        c = self.correntes
        return (
            c[c["carregamento_pct"] > 100.0]
            .sort_values("carregamento_pct", ascending=False)
            .reset_index(drop=True)
        )

    def piores_barras(self, n: int = 10) -> pd.DataFrame:
        return self.fases.nsmallest(n, "v_pu").reset_index(drop=True)

    def resumo(self) -> dict[str, Any]:
        viol = self.violacoes
        fases = self.fases
        return {
            "master": str(self.master),
            "circuito": self.circuito,
            "convergiu": self.convergiu,
            "iteracoes": self.iteracoes,
            "ajustes": list(self.ajustes),
            "n_barras": self.n_barras,
            "n_nos": self.n_nos,
            "n_linhas": self.n_linhas,
            "n_trafos": self.n_trafos,
            "n_cargas": self.n_cargas,
            "n_nos_fase": int(len(fases)),
            "n_desenergizados": self.n_desenergizados,
            "v_min_pu": self.v_min_pu,
            "v_max_pu": self.v_max_pu,
            "n_subtensao": int((viol["tipo"] == "sub").sum()),
            "n_sobretensao": int((viol["tipo"] == "sobre").sum()),
            "n_sobrecargas": int(len(self.sobrecargas)),
            "perdas_kw": self.perdas_kw,
            "perdas_kvar": self.perdas_kvar,
            "potencia_kw": self.potencia_kw,
            "potencia_kvar": self.potencia_kvar,
            "fontes": {f.fonte: round(f.kw, 1) for f in self.fontes.itertuples(index=False)},
            "tempo_s": self.tempo_s,
        }

    def tensoes_mt(self, kv_min: float = 1.0) -> pd.DataFrame:
        """Nós de fase com base acima de ``kv_min`` kV (MT), com o CTMT pelo prefixo da barra."""
        f = self.fases
        mt = f[f["kv_base"] > kv_min].copy()
        mt["ctmt"] = mt["barra"].str.split("_mt_", n=1).str[0].str.upper()
        return mt


def _dss():
    try:
        import opendssdirect as dss
    except ImportError as exc:  # pragma: no cover - depende do extra
        raise ImportError(
            "opendssdirect não instalado; rode `uv sync --extra twin` "
            "(ou `uv add opendssdirect.py`)."
        ) from exc
    return dss


def _comando(dss, texto: str) -> None:
    try:
        dss.Text.Command(texto)
    except Exception as exc:  # DSSException não é exportada de forma estável
        raise ErroOpenDSS(f"{texto!r}: {exc}") from exc


def _tensoes(dss) -> pd.DataFrame:
    linhas: list[tuple[str, str, int, float, float]] = []
    for barra in dss.Circuit.AllBusNames():
        dss.Circuit.SetActiveBus(barra)
        kv = float(dss.Bus.kVBase())
        mags = dss.Bus.puVmagAngle()[0::2]
        for no, v in zip(dss.Bus.Nodes(), mags, strict=False):
            linhas.append((barra, f"{barra}.{int(no)}", int(no), kv, float(v)))
    return pd.DataFrame(linhas, columns=["barra", "no", "fase", "kv_base", "v_pu"])


def _fontes(dss) -> pd.DataFrame:
    linhas = []
    i = dss.Vsources.First()
    while i:
        p = dss.CktElement.TotalPowers()
        linhas.append(
            (
                dss.Vsources.Name(),
                dss.CktElement.BusNames()[0].split(".")[0],
                -float(p[0]),
                -float(p[1]),
            )
        )
        i = dss.Vsources.Next()
    return pd.DataFrame(linhas, columns=["fonte", "barra", "kw", "kvar"])


def _correntes(dss) -> pd.DataFrame:
    nomes = dss.PDElements.AllNames()
    if not nomes:
        return pd.DataFrame(
            columns=["elemento", "tipo", "i_max_a", "i_nominal_a", "carregamento_pct"]
        )
    imax = dss.PDElements.AllMaxCurrents(False)
    pct = dss.PDElements.AllPctNorm(False)
    df = pd.DataFrame(
        {
            "elemento": nomes,
            "tipo": [n.split(".", 1)[0] for n in nomes],
            "i_max_a": imax,
            "carregamento_pct": pct,
        }
    )
    # i_nominal = i_max / (pct/100); elementos sem ampacidade (reatores, chaves) ficam sem
    # carregamento
    com_nominal = df["carregamento_pct"] > 0
    df["i_nominal_a"] = float("nan")
    df.loc[com_nominal, "i_nominal_a"] = (
        df.loc[com_nominal, "i_max_a"] / df.loc[com_nominal, "carregamento_pct"] * 100.0
    )
    df.loc[~com_nominal, "carregamento_pct"] = float("nan")
    return df[["elemento", "tipo", "i_max_a", "i_nominal_a", "carregamento_pct"]]


def run_powerflow(
    master: str | Path,
    *,
    vmin: float = 0.93,
    vmax: float = 1.05,
    modo: str | None = "snapshot",
    estabilizar: bool = True,
    comandos_extra: list[str] | tuple[str, ...] = (),
) -> PowerFlowResult:
    """Compila ``master`` no OpenDSS, resolve e devolve tensões, correntes, perdas e violações.

    ``comandos_extra`` são enviados após a compilação e antes do ``Solve`` (ex.: ``set
    loadmult=0.6``, ``open line.cmt_123 term=1``). Com ``estabilizar=True`` a cascata
    ``ESTABILIZADORES`` é aplicada até a convergência; os rótulos aplicados ficam em
    ``PowerFlowResult.ajustes``.
    """
    master = Path(master).resolve()
    if not master.is_file():
        raise FileNotFoundError(master)
    dss = _dss()
    t0 = time.perf_counter()
    cwd = os.getcwd()  # o `compile` muda o diretório de trabalho do processo
    try:
        _comando(dss, "clear")
        _comando(dss, f'compile "{master}"')
    finally:
        os.chdir(cwd)
    if modo:
        _comando(dss, f"set mode={modo}")
    for cmd in comandos_extra:
        _comando(dss, cmd)

    ajustes: list[str] = []
    dss.Solution.Solve()
    if not dss.Solution.Converged() and estabilizar:
        for rotulo, comandos in ESTABILIZADORES:
            for cmd in comandos:
                _comando(dss, cmd)
            ajustes.append(rotulo)
            dss.Solution.Solve()
            if dss.Solution.Converged():
                break

    perdas = dss.Circuit.Losses()
    potencia = dss.Circuit.TotalPower()
    tensoes = _tensoes(dss)
    return PowerFlowResult(
        master=master,
        circuito=dss.Circuit.Name(),
        convergiu=bool(dss.Solution.Converged()),
        iteracoes=int(dss.Solution.Iterations()),
        ajustes=ajustes,
        vmin_ref=vmin,
        vmax_ref=vmax,
        n_barras=int(dss.Circuit.NumBuses()),
        n_nos=int(dss.Circuit.NumNodes()),
        n_linhas=int(dss.Lines.Count()),
        n_trafos=int(dss.Transformers.Count()),
        n_cargas=int(dss.Loads.Count()),
        tensoes=tensoes,
        correntes=_correntes(dss),
        fontes=_fontes(dss),
        perdas_kw=float(perdas[0]) / 1000.0,
        perdas_kvar=float(perdas[1]) / 1000.0,
        potencia_kw=-float(potencia[0]),
        potencia_kvar=-float(potencia[1]),
        tempo_s=time.perf_counter() - t0,
        extra={
            "modo": dss.Solution.ModeID(),
            "controle_iteracoes": dss.Solution.ControlIterations(),
        },
    )
