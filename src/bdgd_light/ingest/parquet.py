"""Leitura das camadas exportadas por ``bdgd-light export`` (um ``<CAMADA>.parquet`` por camada).

Camadas geográficas são GeoParquet e voltam como ``GeoDataFrame``; tabelas (CTMT, UCBT_tab…)
voltam como ``DataFrame``. Filtros são empurrados para o pyarrow, de modo que tabelas enormes
(UCBT_tab tem 5 M de linhas na Light 2025) nunca são carregadas inteiras quando se quer um
subconjunto de CTMT/transformadores.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

Filtro = tuple[str, str, object]


class CamadaAusenteError(FileNotFoundError):
    """Uma camada indispensável não foi exportada para o diretório Parquet."""

    def __init__(self, camada: str, diretorio: Path):
        self.camada = camada
        self.diretorio = diretorio
        super().__init__(
            f"camada {camada} não encontrada em {diretorio} "
            f"(exporte-a com `bdgd-light export --layers {camada}`)"
        )


@dataclass(frozen=True)
class DiretorioParquet:
    """Diretório com as camadas exportadas."""

    caminho: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "caminho", Path(self.caminho))
        if not self.caminho.is_dir():
            raise FileNotFoundError(f"diretório de Parquet não encontrado: {self.caminho}")

    def arquivo(self, camada: str) -> Path:
        return self.caminho / f"{camada}.parquet"

    def tem(self, camada: str) -> bool:
        return self.arquivo(camada).is_file()

    def camadas(self) -> list[str]:
        return sorted(p.stem for p in self.caminho.glob("*.parquet"))

    def eh_geografica(self, camada: str) -> bool:
        meta = pq.read_metadata(self.arquivo(camada)).metadata or {}
        return b"geo" in meta

    def colunas(self, camada: str) -> list[str]:
        return pq.read_schema(self.arquivo(camada)).names

    def ler(
        self,
        camada: str,
        colunas: Iterable[str] | None = None,
        filtros: list[Filtro] | None = None,
    ) -> gpd.GeoDataFrame | pd.DataFrame:
        """Lê a camada (GeoDataFrame se for GeoParquet), com colunas e filtros opcionais.

        Colunas pedidas que não existem no arquivo são ignoradas; a coluna ``geometry`` é sempre
        incluída em camadas geográficas.
        """
        arquivo = self.arquivo(camada)
        if not arquivo.is_file():
            raise CamadaAusenteError(camada, self.caminho)
        geografica = self.eh_geografica(camada)
        schema = pq.read_schema(arquivo)
        cols = None
        if colunas is not None:
            existentes = set(schema.names)
            cols = [c for c in dict.fromkeys(colunas) if c in existentes]
            if geografica and "geometry" not in cols:
                cols.append("geometry")
        filtros = _tipar_filtros_vazios(filtros, schema)
        if geografica:
            return gpd.read_parquet(arquivo, columns=cols, filters=filtros or None)
        return pd.read_parquet(arquivo, columns=cols, filters=filtros or None)

    def ler_se_existir(
        self,
        camada: str,
        colunas: Iterable[str] | None = None,
        filtros: list[Filtro] | None = None,
    ) -> gpd.GeoDataFrame | pd.DataFrame | None:
        if not self.tem(camada):
            return None
        return self.ler(camada, colunas, filtros)

    def iterar_lotes(
        self, camada: str, colunas: Iterable[str] | None = None, tamanho: int = 500_000
    ) -> Iterator[pd.DataFrame]:
        """Percorre uma tabela grande em lotes (para agregações sem carregar tudo)."""
        arquivo = self.arquivo(camada)
        if not arquivo.is_file():
            raise CamadaAusenteError(camada, self.caminho)
        existentes = set(self.colunas(camada))
        cols = [c for c in dict.fromkeys(colunas) if c in existentes] if colunas else None
        with pq.ParquetFile(arquivo) as pf:
            for lote in pf.iter_batches(batch_size=tamanho, columns=cols):
                yield lote.to_pandas()


def filtro_in(coluna: str, valores: Iterable[object]) -> list[Filtro]:
    """Filtro pyarrow ``coluna IN valores`` (lista vazia filtra tudo)."""
    return [(coluna, "in", list(dict.fromkeys(valores)))]


def _tipar_filtros_vazios(filtros: list[Filtro] | None, schema: pa.Schema) -> list[Filtro] | None:
    """Dá o tipo da coluna a conjuntos ``in`` vazios.

    O pyarrow inferiria ``null`` e falharia com "Array type doesn't match type of values set"
    (ex.: recorte de CTMT sem UNREMT filtrando EQRE por ``UN_RE``).
    """
    if not filtros:
        return filtros
    tipados: list[Filtro] = []
    for coluna, operador, valores in filtros:
        if operador == "in" and coluna in schema.names and not isinstance(valores, pa.Array):
            valores = list(valores)
            if not valores:
                valores = pa.array([], type=schema.field(coluna).type)
        tipados.append((coluna, operador, valores))
    return tipados
