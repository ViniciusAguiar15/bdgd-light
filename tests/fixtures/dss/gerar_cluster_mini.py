"""Gera ``tests/fixtures/dss/cluster_mini/``: saída "como a do bdgd2opendss" para RJO001 e RJO002.

Espelha a rede MT sintética de ``tests/fixtures/gerar_fixture.py`` (mesmos PAC, trechos, chaves e
trafos), no layout de arquivos que o ``bdgd2opendss`` produz para cada CTMT, para que os comandos de
``bdgd_light.twin.comandos_manobras`` (gerados a partir do grafo) se apliquem ao gêmeo em teste:

- ``CircuitoMT_*``: ``Circuit`` em 13,2 kV / 1,045 pu no PAC_INI;
- ``SegmentosMT_*``: ``Line.SMT_<SSDMT>``; ``ChavesMT_*``: NF como ``Line.CMT_<UNSEMT> switch=T`` e
  NA **comentadas** (``!New``), como o conversor faz;
- ``TransformadorMTMTMTBT_*``: ``Transformer.TRF_<UNTRMT>`` 13,2/0,22 kV + reator de neutro;
- ``CargasBT_DU01_*``: cargas modelo 2 (P constante) com ``vminpu=0.5``; ``CargasMT_DU01_*`` só em
  RJO001 (RJO002 não tem UCMT, como TQR33862);
- ``GD_BT_*``: um gerador com nome em branco em cada CTMT (``generator. ``), como na base da Light;
- ``Master_DU01_*``: Master original de um CTMT, com ``Set Voltagebases``.

Uso: ``uv run python tests/fixtures/dss/gerar_cluster_mini.py``
"""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).with_name("cluster_mini")
SUFIXO = "202608382_{ctmt}_------1-----.dss"
CHAVE = "r1=0.001 r0=0.001 x1=0.0 x0=0.0 c1=0.0 c0=0.0  switch = T length=0.00100"

# CTMT → PAC_INI (barramento da Circuit)
CIRCUITOS = {"RJO001": "RJO001_MT_0", "RJO002": "RJO002_MT_0"}
# trecho → (CTMT, PAC_1, PAC_2, comprimento km)
TRECHOS = {
    "SEG001": ("RJO001", "RJO001_MT_1", "RJO001_MT_2", 0.103),
    "SEG002": ("RJO001", "RJO001_MT_3", "RJO001_MT_4", 0.103),
    "SEG003": ("RJO001", "RJO001_MT_4", "RJO001_MT_5", 0.103),
    "SEG006": ("RJO001", "RJO001_MT_4", "RJO001_MT_6", 0.066),
    "SEG004": ("RJO002", "RJO002_MT_1", "RJO002_MT_2", 0.103),
    "SEG005": ("RJO002", "RJO002_MT_3", "RJO002_MT_4", 0.103),
    "SEG007": ("RJO002", "RJO002_MT_4", "RJO002_MT_5", 0.196),
    "SEG008": ("RJO002", "RJO002_MT_4", "RJO002_MT_6", 0.276),
}
# chave → (CTMT, PAC_1, PAC_2, NF/NA)
CHAVES = {
    "CH008": ("RJO001", "RJO001_MT_0", "RJO001_MT_1", "F"),
    "CH001": ("RJO001", "RJO001_MT_2", "RJO001_MT_3", "F"),
    "CH003": ("RJO001", "RJO001_MT_5", "RJO001_MT_7", "A"),
    "CH006": ("RJO001", "RJO001_MT_5", "RJO001_MT_6", "A"),
    "CH009": ("RJO002", "RJO002_MT_0", "RJO002_MT_1", "F"),
    "CH002": ("RJO002", "RJO002_MT_2", "RJO002_MT_3", "F"),
    "CH005": ("RJO002", "RJO002_MT_6", "RJO002_MT_7", "A"),
    "CH007": ("RJO002", "RJO002_MT_8", "RJO002_MT_9", "A"),
}
# trafo → (CTMT, PAC MT, kVA, kW de carga BT no pico)
TRAFOS = {
    "TR003": ("RJO001", "RJO001_MT_2", 45.0, 30.0),
    "TR001": ("RJO001", "RJO001_MT_4", 75.0, 50.0),
    "TR002": ("RJO002", "RJO002_MT_4", 112.5, 80.0),
}
# UCMT → (CTMT, PAC MT, kW)
UCMT = {"UCMT001": ("RJO001", "RJO001_MT_5", 200.0)}


def _linhas(ctmt: str) -> dict[str, list[str]]:
    arquivos: dict[str, list[str]] = {}
    arquivos["CircuitoMT"] = [
        f'New "Circuit.{ctmt}" basekv=13.2 pu=1.0449999570846558 bus1="{CIRCUITOS[ctmt]}" '
        "r1=0.0 x1=0.0001"
    ]
    arquivos["CodCondutor"] = [
        'New "Linecode.CA_50_3" nphases=3 basefreq=60 r1=0.6420 x1=0.4100 units=km normamps=200.00'
    ]
    arquivos["SegmentosMT"] = [
        f'New "Line.SMT_{cod}" phases=3 bus1="{a}.1.2.3" bus2="{b}.1.2.3" linecode="CA_50_3" '
        f"length={km:.9f} units=km"
        for cod, (c, a, b, km) in TRECHOS.items()
        if c == ctmt
    ]
    arquivos["ChavesMT"] = [
        f'{"" if estado == "F" else "!"}New "Line.CMT_{cod}" phases=3 bus1="{a}.1.2.3" '
        f'bus2="{b}.1.2.3" {CHAVE}'
        for cod, (c, a, b, estado) in CHAVES.items()
        if c == ctmt
    ]
    trafos: list[str] = []
    cargas_bt: list[str] = []
    for cod, (c, pac, kva, kw) in TRAFOS.items():
        if c != ctmt:
            continue
        bt = f"{cod}_BT_1"
        trafos += [
            f'New "Transformer.TRF_{cod}A" phases=3 windings=2 buses=["{pac}.1.2.3" '
            f'"{bt}.1.2.3.4"] conns=[Delta Wye] kvs=[13.2 0.22]  kvas=[{kva:g} {kva:g}] '
            "%loadloss=1.217778 %noloadloss=0.297778",
            f'New "Reactor.TRF_{cod}A_R" phases=1 bus1={bt}.4 R=15 X=0 basefreq=60',
        ]
        cargas_bt.append(
            f'New "Load.BT_{cod}_1_M1" bus1="{bt}.1.2.3.4" phases=3 conn=Wye model=2 kv=0.22 '
            f'kw = {kw:.6f} pf=0.92 status=variable vmaxpu=1.5 vminpu=0.5 daily="RES-Tipo1_DU"'
        )
    arquivos["TransformadorMTMTMTBT"] = trafos
    arquivos["CurvaCarga"] = [
        'New "Loadshape.RES-Tipo1_DU" 24 1 mult=('
        + ", ".join(f"{0.45 + 0.55 * (h / 23):.3f}" for h in range(24))
        + ")"
    ]
    arquivos["CargasBT_DU01"] = cargas_bt
    cargas_mt = [
        f'New "Load.MT_{cod}_M1" bus1="{pac}.1.2.3" phases=3 conn=Delta model=2 kv=13.2 '
        f'kw = {kw:.6f} pf=0.92 status=variable vmaxpu=1.5 vminpu=0.5 daily="RES-Tipo1_DU"'
        for cod, (c, pac, kw) in UCMT.items()
        if c == ctmt
    ]
    if cargas_mt:
        arquivos["CargasMT_DU01"] = cargas_mt
    primeiro_bt = next(f"{cod}_BT_1" for cod, (c, *_) in TRAFOS.items() if c == ctmt)
    arquivos["GD_BT"] = [
        'New "Loadshape.default_pv_daily_bt" 24 1 mult=('
        + ", ".join("0.0" if h < 6 or h > 18 else "1.0" for h in range(24))
        + ")",
        f'New "generator.GD.{ctmt}.001" phases=3 bus1={primeiro_bt}.1.2.3.4 basefreq=60 '
        "conn=Delta kv=0.22 pf=0.92 kw=5.0 daily=default_pv_daily_bt",
        # COD_ID em branco, como acontece na base real (duplicado entre CTMT)
        f'New "generator. " phases=1 bus1={primeiro_bt}.2.4 basefreq=60 conn=Wye '
        "kv=0.1270170592217177 pf=0.92 kw=2.0 daily=default_pv_daily_bt",
    ]
    return arquivos


def gerar(raiz: Path = RAIZ) -> None:
    for ctmt in CIRCUITOS:
        pasta = raiz / ctmt
        pasta.mkdir(parents=True, exist_ok=True)
        for arq in pasta.glob("*.dss"):
            arq.unlink()
        arquivos = _linhas(ctmt)
        sufixo = SUFIXO.format(ctmt=ctmt)
        for nome, linhas in arquivos.items():
            (pasta / f"{nome}_{sufixo}").write_text("\n".join(linhas) + "\n", encoding="utf-8")
        master = ["clear"]
        for nome in arquivos:
            if nome != "GD_BT":  # o bdgd2opendss gera GD_BT mas não o inclui no Master
                master.append(f'Redirect "{nome}_{sufixo}"')
        master += [
            "Set mode = daily",
            "Set Voltagebases = [0.22 13.2]",
            "Calc Voltagebases",
            "Set tolerance = 0.0001",
            "Set maxcontroliter = 10",
            "!Solve",
        ]
        (pasta / f"Master_DU01_{sufixo}").write_text("\n".join(master) + "\n", encoding="utf-8")
        print(f"{pasta}: {len(arquivos) + 1} arquivos")


if __name__ == "__main__":
    gerar()
