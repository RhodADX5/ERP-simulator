"""Reglas del maestro de artículos expresadas como CSP y detección de duplicados.

Variables del CSP de un artículo:
    Category, ItemType, BaseUoM, ListPrice, StandardCost, SafetyStock, IsCritical

Restricciones unarias (consistencia de nodo):
    U1  BaseUoM pertenece a UoM_Catalog
    U2  Category es coherente con los atributos técnicos (obligatorios presentes y
        valores dentro del dominio) y, si no se capturó, con el texto del artículo
    U3  ItemType pertenece a la lista de tipos válidos
    U4  ListPrice, StandardCost y SafetyStock son >= 0

Restricciones binarias (AC-3):
    B1  ListPrice >= StandardCost
    B2  IsCritical  ->  SafetyStock > 0
    B3  ItemType permitido para la Category
    B4  BaseUoM permitida para la Category
    B5  Si la BaseUoM no admite decimales, SafetyStock es entero
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from .csp import CSP, CSPResult
from .normalize import extract_attributes, jaccard, normalize_attributes, strip_accents, tokens

ITEM_TYPES = ("Materia Prima", "Subensamble", "Producto Terminado", "Consumible", "Servicio")
SIMILARITY_THRESHOLD = 0.75


@dataclass
class Catalog:
    """Dominios del CSP, leídos de UoM_Catalog, Category_Rule y Attribute_Domain."""
    uom: dict[str, bool]                       # UoMCode -> AllowsDecimal
    categories: dict[str, dict]                # Category -> regla
    attribute_domains: dict[str, dict[str, dict]] = field(default_factory=dict)  # Category -> attr -> {allowed, pattern}

    def domains_for(self, category: str | None) -> dict[str, dict]:
        return self.attribute_domains.get(category or "", {})


# ---------------------------------------------------------------------------
# Atributos
# ---------------------------------------------------------------------------
def prepare_attributes(item: dict, catalog: Catalog, category: str | None) -> tuple[dict, dict]:
    """Normaliza atributos capturados y completa los faltantes con lo que dice el texto."""
    doms = catalog.domains_for(category)
    attrs = normalize_attributes(item.get("TechnicalAttributes") or {}, doms)
    text = f"{item.get('ItemName') or ''} {item.get('Description') or ''}"
    inferred = {}
    for k, v in extract_attributes(text).items():
        if category == "Tarjeta de Video" and k == "capacidad":
            k = "vram"
        if k not in attrs:
            inferred[k] = normalize_value_for(doms, k, v)
    merged = {**inferred, **attrs}
    return merged, inferred


def normalize_value_for(doms: dict, attr: str, value: str) -> str:
    allowed = doms.get(attr, {}).get("allowed")
    if allowed:
        for canon in allowed:
            if canon.casefold() == value.casefold():
                return canon
    return value


def attribute_problems(category: str, attrs: dict, catalog: Catalog) -> list[str]:
    rule = catalog.categories[category]
    doms = catalog.domains_for(category)
    problems = [f"falta el atributo obligatorio '{a}'" for a in rule["required"] if a not in attrs]
    for attr, value in attrs.items():
        dom = doms.get(attr)
        if not dom:
            continue
        if dom.get("allowed") and value not in dom["allowed"]:
            problems.append(f"{attr}='{value}' fuera del dominio {dom['allowed']}")
        if dom.get("pattern") and not re.match(dom["pattern"], value):
            problems.append(f"{attr}='{value}' no cumple el formato {dom['pattern']}")
    return problems


def keyword_match(category: str, item: dict, catalog: Catalog) -> bool:
    text = strip_accents(f"{item.get('ItemName') or ''} {item.get('Description') or ''}").lower()
    return any(k in text for k in catalog.categories[category]["keywords"])


# ---------------------------------------------------------------------------
# CSP del artículo
# ---------------------------------------------------------------------------
def _num(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def build_item_csp(item: dict, catalog: Catalog) -> tuple[CSP, dict]:
    given_cat = item.get("Category")
    given_type = item.get("ItemType")
    given_uom = (item.get("BaseUoM") or "").strip().upper() or None

    csp = CSP()
    csp.add_variable("Category", {given_cat} if given_cat else set(catalog.categories))
    csp.add_variable("ItemType", {given_type} if given_type else set(ITEM_TYPES))
    csp.add_variable("BaseUoM", {given_uom} if given_uom else set(catalog.uom))

    numbers = {}
    for var in ("ListPrice", "StandardCost", "SafetyStock"):
        numbers[var] = _num(item.get(var))
        csp.add_variable(var, {numbers[var]} if numbers[var] is not None else set())
    csp.add_variable("IsCritical", {bool(item.get("IsCritical", False))})

    attrs_by_cat = {c: prepare_attributes(item, catalog, c) for c in catalog.categories}

    # --- unarias
    csp.add_unary("BaseUoM", lambda u: u in catalog.uom, "U1 unidad de medida válida",
                  lambda u: f"'{u}' no existe en UoM_Catalog {sorted(catalog.uom)}")

    def category_ok(c):
        if c not in catalog.categories:
            return False
        if attribute_problems(c, attrs_by_cat[c][0], catalog):
            return False
        return bool(given_cat) or keyword_match(c, item, catalog)

    def category_explain(c):
        if c not in catalog.categories:
            return f"la categoría '{c}' no existe"
        return f"{c}: " + ", ".join(attribute_problems(c, attrs_by_cat[c][0], catalog) or ["el texto no corresponde"])

    csp.add_unary("Category", category_ok, "U2 atributos técnicos de la categoría", category_explain)
    csp.add_unary("ItemType", lambda t: t in ITEM_TYPES, "U3 tipo de artículo válido",
                  lambda t: f"'{t}' no es un ItemType válido {list(ITEM_TYPES)}")
    for var in ("ListPrice", "StandardCost", "SafetyStock"):
        csp.add_unary(var, lambda v: v >= 0, f"U4 {var} no negativo", lambda v, n=var: f"{n}={v} es negativo")

    # --- binarias
    csp.add_binary("ListPrice", "StandardCost", lambda lp, sc: lp >= sc, "B1 ListPrice >= StandardCost")
    csp.add_binary("IsCritical", "SafetyStock", lambda crit, ss: (not crit) or ss > 0,
                   "B2 componente crítico requiere SafetyStock > 0")
    csp.add_binary("Category", "ItemType",
                   lambda c, t: c in catalog.categories and t in catalog.categories[c]["item_types"],
                   "B3 ItemType permitido para la categoría")
    csp.add_binary("Category", "BaseUoM",
                   lambda c, u: c in catalog.categories and u in catalog.categories[c]["uom"],
                   "B4 unidad permitida para la categoría")
    csp.add_binary("BaseUoM", "SafetyStock",
                   lambda u, ss: catalog.uom.get(u, False) or ss == ss.to_integral_value(),
                   "B5 SafetyStock entero si la unidad no admite decimales")

    missing = [v for v, n in numbers.items() if n is None]
    return csp, {"attrs_by_cat": attrs_by_cat, "missing": missing}


@dataclass
class Evaluation:
    result: CSPResult
    missing: list[str]
    category: str | None
    attributes: dict
    inferred_attributes: dict
    suggestions: dict
    ambiguous: dict


def evaluate_item(item: dict, catalog: Catalog) -> Evaluation:
    csp, ctx = build_item_csp(item, catalog)
    result = csp.solve()
    category = next(iter(result.domains["Category"])) if len(result.domains["Category"]) == 1 else None
    attrs, inferred = ctx["attrs_by_cat"].get(category, ({}, {})) if category else ({}, {})

    suggestions, ambiguous = {}, {}
    for var, given in (("Category", item.get("Category")), ("ItemType", item.get("ItemType")),
                       ("BaseUoM", item.get("BaseUoM"))):
        if given:
            continue
        dom = result.domains[var]
        if len(dom) == 1:
            suggestions[var] = next(iter(dom))
        elif len(dom) > 1:
            ambiguous[var] = sorted(dom)
    return Evaluation(result, ctx["missing"], category, attrs, inferred, suggestions, ambiguous)


# ---------------------------------------------------------------------------
# Duplicados
# ---------------------------------------------------------------------------
def structural_key(category: str | None, attrs: dict, catalog: Catalog) -> str | None:
    """Clave irrepetible: categoría + atributos clave normalizados. None si falta alguno."""
    if not category or category not in catalog.categories:
        return None
    parts = []
    for key in catalog.categories[category]["key"]:
        if key not in attrs:
            return None
        value = re.sub(r"\s+", " ", str(attrs[key])).strip().casefold()
        parts.append(f"{key}={value}")
    return f"{category.casefold()}|" + "|".join(parts)


def item_text(item: dict) -> str:
    return f"{item.get('ItemName') or ''} {item.get('Description') or ''}"


def find_duplicates(candidate: dict, category: str | None, attrs: dict, catalog_items: list[dict],
                    catalog: Catalog, exclude_sku: str | None = None) -> tuple[list[dict], list[dict]]:
    """Devuelve (duplicados_exactos, similares_por_texto)."""
    key = structural_key(category, attrs, catalog)
    cand_tokens = tokens(item_text(candidate))
    exact, similar = [], []
    for other in catalog_items:
        if other["SKU"] == exclude_sku or other.get("LifecycleStatus") == "Obsoleto":
            continue
        other_cat = other.get("Category")
        other_attrs, _ = prepare_attributes(other, catalog, other_cat)
        other_key = other.get("StructuralKey") or structural_key(other_cat, other_attrs, catalog)
        if key and other_key == key:
            exact.append({"SKU": other["SKU"], "StructuralKey": key})
            continue
        if category and other_cat and other_cat != category:
            continue
        score = jaccard(cand_tokens, tokens(item_text(other)))
        if score >= SIMILARITY_THRESHOLD:
            similar.append({"SKU": other["SKU"], "similitud": round(score, 2)})
    similar.sort(key=lambda s: -s["similitud"])
    return exact, similar
