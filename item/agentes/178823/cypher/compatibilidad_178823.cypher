// =====================================================================
// Grafo de compatibilidad y sustitutos - SKU Sentinel (178823)
// Se carga desde PostgreSQL con:  python -m sku_sentinel cargar-grafo
//
//   (:Item {sku, name, category, status, list_price, stock, substitute_group})
//   (:Item)-[:COMPATIBLE_WITH]->(:Item)     componente -> tarjeta/ensamble
//   (:Item)-[:SUBSTITUTE_FOR]->(:Item)      puede reemplazar a (se recorre sin dirección)
//   (:Item)-[:IN_GROUP]->(:SubstituteGroup) grupo de sustitución (Category/SubstituteGroup)
// =====================================================================

// 1. Restricción de unicidad
CREATE CONSTRAINT item_sku_178823 IF NOT EXISTS FOR (n:Item) REQUIRE n.sku IS UNIQUE;

// 2. Vecinos de sustitución de un artículo (lo que expande el agente en BFS / Greedy)
//    :param sku => 'SSD-1TB-NVME'
MATCH (i:Item {sku: $sku})
OPTIONAL MATCH (i)-[:SUBSTITUTE_FOR]-(s:Item)
OPTIONAL MATCH (i)-[:IN_GROUP]->(:SubstituteGroup)<-[:IN_GROUP]-(g:Item)
WITH collect(DISTINCT s.sku) + collect(DISTINCT g.sku) AS vecinos
UNWIND vecinos AS sku
RETURN DISTINCT sku ORDER BY sku;

// 3. Equivalente Cypher del BFS: sustituto con stock más cercano en saltos,
//    compatible con la tarjeta madre.  :param cantidad => 20; :param tarjeta => 'MB-B650'
MATCH p = (o:Item {sku: $sku})-[:SUBSTITUTE_FOR*1..4]-(c:Item)
WHERE c.sku <> o.sku AND c.category = o.category AND c.status = 'Activo'
  AND c.stock >= $cantidad
  AND (c)-[:COMPATIBLE_WITH]->(:Item {sku: $tarjeta})
WITH c, p ORDER BY length(p)
WITH c, collect(p)[0] AS p
RETURN c.sku AS sustituto, length(p) AS saltos, c.stock AS stock, c.list_price AS precio,
       [n IN nodes(p) | n.sku] AS camino
ORDER BY saltos, sustituto
LIMIT 5;

// 4. Componentes críticos agotados y cuántos sustitutos compatibles con stock tienen
MATCH (i:Item)-[:COMPATIBLE_WITH]->(mb:Item {sku: $tarjeta})
WHERE i.stock = 0
OPTIONAL MATCH (i)-[:SUBSTITUTE_FOR*1..3]-(s:Item)-[:COMPATIBLE_WITH]->(mb)
WHERE s.stock > 0 AND s.status = 'Activo'
RETURN i.sku AS agotado, collect(DISTINCT s.sku) AS sustitutos_con_stock;

// 5. Componentes compatibles con una tarjeta madre, por categoría
MATCH (c:Item)-[:COMPATIBLE_WITH]->(:Item {sku: $tarjeta})
RETURN c.category AS categoria, collect(c.sku + ' (' + toString(c.stock) + ')') AS componentes
ORDER BY categoria;

// 6. Grupos de sustitución con un solo artículo (riesgo: no hay alternativa)
MATCH (g:SubstituteGroup)<-[:IN_GROUP]-(i:Item)
WITH g, collect(i.sku) AS items
WHERE size(items) = 1
RETURN g.code AS grupo, items;

// 7. Vista para Neo4j Browser
MATCH p = (:Item {sku: $sku})-[:SUBSTITUTE_FOR|IN_GROUP*1..3]-()
RETURN p;
