"""Diagnóstico de convergência de um Master OpenDSS (issue #44).

Responde, para um Master gerado pelo ``bdgd-light dss``: o método padrão converge? qual degrau da
cascata de estabilizadores resolve? a não convergência é lenta ou um ciclo-limite (e em que nós)?
quais cargas de corrente constante precisam do ``vminpu=0.9`` (tensão *terminal* fase-neutro
abaixo de 0,9 pu) e em que circuitos BT/trafos elas estão?

Uso::

    uv run scripts/diagnostico_convergencia.py data/dss/gpkg/<cluster>/Master_DU01_base.dss

Roda o motor DSS no próprio processo (não usa ``twin.powerflow.no_motor``); é uma ferramenta de
investigação, não faz parte do fluxo do gêmeo.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

MATRIZ = (
    ("padrão (maxiterations=15, vminpu do Master)", ()),
    ("maxiterations=100", ("set maxiterations=100",)),
    ("vminpu=0.9 (maxiterations=15)", ("batchedit load..* vminpu=0.9",)),
    ("vminpu=0.95 (maxiterations=15)", ("batchedit load..* vminpu=0.95",)),
    ("maxiterations=100 + vminpu=0.9", ("set maxiterations=100", "batchedit load..* vminpu=0.9")),
    ("cargas model=3 -> model=2", ("batchedit load..* model=2",)),
    ("algorithm=newton + maxiterations=100", ("set algorithm=newton", "set maxiterations=100")),
    ("loadmult=0.6 + maxiterations=100", ("set loadmult=0.6", "set maxiterations=100")),
)


class Diagnostico:
    def __init__(self, master: Path):
        import opendssdirect as dss

        self.dss = dss
        self.master = master.resolve()
        self.cwd = os.getcwd()

    def mapa_trafos(self) -> dict[str, str]:
        """Barra (minúscula) → trafo cujo secundário alimenta o seu circuito BT (componente do
        grafo de linhas/reatores, sem os trafos); barras MT ficam com o nome do circuito."""
        import networkx as nx

        d = self.dss
        g = nx.Graph()
        secundario: dict[str, str] = {}
        for nome in d.Circuit.AllElementNames():
            tipo = nome.split(".")[0].lower()
            if tipo not in ("line", "reactor", "transformer"):
                continue
            d.Circuit.SetActiveElement(nome)
            barras = [b.split(".")[0].lower() for b in d.CktElement.BusNames()]
            if tipo == "transformer" and len(barras) >= 2:
                secundario[barras[1]] = nome.split(".", 1)[1]
            elif len(barras) >= 2 and barras[0] != barras[1]:
                g.add_edge(barras[0], barras[1])
        mapa: dict[str, str] = {}
        for comp in nx.connected_components(g):
            trafos = sorted(secundario[b] for b in comp if b in secundario)
            rotulo = "+".join(trafos) if trafos else "MT"
            for b in comp:
                mapa[b] = rotulo
        return mapa

    def compilar(self, *comandos: str) -> None:
        d = self.dss
        d.Text.Command("clear")
        d.Text.Command(f'compile "{self.master}"')
        os.chdir(self.cwd)  # o compile muda o cwd do processo
        d.Text.Command("set mode=snapshot")
        for c in comandos:
            d.Text.Command(c)

    def resolver(self) -> tuple[bool, int]:
        self.dss.Solution.Solve()
        return bool(self.dss.Solution.Converged()), int(self.dss.Solution.Iterations())

    # ---- 1. matriz de estabilizadores ---------------------------------------------------------
    def matriz(self) -> bool:
        print(f"Master: {self.master}")
        padrao = True
        for rotulo, comandos in MATRIZ:
            self.compilar(*comandos)
            conv, it = self.resolver()
            if rotulo.startswith("padrão"):
                padrao = conv
            print(f"  {rotulo:45s} convergiu={'sim' if conv else 'não':3s} iterações={it}")
        return padrao

    # ---- 2. iteração a iteração: ciclo-limite? ------------------------------------------------
    def oscilacao(self, n_iter: int = 30) -> None:
        d = self.dss
        self.compilar("set maxiterations=1")
        nomes = np.array(d.Circuit.AllNodeNames())
        hist = []
        for _ in range(n_iter):
            d.Solution.Solve()
            hist.append(np.array(d.Circuit.AllBusMagPu()))
        h = np.array(hist[-12:])
        amp = h.max(axis=0) - h.min(axis=0)
        dv = [float(np.abs(hist[k] - hist[k - 1]).max()) for k in range(1, len(hist))]
        print(f"\nmax|dV| por iteração (últimas 12): {' '.join(f'{x:.3f}' for x in dv[-12:])}")
        if max(dv[-6:]) < 1e-4:
            print("  a iteração está convergindo (lenta): mais iterações resolvem")
            return
        print(
            f"  ciclo-limite: {(amp > 0.01).sum()} nós com amplitude > 0,01 pu nas últimas 12 "
            f"iterações (máx {amp.max():.3f} pu)"
        )
        piores = np.argsort(-amp)[:8]
        for i in piores:
            faixa = f"[{h[:, i].min():.3f}, {h[:, i].max():.3f}]"
            print(f"    {nomes[i]:45s} amplitude {amp[i]:.3f}  {faixa}")
        mapa = self.mapa_trafos()
        barras = Counter(
            mapa.get(nomes[i].split(".")[0].lower(), "?") for i in np.where(amp > 0.01)[0]
        )
        print("  circuitos BT (trafo) com nós oscilando:")
        for trafo, n in barras.most_common(8):
            print(f"    {trafo:35s} {n:4d} nós")

    # ---- 3. cargas com tensão terminal < 0,9 pu (solução com vminpu=0.9) ----------------------
    def cargas_criticas(self) -> None:
        d = self.dss
        self.compilar("batchedit load..* vminpu=0.9")
        conv, it = self.resolver()
        if not conv:
            print("\nnem vminpu=0.9 converge; sem análise de cargas")
            return
        cargas = []
        i = d.Loads.First()
        while i:
            nome = d.Loads.Name()
            d.Circuit.SetActiveElement("Load." + nome)
            barra = d.CktElement.BusNames()[0].split(".")[0].lower()
            v = d.CktElement.Voltages()
            fasores = [complex(v[2 * k], v[2 * k + 1]) for k in range(len(v) // 2)]
            nf = int(d.CktElement.NumPhases())
            if nf == 1:
                vt = abs(fasores[0] - fasores[1])
            else:
                vt = min(abs(fasores[k] - fasores[(k + 1) % nf]) for k in range(nf))
            cargas.append((nome, barra, int(d.Loads.Model()), vt / (d.Loads.kV() * 1000)))
            i = d.Loads.Next()
        vt = np.array([c[3] for c in cargas])
        m3 = np.array([c[2] == 3 for c in cargas])
        print(
            f"\ncargas: {len(cargas)} ({m3.sum()} de corrente constante); tensão terminal "
            f"< 0,9 pu: {(vt < 0.9).sum()} (model=3: {(m3 & (vt < 0.9)).sum()}); "
            f"mínima {vt.min():.3f} pu"
        )
        # bastam elas? vminpu=0.9 só nas model=3 com Vterm < 0,9
        self.compilar()
        for nome, _, modelo, v in cargas:
            if modelo == 3 and v < 0.9:
                d.Text.Command(f"edit load.{nome} vminpu=0.9")
        conv, it = self.resolver()
        print(
            f"  vminpu=0.9 só nessas cargas (maxiterations=15): "
            f"convergiu={'sim' if conv else 'não'} iterações={it}"
        )
        mapa = self.mapa_trafos()
        por_trafo: dict[str, list[float]] = defaultdict(list)
        for _, barra, modelo, v in cargas:
            if modelo == 3 and v < 0.9:
                por_trafo[mapa.get(barra, "?")].append(v)
        print("  circuitos BT (trafo) com mais cargas de corrente constante abaixo de 0,9 pu:")
        for trafo, vs in sorted(por_trafo.items(), key=lambda kv: -len(kv[1]))[:10]:
            print(f"    {trafo:35s} {len(vs):4d} cargas  Vterm mín {min(vs):.3f} pu")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("master", type=Path, help="Master .dss (ex.: Master_DU01_base.dss)")
    ap.add_argument("--iteracoes", type=int, default=30, help="iterações da análise de oscilação")
    args = ap.parse_args(argv)
    if not args.master.is_file():
        print(f"Master não encontrado: {args.master}", file=sys.stderr)
        return 2
    diag = Diagnostico(args.master)
    if diag.matriz():
        print("\no método padrão converge: nada a diagnosticar")
        return 0
    diag.oscilacao(args.iteracoes)
    diag.cargas_criticas()
    return 0


if __name__ == "__main__":
    sys.exit(main())
