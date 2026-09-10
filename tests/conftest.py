"""Fixtures compartilhadas: BDGD sintética em ``tests/fixtures/bdgd_mini.gpkg``."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

DIR_FIXTURES = Path(__file__).parent / "fixtures"
GPKG_MINI = DIR_FIXTURES / "bdgd_mini.gpkg"


def carregar_gerador() -> ModuleType:
    """Importa ``tests/fixtures/gerar_fixture.py`` pelo caminho (o diretório não é pacote)."""
    spec = importlib.util.spec_from_file_location(
        "gerar_fixture", DIR_FIXTURES / "gerar_fixture.py"
    )
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def pytest_collection_finish(session: pytest.Session) -> None:
    """O DSS C-API só aceita chamadas da thread que o importou (SIGILL nas demais); o gêmeo o
    importa na thread própria (``twin.powerflow.no_motor``). Importar ``opendssdirect`` na coleta
    (thread principal) quebraria toda a suíte — use ``importlib.util.find_spec`` para pular."""
    if "opendssdirect" in sys.modules:
        raise pytest.UsageError(
            "opendssdirect importado na thread principal durante a coleta; "
            "troque pytest.importorskip por importlib.util.find_spec (ver tests/conftest.py)."
        )


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    session.config._bdgd_exitstatus = int(exitstatus)  # type: ignore[attr-defined]


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config: pytest.Config) -> None:
    """Se a suíte usou o gêmeo, sai com ``os._exit`` (depois dos ``atexit``): a finalização da
    biblioteca DSS C-API na thread principal derruba o processo com SIGSEGV no Linux mesmo com a
    suíte verde (``twin.powerflow.encerrar_processo``)."""
    if "bdgd_light.twin.powerflow" not in sys.modules:
        return
    from bdgd_light.twin.powerflow import encerrar_processo, motor_usado

    if motor_usado():
        encerrar_processo(getattr(config, "_bdgd_exitstatus", 0))


@pytest.fixture(scope="session")
def gerador() -> ModuleType:
    return carregar_gerador()


@pytest.fixture(scope="session")
def bdgd_mini(gerador: ModuleType) -> Path:
    """Caminho do GeoPackage sintético (regenerado se não estiver no disco)."""
    if not GPKG_MINI.exists():
        gerador.gerar(GPKG_MINI)
    return GPKG_MINI


@pytest.fixture(scope="session")
def bairro_mini(bdgd_mini: Path) -> Path:
    """GeoJSON (EPSG:4326) que cobre RJO001 e RJO002 mas não RJO003."""
    caminho = DIR_FIXTURES / "bairro_sintetico.geojson"
    assert caminho.exists()
    return caminho


@pytest.fixture(scope="session")
def parquet_mini(bdgd_mini: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Todas as camadas da fixture exportadas para Parquet (entrada de inventario/recortar)."""
    from rich.console import Console

    from bdgd_light.ingest.export import exportar, listar_camadas

    destino = tmp_path_factory.mktemp("parquet_mini")
    exportar(bdgd_mini, list(listar_camadas(bdgd_mini)), destino, console=Console(quiet=True))
    return destino
