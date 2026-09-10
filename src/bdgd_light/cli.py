"""Interface de linha de comando ``bdgd-light``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pyogrio.errors import DataSourceError
from rich.console import Console
from rich.table import Table

from bdgd_light import __version__
from bdgd_light.ingest.export import TAMANHO_LOTE_PADRAO, CamadaInexistenteError, exportar
from bdgd_light.ingest.interligacoes import (
    RAIO_PADRAO_M,
    contar_por_ctmt,
    detectar_interligacoes,
    vizinhos_de,
)
from bdgd_light.ingest.inventario import carregar_bairro, gravar_csv, inventariar, tabela_top
from bdgd_light.ingest.parquet import CamadaAusenteError, DiretorioParquet
from bdgd_light.ingest.recorte import CtmtInexistenteError, recortar

app = typer.Typer(
    help="Ferramentas do COD agêntico sobre a BDGD da Light (ANEEL).",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


def _versao(mostrar: bool) -> None:
    if mostrar:
        console.print(f"bdgd-light {__version__}")
        raise typer.Exit()


@app.callback()
def principal(
    versao: Annotated[
        bool,
        typer.Option("--version", callback=_versao, is_eager=True, help="Mostra a versão e sai."),
    ] = False,
) -> None:
    """Ferramentas do COD agêntico sobre a BDGD da Light (ANEEL)."""


@app.command()
def export(
    gdb: Annotated[Path, typer.Option("--gdb", help="Caminho da BDGD (.gdb) ou de um GeoPackage.")],
    layers: Annotated[
        str | None,
        typer.Option(
            "--layers",
            help="Camadas separadas por vírgula (ex.: CTMT,SSDMT,UNSEMT). "
            "Padrão: todas as CAMADAS_CHAVE do catálogo que existirem na base.",
        ),
    ] = None,
    out: Annotated[
        Path, typer.Option("--out", help="Diretório de saída (um .parquet por camada).")
    ] = Path("data/parquet"),
    gpkg: Annotated[
        Path | None,
        typer.Option(
            "--gpkg", help="Também grava todas as camadas exportadas num GeoPackage único."
        ),
    ] = None,
    batch_size: Annotated[
        int, typer.Option("--batch-size", min=1, help="Feições lidas/gravadas por lote.")
    ] = TAMANHO_LOTE_PADRAO,
) -> None:
    """Exporta camadas da BDGD para GeoParquet (geográficas) e Parquet (tabelas).

    O CRS original (SIRGAS 2000, EPSG:4674) é preservado.

    Camadas grandes são processadas em lotes para não estourar a memória.
    """
    camadas = [c for c in layers.split(",") if c.strip()] if layers else None
    try:
        exportar(gdb, camadas, out, gpkg=gpkg, batch_size=batch_size, console=console)
    except (CamadaInexistenteError, FileNotFoundError) as erro:
        console.print(f"[bold red]Erro:[/] {erro}")
        raise typer.Exit(code=1) from None
    except DataSourceError as erro:
        console.print(f"[bold red]Erro:[/] não foi possível abrir a base [bold]{gdb}[/]: {erro}")
        raise typer.Exit(code=1) from None


OpcaoParquet = Annotated[
    Path,
    typer.Option("--parquet", help="Diretório com as camadas exportadas por `bdgd-light export`."),
]
OpcaoRaioTie = Annotated[
    float,
    typer.Option(
        "--raio-tie",
        min=0.0,
        help="Raio (m) entre chave NA e extremidade de SSDMT de outro CTMT para ser interligação.",
    ),
]


def _erro(mensagem: str) -> None:
    console.print(f"[bold red]Erro:[/] {mensagem}")
    raise typer.Exit(code=1)


@app.command()
def inventario(
    parquet: OpcaoParquet = Path("data/parquet"),
    out: Annotated[
        Path | None, typer.Option("--out", help="CSV de saída (uma linha por CTMT).")
    ] = Path("data/inventario_ctmt.csv"),
    top: Annotated[
        int,
        typer.Option(
            "--top",
            min=0,
            help="Quantos CTMT mostrar na tabela do terminal, por score (0 = nenhum).",
        ),
    ] = 20,
    bairro: Annotated[
        Path | None,
        typer.Option(
            "--bairro",
            help="Polígono (GeoJSON/GPKG) que restringe aos CTMT com rede MT que o intersecta.",
        ),
    ] = None,
    raio_tie: OpcaoRaioTie = RAIO_PADRAO_M,
) -> None:
    """Inventário de alimentadores (CTMT): extensão, carga, clientes, chaves NA/NF, interligações,
    DER e bbox — para escolher o escopo de um cenário FLISR.

    Score = chaves NA de interligação de campo (fora da SE) × (UCBT + UCMT). Colunas explicadas
    no README.
    """
    try:
        poligono = carregar_bairro(bairro) if bairro else None
        resultado = inventariar(parquet, raio_tie_m=raio_tie, bairro=poligono, console=console)
    except (FileNotFoundError, ValueError) as erro:  # inclui CamadaAusenteError
        _erro(str(erro))
        return
    except DataSourceError as erro:
        _erro(f"não foi possível ler o polígono de bairro [bold]{bairro}[/]: {erro}")
        return
    if out is not None:
        gravar_csv(resultado.tabela, out)
        console.print(
            f"[green]✔[/] {_fmt_int(len(resultado.tabela))} CTMT inventariados em "
            f"{resultado.segundos:.1f} s → [bold]{out}[/]"
        )
    if top:
        console.print(tabela_top(resultado.tabela, top))


@app.command()
def vizinhos(
    ctmt: Annotated[str, typer.Option("--ctmt", help="COD_ID do alimentador.")],
    parquet: OpcaoParquet = Path("data/parquet"),
    raio_tie: OpcaoRaioTie = RAIO_PADRAO_M,
    sem_se: Annotated[
        bool,
        typer.Option(
            "--sem-se/--com-se",
            help="Ignora nas contagens as chaves dentro do polígono da SE (disjuntores de saída, "
            "não transferem carga); elas aparecem só na coluna 'Na SE'. --com-se conta tudo.",
        ),
    ] = True,
) -> None:
    """Lista os CTMT interligados a um alimentador e quantas chaves NA de interligação (ties) de
    campo há com cada um — telecomandadas ou manuais; as de dentro da SE ficam à parte."""
    try:
        fonte = DiretorioParquet(parquet)
        ctmts = set(fonte.ler("CTMT", ["COD_ID"])["COD_ID"])
        if ctmt not in ctmts:
            raise CtmtInexistenteError([ctmt])
        interligacoes = detectar_interligacoes(
            fonte.ler("UNSEMT"),
            fonte.ler("SSDMT", ["COD_ID", "CTMT", "PAC_1", "PAC_2", "geometry"]),
            raio_m=raio_tie,
            sub=fonte.ler_se_existir("SUB"),
        )
    except (FileNotFoundError, CamadaAusenteError, CtmtInexistenteError) as erro:
        _erro(str(erro))
        return
    tabela = vizinhos_de(interligacoes, ctmt, sem_se=sem_se)
    if tabela.empty:
        console.print(f"{ctmt}: nenhuma interligação detectada (raio {raio_tie:g} m).")
        return
    colunas = [
        ("CTMT_VIZ", "CTMT vizinho", "left"),
        ("ties", "Ties", "right"),
        ("ties_telecomandadas", "Telecomandadas", "right"),
        ("ties_manuais", "Manuais", "right"),
        ("ties_em_SE", "Na SE", "right"),
        ("ties_proprias", f"Chaves de {ctmt}", "right"),
        ("ties_do_vizinho", "Chaves do vizinho", "right"),
        ("chaves", "COD_ID das chaves", "left"),
    ]
    # o mesmo COD_ID pode tocar vários vizinhos (barramento de SE): o título conta chaves
    # distintas, como o inventário; a tabela conta pares chave × vizinho
    totais = contar_por_ctmt(interligacoes).loc[ctmt]
    if sem_se:
        titulo = (
            f"Vizinhos de {ctmt}: {len(tabela)} CTMT, "
            f"{int(totais['NA_interligacao_campo'])} chaves NA de interligação de campo "
            f"({int(totais['NA_interligacao_campo_telecomandada'])} telecomandadas), "
            f"{int(tabela['ties'].sum())} pares chave×vizinho; "
            f"{int(totais['NA_interligacao_SE'])} chaves na SE descontadas"
        )
    else:
        titulo = (
            f"Vizinhos de {ctmt}: {len(tabela)} CTMT, "
            f"{int(totais['NA_interligacao'])} chaves NA de interligação "
            f"({int(totais['NA_interligacao_telecomandada'])} telecomandadas, "
            f"{int(totais['NA_interligacao_SE'])} na SE), "
            f"{int(tabela['ties'].sum())} pares chave×vizinho"
        )
    rich_tabela = Table(title=titulo)
    for _, rotulo, alinhamento in colunas:
        rich_tabela.add_column(rotulo, justify=alinhamento, overflow="fold")
    for _, linha in tabela.iterrows():
        rich_tabela.add_row(*(str(linha[c]) for c, _, _ in colunas))
    console.print(rich_tabela)


@app.command("recortar")
def recortar_cmd(
    ctmt: Annotated[
        str, typer.Option("--ctmt", help="COD_ID dos alimentadores, separados por vírgula.")
    ],
    parquet: OpcaoParquet = Path("data/parquet"),
    out: Annotated[
        Path,
        typer.Option(
            "--out",
            help="Diretório de saída (<CTMT>.gpkg + <CTMT>.meta.json por alimentador e, com "
            "vários, o GPKG do cluster). Com um só CTMT pode ser o caminho do .gpkg.",
        ),
    ] = Path("data/feeders"),
    nome_cluster: Annotated[
        str | None,
        typer.Option("--nome-cluster", help="Nome do GPKG do cluster (padrão: cluster_<A>-<B>…)."),
    ] = None,
    raio_tie: OpcaoRaioTie = RAIO_PADRAO_M,
) -> None:
    """Recorta todas as camadas por alimentador (CTMT) para GeoPackage(s) + meta.json.

    Regras de junção entre camadas em docs/bdgd-relacoes.md.
    """
    ctmts = [c.strip() for c in ctmt.split(",") if c.strip()]
    if not ctmts:
        _erro("informe ao menos um CTMT em --ctmt")
        return
    out_dir, nome_gpkg = out, None
    if out.suffix.lower() == ".gpkg":
        if len(ctmts) > 1:
            _erro("com vários CTMT, --out deve ser um diretório")
            return
        out_dir, nome_gpkg = out.parent, out
    try:
        resultado = recortar(
            parquet,
            ctmts,
            out_dir,
            nome_cluster_=nome_cluster,
            raio_tie_m=raio_tie,
            console=console,
        )
    except (FileNotFoundError, ValueError) as erro:  # CamadaAusenteError, CtmtInexistenteError
        _erro(str(erro))
        return
    if nome_gpkg is not None:
        recorte = resultado.recortes[0]
        assert recorte.gpkg is not None and recorte.meta is not None
        recorte.gpkg.replace(nome_gpkg)
        recorte.meta.replace(nome_gpkg.with_suffix(".meta.json"))
        console.print(f"[green]✔[/] recorte gravado em [bold]{nome_gpkg}[/]")


def _fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


if __name__ == "__main__":
    app()
