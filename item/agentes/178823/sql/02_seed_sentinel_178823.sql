-- =====================================================================
-- Datos semilla del Agente SKU Sentinel - 178823
-- Línea Gaming PC de TechAssembly S.A. (mismos componentes que los JSON
-- 179804 / 182068): CPU Ryzen 7, Motherboard B650, RAM 16GB DDR5,
-- SSD 1TB NVMe, PSU 750W y GPU RTX, más alternativas y artículos
-- heredados con problemas de calidad para que el agente los detecte.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Catálogos de dominio
-- ---------------------------------------------------------------------
INSERT INTO UoM_Catalog VALUES
 ('PZA',  'Pieza',      FALSE),
 ('CAJA', 'Caja',       FALSE),
 ('G',    'Gramo',      TRUE),
 ('KG',   'Kilogramo',  TRUE),
 ('M',    'Metro',      TRUE);

INSERT INTO Category_Rule VALUES
 ('CPU',                ARRAY['Materia Prima'],      ARRAY['PZA'],          ARRAY['marca','modelo'],                        ARRAY['marca','modelo','socket'],          ARRAY['cpu','procesador','ryzen','intel','core']),
 ('Motherboard',        ARRAY['Materia Prima'],      ARRAY['PZA'],          ARRAY['marca','modelo','chipset'],              ARRAY['chipset','socket','tipo_memoria'],  ARRAY['motherboard','tarjeta madre','placa','b650','x670']),
 ('RAM',                ARRAY['Materia Prima'],      ARRAY['PZA'],          ARRAY['marca','modelo','capacidad','tipo'],     ARRAY['capacidad','tipo'],                 ARRAY['ram','memoria','ddr4','ddr5','dimm']),
 ('Almacenamiento',     ARRAY['Materia Prima'],      ARRAY['PZA'],          ARRAY['marca','modelo','capacidad','interfaz'], ARRAY['capacidad','interfaz'],             ARRAY['ssd','nvme','disco','sata','m.2']),
 ('Fuente de Poder',    ARRAY['Materia Prima'],      ARRAY['PZA'],          ARRAY['marca','modelo','potencia'],             ARRAY['potencia'],                         ARRAY['fuente','psu','power supply']),
 ('Tarjeta de Video',   ARRAY['Materia Prima'],      ARRAY['PZA'],          ARRAY['marca','modelo','vram'],                 ARRAY['modelo','vram'],                    ARRAY['gpu','tarjeta de video','graphics','rtx','radeon']),
 ('Consumible',         ARRAY['Consumible'],         ARRAY['G','KG','M'],   ARRAY['marca','presentacion'],                  ARRAY['presentacion'],                     ARRAY['pasta','termica','cable','cinta']),
 ('Producto Terminado', ARRAY['Producto Terminado'], ARRAY['PZA'],          ARRAY['modelo'],                                ARRAY['modelo'],                           ARRAY['gaming pc','equipo','computadora']);

INSERT INTO Attribute_Domain VALUES
 ('CPU',              'socket',       ARRAY['AM4','AM5','LGA1700'], NULL),
 ('Motherboard',      'socket',       ARRAY['AM4','AM5','LGA1700'], NULL),
 ('Motherboard',      'tipo_memoria', ARRAY['DDR4','DDR5'],         NULL),
 ('Motherboard',      'chipset',      NULL, '^[A-Z][0-9]{3}[A-Z]?$'),
 ('RAM',              'tipo',         ARRAY['DDR4','DDR5'],         NULL),
 ('RAM',              'capacidad',    NULL, '^[0-9]+GB$'),
 ('Almacenamiento',   'capacidad',    NULL, '^[0-9]+(GB|TB)$'),
 ('Almacenamiento',   'interfaz',     ARRAY['NVMe','SATA'],         NULL),
 ('Fuente de Poder',  'potencia',     NULL, '^[0-9]{3,4}W$'),
 ('Tarjeta de Video', 'vram',         NULL, '^[0-9]+GB$'),
 ('Consumible',       'presentacion', NULL, '^[0-9]+(G|KG|M)$');

-- ---------------------------------------------------------------------
-- Maestro de artículos
-- ---------------------------------------------------------------------
INSERT INTO Item_Master (SKU, ItemName, Description, LifecycleStatus, BaseUoM, ItemType, Category,
                         SubstituteGroup, TechnicalAttributes, StandardCost, ListPrice, SafetyStock, IsCritical) VALUES
 ('PC-GAMING-01',       'Gaming PC',                  'Gaming PC Ryzen 7 / RTX',                 'Activo', 'PZA', 'Producto Terminado', 'Producto Terminado', NULL,
   '{"modelo":"GPC-R7-RTX"}', 28500, 34999, 5, FALSE),
 ('CPU-RYZEN-7',        'CPU Ryzen 7',                'Procesador AMD Ryzen 7 7700X AM5',        'Activo', 'PZA', 'Materia Prima', 'CPU', 'CPU-AM5',
   '{"marca":"AMD","modelo":"Ryzen 7 7700X","socket":"AM5"}', 6200, 7400, 10, TRUE),
 ('MB-B650',            'Motherboard B650',           'Tarjeta madre ASUS TUF B650-PLUS',        'Activo', 'PZA', 'Materia Prima', 'Motherboard', 'MB-AM5',
   '{"marca":"ASUS","modelo":"TUF B650-PLUS","chipset":"B650","socket":"AM5","tipo_memoria":"DDR5"}', 3900, 4600, 10, TRUE),
 ('RAM-16GB-DDR5',      'RAM 16GB DDR5',              'Memoria Kingston Fury 16 GB DDR5',        'Activo', 'PZA', 'Materia Prima', 'RAM', 'RAM-DDR5-16',
   '{"marca":"Kingston","modelo":"Fury Beast","capacidad":"16GB","tipo":"DDR5","velocidad":"5600"}', 1100, 1350, 20, TRUE),
 ('RAM-16GB-DDR5-6000', 'RAM 16GB DDR5 6000',         'Memoria Corsair Vengeance 16GB DDR5 6000','Activo', 'PZA', 'Materia Prima', 'RAM', 'RAM-DDR5-16',
   '{"marca":"Corsair","modelo":"Vengeance","capacidad":"16GB","tipo":"DDR5","velocidad":"6000"}', 1250, 1500, 10, FALSE),
 ('RAM-16GB-DDR4',      'RAM 16GB DDR4',              'Memoria Kingston Fury 16GB DDR4',         'Activo', 'PZA', 'Materia Prima', 'RAM', 'RAM-DDR5-16',
   '{"marca":"Kingston","modelo":"Fury Beast","capacidad":"16GB","tipo":"DDR4","velocidad":"3200"}', 800, 990, 10, FALSE),
 ('SSD-1TB-NVME',       'SSD 1TB NVMe',               'SSD Samsung 980 1TB NVMe M.2',            'Activo', 'PZA', 'Materia Prima', 'Almacenamiento', 'SSD-1TB',
   '{"marca":"Samsung","modelo":"980","capacidad":"1TB","interfaz":"NVMe"}', 1300, 1600, 10, TRUE),
 ('SSD-1TB-SATA',       'SSD 1TB SATA',               'SSD Crucial MX500 1TB SATA',              'Activo', 'PZA', 'Materia Prima', 'Almacenamiento', 'SSD-1TB',
   '{"marca":"Crucial","modelo":"MX500","capacidad":"1TB","interfaz":"SATA"}', 900, 1100, 5, FALSE),
 ('SSD-2TB-NVME',       'SSD 2TB NVMe',               'SSD Samsung 990 Pro 2TB NVMe',            'Activo', 'PZA', 'Materia Prima', 'Almacenamiento', 'SSD-2TB',
   '{"marca":"Samsung","modelo":"990 Pro","capacidad":"2TB","interfaz":"NVMe"}', 2400, 2900, 5, FALSE),
 ('SSD-1TB-NVME-G4',    'SSD 1TB NVMe Gen4',          'SSD WD Black SN850X 1TB NVMe Gen4',       'Activo', 'PZA', 'Materia Prima', 'Almacenamiento', 'SSD-NVME-G4',
   '{"marca":"WD","modelo":"SN850X","capacidad":"1TB","interfaz":"NVMe"}', 1450, 1800, 5, FALSE),
 ('PSU-750W',           'Power Supply 750W',          'Fuente de poder Corsair RM750 750W',      'Activo', 'PZA', 'Materia Prima', 'Fuente de Poder', 'PSU-ATX',
   '{"marca":"Corsair","modelo":"RM750","potencia":"750W"}', 1700, 2100, 10, TRUE),
 ('PSU-850W',           'Power Supply 850W',          'Fuente de poder Corsair RM850 850W',      'Activo', 'PZA', 'Materia Prima', 'Fuente de Poder', 'PSU-ATX',
   '{"marca":"Corsair","modelo":"RM850","potencia":"850W"}', 2000, 2400, 5, FALSE),
 ('GPU-RTX',            'Graphics Card RTX',          'Tarjeta de video NVIDIA RTX 4070 12GB',   'Activo', 'PZA', 'Materia Prima', 'Tarjeta de Video', 'GPU-RTX',
   '{"marca":"NVIDIA","modelo":"RTX 4070","vram":"12GB"}', 11500, 13900, 5, TRUE),
 ('PASTA-TERM',         'Pasta térmica',              'Pasta térmica Arctic MX-4 4G',            'Activo', 'G',   'Consumible', 'Consumible', NULL,
   '{"marca":"Arctic","presentacion":"4G"}', 1.5, 3, 200, FALSE),
 -- Artículos heredados (capturados antes del agente) con problemas de calidad
 ('RAM-KF-16-OLD',      'RAM DDR5 16GB Kingston Fury','RAM DDR5 16GB Kingston Fury',             'Activo', 'PZA', 'Materia Prima', 'RAM', NULL,
   '{"marca":"kingston","modelo":"fury beast","capacidad":"16 GB","tipo":"ddr5"}', 1100, 1350, 20, FALSE),
 ('GPU-RTX-OLD',        'Graphics Card RTX 3060',     'Tarjeta de video RTX 3060',               'Activo', 'PZA', 'Materia Prima', 'Tarjeta de Video', 'GPU-RTX',
   '{"marca":"NVIDIA","modelo":"RTX 3060","vram":"12GB"}', 7000, 6500, 2, FALSE),
 ('CPU-RYZEN-5',        'CPU Ryzen 5',                'Procesador AMD Ryzen 5 7600 AM5',         'Activo', 'PZA', 'Materia Prima', 'CPU', 'CPU-AM5',
   '{"marca":"AMD","modelo":"Ryzen 5 7600","socket":"AM5"}', 4300, 5100, 0, TRUE);

-- ---------------------------------------------------------------------
-- Grafo de compatibilidad y sustitución
-- ---------------------------------------------------------------------
INSERT INTO Item_Compatibility (ItemID, RelatedItemID, Relation)
SELECT a.ItemID, b.ItemID, r.rel
FROM (VALUES
  ('CPU-RYZEN-7',        'MB-B650', 'COMPATIBLE_WITH'),
  ('CPU-RYZEN-5',        'MB-B650', 'COMPATIBLE_WITH'),
  ('RAM-16GB-DDR5',      'MB-B650', 'COMPATIBLE_WITH'),
  ('RAM-16GB-DDR5-6000', 'MB-B650', 'COMPATIBLE_WITH'),
  ('SSD-1TB-NVME',       'MB-B650', 'COMPATIBLE_WITH'),
  ('SSD-1TB-SATA',       'MB-B650', 'COMPATIBLE_WITH'),
  ('SSD-2TB-NVME',       'MB-B650', 'COMPATIBLE_WITH'),
  ('SSD-1TB-NVME-G4',    'MB-B650', 'COMPATIBLE_WITH'),
  ('PSU-750W',           'GPU-RTX', 'COMPATIBLE_WITH'),
  ('PSU-850W',           'GPU-RTX', 'COMPATIBLE_WITH'),
  -- sustitutos (se recorren en ambos sentidos)
  ('RAM-16GB-DDR5-6000', 'RAM-16GB-DDR5',   'SUBSTITUTE_FOR'),
  ('RAM-16GB-DDR4',      'RAM-16GB-DDR5',   'SUBSTITUTE_FOR'),
  ('SSD-1TB-SATA',       'SSD-1TB-NVME',    'SUBSTITUTE_FOR'),
  ('SSD-2TB-NVME',       'SSD-1TB-NVME',    'SUBSTITUTE_FOR'),
  ('SSD-1TB-NVME-G4',    'SSD-2TB-NVME',    'SUBSTITUTE_FOR'),
  ('PSU-850W',           'PSU-750W',        'SUBSTITUTE_FOR'),
  ('CPU-RYZEN-5',        'CPU-RYZEN-7',     'SUBSTITUTE_FOR')
) AS r(a, b, rel)
JOIN Item_Master a ON a.SKU = r.a
JOIN Item_Master b ON b.SKU = r.b;

INSERT INTO Item_UoM_Conversion (ItemID, FromUoM, ToUoM, Factor)
SELECT ItemID, 'KG', 'G', 1000 FROM Item_Master WHERE SKU = 'PASTA-TERM';

-- ---------------------------------------------------------------------
-- Movimientos del último año (alimentan existencias y la clasificación ABC).
-- El trigger fn_process_inventory_transaction actualiza Inventory_Stock.
-- ---------------------------------------------------------------------
CREATE FUNCTION pg_temp.mov(p_sku TEXT, p_wh TEXT, p_effect TEXT, p_qty INT, p_days INT) RETURNS VOID
LANGUAGE plpgsql AS $$
DECLARE v_mov INT;
BEGIN
    INSERT INTO Inventory_Movements (MovementType, RequestedBy, CreatedAt)
    VALUES (CASE WHEN p_effect = 'ADD' THEN 'ENTRADA' ELSE 'SALIDA' END, 'seed_178823',
            now() - make_interval(days => p_days))
    RETURNING MovementID INTO v_mov;
    INSERT INTO Inventory_Transaction (MovementID, ItemID, TransactionDate, Effect, Quantity, WarehouseAffected)
    SELECT v_mov, ItemID, now() - make_interval(days => p_days), p_effect, p_qty, p_wh
    FROM Item_Master WHERE SKU = p_sku;
END $$;

-- Entradas (hace 360 días)
SELECT pg_temp.mov(s, w, 'ADD', q, 360) FROM (VALUES
 ('PC-GAMING-01','ALM-PROD',10), ('CPU-RYZEN-7','ALM-PROD',170), ('CPU-RYZEN-5','ALM-MP',20),
 ('MB-B650','ALM-PROD',160), ('RAM-16GB-DDR5','ALM-PROD',300), ('RAM-16GB-DDR5-6000','ALM-MP',30),
 ('RAM-16GB-DDR4','ALM-CEDIS',50), ('RAM-KF-16-OLD','ALM-MP',5), ('SSD-1TB-NVME','ALM-PROD',60),
 ('SSD-1TB-SATA','ALM-CEDIS',40), ('SSD-2TB-NVME','ALM-MP',10), ('SSD-1TB-NVME-G4','ALM-MP',25),
 ('PSU-750W','ALM-PROD',160), ('PSU-850W','ALM-MP',15), ('GPU-RTX','ALM-PROD',140),
 ('GPU-RTX-OLD','ALM-CEDIS',2), ('PASTA-TERM','ALM-PROD',2000)) AS t(s, w, q);

-- Salidas a producción repartidas en el año (30 Gaming PCs por trimestre)
SELECT pg_temp.mov(s, 'ALM-PROD', 'SUBTRACT', q, d) FROM (VALUES
 ('CPU-RYZEN-7',30), ('MB-B650',30), ('RAM-16GB-DDR5',60), ('SSD-1TB-NVME',15),
 ('PSU-750W',30), ('GPU-RTX',30), ('PASTA-TERM',150)) AS t(s, q)
CROSS JOIN (VALUES (300), (200), (100), (20)) AS dd(d);

SELECT pg_temp.mov('SSD-2TB-NVME', 'ALM-MP', 'SUBTRACT', 10, 15);
SELECT pg_temp.mov('CPU-RYZEN-5',  'ALM-MP', 'SUBTRACT', 5, 40);
