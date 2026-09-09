# bdgd-cemig

Visualização da **BDGD da CEMIG-D** (Base de Dados Geográfica da Distribuidora,
dados abertos da ANEEL) sobre mapa de **satélite de alta resolução**.

Dataset: [Cemig-D 4950 2023-12-31 (ANEEL Dados Abertos)](https://dadosabertos-aneel.opendata.arcgis.com/datasets/52904205104349d19142c5892ec50844/about)

## Estrutura

```
index.html              Visor de mapa (satélite Esri + camadas GeoJSON) — abrir no navegador
scripts/
  baixar_bdgd.py        Baixa e extrai o File Geodatabase da CEMIG-D
  listar_camadas.py     Lista as camadas do .gdb
  converter.py          Converte camada → GeoJSON (EPSG:4326), com recorte por área
data/                   Dados baixados e convertidos (fora do git)
```

## Como usar

### 1. Instalar dependências (uma vez)

```bash
pip3 install -r requirements.txt
```

### 2. Baixar a BDGD da CEMIG

```bash
python3 scripts/baixar_bdgd.py
```

Atenção: o arquivo tem **vários GB** (CEMIG cobre Minas Gerais inteira).

### 3. Ver quais camadas existem

```bash
python3 scripts/listar_camadas.py data/NOME_EXTRAIDO.gdb
```

Principais camadas geográficas: `UNTRD` (transformadores), `SSDMT`/`SSDBT`
(rede de média/baixa tensão), `UCBT`/`UCMT` (unidades consumidoras),
`PONNOT` (postes), `SUB` (subestações), `ARAT` (área de atuação).

### 4. Converter uma camada para GeoJSON (com recorte)

Converta sempre com `--bbox` — a camada inteira é grande demais para o navegador.
Desenhe sua área em <https://boundingbox.klokantech.com> (formato CSV) e:

```bash
# Transformadores na região central de BH
python3 scripts/converter.py data/NOME.gdb UNTRD --bbox -44.02 -19.95 -43.90 -19.88

# Rede de média tensão, limitando feições para teste rápido
python3 scripts/converter.py data/NOME.gdb SSDMT --bbox -44.02 -19.95 -43.90 -19.88 --max 20000
```

### 5. Visualizar

Abra o `index.html` no navegador (2 cliques) e **arraste** os `.geojson`
gerados em `data/` para o mapa. Clique em qualquer feição para ver os
atributos. Precisa de internet (as imagens de satélite são carregadas da Esri).

## Notas

- A BDGD usa SIRGAS 2000 (EPSG:4674); o `converter.py` já reprojeta para
  WGS84 (EPSG:4326), que é o que o mapa web usa.
- Arquivos GeoJSON acima de ~80 MB deixam o navegador lento; reduza o bbox.
- Para análises maiores (MG inteira, cruzamentos, filtros por atributo), o
  caminho natural é importar o .gdb num PostGIS ou usar geopandas direto.
