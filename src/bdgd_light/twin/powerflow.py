"""Fluxo de potência com OpenDSSDirect sobre um Master .dss.

O Master gerado pelo bdgd2opendss vem em ``mode=daily`` e sem ``Solve``; aqui sempre resolvemos um
snapshot (patamar de pico das curvas CRVCRG, ``kw`` = demanda máxima) e, se o método padrão não
convergir, aplicamos uma cascata documentada de estabilizadores (ver ``ESTABILIZADORES``),
registrando no resultado quais foram necessários.

O motor (biblioteca DSS C-API) roda num **subprocesso** dedicado por padrão
(``BDGD_MOTOR=processo``) ou numa thread única do próprio processo (``BDGD_MOTOR=thread``); ver
``no_motor``.
"""

from __future__ import annotations

import atexit
import os
import pickle
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from multiprocessing.connection import Client, Connection, answer_challenge, deliver_challenge
from pathlib import Path
from typing import Any

import pandas as pd

# Cascata de estabilizadores, aplicada em ordem até convergir; cada item é (rótulo, comandos).
#   1. mais iterações — resolve os casos "quase" convergidos (não muda o modelo);
#   2. vminpu=0,9 — abaixo de 0,9 pu as cargas passam a impedância constante (recomendação do
#      próprio OpenDSS para cargas de corrente/potência constante em barras muito deprimidas). Nos
#      clusters da Light é este o degrau que resolve: a não convergência é um ciclo-limite das
#      cargas de corrente constante em circuitos BT muito desequilibrados (issue #44), e não
#      convergência lenta — por isso ``ajustes`` só lista ``maxiterations=100`` quando a solução
#      final de fato passou do limite original de iterações (ver ``_rotular_ajustes``);
#   3. impedância constante em todas as cargas — sempre converge; é o último recurso e subestima a
#      carga nas barras deprimidas.
ESTABILIZADORES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("maxiterations=100", ("set maxiterations=100",)),
    ("vminpu=0.9", ("batchedit load..* vminpu=0.9",)),
    ("model=2", ("batchedit load..* model=2",)),
)
_ROTULO_ITERACOES = ESTABILIZADORES[0][0]

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
    fontes: pd.DataFrame  # fonte (Vsource), barra, kw, kvar fornecidos, i_a (corrente máx. de fase)
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


# O DSS C-API (Free Pascal) só tolera chamadas da thread que o inicializou — de outra thread o
# processo morre com SIGILL — e a sua finalização na saída do processo derruba o Linux com SIGSEGV
# (ver docs/console.md). Duas estratégias, escolhidas por ``BDGD_MOTOR``:
#   processo (padrão): a biblioteca vive num subprocesso dedicado (``python -c`` que importa só este
#       módulo; sem reexecutar o ``__main__`` do pai, ao contrário do ``multiprocessing`` spawn) e o
#       processo pai nunca a carrega. Se o filho morrer (SIGILL/SIGSEGV) a chamada em curso levanta
#       ``MotorError`` e a chamada seguinte recria o filho; a saída do pai é a normal.
#   thread: ``ThreadPoolExecutor`` de uma thread no mesmo processo (estratégia anterior, mantida
#       na transição); exige ``encerrar_processo`` na saída.
MODOS_MOTOR = ("processo", "thread")
_PREFIXO_MOTOR = "opendss"
_MOTOR_THREAD: ThreadPoolExecutor | None = None
_MOTOR_PROCESSO: MotorProcesso | None = None
_TRAVA = threading.Lock()
_motor_usado = False
_sou_motor = False  # True dentro do subprocesso do motor


class MotorError(ErroOpenDSS):
    """O subprocesso do motor OpenDSS morreu ou não respondeu; a chamada seguinte o recria."""


def modo_motor() -> str:
    """Modo do motor (``BDGD_MOTOR``): ``processo`` (padrão) ou ``thread``."""
    modo = os.environ.get("BDGD_MOTOR", MODOS_MOTOR[0]).strip().lower() or MODOS_MOTOR[0]
    if modo not in MODOS_MOTOR:
        raise ValueError(f"BDGD_MOTOR={modo!r} inválido; use {' ou '.join(MODOS_MOTOR)}")
    return modo


def _exportavel(exc: BaseException) -> BaseException:
    """A exceção tal qual, se sobrevive ao pickle; senão um ``ErroOpenDSS`` com o mesmo texto."""
    try:
        pickle.loads(pickle.dumps(exc))
        return exc
    except Exception:  # noqa: BLE001 — DSSException e afins não têm construtor compatível
        return ErroOpenDSS(f"{type(exc).__name__}: {exc}")


def _servir_motor(conexao: Connection) -> None:
    """Laço do subprocesso do motor: recebe ``(fn, args, kwargs)``, executa na thread principal
    (a única) e devolve ``(True, resultado)`` ou ``(False, exceção)``; ``None`` ou o fim da conexão
    (pai encerrado) terminam o laço."""
    global _sou_motor
    _sou_motor = True
    while True:
        try:
            pedido = conexao.recv()
        except EOFError:
            return
        if pedido is None:
            return
        fn, args, kwargs = pedido
        try:
            resposta: tuple[bool, Any] = (True, fn(*args, **kwargs))
        except Exception as exc:  # noqa: BLE001 — devolvida ao processo pai
            resposta = (False, _exportavel(exc))
        try:
            conexao.send(resposta)
        except Exception as exc:  # noqa: BLE001 — resultado não serializável: avisa em vez de travar
            conexao.send((False, MotorError(f"resposta do motor não serializável: {exc}")))


def _main_motor() -> None:
    """Entrada do subprocesso (``python -c``): endereço em ``argv[1]``, chave em stdin."""
    endereco = sys.argv[1]
    chave = sys.stdin.buffer.read(_TAMANHO_CHAVE)
    with Client(endereco, authkey=chave) as conexao:
        _servir_motor(conexao)


def _abortar(sinal: int) -> None:
    """Mata o próprio processo (só faz sentido dentro do subprocesso do motor; ver
    ``simular_falha_do_motor``)."""
    os.kill(os.getpid(), sinal)


def _descrever_saida(codigo: int | None) -> str:
    if codigo is None:
        return "sem código de saída"
    if codigo < 0:
        try:
            return signal.Signals(-codigo).name
        except ValueError:
            return f"sinal {-codigo}"
    return f"código {codigo}"


_TAMANHO_CHAVE = 32
_TIMEOUT_INICIO_S = 60.0


class MotorProcesso:
    """Motor OpenDSS num subprocesso dedicado: uma chamada por vez, filho recriado se morrer.

    O filho é ``python -c "from bdgd_light.twin.powerflow import _main_motor; …"`` ligado ao pai por
    um socket local autenticado (``multiprocessing.connection``, chave aleatória passada por stdin).
    ``timeout_s`` (``BDGD_MOTOR_TIMEOUT``, padrão 600 s) limita a espera por uma resposta;
    estourado, o filho é morto e a chamada levanta ``MotorError``.
    """

    def __init__(self, timeout_s: float | None = None) -> None:
        self._trava = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._conexao: Connection | None = None
        self._pasta: str | None = None
        self.timeout_s = (
            float(os.environ.get("BDGD_MOTOR_TIMEOUT", "600")) if timeout_s is None else timeout_s
        )
        self.inicios = 0
        self.chamadas = 0

    @property
    def ativo(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc is not None else None

    @property
    def reinicios(self) -> int:
        """Quantas vezes o filho precisou ser recriado depois de morrer."""
        return max(self.inicios - 1, 0)

    def _iniciar(self) -> None:
        self._pasta = tempfile.mkdtemp(prefix="bdgd-motor-")
        endereco = os.path.join(self._pasta, "motor.sock")
        chave = os.urandom(_TAMANHO_CHAVE)
        ouvinte = socket.socket(socket.AF_UNIX)
        try:
            ouvinte.bind(endereco)
            ouvinte.listen(1)
            ouvinte.settimeout(1.0)
            proc = subprocess.Popen(  # noqa: S603 — executável e código fixos
                [
                    sys.executable,
                    "-c",
                    "from bdgd_light.twin.powerflow import _main_motor; _main_motor()",
                    endereco,
                ],
                stdin=subprocess.PIPE,
            )
            self._proc = proc
            assert proc.stdin is not None
            proc.stdin.write(chave)
            proc.stdin.close()
            limite = time.monotonic() + _TIMEOUT_INICIO_S
            while True:
                try:
                    ligacao, _ = ouvinte.accept()
                    break
                except TimeoutError:
                    if proc.poll() is not None:
                        raise MotorError(
                            "o motor OpenDSS (subprocesso) morreu ao iniciar "
                            f"({_descrever_saida(proc.returncode)})"
                        ) from None
                    if time.monotonic() > limite:
                        proc.kill()
                        raise MotorError(
                            f"o motor OpenDSS (subprocesso) não se ligou em {_TIMEOUT_INICIO_S:g} s"
                        ) from None
        except BaseException:
            self._encerrar()
            raise
        finally:
            ouvinte.close()
        ligacao.setblocking(True)
        conexao = Connection(ligacao.detach())
        deliver_challenge(conexao, chave)
        answer_challenge(conexao, chave)
        self._conexao = conexao
        self.inicios += 1
        _registrar_encerramento()

    def _encerrar(self) -> None:
        if self._conexao is not None:
            self._conexao.close()
        if self._proc is not None:
            if self._proc.poll() is None:
                self._proc.kill()
            try:
                self._proc.wait(5)
            except subprocess.TimeoutExpired:  # pragma: no cover
                pass
        if self._pasta is not None:
            shutil.rmtree(self._pasta, ignore_errors=True)
        self._proc = self._conexao = self._pasta = None

    def chamar(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        """Executa ``fn(*args, **kwargs)`` no subprocesso e devolve o resultado (ou relança a
        exceção). Se o filho morrer no meio, ``MotorError``."""
        with self._trava:
            if not self.ativo:
                self._encerrar()  # primeira chamada ou filho morto entre duas chamadas
                self._iniciar()
            assert self._conexao is not None and self._proc is not None
            self.chamadas += 1
            try:
                self._conexao.send((fn, args, kwargs))
                if not self._conexao.poll(self.timeout_s):
                    raise TimeoutError(f"sem resposta em {self.timeout_s:g} s")
                ok, carga = self._conexao.recv()
            except (EOFError, OSError, TimeoutError) as exc:
                try:
                    self._proc.wait(1)  # dá tempo de o código de saída ficar disponível
                except subprocess.TimeoutExpired:
                    pass
                saida = _descrever_saida(self._proc.returncode)
                self._encerrar()
                nome = getattr(fn, "__qualname__", repr(fn))
                detalhe = f"{saida}; {exc}" if str(exc) else saida
                raise MotorError(
                    f"o motor OpenDSS (subprocesso) morreu durante {nome} ({detalhe}); "
                    "será recriado na próxima chamada"
                ) from exc
        if ok:
            return carga
        raise carga

    def fechar(self) -> None:
        """Encerra o subprocesso de forma ordeira (sem efeito se não estiver ativo)."""
        with self._trava:
            if self._conexao is not None and self.ativo:
                try:
                    self._conexao.send(None)
                    self._proc.wait(5)  # type: ignore[union-attr]
                except (OSError, subprocess.TimeoutExpired):
                    pass
            self._encerrar()


_encerramento_registrado = False


def _registrar_encerramento() -> None:
    """Na saída do processo pai, mata o filho do motor global (o filho também sai sozinho quando a
    conexão cai, mas assim não fica órfão nem por instantes)."""
    global _encerramento_registrado
    if not _encerramento_registrado:
        _encerramento_registrado = True
        atexit.register(_encerrar_motor_global)


def _encerrar_motor_global() -> None:
    m = _MOTOR_PROCESSO
    if m is not None and m.ativo:
        m._encerrar()


def _motor_processo() -> MotorProcesso:
    global _MOTOR_PROCESSO
    with _TRAVA:
        if _MOTOR_PROCESSO is None:
            _MOTOR_PROCESSO = MotorProcesso()
        return _MOTOR_PROCESSO


def _motor_thread() -> ThreadPoolExecutor:
    global _MOTOR_THREAD
    with _TRAVA:
        if _MOTOR_THREAD is None:
            _MOTOR_THREAD = ThreadPoolExecutor(max_workers=1, thread_name_prefix=_PREFIXO_MOTOR)
        return _MOTOR_THREAD


def no_motor(fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """Executa ``fn`` no motor OpenDSS: no subprocesso (``BDGD_MOTOR=processo``, padrão) ou na
    thread única do motor (``BDGD_MOTOR=thread``); direto, se já estivermos dentro dele.

    ``fn`` e os argumentos precisam ser serializáveis (pickle) no modo processo — funções de módulo
    com caminhos, listas e escalares, como ``_run_powerflow``.
    """
    global _motor_usado
    if _sou_motor or threading.current_thread().name.startswith(_PREFIXO_MOTOR):
        return fn(*args, **kwargs)
    if modo_motor() == "thread":
        _motor_usado = True
        return _motor_thread().submit(fn, *args, **kwargs).result()
    return _motor_processo().chamar(fn, *args, **kwargs)


def motor_usado() -> bool:
    """``True`` se a biblioteca DSS C-API foi carregada **neste** processo (modo ``thread``)."""
    return _motor_usado


def estado_motor() -> dict[str, Any]:
    """Modo, pid, número de chamadas e reinícios do motor — diagnóstico (``/api/estado``)."""
    modo = modo_motor()
    if modo == "thread":
        return {"modo": modo, "carregado": _motor_usado}
    m = _MOTOR_PROCESSO
    return {
        "modo": modo,
        "ativo": bool(m and m.ativo),
        "pid": m.pid if m else None,
        "chamadas": m.chamadas if m else 0,
        "reinicios": m.reinicios if m else 0,
    }


def simular_falha_do_motor(sinal: int = signal.SIGSEGV) -> None:
    """Mata o subprocesso do motor no meio de uma chamada (para testar a resiliência do console):
    levanta ``MotorError``; a chamada seguinte recria o motor. Só no modo ``processo``."""
    if modo_motor() != "processo":
        raise RuntimeError("simular_falha_do_motor só existe no modo BDGD_MOTOR=processo")
    no_motor(_abortar, int(sinal))
    raise MotorError("o motor sobreviveu ao sinal")  # pragma: no cover


def encerrar_processo(codigo: int = 0) -> None:
    """Termina o processo sem a finalização da biblioteca DSS C-API quando ela foi carregada aqui
    (modo ``thread``); no modo ``processo`` (padrão) é um ``sys.exit`` normal.

    No Linux (glibc 2.39, CI) a finalização da biblioteca Free Pascal roda na thread principal
    depois que a thread do motor — dona do heap e dos threadvars dela — já saiu, e o processo morre
    com SIGSEGV *depois* de todo o trabalho feito (``pytest`` verde, código 139). Aqui esvaziamos
    stdout/stderr, rodamos os ``atexit`` e saímos com ``os._exit``.
    """
    if not _motor_usado:
        sys.exit(codigo)
    import atexit

    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.flush()
        except Exception:  # noqa: BLE001 - saída já pode estar fechada
            pass
    atexit._run_exitfuncs()
    os._exit(codigo)


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


def _rotular_ajustes(
    aplicados: list[str], iteracoes: int, limite_original: int, convergiu: bool
) -> list[str]:
    """Estabilizadores que de fato foram necessários.

    A cascata é cumulativa, mas ``maxiterations=100`` só altera o resultado se o ``Solve`` final
    precisou de mais iterações que o limite original: se convergiu em ``iteracoes`` ≤ limite, o
    limite maior não foi usado (ele apenas trunca a iteração) e o rótulo sai da lista — em
    Tijuca, ``["vminpu=0.9"]`` (6 iterações), não ``["maxiterations=100", "vminpu=0.9"]``.
    """
    if not convergiu or len(aplicados) <= 1 or _ROTULO_ITERACOES not in aplicados:
        return list(aplicados)
    if iteracoes <= limite_original:
        return [r for r in aplicados if r != _ROTULO_ITERACOES]
    return list(aplicados)


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
        # corrente de fase máxima no terminal 1 da Vsource = corrente no disjuntor do alimentador
        mags = dss.CktElement.CurrentsMagAng()[0::2][: int(dss.CktElement.NumPhases())]
        linhas.append(
            (
                dss.Vsources.Name(),
                dss.CktElement.BusNames()[0].split(".")[0],
                -float(p[0]),
                -float(p[1]),
                max((float(m) for m in mags), default=float("nan")),
            )
        )
        i = dss.Vsources.Next()
    return pd.DataFrame(linhas, columns=["fonte", "barra", "kw", "kvar", "i_a"])


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
    ``PowerFlowResult.ajustes``. Roda sempre na thread do motor (``no_motor``).
    """
    return no_motor(
        _run_powerflow,
        master,
        vmin=vmin,
        vmax=vmax,
        modo=modo,
        estabilizar=estabilizar,
        comandos_extra=comandos_extra,
    )


def _run_powerflow(
    master: str | Path,
    *,
    vmin: float,
    vmax: float,
    modo: str | None,
    estabilizar: bool,
    comandos_extra: list[str] | tuple[str, ...],
) -> PowerFlowResult:
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
    limite_iteracoes = int(dss.Solution.MaxIterations())
    dss.Solution.Solve()
    if not dss.Solution.Converged() and estabilizar:
        for rotulo, comandos in ESTABILIZADORES:
            for cmd in comandos:
                _comando(dss, cmd)
            ajustes.append(rotulo)
            dss.Solution.Solve()
            if dss.Solution.Converged():
                break
        ajustes = _rotular_ajustes(
            ajustes, int(dss.Solution.Iterations()), limite_iteracoes, dss.Solution.Converged()
        )

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
