// =====================================================================
// Consultas MongoDB sobre la bitácora de decisiones del SKU Sentinel (178823)
// Uso: mongosh "mongodb://localhost:27017/erp_simulator" mongo/consultas_mongo_178823.js
// =====================================================================
const col = db.getCollection("item_sentinel_decisions_178823");

print("1. Decisiones por evento y resultado");
printjson(col.aggregate([
  { $group: { _id: { evento: "$event", decision: "$decision" }, total: { $sum: 1 } } },
  { $sort: { "_id.evento": 1, "_id.decision": 1 } }
]).toArray());

print("2. Altas rechazadas con su motivo principal");
printjson(col.find(
  { event: "ItemDataQualityCheckEvent", decision: "RECHAZADO" },
  { _id: 0, sku: 1, "detail.razones.restriccion": 1, "detail.razones.mensaje": 1, "detail.duplicado_de": 1 }
).toArray());

print("3. Duplicados bloqueados y el SKU que se sugirió usar");
printjson(col.find(
  { "detail.duplicado_de": { $ne: null } },
  { _id: 0, sku: 1, "detail.duplicado_de": 1, timestamp: 1 }
).toArray());

print("4. Sustitutos recomendados: BFS vs Greedy");
printjson(col.find(
  { event: "SubstituteRecommendedEvent" },
  { _id: 0, sku: 1, decision: 1, "detail.bfs.sustituto": 1, "detail.greedy.sustituto": 1, "detail.recomendado": 1 }
).toArray());

print("5. Restricciones que más se incumplen");
printjson(col.aggregate([
  { $unwind: "$detail.razones" },
  { $match: { "detail.razones.restriccion": { $exists: true } } },
  { $group: { _id: "$detail.razones.restriccion", veces: { $sum: 1 } } },
  { $sort: { veces: -1 } }
]).toArray());
