"""Consultas MongoDB sobre la bitácora del SKU Sentinel (178823).

Mismas consultas que consultas_mongo_178823.js, ejecutadas con pymongo
(se usan en GitHub Actions). Variables: MONGO_URI, MONGO_DB.
"""

import json
import os
import sys

from pymongo import MongoClient

col = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[
    os.getenv("MONGO_DB", "erp_simulator")]["item_sentinel_decisions_178823"]


def show(title, rows):
    print(f"\n{title}")
    print(json.dumps(list(rows), indent=2, ensure_ascii=False, default=str))


show("1. Decisiones por evento y resultado", col.aggregate([
    {"$group": {"_id": {"evento": "$event", "decision": "$decision"}, "total": {"$sum": 1}}},
    {"$sort": {"_id.evento": 1, "_id.decision": 1}}]))
show("2. Altas rechazadas con su motivo", col.find(
    {"event": "ItemDataQualityCheckEvent", "decision": "RECHAZADO"},
    {"_id": 0, "sku": 1, "detail.razones.restriccion": 1, "detail.razones.mensaje": 1, "detail.duplicado_de": 1}))
show("3. Duplicados bloqueados y SKU sugerido", col.find(
    {"detail.duplicado_de": {"$ne": None}}, {"_id": 0, "sku": 1, "detail.duplicado_de": 1, "timestamp": 1}))
show("4. Sustitutos: BFS vs Greedy", col.find(
    {"event": "SubstituteRecommendedEvent"},
    {"_id": 0, "sku": 1, "decision": 1, "detail.bfs.sustituto": 1, "detail.greedy.sustituto": 1,
     "detail.recomendado": 1}))
show("5. Restricciones que más se incumplen", col.aggregate([
    {"$unwind": "$detail.razones"},
    {"$match": {"detail.razones.restriccion": {"$exists": True}}},
    {"$group": {"_id": "$detail.razones.restriccion", "veces": {"$sum": 1}}},
    {"$sort": {"veces": -1}}]))

total = col.count_documents({})
print(f"\nDocumentos en la bitácora: {total}")
sys.exit(0 if total > 0 else 1)
