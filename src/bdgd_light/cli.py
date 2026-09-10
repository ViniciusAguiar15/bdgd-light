"""Interface de linha de comando ``bdgd-light``."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

import typer
from pyogrio.errors import DataSourceError
from rich.console import Console
from rich.table import Table

from bdgd_light import __version__
from bdgd_light.grid import (
    ABRIR,
    FECHAR,
    ChaveInexistenteError,
    Clientes,
    Cluster,
    Feeder,
    Rede,
    TrechoInexistenteError,
    estado_geojson,
    ler_camadas,
    manobra,
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
from bdgd_light.ingest.tiles import (
    ZOOM_MAX_PADRAO,
    ZOOM_MIN_PADRAO,
    TippecanoeAusenteError,
    TippecanoeError,
    gerar_tiles,
)

AUDIT_PADRAO = Path("data/audit/llm.jsonl")
CHAVES_RESUMO_AUDIT = ("rodada", "rodadas", "modelo", "resposta", "erro")

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
    score: Annotated[
        bool,
        typer.Option(
            "--score/--sem-score",
            help="Com --falha: roda o fluxo de potência de cada opção no gêmeo OpenDSS "
            "(twin.score_eletrico) e acrescenta as colunas elétricas MT à tabela, ordenando por "
            "viável → margem do disjuntor → UCBT. Usa o modelo em --dss-out (converte do GPKG se "
            "faltar).",
        ),
    ] = False,
    dss_out: Annotated[
        Path | None,
        typer.Option(
            "--dss-out",
            help="Raiz dos modelos OpenDSS por CTMT (<out>/<CTMT>/) para --score. Padrão: "
            "data/dss/gpkg.",
        ),
    ] = None,
    dia: Annotated[
        str, typer.Option("--dia", help="Tipo de dia das cargas em --score: DU, SA ou DO.")
    ] = "DU",
    mes: Annotated[
        int, typer.Option("--mes", min=1, max=12, help="Mês das cargas em --score (1–12).")
    ] = 1,
    vmin: Annotated[
        float, typer.Option("--vmin", help="Limite inferior de tensão MT (pu) em --score.")
    ] = 0.93,
    vmax: Annotated[
        float, typer.Option("--vmax", help="Limite superior de tensão MT (pu) em --score.")
    ] = 1.05,
) -> None:
    """Monta o grafo MT do alimentador (nós = PAC; arestas = trechos SSDMT e chaves UNSEMT),
    energiza a partir do disjuntor da SE e simula falta, isolamento e restauração via ties; com
    --score, valida cada opção de restauração no gêmeo OpenDSS."""
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
        scores = None
        if opcoes and score:
            try:
                scores = _score_opcoes(
                    opcoes, rede, gpkg, dss_out, dia=dia, mes=mes, vmin=vmin, vmax=vmax
                )
            except (FileNotFoundError, ValueError, RuntimeError, ImportError) as erro:
                _erro(str(erro))
                return
        if opcoes:
            _imprimir_opcoes(opcoes, rede, scores)
        elif isolamento.desligados:
            console.print("  [red]nenhuma chave NA restaura os nós desligados[/]")
        rede.isolate_segment(falha, aplicar=True)
    if geojson is not None:
        estado_geojson(rede, geojson)
        console.print(f"[green]✔[/] estado gravado em [bold]{geojson}[/]")


@app.command()
def dss(
    ctmt: Annotated[
        str | None,
        typer.Option(
            "--ctmt",
            help="COD_ID do(s) alimentador(es), por vírgula (padrão com --gpkg: todos os CTMT do "
            "GeoPackage). Com mais de um, monta um Master único do cluster (Circuit no primeiro, "
            "Vsource nos demais) para simular transferência de carga.",
        ),
    ] = None,
    gdb: Annotated[
        Path | None,
        typer.Option(
            "--gdb",
            help="Diretório .gdb da BDGD para converter com o bdgd2opendss (lê o GDB inteiro). "
            "Dispensável se o modelo já estiver em --out ou se houver --gpkg (conversão direta "
            "do recorte).",
        ),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option(
            "--out",
            help="Raiz de saída: bdgd2opendss grava em <out>/sub_<SUB>/<CTMT>/ (36 Masters); a "
            "conversão do GPKG grava em <out>/<CTMT>/ (Masters DU/SA/DO do mês pedido). Padrão: "
            "data/dss (bdgd2opendss) ou data/dss/gpkg (conversão do GPKG). Modelo já existente "
            "em <out> não é reconvertido.",
        ),
    ] = None,
    master: Annotated[
        Path | None,
        typer.Option("--master", help="Roda o fluxo direto neste Master .dss, sem converter."),
    ] = None,
    gpkg: Annotated[
        Path | None,
        typer.Option(
            "--gpkg",
            help="GeoPackage do `bdgd-light recortar`: sem --gdb e sem modelo em --out, o Master "
            "é gerado direto dele (bdgd_light.twin.gpkg2dss, sem FileGDB); é também o grafo que "
            "traduz manobras em comandos OpenDSS (--falha, --restaurar, --abrir, --fechar).",
        ),
    ] = None,
    reconverter: Annotated[
        bool,
        typer.Option(
            "--reconverter",
            help="Com --gpkg: regenera o modelo do recorte mesmo se já existir em --out.",
        ),
    ] = False,
    falha: Annotated[
        str | None,
        typer.Option(
            "--falha",
            help="COD_ID de um trecho SSDMT em falta: abre no gêmeo as chaves que o isolam.",
        ),
    ] = None,
    restaurar: Annotated[
        str | None,
        typer.Option(
            "--restaurar",
            help="Chave NA (de `grafo --falha`) a fechar depois do isolamento para transferir os "
            "nós sãos ao alimentador vizinho.",
        ),
    ] = None,
    abrir: Annotated[
        str | None,
        typer.Option("--abrir", help="COD_ID de chaves a abrir antes do Solve (vírgula)."),
    ] = None,
    fechar: Annotated[
        str | None,
        typer.Option("--fechar", help="COD_ID de chaves a fechar antes do Solve (vírgula)."),
    ] = None,
    dia: Annotated[
        str, typer.Option("--dia", help="Tipo de dia do Master a resolver: DU, SA ou DO.")
    ] = "DU",
    mes: Annotated[int, typer.Option("--mes", min=1, max=12, help="Mês do Master (1–12).")] = 1,
    fluxo: Annotated[
        bool, typer.Option("--fluxo/--sem-fluxo", help="Resolve o fluxo de potência snapshot.")
    ] = True,
    vmin: Annotated[float, typer.Option("--vmin", help="Limite inferior de tensão (pu).")] = 0.93,
    vmax: Annotated[float, typer.Option("--vmax", help="Limite superior de tensão (pu).")] = 1.05,
    estabilizar: Annotated[
        bool,
        typer.Option(
            "--estabilizar/--sem-estabilizar",
            help="Se não convergir, aplica em cascata: maxiterations=100, vminpu=0.9 e model=2.",
        ),
    ] = True,
    comando: Annotated[
        list[str] | None,
        typer.Option(
            "--comando",
            help="Comando OpenDSS extra antes do Solve (repetível), ex.: 'set loadmult=0.6'.",
        ),
    ] = None,
    json_saida: Annotated[
        Path | None,
        typer.Option("--json", help="Grava o resumo, piores barras e sobrecargas em JSON."),
    ] = None,
    top: Annotated[int, typer.Option("--top", help="Linhas nas tabelas de piores casos.")] = 10,
) -> None:
    """Converte alimentadores da BDGD para OpenDSS (bdgd2opendss a partir do GDB, ou direto do
    GeoPackage do recorte) e/ou resolve o fluxo de potência com OpenDSSDirect, reportando
    tensões, violações, perdas e sobrecargas. Com vários --ctmt monta o Master do cluster; com
    --gpkg aplica manobras do grafo (falta, isolamento e restauração) antes do Solve."""
    try:
        from bdgd_light.twin import (
            comandos_manobras,
            converter,
            escolher_master,
            listar_ctmts,
            localizar_pasta,
            montar_master_cluster,
            run_powerflow,
        )
    except ImportError as erro:
        _erro(f"{erro} — instale o extra: uv sync --extra twin")
        return
    ctmts = _lista(ctmt)
    modo_gpkg = gpkg is not None and gdb is None and master is None
    if out is None:  # não mistura os modelos do GPKG com as pastas sub_*/ do bdgd2opendss
        out = Path("data/dss/gpkg") if modo_gpkg else Path("data/dss")
    if master is None and not ctmts:
        if not modo_gpkg:
            _erro(
                "informe --ctmt (com --gdb, --gpkg ou modelo já em --out) para converter "
                "ou --master."
            )
            return
        ctmts = listar_ctmts(gpkg)
        console.print(f"CTMT do GeoPackage: [bold]{', '.join(ctmts)}[/]")
    if gpkg is None and any(x is not None for x in (falha, restaurar, abrir, fechar)):
        _erro("--falha, --restaurar, --abrir e --fechar exigem --gpkg com o grafo do recorte.")
        return
    try:
        comandos_dss = _manobras_dss(gpkg, falha, restaurar, abrir, fechar, comandos_manobras)
        if master is None:
            pastas = []
            for cod in ctmts:
                pasta = localizar_pasta(out, cod)
                if modo_gpkg and (reconverter or not _tem_master(pasta, dia, mes)):
                    pasta = _converter_gpkg(gpkg, cod, out, dia, mes)
                elif pasta is not None and gdb is None:
                    console.print(f"[green]✔[/] modelo de {cod} já existia em [bold]{pasta}[/]")
                elif gdb is None:
                    _erro(
                        f"modelo de {cod} não encontrado em {out}; informe --gdb (bdgd2opendss) "
                        "ou --gpkg (conversão do recorte)."
                    )
                    return
                else:
                    console.print(f"Convertendo [bold]{cod}[/] com bdgd2opendss (lê o GDB todo)…")
                    pasta, segundos = converter(gdb, cod, out)
                    if segundos:
                        console.print(f"[green]✔[/] modelo em [bold]{pasta}[/] ({segundos:.1f} s)")
                    else:
                        console.print(f"[green]✔[/] modelo já existia em [bold]{pasta}[/]")
                pastas.append(pasta)
            if len(pastas) == 1 and not comandos_dss:
                master = escolher_master(pastas[0], dia, mes)
            else:
                nome = ("cluster_" if len(ctmts) > 1 else "") + "-".join(ctmts)
                cenario = "base" if not comandos_dss else "manobras"
                if falha is not None:
                    cenario = f"falha_{falha}" + (f"_via_{restaurar}" if restaurar else "")
                destino = Path(out) / nome / f"Master_{dia.upper()}{mes:02d}_{cenario}.dss"
                master = montar_master_cluster(
                    pastas, destino, dia=dia, mes=mes, comandos=comandos_dss, nome=nome
                )
                console.print(f"[green]✔[/] Master do cenário em [bold]{master}[/]")
                comandos_dss = []  # já estão no Master
        if not fluxo:
            console.print(f"Master: {master}")
            return
        resultado = run_powerflow(
            master,
            vmin=vmin,
            vmax=vmax,
            estabilizar=estabilizar,
            comandos_extra=[*(comando or ()), *comandos_dss],
        )
    except (
        FileNotFoundError,
        ValueError,
        RuntimeError,
        ImportError,
        DataSourceError,
        ChaveInexistenteError,
        TrechoInexistenteError,
    ) as erro:
        _erro(str(erro))
        return
    _imprimir_fluxo(resultado, top)
    if json_saida is not None:
        _gravar_fluxo_json(resultado, json_saida, top)
        console.print(f"[green]✔[/] resumo gravado em [bold]{json_saida}[/]")
    if not resultado.convergiu:
        raise typer.Exit(code=2)


@app.command()
def tiles(
    gpkg: Annotated[
        Path,
        typer.Option("--gpkg", help="GeoPackage de um recorte (`bdgd-light recortar`)."),
    ],
    out: Annotated[
        Path,
        typer.Option(
            "--out",
            help="Arquivo .pmtiles de saída, ex.: console/public/tiles/TQR0007.pmtiles.",
        ),
    ],
    geojson: Annotated[
        Path | None,
        typer.Option(
            "--geojson",
            help="Pasta dos GeoJSON intermediários (EPSG:4326, um por camada). Padrão: "
            "<out sem extensão>_geojson/ ao lado do .pmtiles.",
        ),
    ] = None,
    apenas_geojson: Annotated[
        bool,
        typer.Option(
            "--geojson-only",
            help="Só escreve os GeoJSON (fallback quando o tippecanoe não está instalado).",
        ),
    ] = False,
    zoom_min: Annotated[int, typer.Option("--zoom-min", min=0, max=22)] = ZOOM_MIN_PADRAO,
    zoom_max: Annotated[int, typer.Option("--zoom-max", min=0, max=22)] = ZOOM_MAX_PADRAO,
) -> None:
    """Gera tiles vetoriais (PMTiles) de um recorte para o console MapLibre: exporta cada camada
    geográfica para GeoJSON em EPSG:4326 (com atributos derivados para o estilo: TEN_KV, TIE,
    N_UCBT, UCBT agregada por poste) e chama o tippecanoe."""
    try:
        r = gerar_tiles(
            gpkg,
            out,
            pasta_geojson=geojson,
            zoom_min=zoom_min,
            zoom_max=zoom_max,
            apenas_geojson=apenas_geojson,
        )
    except TippecanoeAusenteError as erro:
        _erro(str(erro))
        return
    except (TippecanoeError, DataSourceError, ValueError) as erro:
        _erro(str(erro))
        return
    tabela = Table(title=f"Tiles de {gpkg.name}", show_lines=False)
    tabela.add_column("camada")
    tabela.add_column("feições", justify="right")
    tabela.add_column("GeoJSON")
    for camada, caminho in r.geojson.items():
        tabela.add_row(camada, _fmt_int(r.feicoes[camada]), str(caminho))
    console.print(tabela)
    for aviso in r.avisos:
        console.print(f"[yellow]⚠ {aviso}[/]")
    if r.bounds:
        console.print("bbox 4326: " + ", ".join(f"{v:.5f}" for v in r.bounds))
    if r.pmtiles is not None:
        console.print(
            f"[green]✔[/] [bold]{r.pmtiles}[/] ({r.bytes / 1e6:.2f} MB, "
            f"zoom {zoom_min}–{zoom_max}, {r.segundos:.1f} s)",
            soft_wrap=True,
        )
    else:
        console.print(f"[green]✔[/] GeoJSON em [bold]{next(iter(r.geojson.values())).parent}[/]")


@app.command()
def llm(
    pergunta: Annotated[
        str, typer.Argument(help="Pergunta para o modelo, ex.: 'Quanto é 2 + 3?'.")
    ],
    provider: Annotated[
        str | None,
        typer.Option(
            "--provider",
            help="Perfil de provedor (ADR-003): openai (padrão; OPENAI_API_KEY), gemini "
            "(GEMINI_API_KEY), ollama (local) ou fake (sem rede). Padrão: env "
            "BDGD_LLM_PROVIDER; sem ela, a primeira chave presente no ambiente.",
        ),
    ] = None,
    fake: Annotated[
        bool,
        typer.Option(
            "--fake",
            help="Atalho de --provider fake: cliente determinístico (sem rede) que imita um "
            "modelo chamando a ferramenta soma(a, b).",
        ),
    ] = False,
    modelo: Annotated[
        str | None,
        typer.Option(
            "--modelo", help="Id do modelo (padrão: env BDGD_LLM_MODEL, depois o do perfil)."
        ),
    ] = None,
    endpoint: Annotated[
        str | None,
        typer.Option(
            "--endpoint",
            help="URL …/chat/completions de outro provedor compatível com a OpenAI, com token em "
            "BDGD_LLM_TOKEN (padrão: env BDGD_LLM_ENDPOINT). Ignora --provider.",
        ),
    ] = None,
    sistema: Annotated[
        str,
        typer.Option("--sistema", help="Mensagem de sistema."),
    ] = "Você é o assistente do COD. Use a ferramenta soma quando precisar somar números.",
    json_saida: Annotated[
        Path | None,
        typer.Option("--json", help="Grava a conversa completa (mensagens, ferramentas, uso)."),
    ] = None,
    audit: Annotated[
        Path,
        typer.Option(
            "--audit",
            help="Log de auditoria só de acréscimo (JSON Lines com hash encadeado, ADR-001 "
            "decisão 6): cada rodada do modelo, chamadas de ferramenta e uso de tokens.",
        ),
    ] = AUDIT_PADRAO,
    sem_audit: Annotated[
        bool, typer.Option("--sem-audit", help="Não grava o log de auditoria.")
    ] = False,
) -> None:
    """Exemplo mínimo de *tool calling* (spike da issue #7, perfis da ADR-003): envia a pergunta
    ao modelo com a ferramenta soma(a, b) disponível, executa as chamadas pedidas e imprime a
    resposta, o uso de tokens e a latência. Segredos só por variável de ambiente
    (OPENAI_API_KEY, GEMINI_API_KEY ou BDGD_LLM_TOKEN)."""
    import json

    try:
        from bdgd_light.agent import (
            SOMA,
            AuditError,
            AuditLog,
            LLMError,
            Message,
            OpenAICompatClient,
            cliente_do_ambiente,
            conversar,
            fake_soma,
        )
    except ImportError as erro:
        _erro(f"{erro} — instale o extra: uv sync --extra agent")
        return
    try:
        log = None if sem_audit else AuditLog(audit)
    except AuditError as erro:
        _erro(f"log de auditoria {audit} inválido: {erro}")
        return
    try:
        if fake:
            cliente = fake_soma()
        elif endpoint:
            cliente = OpenAICompatClient(endpoint, modelo=modelo)
        else:
            cliente = cliente_do_ambiente(modelo, provider=provider)
        conversa = conversar(
            cliente, [Message.system(sistema), Message.user(pergunta)], [SOMA], audit=log
        )
    except (LLMError, ValueError) as erro:
        _erro(str(erro))
        return
    for chamada, resultado in conversa.execucoes:
        args = json.dumps(chamada.arguments, ensure_ascii=False)
        console.print(f"[cyan]⚙ {chamada.name}({args}) → {resultado}[/]")
    console.print(conversa.resposta.content)
    rotulo = conversa.resposta.modelo or getattr(cliente, "modelo", "?")
    uso = conversa.uso_total
    tokens = f", {uso.total_tokens} tokens" if uso else ""
    console.print(
        f"[dim]{rotulo} · {conversa.rodadas} rodada(s){tokens}, {conversa.segundos:.1f} s[/]"
    )
    if json_saida is not None:
        json_saida.write_text(
            json.dumps(conversa.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        console.print(f"[green]✔[/] conversa gravada em [bold]{json_saida}[/]")
    if log is not None:
        console.print(
            f"[dim]auditoria: {len(log)} registro(s) em {audit} · "
            f"hash {conversa.hash_auditoria[:12]}…[/]",
            soft_wrap=True,
        )


@app.command()
def audit(
    caminho: Annotated[
        Path,
        typer.Argument(help="Arquivo JSON Lines do log de auditoria (saída de bdgd-light llm)."),
    ] = AUDIT_PADRAO,
    mostrar: Annotated[
        int, typer.Option("--mostrar", help="Imprime os N últimos registros (resumo).")
    ] = 0,
) -> None:
    """Verifica a cadeia de hashes do log de auditoria (ADR-001, decisão 6): qualquer linha
    alterada, removida ou reordenada é apontada. Sai com código 1 se a cadeia estiver quebrada."""
    from bdgd_light.agent.audit import AuditError, AuditLog, ler

    if not caminho.exists():
        _erro(f"{caminho} não existe.")
        return
    try:
        n = AuditLog.verificar_arquivo(caminho)
    except AuditError as erro:
        _erro(f"cadeia inválida em {caminho}: {erro}")
        return
    console.print(f"[green]✔[/] {caminho}: {n} registro(s), cadeia íntegra", soft_wrap=True)
    if mostrar > 0:
        registros = list(ler(caminho))[-mostrar:]
        tabela = Table("seq", "ts", "tipo", "resumo", "hash")
        for r in registros:
            resumo = ", ".join(
                f"{k}={_resumir(v)}" for k, v in r.dados.items() if k in CHAVES_RESUMO_AUDIT
            )
            tabela.add_row(str(r.seq), r.ts, r.tipo, resumo, r.hash[:12] + "…")
        console.print(tabela)


@app.command()
def mcp(
    cluster: Annotated[
        str | None,
        typer.Option(
            "--cluster",
            help="Cluster a carregar ao subir: nome da demo (tijuca, ipanema, taquara) ou caminho "
            "de um GeoPackage do recorte. Sem ele, o modelo chama load_cluster.",
        ),
    ] = None,
    listar: Annotated[
        bool,
        typer.Option("--listar", help="Só imprime as ferramentas (nome, argumentos, descrição)."),
    ] = False,
    transporte: Annotated[
        str, typer.Option("--transporte", help="stdio (padrão, para clientes locais) ou http.")
    ] = "stdio",
    host: Annotated[str, typer.Option("--host", help="Endereço do transporte http.")] = "127.0.0.1",
    porta: Annotated[int, typer.Option("--porta", help="Porta do transporte http.")] = 8765,
    feeders: Annotated[
        Path, typer.Option("--feeders", help="Pasta dos recortes (GeoPackages).")
    ] = Path("data/feeders"),
    dss_out: Annotated[
        Path,
        typer.Option(
            "--dss-out", help="Modelos OpenDSS do gêmeo (convertidos do GPKG se faltarem)."
        ),
    ] = Path("data/dss/gpkg"),
    estado: Annotated[
        Path,
        typer.Option(
            "--estado",
            help="Pasta de estado da sessão: audit.jsonl (auditoria encadeada) e propostas.json "
            "(fila de aprovação, compartilhada com `bdgd-light aprovar`).",
        ),
    ] = Path("data/agent"),
    dia: Annotated[str, typer.Option("--dia", help="Tipo de dia das cargas: DU, SA ou DO.")] = "DU",
    mes: Annotated[int, typer.Option("--mes", min=1, max=12, help="Mês das cargas.")] = 1,
) -> None:
    """Sobe o servidor MCP com as ferramentas de rede (grafo + gêmeo OpenDSS) para um agente:
    load_cluster, get_topology, inject_fault, locate/isolate_fault, restore_options (com score
    elétrico), run_powerflow, propose_plan e set_switch — que só executa com token emitido por
    aprovação humana (`bdgd-light aprovar`). Toda chamada vai para o log de auditoria."""
    try:
        from bdgd_light.mcp_server import SessaoCOD
        from bdgd_light.mcp_server.servidor import descritores, servir
    except ImportError as erro:
        _erro(f"{erro} — instale o extra: uv sync --extra agent")
        return
    if listar:
        tabela = Table("ferramenta", "argumentos", "descrição", title="Ferramentas MCP bdgd-light")
        for d in descritores():
            props = d["parameters"].get("properties", {})
            obrig = set(d["parameters"].get("required", []))
            args = ", ".join(f"{k}{'' if k in obrig else '?'}" for k in props) or "—"
            tabela.add_row(d["name"], args, d["description"])
        console.print(tabela)
        return
    # em stdio o stdout é o canal do protocolo: mensagens humanas vão para stderr
    saida = Console(stderr=True) if transporte == "stdio" else console
    sessao = SessaoCOD(
        feeders=feeders, dss_out=dss_out, estado_dir=estado, dia=dia.upper(), mes=mes
    )
    if cluster is not None:
        try:
            r = sessao.load_cluster(cluster)
        except (FileNotFoundError, DataSourceError, ValueError) as erro:
            saida.print(f"[red]Erro:[/] {erro}")
            raise typer.Exit(code=1) from None
        saida.print(
            f"[green]✔[/] {r['cluster']}: {_fmt_int(r['resumo']['nos'])} nós, "
            f"{r['resumo']['chaves']} chaves, {r['resumo']['ties']} ties; religadores "
            f"{', '.join(f'{k}={v}' for k, v in r['religadores'].items())}"
        )
    endereco = f" em http://{host}:{porta}/mcp · aprovação: POST /propostas/<id>/aprovar"
    saida.print(
        f"[dim]MCP ({transporte}{endereco if transporte == 'http' else ''}) · propostas: "
        f"{estado / 'propostas.json'} · auditoria: {estado / 'audit.jsonl'}[/]"
    )
    try:
        servir(sessao, transporte, host=host, port=porta)
    except ValueError as erro:
        saida.print(f"[red]Erro:[/] {erro}")
        raise typer.Exit(code=1) from None


@app.command()
def aprovar(
    proposta_id: Annotated[
        str | None,
        typer.Argument(help="Id da proposta (ex.: P-0001). Sem id, lista a fila."),
    ] = None,
    estado: Annotated[
        Path,
        typer.Option("--estado", help="Pasta de estado da sessão (a mesma de `bdgd-light mcp`)."),
    ] = Path("data/agent"),
    rejeitar: Annotated[
        bool, typer.Option("--rejeitar", help="Rejeita em vez de aprovar.")
    ] = False,
    motivo: Annotated[str, typer.Option("--motivo", help="Motivo da rejeição.")] = "",
    operador: Annotated[
        str | None, typer.Option("--operador", help="Quem decide (padrão: usuário do sistema).")
    ] = None,
    validade: Annotated[
        int, typer.Option("--validade", help="Validade do token de aprovação, em segundos.")
    ] = 1800,
) -> None:
    """Lado humano do HITL: lista, aprova (emitindo o token que libera set_switch na ordem da
    proposta) ou rejeita propostas criadas pelo agente via servidor MCP."""
    import getpass

    from bdgd_light.agent.audit import AuditLog
    from bdgd_light.mcp_server import FilaPropostas, SessaoError

    fila = FilaPropostas(estado / "propostas.json")
    if proposta_id is None:
        if not len(fila):
            console.print(f"[yellow]nenhuma proposta em {estado / 'propostas.json'}[/]")
            return
        tabela = Table("id", "status", "falta", "fechar", "fonte", "clientes", "manobras", "viável")
        for p in fila.listar():
            viavel = "—" if not p.score else ("sim" if p.score.get("viavel") else "não")
            tabela.add_row(
                p.id,
                p.status,
                p.falta or "—",
                p.chave or "(só isolar)",
                p.fonte,
                str(p.clientes.get("total", "—")),
                " → ".join(f"{m['acao']} {m['chave']}" for m in p.manobras),
                viavel,
            )
        console.print(tabela)
        return
    quem = operador or getpass.getuser()
    # cadeia própria do lado humano (o servidor mantém a dele em audit.jsonl; o hash do token e
    # aprovada_por/aprovada_em no registro de set_switch ligam as duas)
    hitl = AuditLog(estado / "hitl.jsonl")
    try:
        if rejeitar:
            p = fila.rejeitar(proposta_id, operador=quem, motivo=motivo)
            hitl.registrar("hitl.rejeicao", proposta=p.to_dict(com_token=False), operador=quem)
            console.print(
                f"[red]✘[/] {p.id} rejeitada por {quem}" + (f": {motivo}" if motivo else "")
            )
        else:
            p = fila.aprovar(proposta_id, operador=quem, validade_s=validade)
            hitl.registrar("hitl.aprovacao", proposta=p.to_dict(com_token=False), operador=quem)
            console.print(
                f"[green]✔[/] {p.id} aprovada por {quem} até {p.expira_em} — sequência: "
                + " → ".join(f"{m['acao']} {m['chave']}" for m in p.manobras)
            )
            console.print(f"approval_token: [bold]{p.token}[/]", soft_wrap=True)
    except SessaoError as erro:
        _erro(str(erro))


def _resumir(valor, limite: int = 60) -> str:
    if isinstance(valor, dict) and "tipo" in valor:  # resposta de uma rodada
        if valor.get("tool_calls"):
            texto = "→ " + ", ".join(c["ferramenta"] for c in valor["tool_calls"])
        else:
            texto = str(valor.get("content"))
    else:
        texto = str(valor)
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def _score_opcoes(opcoes, rede: Rede, gpkg: Path, dss_out: Path | None, *, dia, mes, vmin, vmax):
    """Monta o Master base do cluster (convertendo do GPKG o que faltar) e pontua as opções."""
    try:
        from bdgd_light.twin import preparar_master_cluster, score_eletrico
    except ImportError as erro:
        raise ImportError(f"{erro} — instale o extra: uv sync --extra twin") from erro
    out = Path("data/dss/gpkg") if dss_out is None else dss_out
    inicio = time.perf_counter()
    master = preparar_master_cluster(
        gpkg,
        rede.ctmts,
        out,
        dia=dia,
        mes=mes,
        ao_converter=lambda cod, conv: _imprimir_conversao(cod, conv, mes, inicio),
    )
    inicio = time.perf_counter()
    scores = score_eletrico(opcoes, rede, master, vmin=vmin, vmax=vmax)
    console.print(
        f"[green]✔[/] {len(scores)} opções avaliadas no gêmeo [bold]{master.name}[/] "
        f"({time.perf_counter() - inicio:.1f} s)"
    )
    return scores


def _fmt_pu(x: float) -> str:
    return "—" if x != x else f"{x:.3f}".replace(".", ",")


def _imprimir_opcoes(opcoes, rede: Rede, scores=None) -> None:
    """Tabela das opções de restauração; com ``scores`` (twin.score_eletrico) acrescenta as
    colunas elétricas MT e segue a ordem dos scores (viável → margem → UCBT)."""
    if scores is None:
        titulo = f"Opções de restauração ({len(opcoes)})"
        colunas = [
            ("Fechar", "left"),
            ("Chave de", "left"),
            ("Fonte", "left"),
            ("TLCD", "center"),
            ("Nós", "right"),
            ("UCBT", "right"),
            ("UCMT", "right"),
            ("kVA", "right"),
            ("UC na fonte", "right"),
        ]
        linhas = [(o, None) for o in opcoes]
    else:
        # ordem dos scores (viável → margem → UCBT); colunas de rede reduzidas para caber
        titulo = f"Opções de restauração ({len(opcoes)}) — score elétrico MT"
        colunas = [
            ("Fechar", "left"),
            ("Fonte", "left"),
            ("TLCD", "center"),
            ("UCBT", "right"),
            ("UCMT", "right"),
            ("Conv.", "center"),
            ("I disj. A", "right"),
            ("I nom. A", "right"),
            ("Margem", "right"),
            ("Vmin MT", "right"),
            ("Sobrec. MT", "right"),
            ("Perdas kW", "right"),
            ("Viável", "center"),
        ]
        linhas = [(sc.opcao, sc) for sc in scores]
    tabela = Table(title=titulo)
    for rotulo, alinhamento in colunas:
        tabela.add_column(rotulo, justify=alinhamento, overflow="fold")
    for o, sc in linhas:
        celulas = [o.chave + (" (externa)" if o.externa else "")]
        if sc is None:
            celulas += [
                o.ctmt_chave,
                o.fonte,
                "sim" if o.tlcd else "não",
                _fmt_int(len(o.nos)),
                _fmt_int(o.clientes.ucbt),
                _fmt_int(o.clientes.ucmt),
                _fmt_int(int(o.clientes.kva)),
                _fmt_int(o.clientes_fonte.total) if o.fonte in rede.ctmts else "?",
            ]
        else:
            margem = sc.margem_disjuntor
            celulas += [
                o.fonte,
                "sim" if o.tlcd else "não",
                _fmt_int(o.clientes.ucbt),
                _fmt_int(o.clientes.ucmt),
                "sim" if sc.convergiu else "[red]não[/]",
                "—" if sc.i_disjuntor_a != sc.i_disjuntor_a else _fmt_int(round(sc.i_disjuntor_a)),
                "—" if sc.i_nominal_a != sc.i_nominal_a else _fmt_int(round(sc.i_nominal_a)),
                "—" if margem != margem else f"{100 * margem:.0f} %",
                _fmt_pu(sc.vmin_mt_pu),
                _fmt_int(len(sc.sobrecargas_mt)),
                "—" if sc.perdas_kw != sc.perdas_kw else _fmt_int(round(sc.perdas_kw)),
                "[green]sim[/]" if sc.viavel else "[red]NÃO[/]",
            ]
        tabela.add_row(*celulas)
    console.print(tabela)
    if scores is not None:
        for sc in scores:
            if sc.motivos:
                console.print(f"  [red]✘[/] {sc.chave}: {'; '.join(sc.motivos)}")
        ajustes = {tuple(sc.ajustes) for sc in scores if sc.convergiu and sc.ajustes}
        if len(ajustes) == 1 and all(sc.ajustes or not sc.convergiu for sc in scores):
            rotulos = ", ".join(next(iter(ajustes)))
            console.print(f"  [yellow]![/] estabilizadores em todas as opções: {rotulos}")
        elif ajustes:
            for sc in scores:
                if sc.ajustes:
                    console.print(
                        f"  [yellow]![/] {sc.chave}: estabilizadores {', '.join(sc.ajustes)}"
                    )


def _tem_master(pasta: Path | None, dia: str, mes: int) -> bool:
    """A pasta já tem o Master do tipo de dia/mês pedidos?"""
    if pasta is None:
        return False
    from bdgd_light.twin import escolher_master

    try:
        escolher_master(pasta, dia, mes)
    except (FileNotFoundError, ValueError):
        return False
    return True


def _converter_gpkg(gpkg: Path, cod: str, out: Path, dia: str, mes: int) -> Path:
    """Gera (ou regenera) o modelo OpenDSS de ``cod`` direto do GeoPackage do recorte."""
    from bdgd_light.twin import DIAS, converter_ctmt

    inicio = time.perf_counter()
    conv = converter_ctmt(gpkg, cod, out, dias=DIAS, meses=[mes])
    _imprimir_conversao(cod, conv, mes, inicio)
    return conv.pasta


def _imprimir_conversao(cod: str, conv, mes: int, inicio: float) -> None:
    n = conv.contagem
    resumo = ", ".join(
        f"{n.get(k, 0)} {rotulo}"
        for k, rotulo in (
            ("SSDMT", "trechos MT"),
            ("UNSEMT", "chaves MT"),
            ("unidades_trafo", "trafos"),
            ("SSDBT", "trechos BT"),
            ("UCBT_tab", "cargas BT"),
            ("PIP", "IP"),
            ("UCMT_tab", "cargas MT"),
        )
        if k in n
    )
    console.print(
        f"[green]✔[/] {cod} convertido do GeoPackage em [bold]{conv.pasta}[/] "
        f"({time.perf_counter() - inicio:.1f} s): {resumo}; {len(conv.masters)} Masters "
        f"DU/SA/DO do mês {mes:02d}"
    )
    for aviso in conv.avisos:
        console.print(f"[yellow]Aviso:[/] {aviso}")


def _manobras_dss(
    gpkg: Path | None,
    falha: str | None,
    restaurar: str | None,
    abrir: str | None,
    fechar: str | None,
    comandos_manobras,
) -> list[str]:
    """Carrega o grafo do recorte e traduz --abrir/--fechar/--falha/--restaurar em comandos DSS."""
    if gpkg is None:
        return []
    camadas = ler_camadas(gpkg)
    rede: Rede = Feeder(camadas) if len(camadas.ctmt) == 1 else Cluster(camadas)
    manobras = [manobra(ABRIR, cod) for cod in _lista(abrir)]
    manobras += [manobra(FECHAR, cod) for cod in _lista(fechar)]
    if falha is not None:
        isolamento = rede.isolate_segment(falha)
        if restaurar is None:
            manobras += isolamento.manobras
        else:
            opcao = next((o for o in rede.restore_options(falha) if o.chave == restaurar), None)
            if opcao is None:
                raise ValueError(
                    f"a chave {restaurar} não restaura a falta em {falha}; "
                    "veja `bdgd-light grafo --falha`"
                )
            manobras += opcao.manobras
            console.print(
                f"Falta em [bold]{falha}[/]: abrir {', '.join(isolamento.chaves)}; fechar "
                f"[bold]{restaurar}[/] transfere {_fmt_int(len(opcao.nos))} nós "
                f"({_fmt_clientes(opcao.clientes)}) para {opcao.fonte}"
            )
    elif restaurar is not None:
        raise ValueError("--restaurar exige --falha.")
    comandos = comandos_manobras(rede, manobras)
    for c in comandos:
        console.print(f"  [dim]{c[:100]}[/]")
    return comandos


def _imprimir_fluxo(r, top: int) -> None:
    s = r.resumo()
    tabela = Table(title=f"Fluxo de potência — {r.circuito} ({r.master.name})", show_header=False)
    tabela.add_column("campo", style="bold")
    tabela.add_column("valor")
    convergiu = "[green]sim[/]" if r.convergiu else "[red]NÃO[/]"
    linhas = [
        ("Convergiu", f"{convergiu} ({r.iteracoes} iterações, {r.tempo_s:.2f} s)"),
        ("Estabilizadores", ", ".join(r.ajustes) or "nenhum"),
        (
            "Elementos",
            f"{_fmt_int(r.n_barras)} barras, {_fmt_int(r.n_nos)} nós, {_fmt_int(r.n_linhas)} "
            f"linhas, {_fmt_int(r.n_trafos)} trafos, {_fmt_int(r.n_cargas)} cargas",
        ),
        (
            "Potência na fonte",
            f"{_fmt_int(round(r.potencia_kw))} kW / {_fmt_int(round(r.potencia_kvar))} kvar",
        ),
        (
            "Perdas",
            f"{_fmt_int(round(r.perdas_kw))} kW"
            + (f" ({100 * r.perdas_kw / r.potencia_kw:.1f} %)" if r.potencia_kw else ""),
        ),
        ("Tensão (nós de fase)", f"mín {r.v_min_pu:.3f} pu, máx {r.v_max_pu:.3f} pu"),
        (
            f"Fora de [{r.vmin_ref}, {r.vmax_ref}] pu",
            f"{_fmt_int(s['n_subtensao'])} sub, {_fmt_int(s['n_sobretensao'])} sobre "
            f"(de {_fmt_int(s['n_nos_fase'])} nós; {_fmt_int(s['n_desenergizados'])} a 0 pu)",
        ),
        ("Sobrecargas (> 100 %)", _fmt_int(s["n_sobrecargas"])),
    ]
    if len(r.fontes) > 1:
        linhas.insert(
            4,
            (
                "Por fonte",
                "; ".join(
                    f"{f.fonte} ({f.barra}) {_fmt_int(round(f.kw))} kW"
                    for f in r.fontes.itertuples(index=False)
                ),
            ),
        )
    for campo, valor in linhas:
        tabela.add_row(campo, valor)
    console.print(tabela)
    mt = r.tensoes_mt()
    if mt["ctmt"].nunique() > 1:
        t = Table(title="Tensão MT por alimentador")
        for rotulo, alinhamento in [
            ("CTMT", "left"),
            ("nós", "right"),
            ("mín pu", "right"),
            ("máx pu", "right"),
        ]:
            t.add_column(rotulo, justify=alinhamento)
        for nome, g in mt.groupby("ctmt"):
            t.add_row(nome, _fmt_int(len(g)), f"{g['v_pu'].min():.3f}", f"{g['v_pu'].max():.3f}")
        console.print(t)
    piores = r.piores_barras(top)
    if not piores.empty and piores["v_pu"].iloc[0] < r.vmin_ref:
        t = Table(title=f"Piores tensões ({min(top, len(piores))})")
        for rotulo, alinhamento in [("Nó", "left"), ("kV base", "right"), ("V pu", "right")]:
            t.add_column(rotulo, justify=alinhamento)
        for p in piores.itertuples(index=False):
            t.add_row(p.no, f"{p.kv_base:.3f}", f"{p.v_pu:.3f}")
        console.print(t)
    sobre = r.sobrecargas.head(top)
    if not sobre.empty:
        t = Table(title=f"Sobrecargas ({min(top, len(sobre))} de {len(r.sobrecargas)})")
        for rotulo, alinhamento in [
            ("Elemento", "left"),
            ("I máx A", "right"),
            ("I nominal A", "right"),
            ("Carga %", "right"),
        ]:
            t.add_column(rotulo, justify=alinhamento)
        for e in sobre.itertuples(index=False):
            t.add_row(
                e.elemento, f"{e.i_max_a:.1f}", f"{e.i_nominal_a:.1f}", f"{e.carregamento_pct:.0f}"
            )
        console.print(t)


def _gravar_fluxo_json(r, caminho: Path, top: int) -> None:
    import json

    dados = r.resumo()
    dados["piores_barras"] = r.piores_barras(top).to_dict(orient="records")
    dados["sobrecargas"] = r.sobrecargas.head(top).to_dict(orient="records")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


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
        ("Clientes", _fmt_clientes(Clientes.from_dict(r["clientes"]))),
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
