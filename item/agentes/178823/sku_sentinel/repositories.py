"""Acceso a datos del agente: PostgreSQL (maestro), Neo4j (grafo) y MongoDB (bitácora).

Variables de entorno:
    PG_DSN       default "host=localhost port=5432 dbname=erp_item_178823 user=postgres password=postgres"
    NEO4J_URI    si no está definida, el grafo se lee de la tabla Item_Compatibility
    NEO4J_USER / NEO4J_PASSWORD
    MONGO_URI    si no está definida, la bitácora se escribe en evidencias/decisiones_178823.jsonl
    MONGO_DB     default "erp_simulator"
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg2
import psycopg2.extras

DEFAULT_DSN = "host=localhost port=5432 dbname=erp_item_178823 user=postgres password=postgres"
AGENT_ID = "sku-sentinel-178823"
COLLECTION = "item_sentinel_decisions_178823"
EVIDENCE_DIR = Path(__file__).resolve().parent.parent / "evidencias"


def _json_default(o):
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, (datetime,)):
        return o.isoformat()
    if isinstance(o, set):
        return sorted(o)
    return str(o)


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------
class PgRepository:
    ITEM_COLUMNS = """ItemID, SKU, ItemName, Description, LifecycleStatus, BaseUoM, ItemType, Category,
                      SubstituteGroup, TechnicalAttributes, StandardCost, ListPrice, SafetyStock,
                      IsCritical, AbcClass, StructuralKey"""

    def __init__(self, dsn: str | None = None):
        self.conn = psycopg2.connect(dsn or os.getenv("PG_DSN", DEFAULT_DSN))
        self.conn.autocommit = False

    def close(self):
        self.conn.close()

    def _rows(self, sql, params=()):
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    @staticmethod
    def _item(row: dict) -> dict:
        names = {"itemid": "ItemID", "sku": "SKU", "itemname": "ItemName", "description": "Description",
                 "lifecyclestatus": "LifecycleStatus", "baseuom": "BaseUoM", "itemtype": "ItemType",
                 "category": "Category", "substitutegroup": "SubstituteGroup",
                 "technicalattributes": "TechnicalAttributes", "standardcost": "StandardCost",
                 "listprice": "ListPrice", "safetystock": "SafetyStock", "iscritical": "IsCritical",
                 "abcclass": "AbcClass", "structuralkey": "StructuralKey", "stock": "stock"}
        return {names.get(k, k): v for k, v in row.items()}

    # --- catálogos
    def load_catalog(self):
        from .rules import Catalog
        uom = {r["uomcode"]: r["allowsdecimal"] for r in self._rows("SELECT UoMCode, AllowsDecimal FROM UoM_Catalog")}
        cats = {}
        for r in self._rows("SELECT * FROM Category_Rule"):
            cats[r["category"]] = {"item_types": list(r["alloweditemtypes"]), "uom": list(r["alloweduom"]),
                                   "key": list(r["keyattributes"]), "required": list(r["requiredattributes"]),
                                   "keywords": list(r["keywords"])}
        doms: dict[str, dict] = {}
        for r in self._rows("SELECT * FROM Attribute_Domain"):
            doms.setdefault(r["category"], {})[r["attribute"]] = {
                "allowed": list(r["allowedvalues"]) if r["allowedvalues"] else None, "pattern": r["pattern"]}
        return Catalog(uom, cats, doms)

    # --- artículos
    def items(self) -> list[dict]:
        rows = self._rows(f"""
            SELECT {self.ITEM_COLUMNS},
                   COALESCE((SELECT SUM(QuantityAvailable) FROM Inventory_Stock s
                             WHERE s.ItemID = i.ItemID), 0) AS stock
            FROM Item_Master i ORDER BY SKU""")
        return [self._item(r) for r in rows]

    def item(self, sku: str) -> dict | None:
        return next((i for i in self.items() if i["SKU"] == sku), None)

    def insert_item(self, item: dict, structural_key: str | None) -> int:
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO Item_Master (SKU, ItemName, Description, LifecycleStatus, BaseUoM, ItemType,
                    Category, SubstituteGroup, TechnicalAttributes, StandardCost, ListPrice, SafetyStock,
                    IsCritical, StructuralKey)
                VALUES (%s,%s,%s,'En Desarrollo',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING ItemID""",
                (item["SKU"], item.get("ItemName"), item.get("Description") or item.get("ItemName"),
                 item["BaseUoM"], item["ItemType"], item["Category"], item.get("SubstituteGroup"),
                 json.dumps(item.get("TechnicalAttributes") or {}), item["StandardCost"], item["ListPrice"],
                 item["SafetyStock"], bool(item.get("IsCritical")), structural_key))
            item_id = cur.fetchone()[0]
        self.conn.commit()
        return item_id

    def update_item(self, sku: str, item: dict, structural_key: str | None) -> None:
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE Item_Master SET ItemName=%s, Description=%s, BaseUoM=%s, ItemType=%s, Category=%s,
                    SubstituteGroup=%s, TechnicalAttributes=%s, StandardCost=%s, ListPrice=%s,
                    SafetyStock=%s, IsCritical=%s, StructuralKey=%s
                WHERE SKU=%s""",
                (item.get("ItemName"), item.get("Description"), item["BaseUoM"], item["ItemType"],
                 item["Category"], item.get("SubstituteGroup"), json.dumps(item.get("TechnicalAttributes") or {}),
                 item["StandardCost"], item["ListPrice"], item["SafetyStock"], bool(item.get("IsCritical")),
                 structural_key, sku))
        self.conn.commit()

    def set_structural_key(self, sku: str, key: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute("UPDATE Item_Master SET StructuralKey=%s WHERE SKU=%s", (key, sku))
        self.conn.commit()

    def set_abc(self, classes: dict[str, str]) -> None:
        with self.conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, "UPDATE Item_Master SET AbcClass=%s WHERE SKU=%s",
                                          [(c, s) for s, c in classes.items()])
        self.conn.commit()

    def insert_review(self, sku, operation, payload, decision, reasons, suggested) -> int:
        with self.conn.cursor() as cur:
            cur.execute("""INSERT INTO Sentinel_Review (ProposedSKU, Operation, Payload, Decision, Reasons, SuggestedSKU)
                           VALUES (%s,%s,%s,%s,%s,%s) RETURNING ReviewID""",
                        (sku, operation, json.dumps(payload, default=_json_default), decision,
                         json.dumps(reasons, default=_json_default), suggested))
            rid = cur.fetchone()[0]
        self.conn.commit()
        return rid

    # --- consumo y existencias
    def consumption_last_year(self) -> list[dict]:
        rows = self._rows("""
            SELECT i.SKU, i.StandardCost, i.IsCritical, i.SafetyStock,
                   COALESCE(SUM(t.Quantity) FILTER (WHERE t.Effect = 'SUBTRACT'
                            AND t.TransactionDate >= now() - interval '365 days'), 0) AS consumption_qty,
                   COALESCE((SELECT SUM(QuantityAvailable) FROM Inventory_Stock s WHERE s.ItemID = i.ItemID), 0) AS stock
            FROM Item_Master i
            LEFT JOIN Inventory_Transaction t ON t.ItemID = i.ItemID
            WHERE i.LifecycleStatus <> 'Obsoleto'
            GROUP BY i.ItemID""")
        return [{"SKU": r["sku"], "StandardCost": r["standardcost"], "IsCritical": r["iscritical"],
                 "SafetyStock": r["safetystock"], "consumption_qty": r["consumption_qty"], "stock": r["stock"]}
                for r in rows]

    def stock_by_warehouse(self, sku: str) -> list[dict]:
        return self._rows("""SELECT s.Warehouse, s.QuantityAvailable FROM Inventory_Stock s
                             JOIN Item_Master i USING (ItemID) WHERE i.SKU = %s ORDER BY 2 DESC""", (sku,))

    # --- conversiones de unidad
    def conversions(self, sku: str) -> list[dict]:
        return self._rows("""SELECT c.FromUoM, c.ToUoM, c.Factor FROM Item_UoM_Conversion c
                             JOIN Item_Master i USING (ItemID) WHERE i.SKU = %s""", (sku,))

    def insert_conversion(self, sku: str, from_uom: str, to_uom: str, factor: Decimal) -> None:
        with self.conn.cursor() as cur:
            cur.execute("""INSERT INTO Item_UoM_Conversion (ItemID, FromUoM, ToUoM, Factor)
                           SELECT ItemID, %s, %s, %s FROM Item_Master WHERE SKU = %s
                           ON CONFLICT (ItemID, FromUoM, ToUoM) DO UPDATE SET Factor = EXCLUDED.Factor""",
                        (from_uom, to_uom, factor, sku))
            cur.execute("""INSERT INTO Item_UoM_Conversion (ItemID, FromUoM, ToUoM, Factor)
                           SELECT ItemID, %s, %s, %s FROM Item_Master WHERE SKU = %s
                           ON CONFLICT (ItemID, FromUoM, ToUoM) DO UPDATE SET Factor = EXCLUDED.Factor""",
                        (to_uom, from_uom, Decimal(1) / factor, sku))
        self.conn.commit()

    # --- grafo (fuente)
    def compatibility_edges(self) -> list[dict]:
        return self._rows("""SELECT a.SKU AS source, b.SKU AS target, c.Relation AS relation
                             FROM Item_Compatibility c
                             JOIN Item_Master a ON a.ItemID = c.ItemID
                             JOIN Item_Master b ON b.ItemID = c.RelatedItemID
                             ORDER BY 1, 2""")


# ---------------------------------------------------------------------------
# Grafo de compatibilidad
# ---------------------------------------------------------------------------
class PgGraph:
    """Grafo leído de Item_Compatibility (respaldo cuando no hay Neo4j)."""
    source = "PostgreSQL (Item_Compatibility)"

    def __init__(self, repo: PgRepository):
        self.repo = repo
        self.refresh()

    def refresh(self):
        self.items = {i["SKU"]: i for i in self.repo.items()}
        self.edges = self.repo.compatibility_edges()

    def substitute_neighbors(self, sku: str) -> list[str]:
        out = set()
        for e in self.edges:
            if e["relation"] == "SUBSTITUTE_FOR":
                if e["source"] == sku:
                    out.add(e["target"])
                elif e["target"] == sku:
                    out.add(e["source"])
        group = (self.items.get(sku) or {}).get("SubstituteGroup")
        if group:
            out |= {s for s, i in self.items.items() if i.get("SubstituteGroup") == group and s != sku}
        return sorted(out)

    def compatible_with(self, sku: str) -> set[str]:
        return {e["target"] for e in self.edges if e["relation"] == "COMPATIBLE_WITH" and e["source"] == sku}


class Neo4jGraph:
    """Mismo contrato que PgGraph, resuelto con Cypher sobre Neo4j."""
    source = "Neo4j (Cypher)"

    def __init__(self, repo: PgRepository, uri: str, user: str, password: str):
        from neo4j import GraphDatabase
        self.repo = repo
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.driver.verify_connectivity()
        self.items = {i["SKU"]: i for i in repo.items()}

    def close(self):
        self.driver.close()

    def load_from_postgres(self) -> dict:
        items = [{"sku": i["SKU"], "name": i["ItemName"], "category": i["Category"],
                  "group": i["SubstituteGroup"], "status": i["LifecycleStatus"],
                  "price": float(i["ListPrice"] or 0), "stock": float(i["stock"] or 0)}
                 for i in self.repo.items()]
        edges = self.repo.compatibility_edges()
        with self.driver.session() as s:
            s.run("CREATE CONSTRAINT item_sku_178823 IF NOT EXISTS FOR (n:Item) REQUIRE n.sku IS UNIQUE").consume()
            s.run("""UNWIND $rows AS r
                     MERGE (i:Item {sku: r.sku})
                     SET i.name = r.name, i.category = r.category, i.status = r.status,
                         i.list_price = r.price, i.stock = r.stock, i.substitute_group = r.group
                     WITH i, r WHERE r.group IS NOT NULL
                     MERGE (g:SubstituteGroup {code: r.group})
                     MERGE (i)-[:IN_GROUP]->(g)""", rows=items).consume()
            for rel in ("COMPATIBLE_WITH", "SUBSTITUTE_FOR"):
                s.run(f"""UNWIND $rows AS r
                          MATCH (a:Item {{sku: r.source}}), (b:Item {{sku: r.target}})
                          MERGE (a)-[:{rel}]->(b)""",
                      rows=[e for e in edges if e["relation"] == rel]).consume()
        return {"items": len(items), "edges": len(edges)}

    def substitute_neighbors(self, sku: str) -> list[str]:
        query = """
            MATCH (i:Item {sku: $sku})
            OPTIONAL MATCH (i)-[:SUBSTITUTE_FOR]-(s:Item)
            OPTIONAL MATCH (i)-[:IN_GROUP]->(:SubstituteGroup)<-[:IN_GROUP]-(g:Item)
            WITH collect(DISTINCT s.sku) + collect(DISTINCT g.sku) AS skus
            UNWIND skus AS sku RETURN DISTINCT sku"""
        with self.driver.session() as s:
            return sorted(r["sku"] for r in s.run(query, sku=sku) if r["sku"] and r["sku"] != sku)

    def compatible_with(self, sku: str) -> set[str]:
        with self.driver.session() as s:
            return {r["sku"] for r in s.run(
                "MATCH (:Item {sku: $sku})-[:COMPATIBLE_WITH]->(b:Item) RETURN b.sku AS sku", sku=sku)}


def make_graph(repo: PgRepository):
    uri = os.getenv("NEO4J_URI")
    if uri:
        return Neo4jGraph(repo, uri, os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "password"))
    return PgGraph(repo)


# ---------------------------------------------------------------------------
# Bitácora de decisiones
# ---------------------------------------------------------------------------
class AuditLog:
    """Guarda cada decisión del agente en MongoDB (o en un .jsonl si no hay MongoDB)."""

    def __init__(self, path: Path | None = None):
        self.collection = None
        self.path = path or EVIDENCE_DIR / "decisiones_178823.jsonl"
        uri = os.getenv("MONGO_URI")
        if uri:
            from pymongo import MongoClient
            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            client.admin.command("ping")
            self.collection = client[os.getenv("MONGO_DB", "erp_simulator")][COLLECTION]
            self.target = f"MongoDB {COLLECTION}"
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                self.target = str(self.path.relative_to(EVIDENCE_DIR.parent))
            except ValueError:
                self.target = str(self.path)

    def record(self, event: str, sku: str | None, decision: str, detail: dict) -> dict:
        doc = {"agent": AGENT_ID, "event": event, "sku": sku, "decision": decision,
               "detail": json.loads(json.dumps(detail, default=_json_default)),
               "timestamp": datetime.now(timezone.utc).isoformat()}
        if self.collection is not None:
            self.collection.insert_one(dict(doc))
        else:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(doc, ensure_ascii=False) + "\n")
        return doc
