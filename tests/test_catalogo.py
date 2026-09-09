from bdgd_light.catalogo import ARCGIS_DATA_URL, CAMADAS_CHAVE, CATALOGO, DISTRIBUIDORAS


def test_light_2025_no_catalogo():
    item_id, nome, _ = CATALOGO[("light", 2025)]
    assert len(item_id) == 32
    assert nome.startswith("Light_382_2025-12-31")


def test_url_formata_id():
    assert ARCGIS_DATA_URL.format(item_id="abc").endswith("/items/abc/data")


def test_codigos_e_camadas():
    assert DISTRIBUIDORAS["light"] == 382
    for camada in ("CTMT", "SSDMT", "UNSEMT", "UCBT"):
        assert camada in CAMADAS_CHAVE
