"""Pruebas de integración del agente contra PostgreSQL (datos semilla)."""

import json


def test_bloquea_duplicado_y_sugiere_sku_existente(agent):
    d = agent.registrar_articulo({
        "SKU": "RAM-NUEVA", "ItemName": "RAM DDR5 16GB Kingston Fury", "Description": "RAM DDR5 16GB Kingston Fury",
        "ItemType": "Materia Prima", "Category": "RAM", "BaseUoM": "PZA",
        "TechnicalAttributes": {"marca": "KINGSTON", "modelo": "fury beast", "capacidad": "16 GB", "tipo": "ddr5"},
        "StandardCost": 1100, "ListPrice": 1350, "SafetyStock": 20, "IsCritical": True})
    assert d.decision == "RECHAZADO"
    assert d.duplicado_de == "RAM-16GB-DDR5"
    assert d.sugerencias["UsarSKUExistente"] == "RAM-16GB-DDR5"
    assert d.review_id is not None
    assert agent.repo.item("RAM-NUEVA") is None


def test_alta_valida_se_clasifica_y_guarda(agent):
    d = agent.registrar_articulo({
        "SKU": "SSD-2TB-KC3000", "ItemName": "SSD Kingston KC3000 2TB NVMe",
        "Description": "Unidad SSD Kingston KC3000 2TB NVMe M.2", "TechnicalAttributes": {"modelo": "KC3000"},
        "StandardCost": 2300, "ListPrice": 2790, "SafetyStock": 4})
    assert d.decision == "APROBADO" and d.evento == "ItemCreatedEvent"
    saved = agent.repo.item("SSD-2TB-KC3000")
    assert saved["Category"] == "Almacenamiento" and saved["BaseUoM"] == "PZA"
    assert saved["ItemType"] == "Materia Prima" and saved["LifecycleStatus"] == "En Desarrollo"
    assert saved["TechnicalAttributes"]["marca"] == "Kingston"
    assert saved["StructuralKey"] == "almacenamiento|marca=kingston|modelo=kc3000|capacidad=2tb|interfaz=nvme"


def test_precio_menor_al_costo_rechazado(agent):
    d = agent.evaluar_articulo({
        "SKU": "GPU-X", "ItemName": "RTX 4060", "Description": "Tarjeta de video RTX 4060 8GB", "Category": "Tarjeta de Video",
        "ItemType": "Materia Prima", "BaseUoM": "PZA", "TechnicalAttributes": {"marca": "NVIDIA", "modelo": "RTX 4060"},
        "StandardCost": 7800, "ListPrice": 7200, "SafetyStock": 5})
    assert d.decision == "RECHAZADO"
    assert any(r.get("restriccion") == "B1 ListPrice >= StandardCost" for r in d.razones)


def test_posible_duplicado_por_texto_queda_pendiente(agent):
    d = agent.evaluar_articulo({
        "SKU": "PSU-750-RM", "ItemName": "Power Supply 750W Corsair RM750",
        "Description": "Fuente de poder Corsair RM750 750W", "ItemType": "Materia Prima", "BaseUoM": "PZA",
        "StandardCost": 1700, "ListPrice": 2100, "SafetyStock": 10})
    assert d.decision == "PENDIENTE_REVISION"
    assert d.similares[0]["SKU"] == "PSU-750W"


def test_cambio_de_sku_existente_no_se_compara_consigo_mismo(agent):
    item = agent.repo.item("PSU-850W")
    item["ListPrice"] = 2500
    d = agent.registrar_articulo(item, "CAMBIO")
    assert d.decision == "APROBADO" and agent.repo.item("PSU-850W")["ListPrice"] == 2500


def test_conversiones_de_unidad(agent):
    assert agent.registrar_conversion("PASTA-TERM", "CAJA", "G", 40).decision == "APROBADO"
    assert {(c["fromuom"], c["touom"]) for c in agent.repo.conversions("PASTA-TERM")} >= {("CAJA", "G"), ("G", "CAJA")}
    bad = agent.registrar_conversion("PASTA-TERM", "KG", "G", 950)
    assert bad.razones[0]["codigo"] == "CONVERSION_INCONSISTENTE"
    assert agent.registrar_conversion("CPU-RYZEN-7", "CAJA", "PZA", 2.5).razones[0]["codigo"] == "FACTOR_FRACCIONARIO"
    assert agent.registrar_conversion("CPU-RYZEN-7", "CJA", "PZA", 10).razones[0]["codigo"] == "UOM_INVALIDA"


def test_sustituto_bfs_vs_greedy(agent):
    r = agent.recomendar_sustituto("SSD-1TB-NVME", 20, compatible_con="MB-B650")
    assert r["decision"] == "RECOMENDACION"
    assert r["bfs"]["sustituto"] == "SSD-1TB-SATA" and r["bfs"]["saltos"] == 1
    assert r["greedy"]["sustituto"] == "SSD-1TB-NVME-G4" and r["greedy"]["saltos"] == 2
    assert r["recomendado"] == "SSD-1TB-NVME-G4"


def test_sustituto_respeta_compatibilidad(agent):
    # RAM DDR4 tiene stock pero no es compatible con la B650; no debe recomendarse
    r = agent.recomendar_sustituto("RAM-16GB-DDR5", 100, compatible_con="MB-B650")
    assert r["recomendado"] is None and r["decision"] == "ESCALAR"
    r = agent.recomendar_sustituto("RAM-16GB-DDR5", 25, compatible_con="MB-B650")
    assert r["decision"] == "SIN_ACCION"


def test_abc_persistido(agent):
    rows = {r["sku"]: r for r in agent.clasificar_abc()}
    assert rows["GPU-RTX"]["abc"] == "A" and rows["PSU-750W"]["abc"] == "B"
    assert "Componente crítico sin existencias: buscar sustituto" in rows["SSD-1TB-NVME"]["alerts"]
    assert agent.repo.item("GPU-RTX")["AbcClass"] == "A"


def test_auditoria_del_catalogo(agent):
    out = agent.auditar_catalogo(indexar=True)
    skus = {v["sku"] for v in out["violaciones"]}
    assert skus == {"CPU-RYZEN-5", "GPU-RTX-OLD"}
    assert out["duplicados"][0]["skus"] == ["RAM-16GB-DDR5", "RAM-KF-16-OLD"]
    # los duplicados no se indexan: la clave única de la BD no lo permitiría
    assert agent.repo.item("RAM-KF-16-OLD")["StructuralKey"] is None
    assert agent.repo.item("CPU-RYZEN-7")["StructuralKey"] is not None


def test_bitacora_registra_cada_decision(agent):
    agent.recomendar_sustituto("SSD-1TB-NVME", 20, compatible_con="MB-B650")
    lines = [json.loads(x) for x in agent.audit.path.read_text(encoding="utf-8").splitlines()]
    assert lines[-1]["event"] == "SubstituteRecommendedEvent"
    assert lines[-1]["agent"] == "sku-sentinel-178823"
