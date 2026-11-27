"""Línea de comandos del agente SKU Sentinel (178823).

    python -m sku_sentinel demo                     # escenarios completos + reporte en evidencias/
    python -m sku_sentinel evaluar archivo.json     # evalúa un alta sin guardarla
    python -m sku_sentinel registrar archivo.json   # evalúa y guarda si se aprueba
    python -m sku_sentinel conversion SKU DE A FACTOR
    python -m sku_sentinel sustituto SKU CANTIDAD [--compatible-con SKU]
    python -m sku_sentinel abc
    python -m sku_sentinel auditar [--indexar]
    python -m sku_sentinel cargar-grafo              # PostgreSQL -> Neo4j (requiere NEO4J_URI)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from .agent import SkuSentinelAgent
from .repositories import EVIDENCE_DIR, AuditLog, Neo4jGraph, PgRepository, _json_default, make_graph


def dump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=_json_default)


SCENARIOS = [
    ("E1 Alta duplicada con otra redacción", {
        "SKU": "RAM-KINGSTON-16-NEW", "ItemName": "RAM DDR5 16GB Kingston Fury",
        "Description": "RAM DDR5 16GB Kingston Fury", "ItemType": "Materia Prima", "Category": "RAM",
        "BaseUoM": "pza", "TechnicalAttributes": {"Marca": "kingston", "Modelo": "Fury Beast",
                                                  "Capacidad": "16 gb", "Tipo": "ddr5"},
        "StandardCost": 1100, "ListPrice": 1350, "SafetyStock": 20, "IsCritical": True}),
    ("E2 Precio de lista menor al costo", {
        "SKU": "GPU-RTX-4060", "ItemName": "Graphics Card RTX 4060", "Description": "Tarjeta de video NVIDIA RTX 4060 8GB",
        "ItemType": "Materia Prima", "Category": "Tarjeta de Video", "BaseUoM": "PZA",
        "TechnicalAttributes": {"marca": "NVIDIA", "modelo": "RTX 4060", "vram": "8GB"},
        "StandardCost": 7800, "ListPrice": 7200, "SafetyStock": 5, "IsCritical": False}),
    ("E3 Unidad de medida inválida y atributo fuera de dominio", {
        "SKU": "RAM-32GB-DDR7", "ItemName": "RAM 32GB", "Description": "Memoria 32GB DDR7",
        "ItemType": "Materia Prima", "Category": "RAM", "BaseUoM": "CJA",
        "TechnicalAttributes": {"marca": "Kingston", "modelo": "Fury Renegade", "capacidad": "32GB", "tipo": "DDR7"},
        "StandardCost": 2100, "ListPrice": 2500, "SafetyStock": 10, "IsCritical": False}),
    ("E4 Componente crítico sin SafetyStock", {
        "SKU": "PSU-1000W", "ItemName": "Power Supply 1000W", "Description": "Fuente de poder Corsair RM1000x 1000W",
        "ItemType": "Materia Prima", "Category": "Fuente de Poder", "BaseUoM": "PZA",
        "TechnicalAttributes": {"marca": "Corsair", "modelo": "RM1000x", "potencia": "1000W"},
        "StandardCost": 2600, "ListPrice": 3100, "SafetyStock": 0, "IsCritical": True}),
    ("E5 Alta sin Category, ItemType ni UoM: el AC-3 los deduce", {
        "SKU": "SSD-2TB-KC3000", "ItemName": "SSD Kingston KC3000 2TB NVMe",
        "Description": "Unidad SSD Kingston KC3000 2TB NVMe M.2", "TechnicalAttributes": {"modelo": "KC3000"},
        "StandardCost": 2300, "ListPrice": 2790, "SafetyStock": 4, "IsCritical": False, "SubstituteGroup": "SSD-2TB"}),
    ("E6 Texto casi igual sin atributos clave (posible duplicado)", {
        "SKU": "PSU-750-RM", "ItemName": "Power Supply 750W Corsair RM750",
        "Description": "Fuente de poder Corsair RM750 750W", "ItemType": "Materia Prima", "BaseUoM": "PZA",
        "StandardCost": 1700, "ListPrice": 2100, "SafetyStock": 10, "IsCritical": False}),
]


def run_demo(agent: SkuSentinelAgent) -> dict:
    report = {"generado": datetime.now(timezone.utc).isoformat(), "grafo": agent.graph.source,
              "bitacora": agent.audit.target, "escenarios": []}
    lines = [f"# Evidencia de ejecución - SKU Sentinel & Data Steward (178823)\n",
             f"- Fecha: {report['generado']}", f"- Grafo: {agent.graph.source}",
             f"- Bitácora de decisiones: {agent.audit.target}\n"]

    lines.append("## Fase 1-2. Altas de artículos (CSP + AC-3 + deduplicación)\n")
    lines.append("| Escenario | SKU | Decisión | Motivo principal | Sugerencias |")
    lines.append("|---|---|---|---|---|")
    for title, item in SCENARIOS:
        d = agent.registrar_articulo(item)
        motivo = (d.razones or d.advertencias or [{"mensaje": "cumple todas las restricciones"}])[0]
        texto = motivo.get("restriccion", "") + (": " if motivo.get("restriccion") else "") + motivo["mensaje"]
        extra = len(d.razones or d.advertencias) - 1
        if extra > 0:
            texto += f" (+{extra} motivo{'s' if extra > 1 else ''} más)"
        lines.append(f"| {title} | `{d.sku}` | **{d.decision}** | {texto.replace('|', '/')} | "
                     f"{', '.join(f'{k}={v}' for k, v in d.sugerencias.items()) or '-'} |")
        report["escenarios"].append({"escenario": title, **d.to_dict()})

    lines.append("\n## EVT-302. Conversiones de unidad\n")
    lines.append("| Solicitud | Decisión | Motivo |")
    lines.append("|---|---|---|")
    for args in (("PASTA-TERM", "CAJA", "G", 40), ("PASTA-TERM", "KG", "G", 950), ("CPU-RYZEN-7", "CAJA", "PZA", 2.5)):
        d = agent.registrar_conversion(*args)
        lines.append(f"| {args[0]}: 1 {args[1]} = {args[3]} {args[2]} | **{d.decision}** | "
                     f"{d.razones[0]['mensaje'] if d.razones else 'registrada (y su inversa)'} |")
        report["escenarios"].append({"escenario": f"Conversión {args}", **d.to_dict()})

    lines.append("\n## Fase 3. Sustituto para un componente agotado (BFS vs Greedy)\n")
    sub = agent.recomendar_sustituto("SSD-1TB-NVME", 20, compatible_con="MB-B650")
    report["sustituto"] = sub
    lines.append(f"Solicitud: 20 piezas de `SSD-1TB-NVME` compatibles con `MB-B650` (stock actual: {sub['stock_actual']:g}).\n")
    lines.append("| Algoritmo | Sustituto | Camino | Saltos | Nodos expandidos | h(n) |")
    lines.append("|---|---|---|---|---|---|")
    for key in ("bfs", "greedy"):
        r = sub[key]
        lines.append(f"| {r['algoritmo']} | `{r['sustituto']}` | {' → '.join(r['camino'])} | {r['saltos']} | "
                     f"{r['nodos_expandidos']} | {r['h']} |")
    lines.append(f"\n**Decisión:** {sub['decision']}. {sub['accion']}.")

    lines.append("\n## Fase 3. Segmentación ABC\n")
    abc = agent.clasificar_abc()
    report["abc"] = abc
    lines.append("| SKU | Valor de consumo | % acumulado | Clase | Rotación | Alertas |")
    lines.append("|---|---|---|---|---|---|")
    for r in abc:
        lines.append(f"| `{r['sku']}` | {r['consumption_value']:,.2f} | {r['cumulative']:.1%} | **{r['abc']}** | "
                     f"{r['rotation'] if r['rotation'] is not None else '-'} | {'; '.join(r['alerts']) or '-'} |")

    lines.append("\n## Auditoría del catálogo existente\n")
    audit = agent.auditar_catalogo(indexar=True)
    report["auditoria"] = audit
    for v in audit["violaciones"]:
        lines.append(f"- `{v['sku']}`: {'; '.join(v['problemas'])}")
    for dup in audit["duplicados"]:
        lines.append(f"- Duplicado estructural: {', '.join(f'`{s}`' for s in dup['skus'])} (`{dup['clave']}`)")
    lines.append(f"- Claves estructurales indexadas en Item_Master: {audit['claves_indexadas']}")

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "demo_178823.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (EVIDENCE_DIR / "demo_178823.json").write_text(dump(report), encoding="utf-8")
    print("\n".join(lines))
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="sku_sentinel", description="Agente SKU Sentinel & Data Steward (178823)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    for name in ("evaluar", "registrar"):
        s = sub.add_parser(name)
        s.add_argument("archivo")
        s.add_argument("--cambio", action="store_true", help="evaluar como modificación de un SKU existente")
    c = sub.add_parser("conversion")
    c.add_argument("sku"); c.add_argument("de"); c.add_argument("a"); c.add_argument("factor")
    s = sub.add_parser("sustituto")
    s.add_argument("sku"); s.add_argument("cantidad", type=float); s.add_argument("--compatible-con")
    sub.add_parser("abc")
    a = sub.add_parser("auditar"); a.add_argument("--indexar", action="store_true")
    sub.add_parser("cargar-grafo")
    args = p.parse_args(argv)

    repo = PgRepository()
    try:
        if args.cmd == "cargar-grafo":
            import os
            g = Neo4jGraph(repo, os.environ["NEO4J_URI"], os.getenv("NEO4J_USER", "neo4j"),
                           os.getenv("NEO4J_PASSWORD", "password"))
            print(dump(g.load_from_postgres()))
            g.close()
            return 0
        agent = SkuSentinelAgent(repo, make_graph(repo), AuditLog())
        if args.cmd == "demo":
            run_demo(agent)
        elif args.cmd in ("evaluar", "registrar"):
            with open(args.archivo, encoding="utf-8") as fh:
                item = json.load(fh)
            op = "CAMBIO" if args.cambio else "ALTA"
            d = agent.evaluar_articulo(item, op) if args.cmd == "evaluar" else agent.registrar_articulo(item, op)
            print(dump(d.to_dict()))
            return 0 if d.decision != "RECHAZADO" else 2
        elif args.cmd == "conversion":
            print(dump(agent.registrar_conversion(args.sku, args.de, args.a, args.factor).to_dict()))
        elif args.cmd == "sustituto":
            print(dump(agent.recomendar_sustituto(args.sku, args.cantidad, args.compatible_con)))
        elif args.cmd == "abc":
            print(dump(agent.clasificar_abc()))
        elif args.cmd == "auditar":
            print(dump(agent.auditar_catalogo(indexar=args.indexar)))
    finally:
        repo.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
