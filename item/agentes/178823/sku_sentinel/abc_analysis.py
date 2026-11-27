"""Segmentación ABC por valor de consumo y rotación.

Valor de consumo anual = unidades consumidas (salidas del último año) x StandardCost.
Clase A: hasta 80 % acumulado del valor, B: hasta 95 %, C: resto.
Rotación = unidades consumidas / existencia actual.
"""

from __future__ import annotations

from dataclasses import dataclass

A_LIMIT = 0.80
B_LIMIT = 0.95


@dataclass
class AbcRow:
    sku: str
    consumption_qty: float
    consumption_value: float
    share: float
    cumulative: float
    abc: str
    rotation: float | None
    is_critical: bool
    safety_stock: float
    alerts: list[str]


def classify(rows: list[dict]) -> list[AbcRow]:
    """rows: [{SKU, consumption_qty, StandardCost, stock, IsCritical, SafetyStock}]"""
    data = []
    for r in rows:
        value = float(r["consumption_qty"]) * float(r["StandardCost"])
        data.append((value, r))
    data.sort(key=lambda t: (-t[0], t[1]["SKU"]))
    total = sum(v for v, _ in data) or 1.0

    out: list[AbcRow] = []
    cumulative = 0.0
    for value, r in data:
        share = value / total
        prev = cumulative
        cumulative += share
        # el artículo se clasifica por dónde *empieza* su aporte acumulado:
        # el que cruza el 80 % todavía es A, el que cruza el 95 % todavía es B
        if value == 0:
            abc = "C"
        elif prev < A_LIMIT:
            abc = "A"
        elif prev < B_LIMIT:
            abc = "B"
        else:
            abc = "C"
        stock = float(r.get("stock") or 0)
        rotation = round(float(r["consumption_qty"]) / stock, 2) if stock > 0 else None
        alerts = []
        crit = bool(r.get("IsCritical"))
        ss = float(r.get("SafetyStock") or 0)
        if (abc == "A" or crit) and ss <= 0:
            alerts.append("Artículo A/crítico sin SafetyStock")
        if crit and stock <= 0:
            alerts.append("Componente crítico sin existencias: buscar sustituto")
        if stock > 0 and float(r["consumption_qty"]) == 0:
            alerts.append("Sin consumo en 12 meses: candidato a revisión de ciclo de vida")
        elif abc == "C" and rotation is not None and rotation < 0.5:
            alerts.append("Baja rotación: revisar si conviene seguir comprándolo")
        out.append(AbcRow(r["SKU"], float(r["consumption_qty"]), round(value, 2), round(share, 4),
                          round(cumulative, 4), abc, rotation, crit, ss, alerts))
    return out
