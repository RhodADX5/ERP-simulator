"""Pruebas unitarias de los algoritmos (no requieren base de datos)."""

from decimal import Decimal

from sku_sentinel.abc_analysis import classify
from sku_sentinel.csp import CSP
from sku_sentinel.normalize import jaccard, join_units, normalize_attributes, tokens
from sku_sentinel.rules import Catalog, evaluate_item, structural_key
from sku_sentinel.search import bfs, greedy_best_first, similarity_heuristic

CATALOG = Catalog(
    uom={"PZA": False, "G": True, "CAJA": False},
    categories={
        "RAM": {"item_types": ["Materia Prima"], "uom": ["PZA"], "key": ["marca", "capacidad", "tipo"],
                "required": ["capacidad", "tipo"], "keywords": ["ram", "memoria", "ddr5"]},
        "Consumible": {"item_types": ["Consumible"], "uom": ["G"], "key": ["marca", "presentacion"],
                       "required": ["presentacion"], "keywords": ["pasta"]},
    },
    attribute_domains={"RAM": {"tipo": {"allowed": ["DDR4", "DDR5"], "pattern": None},
                               "capacidad": {"allowed": None, "pattern": r"^[0-9]+GB$"}}},
)


def ram(**kw):
    base = {"SKU": "RAM-X", "ItemName": "RAM 16GB DDR5", "Description": "Memoria Kingston 16 GB DDR5",
            "Category": "RAM", "ItemType": "Materia Prima", "BaseUoM": "PZA",
            "TechnicalAttributes": {"marca": "Kingston", "capacidad": "16GB", "tipo": "DDR5"},
            "StandardCost": 1100, "ListPrice": 1350, "SafetyStock": 20, "IsCritical": True}
    base.update(kw)
    return base


# ---------------- CSP / AC-3 ----------------
def test_ac3_reduce_dominios_y_detecta_vacio():
    csp = CSP()
    csp.add_variable("X", {1, 2, 3})
    csp.add_variable("Y", {1, 2, 3})
    csp.add_binary("X", "Y", lambda x, y: x > y, "X>Y")
    r = csp.solve()
    assert r.consistent and r.domains == {"X": {2, 3}, "Y": {1, 2}}
    csp.add_variable("Y", {3})
    r = csp.solve()
    assert not r.consistent and r.conflicts[0].constraint == "X>Y"


def test_consistencia_de_nodo_explica_el_fallo():
    csp = CSP()
    csp.add_variable("U", {"CJA"})
    csp.add_unary("U", lambda u: u in {"PZA"}, "U1", lambda u: f"{u} no existe")
    r = csp.solve()
    assert not r.consistent and r.conflicts[0].detail == "CJA no existe"


def test_articulo_valido():
    ev = evaluate_item(ram(), CATALOG)
    assert ev.result.consistent and ev.category == "RAM"


def test_precio_menor_que_costo():
    ev = evaluate_item(ram(ListPrice=900), CATALOG)
    assert [c.constraint for c in ev.result.conflicts] == ["B1 ListPrice >= StandardCost"]


def test_critico_sin_safety_stock():
    ev = evaluate_item(ram(SafetyStock=0), CATALOG)
    assert any(c.constraint.startswith("B2") for c in ev.result.conflicts)


def test_uom_invalida_y_atributo_fuera_de_dominio():
    ev = evaluate_item(ram(BaseUoM="CJA", TechnicalAttributes={"marca": "K", "capacidad": "16GB", "tipo": "DDR7"}),
                       CATALOG)
    names = {c.constraint for c in ev.result.conflicts}
    assert "U1 unidad de medida válida" in names and "U2 atributos técnicos de la categoría" in names


def test_safety_stock_fraccionario_en_pieza():
    ev = evaluate_item(ram(SafetyStock=Decimal("2.5")), CATALOG)
    assert any(c.constraint.startswith("B5") for c in ev.result.conflicts)


def test_ac3_deduce_categoria_tipo_y_unidad():
    item = ram(Category=None, ItemType=None, BaseUoM=None, TechnicalAttributes={"marca": "Kingston"})
    ev = evaluate_item(item, CATALOG)
    assert ev.result.consistent
    assert ev.suggestions == {"Category": "RAM", "ItemType": "Materia Prima", "BaseUoM": "PZA"}
    assert ev.inferred_attributes == {"tipo": "DDR5", "capacidad": "16GB"}


# ---------------- normalización y duplicados ----------------
def test_normalizacion_de_texto():
    assert join_units("16 gb y 750 w") == "16GB y 750W"
    a = tokens("Memoria Kingston Fury 16 GB DDR5")
    b = tokens("RAM DDR5 16GB Kingston Fury")
    assert a == b and jaccard(a, b) == 1.0


def test_clave_estructural_ignora_redaccion():
    doms = CATALOG.domains_for("RAM")
    k1 = structural_key("RAM", normalize_attributes({"Marca": "kingston", "Capacidad": "16 gb", "Tipo": "ddr5"}, doms), CATALOG)
    k2 = structural_key("RAM", normalize_attributes({"marca": "Kingston", "capacidad": "16GB", "tipo": "DDR5"}, doms), CATALOG)
    assert k1 == k2 == "ram|marca=kingston|capacidad=16gb|tipo=ddr5"
    assert structural_key("RAM", {"marca": "Kingston"}, CATALOG) is None


# ---------------- BFS y Greedy ----------------
GRAPH = {"O": ["A", "B"], "A": ["O"], "B": ["O", "C"], "C": ["B"]}
HVAL = {"O": 0, "A": 0.9, "B": 0.5, "C": 0.1}


def test_bfs_devuelve_el_mas_cercano():
    r = bfs("O", GRAPH.get, lambda n: n in {"A", "C"})
    assert r.found == "A" and r.hops == 1


def test_greedy_devuelve_el_de_menor_heuristica():
    r = greedy_best_first("O", GRAPH.get, lambda n: n in {"A", "C"}, HVAL.get)
    assert r.found == "C" and r.path == ["O", "B", "C"]


def test_sin_meta():
    assert bfs("O", GRAPH.get, lambda n: False).found is None
    assert greedy_best_first("O", GRAPH.get, lambda n: False, HVAL.get).found is None


def test_heuristica_pondera_atributos_funcionales():
    o = {"SKU": "O", "attrs": {"marca": "X", "capacidad": "1TB", "interfaz": "NVMe"}, "ListPrice": 100}
    misma_interfaz = {"SKU": "A", "attrs": {"marca": "Y", "capacidad": "1TB", "interfaz": "NVMe"}, "ListPrice": 100}
    otra_interfaz = {"SKU": "B", "attrs": {"marca": "X", "capacidad": "1TB", "interfaz": "SATA"}, "ListPrice": 100}
    key, req = ["marca", "capacidad", "interfaz"], ["capacidad", "interfaz"]
    assert similarity_heuristic(o, misma_interfaz, key, req) < similarity_heuristic(o, otra_interfaz, key, req)


# ---------------- ABC ----------------
def test_clasificacion_abc():
    rows = [{"SKU": s, "consumption_qty": q, "StandardCost": 1, "stock": 10, "IsCritical": False, "SafetyStock": 1}
            for s, q in (("A1", 70), ("A2", 15), ("B1", 10), ("C1", 5), ("C2", 0))]
    out = {r.sku: r.abc for r in classify(rows)}
    assert out == {"A1": "A", "A2": "A", "B1": "B", "C1": "C", "C2": "C"}
