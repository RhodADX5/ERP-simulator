"""SKU Sentinel & Data Steward - Agente 1 del Maestro de Artículos (178823).

Fases (item/Agentes Item.txt):
  1. Deduplicación y clasificación estructural      -> evaluar_articulo / registrar_articulo
  2. Validación de reglas de integridad del maestro -> CSP con consistencia de nodo + AC-3
  3. Sustitutos y segmentación ABC                  -> recomendar_sustituto (BFS + Greedy), clasificar_abc

Eventos que atiende (item_master_events_182239.json / item_master_agents_177622.json):
  ItemDataQualityCheckEvent (antes de ItemCreatedEvent), ItemCreatedEvent, UoMConversionAddedEvent,
  SubstituteRecommendedEvent.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import asdict, dataclass, field
from decimal import Decimal

from .abc_analysis import classify
from .repositories import AuditLog, PgRepository, make_graph
from .rules import evaluate_item, find_duplicates, prepare_attributes, structural_key
from .search import bfs, greedy_best_first, similarity_heuristic

APROBADO, PENDIENTE, RECHAZADO = "APROBADO", "PENDIENTE_REVISION", "RECHAZADO"


@dataclass
class Decision:
    sku: str
    operacion: str
    decision: str
    razones: list[dict] = field(default_factory=list)
    advertencias: list[dict] = field(default_factory=list)
    sugerencias: dict = field(default_factory=dict)
    duplicado_de: str | None = None
    similares: list[dict] = field(default_factory=list)
    atributos_normalizados: dict = field(default_factory=dict)
    atributos_inferidos: dict = field(default_factory=dict)
    clave_estructural: str | None = None
    revisiones_ac3: int = 0
    evento: str | None = None
    item_id: int | None = None
    review_id: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class SkuSentinelAgent:
    def __init__(self, repo: PgRepository, graph=None, audit: AuditLog | None = None):
        self.repo = repo
        self.graph = graph or make_graph(repo)
        self.audit = audit or AuditLog()
        self.catalog = repo.load_catalog()

    # ------------------------------------------------------------------
    # Fase 1 y 2: calidad del alta / cambio
    # ------------------------------------------------------------------
    def evaluar_articulo(self, propuesta: dict, operacion: str = "ALTA") -> Decision:
        """Evalúa sin escribir en el maestro (ItemDataQualityCheckEvent)."""
        sku = (propuesta.get("SKU") or "").strip()
        items = self.repo.items()
        existing = next((i for i in items if i["SKU"] == sku), None)
        d = Decision(sku=sku, operacion=operacion, decision=APROBADO, evento="ItemDataQualityCheckEvent")

        if not sku:
            d.razones.append({"codigo": "SKU_REQUERIDO", "mensaje": "El SKU es obligatorio"})
        elif operacion == "ALTA" and existing:
            d.razones.append({"codigo": "SKU_EXISTENTE", "mensaje": f"El SKU {sku} ya existe en Item_Master"})
        elif operacion == "CAMBIO" and not existing:
            d.razones.append({"codigo": "SKU_INEXISTENTE", "mensaje": f"El SKU {sku} no existe"})

        propuesta = self._with_brand(propuesta, items)
        ev = evaluate_item(propuesta, self.catalog)
        d.revisiones_ac3 = ev.result.revisions
        d.sugerencias = ev.suggestions
        d.atributos_normalizados = ev.attributes
        d.atributos_inferidos = ev.inferred_attributes

        for var in ev.missing:
            d.razones.append({"codigo": "DATO_FALTANTE", "restriccion": var, "mensaje": f"Falta {var}"})
        for c in ev.result.conflicts:
            d.razones.append({"codigo": "RESTRICCION", "restriccion": c.constraint,
                              "variable": c.variable, "mensaje": c.detail})
        for var, values in ev.ambiguous.items():
            d.advertencias.append({"codigo": "CLASIFICACION_AMBIGUA", "variable": var,
                                   "mensaje": f"{var} admite {values}; requiere decisión del Data Steward"})

        if ev.category:
            d.clave_estructural = structural_key(ev.category, ev.attributes, self.catalog)
            exact, similar = find_duplicates(propuesta, ev.category, ev.attributes, items, self.catalog,
                                             exclude_sku=sku if operacion == "CAMBIO" else None)
            if exact:
                d.duplicado_de = exact[0]["SKU"]
                d.razones.append({"codigo": "DUPLICADO", "restriccion": "Clave estructural irrepetible",
                                  "mensaje": f"Mismos atributos clave que {exact[0]['SKU']} ({exact[0]['StructuralKey']})"})
            d.similares = similar
            if similar and not exact:
                d.advertencias.append({"codigo": "POSIBLE_DUPLICADO",
                                       "mensaje": f"Texto muy parecido a {[s['SKU'] for s in similar]}"})
            if not d.clave_estructural:
                missing_keys = [k for k in self.catalog.categories[ev.category]["key"] if k not in ev.attributes]
                d.advertencias.append({"codigo": "CLAVE_INCOMPLETA",
                                       "mensaje": f"Faltan atributos clave {missing_keys}; solo se pudo comparar el texto"})

        if ev.inferred_attributes:
            d.advertencias.append({"codigo": "ATRIBUTOS_INFERIDOS",
                                   "mensaje": f"Se tomaron del texto: {ev.inferred_attributes}"})

        if d.razones:
            d.decision = RECHAZADO
        elif d.advertencias and any(a["codigo"] in ("POSIBLE_DUPLICADO", "CLASIFICACION_AMBIGUA", "CLAVE_INCOMPLETA")
                                    for a in d.advertencias):
            d.decision = PENDIENTE
        if d.decision == RECHAZADO and d.duplicado_de:
            d.sugerencias["UsarSKUExistente"] = d.duplicado_de
        return d

    def registrar_articulo(self, propuesta: dict, operacion: str = "ALTA") -> Decision:
        """Evalúa y, si procede, escribe en Item_Master (ItemCreatedEvent). Si no, abre revisión."""
        d = self.evaluar_articulo(propuesta, operacion)
        if d.decision == APROBADO:
            item = dict(propuesta)
            for var, val in d.sugerencias.items():
                if var in ("Category", "ItemType", "BaseUoM"):
                    item[var] = val
            item["BaseUoM"] = item["BaseUoM"].upper()
            item["TechnicalAttributes"] = d.atributos_normalizados
            if operacion == "ALTA":
                d.item_id = self.repo.insert_item(item, d.clave_estructural)
                d.evento = "ItemCreatedEvent"
            else:
                self.repo.update_item(item["SKU"], item, d.clave_estructural)
                d.evento = "ItemUpdatedEvent"
        else:
            d.review_id = self.repo.insert_review(d.sku or "(sin SKU)", operacion, propuesta, d.decision,
                                                  d.razones + d.advertencias, d.duplicado_de)
        self.audit.record(d.evento, d.sku, d.decision, d.to_dict())
        return d

    def _with_brand(self, propuesta: dict, items: list[dict]) -> dict:
        """Si falta la marca, la busca en el texto entre las marcas que ya existen en el catálogo."""
        attrs = dict(propuesta.get("TechnicalAttributes") or {})
        if any(k.lower() == "marca" for k in attrs):
            return propuesta
        text = f"{propuesta.get('ItemName') or ''} {propuesta.get('Description') or ''}".lower()
        brands = {str((i.get("TechnicalAttributes") or {}).get("marca", "")).strip() for i in items}
        for brand in sorted(b for b in brands if b):
            if re.search(rf"\b{re.escape(brand.lower())}\b", text):
                attrs["marca"] = brand
                return {**propuesta, "TechnicalAttributes": attrs}
        return propuesta

    # ------------------------------------------------------------------
    # EVT-302: conversiones de unidad
    # ------------------------------------------------------------------
    def registrar_conversion(self, sku: str, from_uom: str, to_uom: str, factor) -> Decision:
        from_uom, to_uom = from_uom.upper(), to_uom.upper()
        d = Decision(sku=sku, operacion="CONVERSION_UOM", decision=APROBADO, evento="UoMConversionAddedEvent")
        item = self.repo.item(sku)
        factor = Decimal(str(factor))
        if not item:
            d.razones.append({"codigo": "SKU_INEXISTENTE", "mensaje": f"{sku} no existe"})
        for u in (from_uom, to_uom):
            if u not in self.catalog.uom:
                d.razones.append({"codigo": "UOM_INVALIDA", "mensaje": f"'{u}' no existe en UoM_Catalog"})
        if from_uom == to_uom:
            d.razones.append({"codigo": "UOM_IGUAL", "mensaje": "Origen y destino son la misma unidad"})
        if factor <= 0:
            d.razones.append({"codigo": "FACTOR_INVALIDO", "mensaje": "El factor debe ser mayor que 0"})
        if item and not d.razones:
            if item["BaseUoM"] not in (from_uom, to_uom) and \
                    self._conversion_factor(sku, item["BaseUoM"], from_uom) is None:
                d.razones.append({"codigo": "SIN_RUTA_A_BASE",
                                  "mensaje": f"La conversión debe involucrar la unidad base {item['BaseUoM']} "
                                             "o una unidad ya convertible a ella"})
            current = self._conversion_factor(sku, from_uom, to_uom)
            if current is not None and abs(current - factor) > Decimal("0.000001") * max(current, factor):
                d.razones.append({"codigo": "CONVERSION_INCONSISTENTE",
                                  "mensaje": f"Ya existe una ruta {from_uom}->{to_uom} con factor {format(current.normalize(), 'f')}"})
            if to_uom == item["BaseUoM"] and not self.catalog.uom[to_uom] and factor != factor.to_integral_value():
                d.razones.append({"codigo": "FACTOR_FRACCIONARIO",
                                  "mensaje": f"La unidad base {to_uom} no admite decimales"})
        if d.razones:
            d.decision = RECHAZADO
        else:
            self.repo.insert_conversion(sku, from_uom, to_uom, factor)
        self.audit.record(d.evento, sku, d.decision,
                          {**d.to_dict(), "conversion": {"from": from_uom, "to": to_uom, "factor": factor}})
        return d

    def _conversion_factor(self, sku: str, a: str, b: str) -> Decimal | None:
        """BFS sobre las conversiones registradas: factor acumulado de a hacia b."""
        if a == b:
            return Decimal(1)
        graph: dict[str, list[tuple[str, Decimal]]] = {}
        for c in self.repo.conversions(sku):
            graph.setdefault(c["fromuom"], []).append((c["touom"], Decimal(c["factor"])))
        queue, seen = deque([(a, Decimal(1))]), {a}
        while queue:
            node, acc = queue.popleft()
            for nxt, f in graph.get(node, []):
                if nxt in seen:
                    continue
                if nxt == b:
                    return acc * f
                seen.add(nxt)
                queue.append((nxt, acc * f))
        return None

    # ------------------------------------------------------------------
    # Fase 3: sustitutos
    # ------------------------------------------------------------------
    def recomendar_sustituto(self, sku: str, cantidad: float, compatible_con: str | None = None) -> dict:
        items = {i["SKU"]: i for i in self.repo.items()}
        origin = items.get(sku)
        if not origin:
            raise ValueError(f"{sku} no existe")
        rule = self.catalog.categories.get(origin["Category"], {"key": [], "required": []})

        def view(it):
            attrs, _ = prepare_attributes(it, self.catalog, it.get("Category"))
            return {"SKU": it["SKU"], "attrs": attrs, "ListPrice": it["ListPrice"]}

        origin_view = view(origin)
        compat_cache: dict[str, set[str]] = {}

        def is_goal(candidate: str) -> bool:
            it = items.get(candidate)
            if not it or candidate == sku or it["LifecycleStatus"] != "Activo":
                return False
            if it["Category"] != origin["Category"] or float(it["stock"]) < cantidad:
                return False
            if compatible_con:
                if candidate not in compat_cache:
                    compat_cache[candidate] = self.graph.compatible_with(candidate)
                if compatible_con not in compat_cache[candidate]:
                    return False
            return True

        def h(candidate: str) -> float:
            it = items.get(candidate)
            return similarity_heuristic(origin_view, view(it), rule["key"], rule["required"]) if it else 9.0

        stock_origin = float(origin["stock"])
        bfs_res = bfs(sku, self.graph.substitute_neighbors, is_goal)
        greedy_res = greedy_best_first(sku, self.graph.substitute_neighbors, is_goal, h)

        recommended = greedy_res.found or bfs_res.found
        if stock_origin >= cantidad:
            decision, accion = "SIN_ACCION", f"{sku} tiene {stock_origin:g} piezas; no requiere sustituto"
        elif recommended:
            decision = "RECOMENDACION"
            accion = (f"Usar {recommended} en lugar de {sku} ({stock_origin:g} disponibles de {cantidad:g}"
                      + (f", compatible con {compatible_con}" if compatible_con else "") + ")")
        else:
            decision, accion = "ESCALAR", f"Sin sustituto compatible con stock para {sku}: escalar a Compras"

        def describe(res):
            return {"algoritmo": res.algorithm, "sustituto": res.found, "camino": res.path, "saltos": res.hops,
                    "nodos_expandidos": len(res.explored), "orden_expansion": res.explored,
                    "h": h(res.found) if res.found else None,
                    "stock": float(items[res.found]["stock"]) if res.found else None}

        out = {"sku": sku, "cantidad_requerida": cantidad, "stock_actual": stock_origin,
               "compatible_con": compatible_con, "grafo": self.graph.source,
               "decision": decision, "accion": accion, "recomendado": recommended if decision == "RECOMENDACION" else None,
               "bfs": describe(bfs_res), "greedy": describe(greedy_res)}
        self.audit.record("SubstituteRecommendedEvent", sku, decision, out)
        return out

    # ------------------------------------------------------------------
    # Fase 3: segmentación ABC
    # ------------------------------------------------------------------
    def clasificar_abc(self, persistir: bool = True) -> list[dict]:
        rows = classify(self.repo.consumption_last_year())
        if persistir:
            self.repo.set_abc({r.sku: r.abc for r in rows})
        out = [asdict(r) for r in rows]
        self.audit.record("ItemAbcClassifiedEvent", None, "CLASIFICADO",
                          {"resumen": {c: sum(1 for r in rows if r.abc == c) for c in "ABC"},
                           "alertas": [{"sku": r.sku, "alertas": r.alerts} for r in rows if r.alerts]})
        return out

    # ------------------------------------------------------------------
    # Auditoría del catálogo completo
    # ------------------------------------------------------------------
    def auditar_catalogo(self, indexar: bool = False) -> dict:
        """Corre el CSP sobre todo Item_Master y busca duplicados entre artículos existentes."""
        items = self.repo.items()
        violaciones, keys = [], {}
        for it in items:
            if it["LifecycleStatus"] == "Obsoleto":
                continue
            ev = evaluate_item(it, self.catalog)
            problems = [f"{c.constraint}: {c.detail}" for c in ev.result.conflicts]
            if problems:
                violaciones.append({"sku": it["SKU"], "problemas": problems})
            key = structural_key(ev.category, ev.attributes, self.catalog) if ev.category else None
            if key:
                keys.setdefault(key, []).append(it["SKU"])
        duplicados = [{"clave": k, "skus": v} for k, v in sorted(keys.items()) if len(v) > 1]
        indexados = 0
        if indexar:
            for key, skus in keys.items():
                if len(skus) == 1:
                    current = next(i for i in items if i["SKU"] == skus[0]).get("StructuralKey")
                    if current != key:
                        self.repo.set_structural_key(skus[0], key)
                        indexados += 1
        out = {"articulos_revisados": len(items), "violaciones": violaciones,
               "duplicados": duplicados, "claves_indexadas": indexados}
        self.audit.record("ItemCatalogAuditEvent", None,
                          "CON_HALLAZGOS" if violaciones or duplicados else "SIN_HALLAZGOS", out)
        return out
