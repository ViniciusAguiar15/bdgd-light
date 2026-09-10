"""Interface de linha de comando ``bdgd-light``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pyogrio.errors import DataSourceError
from rich.console import Console
from rich.table import Table

from bdgd_light import __version__
from bdgd_light.grid import (
    ChaveInexistenteError,
    Clientes,
    Cluster,
    Feeder,
    Rede,
    TrechoInexistenteError,
    estado_geojson,
    ler_camadas,
)
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


@app.command()
def grafo(
    gpkg: Annotated[
        Path,
        typer.Option(
            "--gpkg",
            help="GeoPackage do `bdgd-light recortar`: <CTMT>.gpkg (um alimentador) ou "
            "cluster_<A>-<B>….gpkg (vários, com as ties ligadas pelos PAC reais).",
        ),
    ],
    falha: Annotated[
        str | None,
        typer.Option(
            "--falha",
            help="COD_ID de um trecho SSDMT em falta: mostra as chaves a abrir para isolá-lo e as "
            "chaves NA que restauram os nós sãos desligados.",
        ),
    ] = None,
    abrir: Annotated[
        str | None,
        typer.Option("--abrir", help="COD_ID de chaves UNSEMT a abrir antes da análise (vírgula)."),
    ] = None,
    fechar: Annotated[
        str | None,
        typer.Option("--fechar", help="COD_ID de chaves a fechar antes da análise, por vírgula."),
    ] = None,
    geojson: Annotated[
        Path | None,
        typer.Option(
            "--geojson",
            help="Grava o estado da rede (energizado/fonte por trecho, chaves, trafos) em GeoJSON "
            "EPSG:4326. Com --falha, o estado é o de depois da manobra de isolamento.",
        ),
    ] = None,
    ties_na_se: Annotated[
        bool,
        typer.Option(
            "--ties-na-se/--sem-ties-na-se",
            help="Inclui como ties as chaves NA dentro do polígono da SE (padrão: ignora).",
        ),
    ] = False,
) -> None:
    """Monta o grafo MT do alimentador (nós = PAC; arestas = trechos SSDMT e chaves UNSEMT),
    energiza a partir do disjuntor da SE e simula falta, isolamento e restauração via ties."""
    try:
        camadas = ler_camadas(gpkg)
        rede: Rede = (
            Feeder(camadas, ties_na_se=ties_na_se)
            if len(camadas.ctmt) == 1
            else Cluster(camadas, ties_na_se=ties_na_se)
        )
        for cod in _lista(abrir):
            rede.open_switch(cod)
        for cod in _lista(fechar):
            rede.close_switch(cod)
    except (FileNotFoundError, DataSourceError, ValueError, ChaveInexistenteError) as erro:
        _erro(str(erro))
        return
    _imprimir_resumo(rede)
    for aviso in rede.avisos:
        console.print(f"[yellow]![/] {aviso}")
    _imprimir_ties(rede)
    if falha is not None:
        try:
            isolamento = rede.isolate_segment(falha)
            opcoes = rede.restore_options(falha)
        except TrechoInexistenteError as erro:
            _erro(str(erro))
            return
        console.print(
            f"\n[bold]Falta em {falha}[/] → abrir {', '.join(isolamento.chaves) or 'nenhuma chave'}"
        )
        console.print(
            f"  zona isolada: {len(isolamento.zona)} nós, {_fmt_clientes(isolamento.clientes_zona)}"
        )
        console.print(
            f"  desligados restauráveis: {len(isolamento.desligados)} nós, "
            f"{_fmt_clientes(isolamento.clientes_desligados)}"
        )
        if opcoes:
            tabela = Table(title=f"Opções de restauração ({len(opcoes)})")
            for rotulo, alinhamento in [
                ("Fechar", "left"),
                ("Chave de", "left"),
                ("Fonte", "left"),
                ("TLCD", "center"),
                ("Nós", "right"),
                ("UCBT", "right"),
                ("UCMT", "right"),
                ("kVA", "right"),
                ("UC na fonte", "right"),
            ]:
                tabela.add_column(rotulo, justify=alinhamento, overflow="fold")
            for o in opcoes:
                tabela.add_row(
                    o.chave + (" (externa)" if o.externa else ""),
                    o.ctmt_chave,
                    o.fonte,
                    "sim" if o.tlcd else "não",
                    _fmt_int(len(o.nos)),
                    _fmt_int(o.clientes.ucbt),
                    _fmt_int(o.clientes.ucmt),
                    _fmt_int(int(o.clientes.kva)),
                    _fmt_int(o.clientes_fonte.total) if o.fonte in rede.ctmts else "?",
                )
            console.print(tabela)
        elif isolamento.desligados:
            console.print("  [red]nenhuma chave NA restaura os nós desligados[/]")
        rede.isolate_segment(falha, aplicar=True)
    if geojson is not None:
        estado_geojson(rede, geojson)
        console.print(f"[green]✔[/] estado gravado em [bold]{geojson}[/]")


def _lista(valor: str | None) -> list[str]:
    return [c.strip() for c in (valor or "").split(",") if c.strip()]


def _fmt_clientes(c: Clientes) -> str:
    return (
        f"{_fmt_int(c.ucbt)} UCBT, {_fmt_int(c.ucmt)} UCMT, {_fmt_int(c.trafos)} trafos "
        f"({_fmt_int(int(c.kva))} kVA)"
    )


def _imprimir_resumo(rede: Rede) -> None:
    r = rede.resumo()
    tabela = Table(title=f"Grafo de {', '.join(r['ctmt'])}", show_header=False)
    tabela.add_column("campo", style="bold")
    tabela.add_column("valor")
    linhas = [
        ("Fonte(s)", ", ".join(f"{c}: {n}" for c, n in r["fontes"].items()) or "nenhuma"),
        ("Nós (PAC MT)", _fmt_int(r["nos"])),
        ("Trechos SSDMT", f"{_fmt_int(r['trechos'])} ({r['km']:.3f} km)"),
        ("Chaves UNSEMT", f"{r['chaves']} ({r['chaves_NF']} NF, {r['chaves_NA']} NA)"),
        ("Ties", f"{r['ties']} ({r['ties_externas']} de chaves de outros CTMT)"),
        ("CTMT externos", ", ".join(r["externos"]) or "nenhum"),
        ("Transformadores", _fmt_int(r["trafos"])),
        ("Clientes", _fmt_clientes(r["clientes"])),
        ("Nós energizados", f"{_fmt_int(r['energizados'])} de {_fmt_int(r['nos'])}"),
    ]
    for campo, valor in linhas:
        tabela.add_row(campo, valor)
    console.print(tabela)


def _imprimir_ties(rede: Rede) -> None:
    ties = rede.tie_switches()
    if ties.empty:
        console.print("Nenhuma tie (chave NA de interligação) no grafo.")
        return
    tabela = Table(title=f"Ties ({len(ties)})")
    for rotulo, alinhamento in [
        ("Chave", "left"),
        ("CTMT", "left"),
        ("Vizinho", "left"),
        ("PAC", "left"),
        ("TLCD", "center"),
        ("Estado", "center"),
        ("Dist. m", "right"),
    ]:
        tabela.add_column(rotulo, justify=alinhamento, overflow="fold")
    for t in ties.itertuples(index=False):
        tabela.add_row(
            t.chave + (" (externa)" if t.externa else ""),
            t.ctmt,
            t.ctmt_viz,
            t.pac,
            "sim" if t.tlcd else "não",
            "aberta" if t.aberta else "fechada",
            f"{t.dist_m:.1f}",
        )
    console.print(tabela)


def _fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


if __name__ == "__main__":
    app()
