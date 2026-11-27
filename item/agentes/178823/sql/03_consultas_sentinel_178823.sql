-- =====================================================================
-- Consultas PostgreSQL del Agente SKU Sentinel - 178823
-- (las mismas que usa el agente desde sku_sentinel/repositories.py,
--  más consultas de seguimiento para el Data Steward)
-- =====================================================================

-- Q1. Reglas de integridad del maestro que el agente valida (precio < costo,
--     crítico sin SafetyStock, unidad inexistente)
SELECT i.SKU, i.ListPrice, i.StandardCost, i.IsCritical, i.SafetyStock, i.BaseUoM,
       (i.ListPrice < i.StandardCost)                      AS precio_menor_costo,
       (i.IsCritical AND i.SafetyStock = 0)                AS critico_sin_safety,
       (u.UoMCode IS NULL)                                 AS uom_invalida
FROM Item_Master i
LEFT JOIN UoM_Catalog u ON u.UoMCode = i.BaseUoM
WHERE i.ListPrice < i.StandardCost OR (i.IsCritical AND i.SafetyStock = 0) OR u.UoMCode IS NULL;

-- Q2. Posibles duplicados por atributos clave (antes de que el agente indexe StructuralKey)
SELECT Category,
       lower(TechnicalAttributes->>'marca')  AS marca,
       lower(TechnicalAttributes->>'modelo') AS modelo,
       array_agg(SKU ORDER BY SKU)           AS skus
FROM Item_Master
WHERE LifecycleStatus <> 'Obsoleto'
GROUP BY 1, 2, 3
HAVING COUNT(*) > 1;

-- Q3. Existencia total por artículo (meta de la búsqueda de sustitutos)
SELECT i.SKU, i.Category, COALESCE(SUM(s.QuantityAvailable), 0) AS stock
FROM Item_Master i
LEFT JOIN Inventory_Stock s ON s.ItemID = i.ItemID
GROUP BY i.ItemID
ORDER BY stock, i.SKU;

-- Q4. Consumo del último año (entrada de la segmentación ABC)
SELECT i.SKU, i.StandardCost,
       COALESCE(SUM(t.Quantity) FILTER (WHERE t.Effect = 'SUBTRACT'
                AND t.TransactionDate >= now() - interval '365 days'), 0) AS consumo_12m,
       COALESCE(SUM(t.Quantity) FILTER (WHERE t.Effect = 'SUBTRACT'
                AND t.TransactionDate >= now() - interval '365 days'), 0) * i.StandardCost AS valor_consumo
FROM Item_Master i
LEFT JOIN Inventory_Transaction t ON t.ItemID = i.ItemID
GROUP BY i.ItemID
ORDER BY valor_consumo DESC;

-- Q5. Resultado de la clasificación ABC guardada por el agente
SELECT AbcClass, COUNT(*) AS articulos, array_agg(SKU ORDER BY SKU) AS skus
FROM Item_Master GROUP BY AbcClass ORDER BY AbcClass;

-- Q6. Bandeja de revisión del Data Steward (altas rechazadas o pendientes)
SELECT ReviewID, ProposedSKU, Decision, SuggestedSKU,
       jsonb_path_query_array(Reasons, '$[*].mensaje') AS motivos, CreatedAt
FROM Sentinel_Review
WHERE Status = 'ABIERTA'
ORDER BY CreatedAt DESC;

-- Q7. Conversiones de unidad registradas
SELECT i.SKU, c.FromUoM, c.ToUoM, c.Factor
FROM Item_UoM_Conversion c JOIN Item_Master i USING (ItemID)
ORDER BY i.SKU, c.FromUoM;

-- Q8. Grafo de compatibilidad en forma tabular (lo que se carga a Neo4j)
SELECT a.SKU AS origen, c.Relation, b.SKU AS destino
FROM Item_Compatibility c
JOIN Item_Master a ON a.ItemID = c.ItemID
JOIN Item_Master b ON b.ItemID = c.RelatedItemID
ORDER BY c.Relation, origen;
