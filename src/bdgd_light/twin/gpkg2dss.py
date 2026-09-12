"""Conversão **direta** do GeoPackage do recorte (``bdgd-light recortar``) para OpenDSS.

O bdgd2opendss só lê o ``.gdb`` inteiro (18 tabelas, sem filtro espacial). Este módulo reproduz a
modelagem dele — mesmas tabelas de códigos do Manual da BDGD, mesmas fórmulas de kW por curva de
carga, mesmos nomes de elementos e de arquivos — a partir das camadas já recortadas por CTMT, para
que o gêmeo rode sem o GDB e para que ``montar_master_cluster``/``comandos_manobras`` continuem
válidos sem tradução (``Line.SMT_<SSDMT>``, ``Line.CMT_<UNSEMT>``, ``Transformer.TRF_<UNTRMT>A``,
``Load.BT_<RAMAL>``; barras = PAC).

Diferenças conscientes em relação ao bdgd2opendss (ver ``docs/spike-opendss.md``):

- bancos de unidades monofásicas (``TIP_TRAFO`` ``DF``/``DA``) já saem como ``phases=1`` com a
  tensão do enrolamento (o bdgd2opendss escreve ``phases=3`` com barras de 2 nós, bdgd2opendss#35);
- nos bancos, as perdas ``PER_FER``/``PER_TOT`` da UNTRMT (do conjunto) são divididas entre as
  unidades (o bdgd2opendss repete as perdas do conjunto em cada unidade);
- elementos isolados da fonte (mesmo critério de grafo do bdgd2opendss) saem **comentados** em vez
  de omitidos, para auditoria;
- só os Masters pedidos (tipo de dia × mês) são escritos, não os 36;
- ``CodCondutor``/``CurvaCarga`` só trazem os códigos usados pelo CTMT (o bdgd2opendss escreve o
  catálogo inteiro);
- reguladores não são gerados (a Light não tem reguladores nos clusters da demo);
- ``GD_BT`` pode ser gerado **sob demanda** a partir da MMGD pública da ANEEL + BDGD Light, mas o
  Master segue saindo sem ``Redirect`` desse arquivo por padrão; a iluminação pública (``PIP``)
  entra no ``CargasBT`` como ``Load.BT_IP<COD_ID>``, igual ao bdgd2opendss.
"""

from __future__ import annotations

import calendar
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd
import pyogrio

ANO_PADRAO = 2026
"""Ano da extração (``BASE.DAT_EXT``) da BDGD Light 2025 — é o que o bdgd2opendss usa para contar
os dias úteis/sábados/domingos de cada mês no cálculo de kW; sem a tabela BASE no recorte, fica
fixo."""

DIAS = ("DU", "SA", "DO")
PREFIXO_ARQUIVO = "gpkg"
_RAIZ3 = math.sqrt(3.0)

# --- tabelas de códigos (Manual da BDGD, Módulo 10 do PRODIST; mesmas do bdgd2opendss) ------------

TENSAO_KV: dict[str, float] = {
    "0": 0.0, "1": 0.11, "2": 0.115, "3": 0.120, "4": 0.121, "5": 0.125, "6": 0.127, "7": 0.208,
    "8": 0.216, "9": 0.2165, "10": 0.220, "11": 0.230, "12": 0.231, "13": 0.240, "14": 0.254,
    "15": 0.380, "16": 0.400, "17": 0.440, "18": 0.480, "19": 0.500, "20": 0.600, "21": 0.750,
    "22": 1.0, "23": 2.3, "24": 3.2, "25": 3.6, "26": 3.785, "27": 3.8, "28": 3.848, "29": 3.985,
    "30": 4.160, "31": 4.2, "32": 4.207, "33": 4.368, "34": 4.560, "35": 5, "36": 6, "37": 6.6,
    "38": 6.93, "39": 7.96, "40": 8.67, "103": 11, "41": 11.4, "104": 11.5, "42": 11.9, "43": 12.0,
    "44": 12.6, "45": 12.7, "105": 13, "46": 13.2, "47": 13.337, "48": 13.530, "49": 13.8,
    "50": 13.86, "51": 14.14, "52": 14.19, "53": 14.4, "54": 14.835, "55": 15, "56": 15.2,
    "57": 19.053, "58": 19.919, "106": 20, "59": 21, "60": 21.5, "61": 22, "62": 23, "63": 23.1,
    "64": 23.827, "65": 24, "66": 24.2, "67": 25, "68": 25.8, "69": 27, "70": 30, "71": 33,
    "72": 34.5, "73": 36, "74": 38, "75": 40, "76": 44, "77": 45, "78": 45.4, "79": 48, "80": 60,
    "81": 66, "107": 68, "82": 69, "83": 72.5, "108": 85, "84": 88, "85": 88.2, "86": 92, "87": 100,
    "88": 120, "89": 121, "90": 123, "91": 131.6, "92": 131.630, "93": 131.635, "94": 138,
    "95": 145, "96": 230, "97": 345, "109": 440, "98": 500, "99": 750, "100": 1000, "101": 245,
    "102": 550,
}  # fmt: skip

POTENCIA_KVA: dict[str, float] = {
    "0": 0, "1": 3, "2": 5, "3": 10, "4": 15, "5": 20, "6": 22.5, "7": 25, "8": 30, "9": 35,
    "10": 37.5, "11": 38.1, "12": 40, "13": 45, "14": 50, "15": 60, "16": 75, "17": 76.2, "18": 88,
    "19": 100, "20": 112.5, "21": 114.3, "22": 120, "23": 138, "24": 150, "25": 167, "26": 175,
    "27": 180, "28": 200, "29": 207, "30": 225, "31": 250, "32": 276, "33": 288, "34": 300,
    "35": 332, "36": 333, "37": 400, "38": 414, "39": 432, "40": 500, "41": 509, "42": 667,
    "43": 750, "44": 833, "45": 1000, "46": 1250, "47": 1300, "48": 1500, "49": 1750, "50": 2000,
    "51": 2250, "52": 2300, "53": 2400, "54": 2500, "55": 2750, "56": 2900, "57": 3000, "58": 3125,
    "59": 3300, "60": 3750, "61": 4000, "62": 4200, "63": 4500, "64": 5000, "65": 6250, "66": 6500,
    "67": 7000, "68": 7500, "69": 7800, "70": 8000, "71": 9000, "72": 9375, "73": 9600, "74": 10000,
    "75": 12000, "76": 12500, "77": 13300, "78": 15000, "79": 16000, "80": 18000, "81": 18750,
    "82": 20000, "83": 25000, "84": 26000, "85": 26600, "86": 28000, "87": 30000, "88": 32000,
    "89": 33000, "90": 33300, "91": 40000, "92": 45000, "93": 50000, "94": 60000, "95": 67000,
    "96": 75000, "97": 80000, "98": 83000, "99": 85000, "100": 90000, "101": 100000,
    "102": 200000, "103": 14550000, "104": 17320000, "105": 19100000, "106": 41550000,
}  # fmt: skip

# resistência (ohm/km) por código de condutor regulatório (R_REGUL); o bdgd2opendss usa o menor
# entre R1 e este valor
RESISTENCIA_REGUL: dict[str, float] = {
    "0": 0, "AL6AWG": 2.469, "AL4AWG": 1.551, "AL3AWG": 1.229, "AL2AWG": 0.975, "AL1AWG": 0.774,
    "AL1_0AWG": 0.613, "AL2_0AWG": 0.486, "AL3_0AWG": 0.386, "AL4_0AWG": 0.306, "AL250MCM": 0.259,
    "AL266_8MCM": 0.245, "AL300MCM": 0.217, "AL336_4MCM": 0.195, "AL350MCM": 0.185,
    "AL397_5MCM": 0.165, "AL450MCM": 0.145, "AL477MCM": 0.138, "AL500MCM": 0.131,
    "AL556_5MCM": 0.119, "ALI10MM2": 3.514, "ALI16MM2": 2.179, "ALI25MM2": 1.369, "ALI35MM2": 0.991,
    "ALI50MM2": 0.732, "ALI70MM2": 0.506, "ALI95MM2": 0.365, "ALI120MM2": 0.289, "ALI150MM2": 0.236,
    "ALI185MM2": 0.188, "ALI240MM2": 0.143, "ALI300MM2": 0.115, "CUM0_5MM2": 40.952,
    "CUM0_75MM2": 27.87, "CUM1MM2": 20.59, "CUM1_5MM2": 13.764, "CUM2_5MM2": 8.429,
    "CUM4MM2": 5.244, "CUM6MM2": 3.504, "CUM10MM2": 2.082, "CUM16MM2": 1.308, "CUM25MM2": 0.827,
    "CUM35MM2": 0.596, "CUM50MM2": 0.441, "CUM70MM2": 0.305, "CUM95MM2": 0.22, "CUM120MM2": 0.175,
    "CUM150MM2": 0.142, "CUM185MM2": 0.114, "CUM240MM2": 0.087, "CUM300MM2": 0.07,
    "CUM400MM2": 0.056, "CUM500MM2": 0.044, "CUM630MM2": 0.036, "CUM800MM2": 0.029,
    "CUM1000MM2": 0.025, "CUM1200MM2": 0.022,
    "CUM1400MM2": 0.02, "CUM1600MM2": 0.019, "CUM1800MM2": 0.017, "CUM2000MM2": 0.016,
    "CU10AWG": 3.754, "CU9AWG": 2.958, "CU8AWG": 2.389, "CU7AWG": 1.82, "CU6AWG": 1.564,
    "CU5AWG": 1.138, "CU4AWG": 0.984, "CU3AWG": 0.78, "CU2AWG": 0.62, "CU1AWG": 0.491,
    "CU1_0AWG": 0.389, "CU2_0AWG": 0.308, "CU3_0AWG": 0.245, "CU4_0AWG": 0.195,
    "AZN1X3_09MM": 29.142, "AZN3X2_25MM": 18.325, "AZN5X6MM": 11.411, "AAL7X9AWG": 2.1,
    "AAL7X8AWG": 1.673, "AAL7X7AWG": 1.32, "AAL7X6AWG": 1.047, "AAL7X5AWG": 0.833,
    "AAL7X10AWG": 2.651, "AAL3X9AWG": 4.873, "AAL3X8AWG": 3.883, "AAL3X7AWG": 3.064,
    "AAL3X6AWG": 2.432, "AAL3X5AWG": 1.934, "AAL3X10AWG": 6.153,
}  # fmt: skip

# FAS_CON → nós da barra (".1.2.3.4"), fases, condutores e ligação
NOS: dict[str, str] = {
    "ABCN": "1.2.3.4", "ABC": "1.2.3", "ABN": "1.2.4", "BCN": "2.3.4", "CAN": "3.1.4", "AX": "1.4",
    "BX": "2.4", "CX": "3.4", "AB": "1.2", "BC": "2.3", "CA": "3.1", "AN": "1.4", "BN": "2.4",
    "CN": "3.4", "A": "1", "B": "2", "C": "3", "N": "4",
}  # fmt: skip
NOS_PRIMARIO: dict[str, str] = {
    **NOS, "ABN": "1.2.0", "BCN": "2.3.0", "CAN": "3.1.0", "ABCN": "1.2.3.0"
}  # fmt: skip
NOS_TERCIARIO: dict[str, str] = {"AN": "4.1", "BN": "4.2", "CN": "4.3"}
FASES: dict[str, int] = {
    "ABCN": 3, "ABC": 3, "ABN": 2, "BCN": 2, "CAN": 2, "AX": 1, "BX": 1, "CX": 1, "AB": 2, "BC": 2,
    "CA": 2, "AN": 1, "BN": 1, "CN": 1, "A": 1, "B": 1, "C": 1, "N": 0,
}  # fmt: skip
CONDUTORES: dict[str, int] = {
    "ABCN": 4, "ABC": 3, "ABN": 3, "BCN": 3, "CAN": 3, "AX": 3, "BX": 3, "CX": 3, "AB": 2, "BC": 2,
    "CA": 2, "AN": 2, "BN": 2, "CN": 2, "A": 1, "B": 1, "C": 1, "N": 1,
}  # fmt: skip
CONEXAO: dict[str, str] = {
    "ABCN": "Wye", "ABC": "Delta", "ABN": "Wye", "BCN": "Wye", "CAN": "Wye", "AX": "Wye",
    "BX": "Wye", "CX": "Wye", "AB": "Delta", "BC": "Delta", "CA": "Delta", "AN": "Wye", "BN": "Wye",
    "CN": "Wye", "A": "Wye", "B": "Wye", "C": "Wye", "N": "Wye",
}  # fmt: skip
CONEXAO_CARGA: dict[str, str] = {
    **dict.fromkeys(("A", "B", "C", "AN", "BN", "CN", "AX", "BX", "CX"), "Wye"),
    **dict.fromkeys(("AB", "BC", "CA", "ABN", "BCN", "CAN", "ABC", "ABCN"), "Delta"),
}
ENROLAMENTOS: dict[str, int] = {"M": 2, "B": 2, "T": 2, "MT": 3, "DA": 2, "DF": 2}

# Suspeitos de qualidade de dado que pesam na convergência do fluxo (issue #44), só avisados:
#   - RAMLIG com COMP acima de RAMAL_LONGO_M é um circuito BT inteiro cadastrado como ramal;
#   - trafo "de fase única": pelo menos FASE_UNICA_MIN_UC UC monofásicas e FASE_UNICA_FRACAO delas
#     com o mesmo FAS_CON — a carga toda numa fase leva o neutro a dezenas de volts e faz o
#     modelo de corrente constante do OpenDSS oscilar (é o que exige ``vminpu=0.9`` em Tijuca).
#     Não redistribuímos as fases: em vários desses circuitos a rede BT é cadastrada a 2 fios
#     (SSDBT/RAMLIG ``AN``), e mover UC para B/C criaria nós sem condutor.
RAMAL_LONGO_M = 300.0
FASE_UNICA_MIN_UC = 20
FASE_UNICA_FRACAO = 0.9
MONOFASICAS = frozenset({"A", "B", "C", "AN", "BN", "CN", "AX", "BX", "CX"})

_CHAVE = "r1=0.001 r0=0.001 x1=0.0 x0=0.0 c1=0.0 c0=0.0  switch = T length=0.00100"
_ENERGIAS = [f"ENE_{m:02d}" for m in range(1, 13)]
_POTENCIAS = [f"POT_{i:02d}" for i in range(1, 97)]
PREFIXO_ELEMENTO_TRECHO_MT = "smt_"
TIPO_TRECHO_MT_OPEN_DSS = PREFIXO_ELEMENTO_TRECHO_MT.removesuffix("_").upper()


class GpkgInvalidoError(ValueError):
    """O GeoPackage não tem as camadas/colunas mínimas para gerar um Master."""


@dataclass(frozen=True)
class ConfiguracaoGd:
    """Fontes necessárias para materializar a GD opcional no gêmeo."""

    parquet_dir: Path
    mmgd_path: Path


@dataclass(frozen=True)
class ResumoGdCtmt:
    """Resumo da GD modelada para um CTMT."""

    ctmt: str
    n_elementos: int
    potencia_total_kw: float
    n_empreendimentos_exatos: int
    potencia_exata_kw: float
    n_elementos_exatos: int
    n_empreendimentos_agregados: int
    potencia_agregada_kw: float
    n_elementos_agregados: int
    criterio_agregado: str | None
    grupos_agregados: tuple[str, ...] = ()
    observacoes: tuple[str, ...] = ()


@dataclass
class ConversaoGpkg:
    """Resultado da conversão de um CTMT."""

    ctmt: str
    pasta: Path
    masters: list[Path]
    contagem: dict[str, int] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    gd: ResumoGdCtmt | None = None

    @property
    def master(self) -> Path:
        return self.masters[0]


# --- calendário (dias úteis / sábados / domingos+feriados por mês) --------------------------------


def _pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher, o mesmo do bdgd2opendss)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    mes = (h + m - 7 * n + 114) // 31
    dia = (h + m - 7 * n + 114) % 31 + 1
    return date(ano, mes, dia)


def feriados_nacionais(ano: int) -> list[date]:
    """Feriados nacionais (lista do pacote ``holidays`` + Carnaval e Corpus Christi, como o
    bdgd2opendss)."""
    pascoa = _pascoa(ano)
    fixos = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (12, 25)]
    if ano >= 2024:
        fixos.append((11, 20))  # Consciência Negra (nacional desde 2024)
    moveis = [pascoa - timedelta(days=2), pascoa - timedelta(days=47), pascoa + timedelta(days=60)]
    return sorted({date(ano, m, d) for m, d in fixos} | set(moveis))


def dias_por_tipo(ano: int = ANO_PADRAO) -> dict[str, dict[int, int]]:
    """``{"DU": {mes: n}, "SA": …, "DO": …}``; feriados em dia de semana saem de DU e entram em
    DO."""
    feriados = feriados_nacionais(ano)
    tipos: dict[str, dict[int, int]] = {t: {} for t in DIAS}
    for mes in range(1, 13):
        n_dias = calendar.monthrange(ano, mes)[1]
        semana = [date(ano, mes, d).weekday() for d in range(1, n_dias + 1)]
        uteis = sum(1 for w in semana if w < 5)
        sabados = sum(1 for w in semana if w == 5)
        domingos = sum(1 for w in semana if w == 6)
        feriados_uteis = sum(1 for f in feriados if f.month == mes and f.weekday() < 5)
        tipos["DU"][mes] = uteis - feriados_uteis
        tipos["SA"][mes] = sabados
        tipos["DO"][mes] = domingos + feriados_uteis
    return tipos


# --- leitura --------------------------------------------------------------------------------------


def _camadas(gpkg: Path) -> set[str]:
    return {nome for nome, _ in pyogrio.list_layers(gpkg)}


def _ler(gpkg: Path, camada: str, existentes: set[str]) -> pd.DataFrame:
    if camada not in existentes:
        return pd.DataFrame()
    df = pyogrio.read_dataframe(gpkg, layer=camada, read_geometry=False)
    for col in df.columns:
        if df[col].dtype == object or str(df[col].dtype) in ("string", "str"):
            df[col] = df[col].astype("string").str.strip().fillna("")
    return df


def _por_ctmt(df: pd.DataFrame, ctmt: str) -> pd.DataFrame:
    if df.empty or "CTMT" not in df.columns:
        return df
    return df[df["CTMT"] == ctmt].reset_index(drop=True)


def _texto(valor) -> str:
    if valor is None or (isinstance(valor, float) and math.isnan(valor)) or valor is pd.NA:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def _num(valor, padrao: float = 0.0) -> float:
    try:
        x = float(valor)
    except (TypeError, ValueError):
        return padrao
    return padrao if math.isnan(x) else x


def nome_elemento_trecho_mt(cod_id) -> str:
    """Nome OpenDSS do trecho MT (camada ``SSDMT``)."""
    return f"Line.{PREFIXO_ELEMENTO_TRECHO_MT.upper()}{_texto(cod_id)}"


def cod_id_trecho_mt_de_elemento(elemento: object) -> str | None:
    """Extrai o ``COD_ID`` de ``Line.SMT_<COD_ID>`` de forma case-insensitive."""
    nome = str(elemento or "").strip()
    prefixo = f"line.{PREFIXO_ELEMENTO_TRECHO_MT}"
    if not nome.lower().startswith(prefixo):
        return None
    cod_id = nome[len(prefixo) :].strip()
    return cod_id.upper() or None


def _kv(codigo, padrao: float = 0.0) -> float:
    return TENSAO_KV.get(_texto(codigo), padrao)


# --- curvas de carga e kW -------------------------------------------------------------------------


@dataclass
class _Curvas:
    """Curvas ``CRVCRG`` pré-processadas: mult normalizada, fator de carga e proporção por tipo."""

    mult: dict[tuple[str, str], list[float]]
    fc: dict[tuple[str, str], float]
    prop: dict[tuple[str, str], float]  # soma_pot[tip] / Σ_tips soma_pot (por curva)

    @classmethod
    def das_linhas(cls, crv: pd.DataFrame) -> _Curvas:
        mult, fc, soma = {}, {}, {}
        if crv.empty:
            return cls(mult, fc, {})
        pot_cols = [c for c in _POTENCIAS if c in crv.columns]
        for _, r in crv.iterrows():
            chave = (_texto(r["COD_ID"]), _texto(r["TIP_DIA"]))
            valores = [_num(r[c]) for c in pot_cols]
            passo = max(1, len(valores) // 24)
            medias = [sum(valores[i : i + passo]) / passo for i in range(0, len(valores), passo)][
                :24
            ]
            medias += [0.0] * (24 - len(medias))
            maximo = max(medias)
            mult[chave] = [m / maximo for m in medias] if maximo > 0 else [0.0] * 24
            soma[chave] = sum(medias)
            fc[chave] = (soma[chave] / 24) / maximo if maximo > 0 else 1.0
        total_por_curva: dict[str, float] = {}
        for (cod, _), s in soma.items():
            total_por_curva[cod] = total_por_curva.get(cod, 0.0) + s
        prop = {
            k: (s / total_por_curva[k[0]] if total_por_curva[k[0]] else 0.0)
            for k, s in soma.items()
        }
        return cls(mult, fc, prop)

    def tem(self, cod: str) -> bool:
        return any(k[0] == cod for k in self.mult)

    def garantir(self, cods: Iterable[str]) -> list[str]:
        """Cria curvas planas (``mult`` = 1) para os ``TIP_CC`` sem CRVCRG; devolve os criados."""
        criados = []
        for cod in sorted({c for c in cods if c and not self.tem(c)}):
            for tip in DIAS:
                self.mult[(cod, tip)] = [1.0] * 24
                self.fc[(cod, tip)] = 1.0
                self.prop[(cod, tip)] = 1 / 3
            criados.append(cod)
        return criados

    def kw(self, cod: str, tip_dia: str, mes: int, energia_kwh: float, dias: dict) -> float:
        """kW de pico do tipo de dia (fórmula ``Load.calculate_kw`` do bdgd2opendss)."""
        chave = (cod, tip_dia)
        if chave not in self.fc or self.fc[chave] <= 0:
            # curva desconhecida: patamar plano (energia dividida pelas horas do mês)
            n_dias = sum(dias[t][mes] for t in DIAS)
            return energia_kwh / (n_dias * 24) if n_dias else 0.0
        peso = {t: self.prop.get((cod, t), 0.0) * dias[t][mes] for t in DIAS}
        total = sum(peso.values())
        prop_mes = peso[tip_dia] / total if total else 0.0
        n = dias[tip_dia][mes]
        return energia_kwh * prop_mes / (n * 24 * self.fc[chave]) if n else 0.0


# --- GD opcional ---------------------------------------------------------------------------------


_SHAPE_SOLAR = (
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.05,
    0.15,
    0.35,
    0.6,
    0.82,
    0.95,
    1.0,
    0.95,
    0.82,
    0.6,
    0.35,
    0.15,
    0.05,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
)
_SHAPE_NAO_SOLAR = (1.0,) * 24
_COLUNAS_CARGA_REF = ("CTMT", "MUN", "CAR_INST")


def _shape_dss(nome: str, valores: Sequence[float]) -> str:
    mult = ", ".join(f"{v:.4f}" for v in valores)
    return f'New "Loadshape.{nome}" 24 1 mult=({mult})'


def _eh_solar(sigla: object, descricao: object) -> bool:
    sigla_txt = _texto(sigla).upper()
    desc = _texto(descricao).casefold()
    return sigla_txt == "UFV" or "solar" in desc


def _peso_carga(valor: object) -> float:
    return max(_num(valor), 0.0)


@lru_cache(maxsize=8)
def _base_gd_light(parquet_dir: str, mmgd_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    from bdgd_light.ingest.gd import carregar_bdgd_gd, carregar_mmgd, normalizar_mmgd
    from bdgd_light.ingest.parquet import DiretorioParquet

    fonte = DiretorioParquet(Path(parquet_dir))
    mmgd = normalizar_mmgd(carregar_mmgd(Path(mmgd_path)))
    bdgd_gd = carregar_bdgd_gd(fonte)
    chaves_exatas = set(bdgd_gd.loc[bdgd_gd["ceg_gd"].ne(""), "ceg_gd"])
    sem_chave = mmgd.loc[~mmgd["cod_empreendimento"].isin(chaves_exatas)].copy()
    sem_chave["tipo_modelo"] = sem_chave.apply(
        lambda r: (
            "PVSystem" if _eh_solar(r["sig_tipo_geracao"], r["fonte_geracao"]) else "Generator"
        ),
        axis=1,
    )
    agregado = (
        sem_chave.groupby(["cod_municipio_ibge", "municipio", "tipo_modelo"], dropna=False)
        .agg(
            n_empreendimentos=("cod_empreendimento", "nunique"),
            potencia_kw=("potencia_kw", "sum"),
        )
        .reset_index()
    )
    return mmgd, agregado


@lru_cache(maxsize=8)
def _carga_ctmt_municipio(parquet_dir: str) -> pd.DataFrame:
    from bdgd_light.ingest.parquet import DiretorioParquet

    fonte = DiretorioParquet(Path(parquet_dir))
    grupos: list[pd.DataFrame] = []
    for camada in ("UCBT_tab", "UCMT_tab"):
        if not fonte.tem(camada):
            continue
        lotes = []
        for lote in fonte.iterar_lotes(camada, _COLUNAS_CARGA_REF, tamanho=500_000):
            if lote.empty:
                continue
            dados = lote[["CTMT", "MUN"]].copy()
            dados["carga_ref"] = lote["CAR_INST"].map(_peso_carga)
            dados["CTMT"] = dados["CTMT"].map(_texto)
            dados["MUN"] = pd.to_numeric(dados["MUN"], errors="coerce").astype("Int64")
            lotes.append(
                dados[dados["CTMT"].ne("") & dados["MUN"].notna() & (dados["carga_ref"] > 0.0)]
            )
        if lotes:
            grupos.append(pd.concat(lotes, ignore_index=True))
    if not grupos:
        return pd.DataFrame(columns=["CTMT", "MUN", "carga_ref", "carga_municipio"])
    base = pd.concat(grupos, ignore_index=True)
    carga = base.groupby(["CTMT", "MUN"], as_index=False, dropna=False)["carga_ref"].sum()
    carga["carga_municipio"] = carga.groupby("MUN", dropna=False)["carga_ref"].transform("sum")
    return carga


def _alocacao_exata(
    ctmt: str,
    mmgd: pd.DataFrame,
    bdgd_local: pd.DataFrame,
) -> tuple[list[dict[str, object]], list[str]]:
    if bdgd_local.empty:
        return [], []
    local = bdgd_local.copy()
    local["CEG_GD"] = local["CEG_GD"].map(_texto)
    local = local[local["CEG_GD"].ne("")]
    if local.empty:
        return [], []
    mmgd_idx = mmgd.set_index("cod_empreendimento", drop=False)
    elementos: list[dict[str, object]] = []
    observacoes: list[str] = []
    for ceg, grupo in local.groupby("CEG_GD", sort=True):
        if ceg not in mmgd_idx.index:
            continue
        if isinstance(mmgd_idx.loc[ceg], pd.DataFrame):
            mmgd_row = mmgd_idx.loc[ceg].iloc[0]
            observacoes.append(f"{ctmt}: MMGD duplicada na chave {ceg}; usada a primeira linha.")
        else:
            mmgd_row = mmgd_idx.loc[ceg]
        pesos = grupo["POT_INST"].map(lambda x: max(_num(x), 0.0))
        soma_pesos = float(pesos.sum())
        if soma_pesos <= 0:
            pesos = pd.Series([1.0] * len(grupo), index=grupo.index)
            soma_pesos = float(len(grupo))
        for idx, bdgd_row in grupo.iterrows():
            elementos.append(
                {
                    "metodo": "chave_direta_pac",
                    "ceg_gd": ceg,
                    "cod_id_bdgd": _texto(bdgd_row.get("COD_ID")),
                    "camada": _texto(bdgd_row.get("_camada_gd")),
                    "pac": _texto(bdgd_row.get("PAC")),
                    "uni_tr_mt": _texto(bdgd_row.get("UNI_TR_MT")),
                    "fas_con": _texto(bdgd_row.get("FAS_CON")),
                    "ten_con": _texto(bdgd_row.get("TEN_CON")),
                    "tipo_modelo": (
                        "PVSystem"
                        if _eh_solar(mmgd_row["sig_tipo_geracao"], mmgd_row["fonte_geracao"])
                        else "Generator"
                    ),
                    "fonte_geracao": _texto(mmgd_row["fonte_geracao"]),
                    "sig_tipo_geracao": _texto(mmgd_row["sig_tipo_geracao"]),
                    "potencia_kw": (
                        float(mmgd_row["potencia_kw"]) * float(pesos.loc[idx]) / soma_pesos
                    ),
                }
            )
    return elementos, observacoes


def _alocacao_agregada(
    ctmt: str,
    tabelas: dict[str, pd.DataFrame],
    config: ConfiguracaoGd,
) -> tuple[list[dict[str, object]], list[str]]:
    carga_ref = _carga_ctmt_municipio(str(Path(config.parquet_dir).resolve()))
    _, agregado = _base_gd_light(
        str(Path(config.parquet_dir).resolve()), str(Path(config.mmgd_path).resolve())
    )
    municipios = sorted(
        {
            int(m)
            for nome in ("UCBT_tab", "UCMT_tab")
            if "MUN" in tabelas[nome].columns
            for m in pd.to_numeric(tabelas[nome]["MUN"], errors="coerce").dropna().astype(int)
        }
    )
    if not municipios:
        return [], []
    ref_bt = pd.DataFrame(columns=["UNI_TR_MT", "peso"])
    if {"UNI_TR_MT", "CAR_INST"} <= set(tabelas["UCBT_tab"].columns):
        ref_bt = (
            tabelas["UCBT_tab"][["UNI_TR_MT", "CAR_INST"]]
            .copy()
            .assign(
                UNI_TR_MT=lambda x: x["UNI_TR_MT"].map(_texto),
                peso=lambda x: x["CAR_INST"].map(_peso_carga),
            )
        )
        ref_bt = ref_bt[ref_bt["UNI_TR_MT"].ne("") & (ref_bt["peso"] > 0.0)]
        ref_bt = ref_bt.groupby("UNI_TR_MT", as_index=False)["peso"].sum()
    ref_mt = pd.DataFrame()
    if {"PAC", "FAS_CON", "TEN_FORN", "CAR_INST"} <= set(tabelas["UCMT_tab"].columns):
        ref_mt = tabelas["UCMT_tab"][["PAC", "FAS_CON", "TEN_FORN", "CAR_INST"]].copy()
        ref_mt["PAC"] = ref_mt["PAC"].map(_texto)
        ref_mt["FAS_CON"] = ref_mt["FAS_CON"].map(_texto)
        ref_mt["TEN_FORN"] = ref_mt["TEN_FORN"].map(_texto)
        ref_mt["peso"] = ref_mt["CAR_INST"].map(_peso_carga)
        ref_mt = ref_mt[ref_mt["PAC"].ne("") & (ref_mt["peso"] > 0.0)]
        ref_mt = ref_mt.groupby(["PAC", "FAS_CON", "TEN_FORN"], as_index=False)["peso"].sum()

    pontos: list[dict[str, object]] = []
    for row in ref_bt.itertuples(index=False):
        pontos.append(
            {
                "metodo": "agregado_municipio_proporcional_carga",
                "grupo": "BT",
                "id_ref": row.UNI_TR_MT,
                "peso": float(row.peso),
            }
        )
    for row in ref_mt.itertuples(index=False):
        pontos.append(
            {
                "metodo": "agregado_municipio_proporcional_carga",
                "grupo": "MT",
                "id_ref": row.PAC,
                "pac": row.PAC,
                "fas_con": row.FAS_CON,
                "ten_con": row.TEN_FORN,
                "peso": float(row.peso),
            }
        )
    peso_total = sum(float(p["peso"]) for p in pontos)
    if peso_total <= 0:
        return [], []

    local = carga_ref[carga_ref["CTMT"] == ctmt]
    if local.empty:
        return [], []
    frac_por_municipio = {
        int(r.MUN): (
            float(r.carga_ref) / float(r.carga_municipio) if float(r.carga_municipio) > 0 else 0.0
        )
        for r in local.itertuples(index=False)
    }
    elementos: list[dict[str, object]] = []
    grupos: list[str] = []
    for mun in municipios:
        frac_ctmt = frac_por_municipio.get(mun, 0.0)
        if frac_ctmt <= 0:
            continue
        saldo = agregado[pd.to_numeric(agregado["cod_municipio_ibge"], errors="coerce") == mun]
        for row in saldo.itertuples(index=False):
            potencia_ctmt = float(row.potencia_kw) * frac_ctmt
            if potencia_ctmt <= 0:
                continue
            grupos.append(f"{mun} / {row.municipio} ({row.tipo_modelo})")
            for ponto in pontos:
                elementos.append(
                    {
                        **ponto,
                        "tipo_modelo": row.tipo_modelo,
                        "tipo_geracao": row.tipo_modelo,
                        "fonte_geracao": _texto(row.municipio),
                        "municipio": _texto(row.municipio),
                        "cod_municipio_ibge": mun,
                        "n_empreendimentos": int(row.n_empreendimentos),
                        "potencia_kw": potencia_ctmt * float(ponto["peso"]) / peso_total,
                    }
                )
    return elementos, grupos


# --- conversão de um CTMT -------------------------------------------------------------------------


class _Conversor:
    def __init__(self, gpkg: Path, ctmt_row: pd.Series, tabelas: dict[str, pd.DataFrame], ano: int):
        self.gpkg = gpkg
        self.ct = ctmt_row
        self.ctmt = _texto(ctmt_row["COD_ID"])
        self.t = tabelas
        self.dias = dias_por_tipo(ano)
        self.avisos: list[str] = []
        self.contagem: dict[str, int] = {}
        self.basekv = _kv(ctmt_row.get("TEN_NOM"), 13.8)
        if self.basekv <= 0:
            self.basekv = 13.8
            self.avisos.append(f"{self.ctmt}: TEN_NOM inválida; assumindo 13,8 kV")
        self.pu = _num(ctmt_row.get("TEN_OPE"), 1.0) or 1.0
        self.pac_ini = _texto(ctmt_row.get("PAC_INI"))
        self.kv_bt: dict[str, float] = {}  # UNTRMT → tensão de linha BT
        self.kv_fase_bt: dict[str, float] = {}  # UNTRMT → tensão fase-neutro para carga 1F
        self.ref_gd_bt: dict[str, dict[str, str | float]] = {}
        self.bases_kv: set[float] = {self.basekv}
        self.conectados: set[str] = set()

    # ---- conectividade (mesmo grafo do bdgd2opendss: todas as chaves, inclusive NA) ------------
    def _conectividade(self) -> None:
        pai: dict[str, str] = {}

        def achar(x: str) -> str:
            while pai.setdefault(x, x) != x:
                pai[x] = pai[pai[x]]
                x = pai[x]
            return x

        def unir(a: str, b: str) -> None:
            if a and b:
                ra, rb = achar(a), achar(b)
                if ra != rb:
                    pai[ra] = rb

        for nome in ("SSDMT", "UNSEMT", "UNTRMT", "SSDBT", "UNSEBT", "RAMLIG"):
            df = self.t[nome]
            if df.empty or "PAC_1" not in df.columns:
                continue
            for a, b in zip(df["PAC_1"], df["PAC_2"], strict=True):
                unir(_texto(a), _texto(b))
        if not self.pac_ini:
            self.avisos.append(f"{self.ctmt}: CTMT sem PAC_INI; nada será considerado isolado")
            self.conectados = set(pai)
            return
        if self.pac_ini not in pai:
            self.avisos.append(
                f"{self.ctmt}: PAC_INI {self.pac_ini!r} não pertence a nenhum elemento — o "
                "alimentador não tem conexão com a fonte; nada será considerado isolado"
            )
            return
        raiz = achar(self.pac_ini)
        self.conectados = {n for n in pai if achar(n) == raiz}

    # ---- suspeitos de qualidade de dado (issue #44) ---------------------------------------------
    def suspeitos(self) -> None:
        """Registra em ``avisos``/``contagem`` os ramais longos (``ramais_longos``) e os trafos de
        fase única (``trafos_fase_unica``)."""
        ram = self.t["RAMLIG"]
        if not ram.empty and "COMP" in ram.columns:
            comp = ram["COMP"].map(_num)
            longos = ram[comp > RAMAL_LONGO_M]
            self.contagem["ramais_longos"] = len(longos)
            if len(longos):
                pior = longos.loc[comp[longos.index].idxmax()]
                uc = self.t["UCBT_tab"]
                n_uc = (
                    int((uc["RAMAL"].map(_texto) == _texto(pior["COD_ID"])).sum())
                    if "RAMAL" in uc.columns
                    else 0
                )
                self.avisos.append(
                    f"{self.ctmt}: {len(longos)} ramais RAMLIG com mais de {RAMAL_LONGO_M:g} m "
                    f"(maior: {_texto(pior['COD_ID'])}, {_num(pior['COMP']):.0f} m, {n_uc} UC) — "
                    "provável circuito BT cadastrado como ramal"
                )
        uc = self.t["UCBT_tab"]
        if uc.empty or "FAS_CON" not in uc.columns or "UNI_TR_MT" not in uc.columns:
            return
        fas = uc["FAS_CON"].map(_texto)
        mono = uc[fas.isin(MONOFASICAS)]
        degenerados: list[tuple[str, int, int, str]] = []
        for trafo, grupo in mono.groupby(mono["UNI_TR_MT"].map(_texto), sort=True):
            if len(grupo) < FASE_UNICA_MIN_UC:
                continue
            por_fase = fas[grupo.index].str[0].value_counts()
            fase, n = str(por_fase.index[0]), int(por_fase.iloc[0])
            if n / len(grupo) >= FASE_UNICA_FRACAO:
                degenerados.append((trafo, n, len(grupo), fase))
        self.contagem["trafos_fase_unica"] = len(degenerados)
        if not degenerados:
            return
        degenerados.sort(key=lambda d: -d[1])
        top = ", ".join(
            f"{t} ({n} de {tot} UC monofásicas em {f})" for t, n, tot, f in degenerados[:3]
        )
        self.avisos.append(
            f"{self.ctmt}: {len(degenerados)} trafos com >= {FASE_UNICA_FRACAO:.0%} das UC "
            f"monofásicas na mesma fase ({top}) — desequilíbrio da BDGD que exige o "
            "estabilizador vminpu=0.9 no fluxo (issue #44)"
        )

    def _ligado(self, *pacs) -> bool:
        return not self.conectados or any(_texto(p) in self.conectados for p in pacs)

    def _isolado(self, linha: str, nome: str) -> str:
        self.contagem[f"isolados_{nome}"] = self.contagem.get(f"isolados_{nome}", 0) + 1
        return "!" + linha

    # ---- arquivos ------------------------------------------------------------------------------
    def circuito(self) -> list[str]:
        return [
            f'New "Circuit.{self.ctmt}" basekv={self.basekv:g} pu={self.pu} '
            f'bus1="{self.pac_ini}" r1=0.0 x1=0.0001'
        ]

    def linecodes(self) -> list[str]:
        seg = self.t["SEGCON"]
        linhas: list[str] = []
        if seg.empty:
            self.avisos.append(f"{self.ctmt}: sem SEGCON; linecodes não gerados")
            return linhas
        for _, r in seg.iterrows():
            r1 = _num(r.get("R1"))
            regul = RESISTENCIA_REGUL.get(_texto(r.get("R_REGUL")), None)
            if regul is not None and 0 < regul < r1:
                r1 = regul
            x1 = _num(r.get("X1"))
            normamps = _num(r.get("CMAX")) or _num(r.get("CNOM"))
            for n in range(1, 5):
                linhas.append(
                    f'New "Linecode.{_texto(r["COD_ID"])}_{n}" nphases={n} basefreq=60 '
                    f"r1={r1:.4f} x1={x1:.4f} units=km normamps={normamps:.2f}"
                )
        self.contagem["linecodes"] = len(seg)
        return linhas

    def _segmentos(self, nome: str, prefixo: str, bt: bool) -> list[str]:
        df = self.t[nome]
        linhas: list[str] = []
        if df.empty:
            return linhas
        nulos = 0
        for _, r in df.iterrows():
            fas = _texto(r.get("FAS_CON")) or ("ABCN" if bt else "ABC")
            fases = CONDUTORES.get(fas, 4) if bt else FASES.get(fas, 3)
            nos = NOS.get(fas, "1.2.3.4" if bt else "1.2.3")
            comp_m = _num(r.get("COMP"))
            if comp_m <= 0:
                # o bdgd2opendss mantém o COMP da BDGD; só um comprimento nulo quebraria o OpenDSS
                nulos += 1
                comp_m = 0.001
            a, b = _texto(r["PAC_1"]), _texto(r["PAC_2"])
            nome_elemento = (
                nome_elemento_trecho_mt(r["COD_ID"])
                if prefixo == TIPO_TRECHO_MT_OPEN_DSS
                else f"Line.{prefixo}_{_texto(r['COD_ID'])}"
            )
            linha = (
                f'New "{nome_elemento}" phases={fases} bus1="{a}.{nos}" '
                f'bus2="{b}.{nos}" linecode="{_texto(r.get("TIP_CND"))}_{fases}" '
                f"length={comp_m / 1000:.9f} units=km"
            )
            linhas.append(linha if self._ligado(a, b) else self._isolado(linha, nome))
        if nulos:
            self.avisos.append(f"{self.ctmt}: {nulos} {nome} com COMP nulo ajustados para 1 mm")
        self.contagem[nome] = len(df)
        return linhas

    def _chaves(self, nome: str, prefixo: str, bt: bool) -> list[str]:
        df = self.t[nome]
        linhas: list[str] = []
        if df.empty:
            return linhas
        abertas = 0
        for _, r in df.iterrows():
            fas = _texto(r.get("FAS_CON")) or ("ABCN" if bt else "ABC")
            fases = FASES.get(fas, 3)
            nos = NOS.get(fas, "1.2.3.4" if bt else "1.2.3")
            a, b = _texto(r["PAC_1"]), _texto(r["PAC_2"])
            linha = (
                f'New "Line.{prefixo}_{_texto(r["COD_ID"])}" phases={fases} bus1="{a}.{nos}" '
                f'bus2="{b}.{nos}" {_CHAVE}'
            )
            if _texto(r.get("P_N_OPE")).upper() == "A":
                abertas += 1
                linhas.append("!" + linha)  # NA: comentada, como no bdgd2opendss
            else:
                linhas.append(linha if self._ligado(a, b) else self._isolado(linha, nome))
        self.contagem[nome] = len(df)
        self.contagem[f"{nome}_NA"] = abertas
        return linhas

    def transformadores(self) -> list[str]:
        tr = self.t["UNTRMT"]
        eq = self.t["EQTRMT"]
        linhas: list[str] = []
        if tr.empty:
            return linhas
        eq_por_tr: dict[str, list[pd.Series]] = {}
        if not eq.empty and "UNI_TR_MT" in eq.columns:
            for _, r in eq.iterrows():
                eq_por_tr.setdefault(_texto(r["UNI_TR_MT"]), []).append(r)
        n_unidades = 0
        for _, r in tr.iterrows():
            cod = _texto(r["COD_ID"])
            if _texto(r.get("SIT_ATIV")).upper() == "DS":
                continue
            unidades = eq_por_tr.get(cod) or [None]
            if len(unidades) > 6:
                self.avisos.append(
                    f"{self.ctmt}: banco {cod} com {len(unidades)} unidades; ignorado"
                )
                continue
            tip = _texto(r.get("TIP_TRAFO")) or "T"
            kv2 = _num(r.get("TEN_LIN_SE"))
            if kv2 <= 0 and unidades[0] is not None:
                kv2 = _kv(unidades[0].get("TEN_SEC"))
            if kv2 <= 0:
                kv2 = 0.22
                self.avisos.append(f"{self.ctmt}: trafo {cod} sem tensão BT; assumindo 0,22 kV")
            # kVA de cada unidade: código EQTRMT.POT_NOM (como o bdgd2opendss, que não lê o
            # POT_NOM da UNTRMT); sem EQTRMT, o POT_NOM da UNTRMT (kVA do conjunto) / unidades
            kva_banco = _num(r.get("POT_NOM"))
            kvas_unid = [
                POTENCIA_KVA.get(_texto(u.get("POT_NOM")), 0.0) if u is not None else 0.0
                for u in unidades
            ]
            if any(k <= 0 for k in kvas_unid):
                kvas_unid = [kva_banco / len(unidades)] * len(unidades)
            if any(k <= 0 for k in kvas_unid):
                self.avisos.append(f"{self.ctmt}: trafo {cod} sem POT_NOM; ignorado")
                continue
            # perdas da UNTRMT são do conjunto: cada unidade do banco fica com 1/n (o
            # bdgd2opendss repete as perdas do conjunto em cada unidade)
            per_fer = _num(r.get("PER_FER")) / len(unidades)
            per_tot = _num(r.get("PER_TOT")) / len(unidades)
            if _texto(r.get("POS")) not in ("", "PD"):
                per_fer = per_tot = 0.0  # trafo de terceiros: perdas neutralizadas (bdgd2opendss)
            pac1, pac2, pac3 = _texto(r["PAC_1"]), _texto(r["PAC_2"]), _texto(r.get("PAC_3"))
            self.bases_kv.add(round(kv2, 4))
            self.kv_bt[cod] = kv2
            if tip == "MT":
                self.kv_fase_bt[cod] = kv2 / 2
            elif tip in ("M", "B"):
                self.kv_fase_bt[cod] = kv2
            else:
                self.kv_fase_bt[cod] = kv2 / _RAIZ3
            lig_s_base = (
                _texto(unidades[0].get("LIG_FAS_S"))
                if unidades[0] is not None
                else (_texto(r.get("FAS_CON_S")) or "ABCN")
            )
            self.ref_gd_bt[cod] = {
                "pac": pac2,
                "fas_con": (
                    lig_s_base if lig_s_base in NOS else (_texto(r.get("FAS_CON_S")) or "ABCN")
                ),
                "kv_linha": kv2,
                "kv_fase": self.kv_fase_bt[cod],
            }
            for idx, u in enumerate(unidades):
                sufixo = chr(65 + idx)
                kva = kvas_unid[idx]
                loadloss = max(per_tot - per_fer, 0.0) / (10 * kva)
                noloadloss = per_fer / (10 * kva)
                lig_p = _texto(u.get("LIG_FAS_P")) if u is not None else ""
                lig_s = _texto(u.get("LIG_FAS_S")) if u is not None else ""
                lig_t = _texto(u.get("LIG_FAS_T")) if u is not None else ""
                lig_p = lig_p if lig_p in NOS else (_texto(r.get("FAS_CON_P")) or "ABC")
                lig_s = lig_s if lig_s in NOS else (_texto(r.get("FAS_CON_S")) or "ABCN")
                lig_t = lig_t if lig_t in NOS_TERCIARIO else (_texto(r.get("FAS_CON_T")) or "")
                nos1 = NOS_PRIMARIO.get(lig_p, "1.2.3")
                nos2 = NOS.get(lig_s, "1.2.3.4")
                conn_p, conn_s = CONEXAO.get(lig_p, "Delta"), CONEXAO.get(lig_s, "Wye")
                fases = 3 if lig_p in ("ABC", "ABCN") else 1
                kv1 = self.basekv / _RAIZ3 if conn_p == "Wye" and fases == 1 else self.basekv
                enrol = ENROLAMENTOS.get(tip, 2)
                if enrol == 3 and lig_t in NOS_TERCIARIO:
                    # monofásico com terciário (MT): 3 enrolamentos, BT dividida em duas metades
                    buses = f'"{pac1}.{nos1}" "{pac2}.{nos2}" "{pac2}.{NOS_TERCIARIO[lig_t]}"'
                    kvs = f"{kv1:g} {kv2 / 2:.13g} {kv2 / 2:.13g}"
                    kvas = f"{kva:g} {kva:g} {kva:g}"
                    conns = f"{conn_p} {conn_s} Wye"
                else:
                    enrol = 2
                    # unidade de banco (DF/DA): TEN_LIN_SE é a tensão de linha do banco e cada
                    # unidade liga fase–neutro na BT → tensão do enrolamento = linha/√3
                    # (o bdgd2opendss escreve phases=3 e kv de linha; bdgd2opendss#35)
                    kv2_u = kv2 / _RAIZ3 if fases == 1 and tip in ("DF", "DA") else kv2
                    buses = f'"{pac1}.{nos1}" "{pac2}.{nos2}"'
                    kvs = f"{kv1:g} {kv2_u:.13g}"
                    kvas = f"{kva:g} {kva:g}"
                    conns = f"{conn_p} {conn_s}"
                nome = f"TRF_{cod}{sufixo}"
                linha = (
                    f'New "Transformer.{nome}" phases={fases} windings={enrol} buses=[{buses}] '
                    f"conns=[{conns}] kvs=[{kvs}]  kvas=[{kvas}] "
                    f"%loadloss={loadloss:.6f} %noloadloss={noloadloss:.6f}"
                )
                reator = f'New "Reactor.{nome}_R" phases=1 bus1={pac2}.4 R=15 X=0 basefreq=60'
                if self._ligado(pac1, pac2, pac3):
                    linhas += [linha, reator]
                else:
                    linhas += [self._isolado(linha, "UNTRMT"), "!" + reator]
                n_unidades += 1
        self.contagem["UNTRMT"] = len(tr)
        self.contagem["unidades_trafo"] = n_unidades
        return linhas

    def medidor(self) -> list[str]:
        """Energymeter no disjuntor (chave no PAC_INI) ou, sem chave, no primeiro trecho MT."""
        se = self.t["UNSEMT"]
        if not se.empty:
            no_ini = se[(se["PAC_1"] == self.pac_ini) | (se["PAC_2"] == self.pac_ini)]
            if "P_N_OPE" in no_ini.columns:
                no_ini = no_ini[no_ini["P_N_OPE"] != "A"]
            if not no_ini.empty:
                cod = _texto(no_ini.iloc[0]["COD_ID"])
                return [f'New "Energymeter.M_{self.ctmt}" element="Line.CMT_{cod}" terminal=1']
        mt = self.t["SSDMT"]
        if not mt.empty:
            no_ini = mt[(mt["PAC_1"] == self.pac_ini) | (mt["PAC_2"] == self.pac_ini)]
            if not no_ini.empty:
                cod = _texto(no_ini.iloc[0]["COD_ID"])
                return [
                    (
                        f'New "Energymeter.M_{self.ctmt}" '
                        f'element="{nome_elemento_trecho_mt(cod)}" terminal=1'
                    )
                ]
        self.avisos.append(f"{self.ctmt}: nenhum elemento no PAC_INI {self.pac_ini!r}; sem medidor")
        return []

    def curvas(self, curvas: _Curvas) -> list[str]:
        linhas = []
        for (cod, tip), mult in sorted(curvas.mult.items()):
            valores = ", ".join(str(round(v, 9)) for v in mult)  # mesmo formato do bdgd2opendss
            linhas.append(f'New "Loadshape.{cod}_{tip}" 24 1 mult=({valores})')
        self.contagem["curvas"] = len(linhas)
        return linhas

    def cargas(self, nome: str, curvas: _Curvas, tip_dia: str, mes: int) -> list[str]:
        df = self.t[nome]
        linhas: list[str] = []
        if df.empty:
            return linhas
        ip = nome == "PIP"
        bt = ip or nome.startswith("UCBT")
        if ip:
            col_id = "COD_ID"  # iluminação pública: nome BT_IP<COD_ID>, sem sufixo de repetição
        elif bt and "RAMAL" in df.columns:
            col_id = "RAMAL"
        else:
            col_id = "PN_CON" if "PN_CON" in df.columns else "COD_ID"
        ids = df[col_id].map(_texto)
        repetidos = ids[ids.duplicated(keep=False)] if not ip else ids.iloc[0:0]
        sufixos: dict[str, int] = {}
        energias = [c for c in _ENERGIAS if c in df.columns]
        col_mes = f"ENE_{mes:02d}"
        n = 0
        # cargas são reescritas por dia×mês: a contagem de isoladas não pode acumular
        self.contagem.pop(f"isolados_{nome}", None)
        for i, r in df.iterrows():
            ident = ids[i]
            if i in repetidos.index:
                sufixos[ident] = sufixos.get(ident, 0) + 1
                ident = f"{ident}_{sufixos[ident]}"
            total = sum(_num(r[c]) for c in energias)
            if total == 0:
                continue
            pac = _texto(r["PAC"])
            fas = _texto(r.get("FAS_CON")) or ("AN" if bt else "ABC")
            fases = 3 if fas in ("ABC", "ABCN") else 1
            conn = CONEXAO_CARGA.get(fas, "Wye")
            nos = NOS.get(fas, "1.2.3.4")
            tip_cc = _texto(r.get("TIP_CC")) or "flat"
            kw_total = curvas.kw(tip_cc, tip_dia, mes, _num(r.get(col_mes)), self.dias)
            kw = math.trunc(kw_total * 1e6) / 1e6 / 2
            if bt:
                trafo = _texto(r.get("UNI_TR_MT"))
                kv_linha = self.kv_bt.get(trafo) or _kv(r.get("TEN_FORN"), 0.22) or 0.22
                if fases == 1 and conn == "Wye":
                    kv = self.kv_fase_bt.get(trafo) or kv_linha / _RAIZ3
                else:
                    kv = kv_linha
                prefixo = "BT_IP" if ip else "BT_"
            else:
                kv = self.basekv
                prefixo = "MT_"
            daily = f"{tip_cc}_{tip_dia}"
            base = (
                f'New "Load.{prefixo}{ident}_M{{m}}" bus1="{pac}.{nos}" phases={fases} conn={conn} '
                f"model={{modelo}} kv={kv:.9f} kw = {kw} pf=0.92 status=variable vmaxpu=1.5 "
                f'vminpu=0.5 daily="{daily}"'
            )
            l1 = base.format(m=1, modelo=2)
            l2 = base.format(m=2, modelo=3)
            if self._ligado(pac):
                linhas += [l1, l2]
            else:
                linhas += [self._isolado(l1, nome), "!" + l2]
            n += 1
        self.contagem[nome] = n
        return linhas

    def gd(self, config: ConfiguracaoGd) -> tuple[list[str], ResumoGdCtmt | None]:
        mmgd, _ = _base_gd_light(
            str(Path(config.parquet_dir).resolve()), str(Path(config.mmgd_path).resolve())
        )
        tabelas_gd = []
        for nome in ("UGBT_tab", "UGMT_tab"):
            df = self.t.get(nome, pd.DataFrame()).copy()
            if df.empty:
                continue
            df["_camada_gd"] = nome
            tabelas_gd.append(df)
        bdgd_local = pd.concat(tabelas_gd, ignore_index=True) if tabelas_gd else pd.DataFrame()
        elementos_exatos, observacoes = _alocacao_exata(self.ctmt, mmgd, bdgd_local)
        elementos_agregados, grupos_agregados = _alocacao_agregada(self.ctmt, self.t, config)
        elementos = [*elementos_exatos, *elementos_agregados]
        if not elementos:
            return [], None
        linhas = [
            "! GD opcional da issue #98 — arquivo gerado sem alterar o padrão do Master.",
            (
                "! Regra: chave direta `CEG_GD -> PAC` quando existe; "
                "saldo sem chave direta da MMGD Light"
            ),
            (
                "! é rateado por município proporcionalmente à carga do CTMT "
                "e alocado por transformador BT"
            ),
            "! e PAC MT. O Master só inclui este arquivo com `--gd`.",
            _shape_dss("gd_pv_diario", _SHAPE_SOLAR),
            _shape_dss("gd_nao_solar_diario", _SHAPE_NAO_SOLAR),
        ]
        linhas += self._linhas_gd_explicitas(elementos_exatos)
        linhas += self._linhas_gd_agregadas(elementos_agregados)
        resumo = ResumoGdCtmt(
            ctmt=self.ctmt,
            n_elementos=len(elementos),
            potencia_total_kw=sum(float(e["potencia_kw"]) for e in elementos),
            n_empreendimentos_exatos=len({str(e["ceg_gd"]) for e in elementos_exatos}),
            potencia_exata_kw=sum(float(e["potencia_kw"]) for e in elementos_exatos),
            n_elementos_exatos=len(elementos_exatos),
            n_empreendimentos_agregados=sum(
                {
                    (int(e.get("cod_municipio_ibge", 0)), _texto(e.get("tipo_modelo"))): int(
                        e.get("n_empreendimentos", 0)
                    )
                    for e in elementos_agregados
                }.values()
            ),
            potencia_agregada_kw=sum(float(e["potencia_kw"]) for e in elementos_agregados),
            n_elementos_agregados=len(elementos_agregados),
            criterio_agregado="municipio proporcional à carga" if elementos_agregados else None,
            grupos_agregados=tuple(dict.fromkeys(grupos_agregados)),
            observacoes=tuple(dict.fromkeys(observacoes)),
        )
        return linhas, resumo

    def _linhas_gd_explicitas(self, elementos: list[dict[str, object]]) -> list[str]:
        if not elementos:
            return []
        linhas = [
            (
                "! chave_direta_pac: MMGD `CodEmpreendimento` casada com BDGD `CEG_GD`; "
                "injeção no PAC da unidade geradora."
            )
        ]
        for idx, elemento in enumerate(elementos, start=1):
            nome = f"{self.ctmt}_exata_{idx:04d}"
            linhas.append(
                f"! exata {elemento['ceg_gd']} ({elemento['camada']}/{elemento['cod_id_bdgd']}) "
                f"{elemento['potencia_kw']:.3f} kW — {_texto(elemento['fonte_geracao'])}"
            )
            linhas.append(self._elemento_gd(nome, elemento))
        return linhas

    def _linhas_gd_agregadas(self, elementos: list[dict[str, object]]) -> list[str]:
        if not elementos:
            return []
        linhas = [
            (
                "! agregado_municipio_proporcional_carga: "
                "saldo MMGD sem chave direta distribuído por "
                "carga do CTMT; agrupamento possível na Light atual = município."
            )
        ]
        for idx, elemento in enumerate(elementos, start=1):
            rotulo = _texto(elemento.get("municipio")) or (
                f"MUN {elemento.get('cod_municipio_ibge')}"
            )
            linhas.append(
                f"! agregado {rotulo} / {elemento['grupo']} / {elemento['tipo_modelo']} "
                f"{elemento['potencia_kw']:.6f} kW"
            )
            linhas.append(self._elemento_gd(f"{self.ctmt}_agregado_{idx:05d}", elemento))
        return linhas

    def _elemento_gd(self, nome: str, elemento: dict[str, object]) -> str:
        grupo = _texto(elemento.get("grupo"))
        if grupo == "BT":
            ref = self.ref_gd_bt.get(
                _texto(elemento.get("id_ref") or elemento.get("uni_tr_mt")), {}
            )
            pac = _texto(ref.get("pac") or elemento.get("pac"))
            fas = _texto(ref.get("fas_con") or elemento.get("fas_con")) or "ABCN"
            uni_tr_mt = _texto(elemento.get("uni_tr_mt") or elemento.get("id_ref"))
            kv_linha = float(ref.get("kv_linha") or self.kv_bt.get(uni_tr_mt, 0.22))
            kv_fase = float(ref.get("kv_fase") or self.kv_fase_bt.get(uni_tr_mt, kv_linha / _RAIZ3))
        else:
            pac = _texto(elemento.get("pac"))
            fas = _texto(elemento.get("fas_con")) or "ABC"
            kv_linha = _kv(elemento.get("ten_con"), self.basekv) or self.basekv
            kv_fase = kv_linha / _RAIZ3
        fases = FASES.get(fas, 3 if grupo != "BT" else 1)
        conn = CONEXAO.get(fas, "Wye")
        nos = NOS.get(fas, "1.2.3" if fases > 1 else "1.4")
        kv = kv_fase if fases == 1 and conn == "Wye" else kv_linha
        shape = (
            "gd_pv_diario"
            if _texto(elemento.get("tipo_modelo")) == "PVSystem"
            else "gd_nao_solar_diario"
        )
        potencia = max(float(elemento["potencia_kw"]), 0.0)
        if _texto(elemento.get("tipo_modelo")) == "PVSystem":
            linha = (
                f'New "PVSystem.GD_{nome}" phases={fases} bus1="{pac}.{nos}" conn={conn} '
                f"kv={kv:.9f} pmpp={potencia:.6f} kva={max(potencia, 0.001):.6f} pf=1 "
                f"irradiance=1 daily={shape}"
            )
        else:
            linha = (
                f'New "Generator.GD_{nome}" phases={fases} bus1="{pac}.{nos}" conn={conn} '
                f"kv={kv:.9f} kw={potencia:.6f} pf=1 model=1 daily={shape}"
            )
        return linha if self._ligado(pac) else self._isolado(linha, "GD_BT")


CARGAS = ("UCBT_tab", "UCMT_tab", "PIP")


def _agrupar_cargas(df: pd.DataFrame) -> pd.DataFrame:
    """Reproduz o ``groupby('COD_ID')`` do bdgd2opendss: ordena por ``COD_ID`` (é essa ordem que
    numera os ramais repetidos) e soma as energias de eventuais ``COD_ID`` duplicados."""
    if df.empty or "COD_ID" not in df.columns:
        return df
    if df["COD_ID"].duplicated().any():
        energias = [c for c in _ENERGIAS if c in df.columns]
        agg = {c: "last" for c in df.columns if c != "COD_ID" and c not in energias}
        agg |= {c: "sum" for c in energias}
        return df.groupby("COD_ID", as_index=False, sort=True).agg(agg)
    return df.sort_values("COD_ID", kind="stable").reset_index(drop=True)


def _escrever(pasta: Path, prefixo: str, ctmt: str, linhas: Sequence[str]) -> Path | None:
    if not linhas:
        return None
    arq = pasta / f"{prefixo}_{PREFIXO_ARQUIVO}_{ctmt}.dss"
    arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return arq


def converter_ctmt(
    gpkg: str | Path,
    ctmt: str,
    out: str | Path,
    *,
    dias: Iterable[str] = DIAS,
    meses: Iterable[int] = (1,),
    ano: int = ANO_PADRAO,
    gd: ConfiguracaoGd | None = None,
) -> ConversaoGpkg:
    """Converte um CTMT do GeoPackage para ``<out>/<ctmt>/`` e devolve os caminhos gerados.

    Ramais longos e trafos de fase única (suspeitos de qualidade de dado que pesam na
    convergência, issue #44) saem em ``avisos`` e ``contagem``.
    """
    gpkg = Path(gpkg)
    if not gpkg.is_file():
        raise FileNotFoundError(gpkg)
    existentes = _camadas(gpkg)
    if "CTMT" not in existentes:
        raise GpkgInvalidoError(f"{gpkg.name} não tem a camada CTMT")
    ctmts = _ler(gpkg, "CTMT", existentes)
    sel = ctmts[ctmts["COD_ID"] == ctmt]
    if sel.empty:
        raise GpkgInvalidoError(
            f"CTMT {ctmt!r} não está em {gpkg.name}; disponíveis: {', '.join(ctmts['COD_ID'])}"
        )
    nomes = (
        "SSDMT", "UNSEMT", "UNTRMT", "SSDBT", "UNSEBT", "RAMLIG", "UCBT_tab", "UCMT_tab",
        "UGBT_tab", "UGMT_tab", "PIP", "EQTRMT", "SEGCON", "CRVCRG",
    )  # fmt: skip
    tabelas = {n: _por_ctmt(_ler(gpkg, n, existentes), ctmt) for n in nomes}
    if tabelas["UCBT_tab"].empty and "UCBT" in existentes:
        tabelas["UCBT_tab"] = _por_ctmt(_ler(gpkg, "UCBT", existentes), ctmt)
    for n in CARGAS:
        tabelas[n] = _agrupar_cargas(tabelas[n])
    if tabelas["SSDMT"].empty:
        raise GpkgInvalidoError(f"{ctmt}: sem trechos SSDMT em {gpkg.name}")
    if not tabelas["EQTRMT"].empty and "UNI_TR_MT" in tabelas["EQTRMT"].columns:
        cods = set(tabelas["UNTRMT"].get("COD_ID", pd.Series(dtype=str)).map(_texto))
        eq = tabelas["EQTRMT"]
        tabelas["EQTRMT"] = eq[eq["UNI_TR_MT"].map(_texto).isin(cods)].reset_index(drop=True)

    dias = [d.upper() for d in dias]
    for d in dias:
        if d not in DIAS:
            raise ValueError(f"dia deve ser um de {DIAS}, não {d!r}")
    meses = list(meses)
    if any(m < 1 or m > 12 for m in meses):
        raise ValueError("mes deve estar entre 1 e 12")

    pasta = Path(out) / ctmt
    pasta.mkdir(parents=True, exist_ok=True)
    c = _Conversor(gpkg, sel.iloc[0], tabelas, ano)
    c._conectividade()
    c.suspeitos()
    curvas = _Curvas.das_linhas(tabelas["CRVCRG"])
    tipos_cc = [
        _texto(x) or "flat"
        for nome in CARGAS
        if "TIP_CC" in tabelas[nome].columns
        for x in tabelas[nome]["TIP_CC"]
    ]
    for nome in CARGAS:
        if not tabelas[nome].empty and "TIP_CC" not in tabelas[nome].columns:
            tipos_cc.append("flat")
    if criados := curvas.garantir(tipos_cc):
        c.avisos.append(f"{ctmt}: sem curva CRVCRG para {criados}; patamar plano (mult=1)")

    fixos: list[tuple[str, list[str]]] = [
        ("CircuitoMT", c.circuito()),
        ("CodCondutor", c.linecodes()),
        ("TransformadorMTMTMTBT", c.transformadores()),
        ("SegmentosMT", c._segmentos("SSDMT", TIPO_TRECHO_MT_OPEN_DSS, bt=False)),
        ("ChavesMT", c._chaves("UNSEMT", "CMT", bt=False)),
        ("SegmentosBT", c._segmentos("SSDBT", "SBT", bt=True)),
        ("ChavesBT", c._chaves("UNSEBT", "CBT", bt=True)),
        ("RamaisBT", c._segmentos("RAMLIG", "RBT", bt=True)),
        ("Medidores", c.medidor()),
        ("CurvaCarga", c.curvas(curvas)),
    ]
    redirects = [
        arq.name for prefixo, linhas in fixos if (arq := _escrever(pasta, prefixo, ctmt, linhas))
    ]
    resumo_gd = None
    if gd is not None:
        linhas_gd, resumo_gd = c.gd(gd)
        if linhas_gd:
            arq_gd = _escrever(pasta, "GD_BT", ctmt, linhas_gd)
            if arq_gd is not None:
                c.contagem["GD_BT"] = resumo_gd.n_elementos
                c.contagem["GD_exata"] = resumo_gd.n_elementos_exatos
                c.contagem["GD_agregada"] = resumo_gd.n_elementos_agregados
                c.avisos.extend(resumo_gd.observacoes)
    bases = " ".join(f"{b:g}" for b in sorted(c.bases_kv))
    masters: list[Path] = []
    for mes in meses:
        for dia in dias:
            sufixo = f"{dia}{mes:02d}"
            extra = []
            # iluminação pública (PIP) entra no mesmo arquivo CargasBT, como no bdgd2opendss
            linhas_bt = c.cargas("UCBT_tab", curvas, dia, mes) + c.cargas("PIP", curvas, dia, mes)
            for prefixo, linhas in (
                ("CargasBT", linhas_bt),
                ("CargasMT", c.cargas("UCMT_tab", curvas, dia, mes)),
            ):
                arq = _escrever(pasta, f"{prefixo}_{sufixo}", ctmt, linhas)
                if arq is not None:
                    extra.append(arq.name)
            master = pasta / f"Master_{sufixo}_{PREFIXO_ARQUIVO}_{ctmt}.dss"
            corpo = ["clear"]
            corpo += [f'Redirect "{n}"' for n in redirects + extra]
            corpo += [
                "Set mode = daily",
                f"Set Voltagebases = [{bases}]",
                "Calc Voltagebases",
                "Set tolerance = 0.0001",
                "Set maxcontroliter = 10",
            ]
            master.write_text("\n".join(corpo) + "\n", encoding="utf-8")
            masters.append(master)
    isolados = sum(v for k, v in c.contagem.items() if k.startswith("isolados_"))
    if isolados:
        c.avisos.append(f"{ctmt}: {isolados} elementos sem caminho até {c.pac_ini} (comentados)")
    return ConversaoGpkg(ctmt, pasta, masters, c.contagem, c.avisos, gd=resumo_gd)


def listar_ctmts(gpkg: str | Path) -> list[str]:
    """COD_ID dos alimentadores presentes na camada ``CTMT`` do GeoPackage."""
    gpkg = Path(gpkg)
    if "CTMT" not in _camadas(gpkg):
        raise GpkgInvalidoError(f"{gpkg.name} não tem a camada CTMT")
    ctmt = pyogrio.read_dataframe(gpkg, layer="CTMT", read_geometry=False)
    return [str(x).strip() for x in ctmt["COD_ID"]]


def converter_gpkg(
    gpkg: str | Path,
    out: str | Path,
    *,
    ctmts: Sequence[str] | None = None,
    dias: Iterable[str] = DIAS,
    meses: Iterable[int] = (1,),
    ano: int = ANO_PADRAO,
    gd: ConfiguracaoGd | None = None,
) -> list[ConversaoGpkg]:
    """Converte todos (ou só ``ctmts``) os alimentadores do GeoPackage; um ``<out>/<CTMT>/`` por
    CTMT."""
    ctmts = list(ctmts) if ctmts else listar_ctmts(gpkg)
    return [converter_ctmt(gpkg, c, out, dias=dias, meses=meses, ano=ano, gd=gd) for c in ctmts]
