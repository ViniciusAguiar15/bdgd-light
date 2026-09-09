"""Fixtures compartilhadas: BDGD sintética em ``tests/fixtures/bdgd_mini.gpkg``."""

from __future__ import annotations

import importlib.util
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
