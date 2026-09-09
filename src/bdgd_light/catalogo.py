"""Catálogo de itens da BDGD no portal de dados abertos da ANEEL (ArcGIS Hub).

IDs obtidos em 2026-09-09 via API de busca do hub
(https://dadosabertos-aneel.opendata.arcgis.com). Download direto:
https://www.arcgis.com/sharing/rest/content/items/<ID>/data
"""

ARCGIS_DATA_URL = "https://www.arcgis.com/sharing/rest/content/items/{item_id}/data"

# distribuidora -> código ANEEL
DISTRIBUIDORAS = {
    "light": 382,
    "cemig": 4950,
}

# (distribuidora, ano de referência) -> (item_id, nome do arquivo no portal, tamanho aprox.)
CATALOGO = {
    ("light", 2025): ("430f90486174407aabe3b07f50ca6150", "Light_382_2025-12-31_V11_20260824-0926", "1.14 GB"),
    ("light", 2024): ("6a3c464bde7b4c0b9dc661f99341e050", "Light_382_2024-12-31_V11_20250925-1811", "1.17 GB"),
    ("light", 2023): ("111ae92a6f594e4181e3f18507b6331d", "Light_382_2023-12-31_V11_20241216-1348", "1.51 GB"),
    ("light", 2022): ("c6525567fc73441cb2fc7d894e24e10c", "Light_382_2022-12-31_V11_20230914-1042", "1.56 GB"),
    ("light", 2021): ("cf579d43496a4b968c3f0e1e72f54e62", "Light_382_2021-12-31_V10_20221208-1908", "1.41 GB"),
    ("light", 2020): ("0c8f0e3626564995ab7d92758a885cc9", "Light_382_2020-12-31_M10_20230927-1410", "1.02 GB"),
    ("light", 2019): ("bf430d6ac7a440858737ca78954207a8", "Light_382_2019-12-31_M10_20231017-0037", "1.13 GB"),
    ("light", 2018): ("859930b898134723b9b8b9b857305a24", "Light_382_2018-12-31_M10_20231121-1835", "1.06 GB"),
    ("light", 2017): ("ab4cbb3d1e794167835e5c74d371f7b5", "Light_382_2017-12-31_M10_20231209-0050", "1.11 GB"),
    ("cemig", 2023): ("52904205104349d19142c5892ec50844", "Cemig-D_4950_2023-12-31_V11_20250315-1513", "4.5 GB"),
}

# Camadas da BDGD mais relevantes para o projeto (Módulo 10 do PRODIST)
CAMADAS_CHAVE = {
    "CTMT": "alimentadores de média tensão (circuitos)",
    "SUB": "subestações",
    "SSDMT": "segmentos de rede MT (linhas)",
    "SSDBT": "segmentos de rede BT (linhas)",
    "UNTRMT": "transformadores de distribuição MT/BT",
    "UNSEMT": "chaves/seccionadoras MT (NA/NF)",
    "UNSEBT": "chaves BT",
    "UNREMT": "reguladores de tensão MT",
    "UNCRMT": "bancos de capacitores MT",
    "UCMT": "unidades consumidoras MT",
    "UCBT": "unidades consumidoras BT",
    "UGMT": "geração distribuída MT",
    "UGBT": "geração distribuída BT",
    "PONNOT": "pontos notáveis (postes)",
    "RAMLIG": "ramais de ligação",
    "CRVCRG": "curvas típicas de carga (tabela)",
    "EQTRMT": "equipamentos de transformação MT (tabela)",
    "ARAT": "área de atuação",
    "CONJ": "conjuntos elétricos (DEC/FEC)",
}
