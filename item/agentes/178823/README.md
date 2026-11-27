# SKU Sentinel & Data Steward — 178823

Agente inteligente del **Maestro de Artículos (Item Master Data)** del ERP-Simulator. Es el "Agente 1" de `item/Agentes Item.txt`. Revisa cada alta o cambio de SKU antes de que llegue a `Item_Master`:

- bloquea duplicados capturados con otra redacción;
- valida la coherencia entre tipo, unidad de medida, precio, costo y SafetyStock;
- deduce la clasificación cuando falta;
- cuando un componente se agota, recomienda un sustituto compatible con stock;
- segmenta el catálogo con un análisis ABC.

## Qué cubre

| Fuente | Requerimiento | Implementación |
|---|---|---|
| `Agentes Item.txt` · Fase 1 | Deduplicación y clasificación estructural | Clave estructural (`Category` + atributos clave normalizados), similitud de texto y clasificación de `Category` / `ItemType` / `BaseUoM` por AC-3 |
| `Agentes Item.txt` · Fase 2 | `ListPrice >= StandardCost`, unidad válida, `SafetyStock > 0` en críticos | CSP con consistencia de nodo + AC-3 (`sku_sentinel/rules.py`) |
| `Agentes Item.txt` · Fase 3 | Sustituto compatible con la Motherboard y con stock; clasificación por criticidad y rotación | BFS y Greedy Best-First sobre `(:Item)-[:COMPATIBLE_WITH\|SUBSTITUTE_FOR]` en Neo4j; ABC por valor de consumo |
| `Agentes Item.txt` · mejora de esquema | `atributosTecnicos`, `Category`, `SubstituteGroup` | `sql/01_extension_sentinel_178823.sql` |
| `item_master_events_182239.json` | EVT-401 `ItemCreatedEvent` | El alta solo se guarda si el agente la aprueba |
| `item_master_events_182239.json` | EVT-302 `UoMConversionAddedEvent` | Validación de conversiones (factor > 0, unidad existente, consistencia por BFS, sin fracciones en unidades enteras) |
| `item_master_agents_177622.json` | AGT-04-01 `ItemDataQualityCheckEvent` | Se ejecuta antes del alta; lo que no pasa queda en `Sentinel_Review` |
| `item_master_agents_177622.json` | AGT-04-02 `SubstituteRecommendedEvent` | `recomendar_sustituto` |

**En qué se diferencia de otras propuestas del repo:**
- **177622** propone Naive Bayes + k-NN. Este agente usa restricciones explícitas (CSP / AC-3), así que explica qué regla falla.
- **185003** propone el ItemMaster Guardian, que es otro agente: cubre ciclo de vida, BOM y punto de reorden.

## Algoritmos

### CSP con consistencia de nodo y AC-3

Cada artículo propuesto es un CSP.

| Variable | Dominio |
|---|---|
| `Category` | `Category_Rule` (todas, si no se capturó) |
| `ItemType` | 5 tipos válidos |
| `BaseUoM` | `UoM_Catalog` |
| `ListPrice`, `StandardCost`, `SafetyStock`, `IsCritical` | valor capturado |

| Restricción | Tipo | Regla |
|---|---|---|
| U1 | unaria | la unidad existe en `UoM_Catalog` |
| U2 | unaria | la categoría es coherente con los atributos técnicos (obligatorios presentes, valores dentro de `Attribute_Domain`) y con el texto |
| U3 | unaria | `ItemType` válido |
| U4 | unaria | montos no negativos |
| B1 | binaria | `ListPrice >= StandardCost` |
| B2 | binaria | `IsCritical → SafetyStock > 0` |
| B3 | binaria | `ItemType` permitido para la categoría |
| B4 | binaria | unidad permitida para la categoría |
| B5 | binaria | `SafetyStock` entero si la unidad no admite decimales |

- Si un dominio queda vacío, el agente **rechaza** el alta y dice qué restricción lo vació.
- Si una variable no capturada queda con un solo valor, el agente lo **sugiere** (clasificación automática).
- Si queda con varios valores, deja el alta **pendiente de revisión**.

### BFS y Greedy Best-First Search

- **Grafo:** se recorren las relaciones `SUBSTITUTE_FOR` y el `SubstituteGroup` del artículo. Se cargan a Neo4j desde `Item_Compatibility`.
- **Meta:** un artículo de la misma categoría, `Activo`, con stock ≥ cantidad requerida y `COMPATIBLE_WITH` la tarjeta indicada.
- **BFS:** encuentra el sustituto más cercano en número de saltos.
- **Greedy:** expande primero el nodo con menor `h(n)`:

  `h(n) = distancia de atributos clave (los funcionales pesan doble) + 0.25 × |Δprecio| / precio`

Ejemplo con los datos semilla: faltan 20 SSD 1TB NVMe para la Motherboard B650.

| Algoritmo | Sustituto | Saltos | Por qué |
|---|---|---|---|
| BFS | `SSD-1TB-SATA` | 1 | El más cercano en el grafo, pero cambia la interfaz a SATA |
| Greedy | `SSD-1TB-NVME-G4` | 2 | Misma capacidad y misma interfaz NVMe; es el que se recomienda |

### Segmentación ABC

`valor = salidas de 12 meses × StandardCost`; A hasta 80 % acumulado, B hasta 95 %, C el resto. Además genera alertas:
- artículo A o crítico sin SafetyStock;
- componente crítico agotado;
- baja rotación o sin consumo.

## Estructura

```
item/agentes/178823/
├── sku_sentinel/
│   ├── agent.py          # agente: evaluar / registrar / conversion / sustituto / abc / auditar
│   ├── csp.py            # consistencia de nodo + AC-3
│   ├── rules.py          # CSP del artículo y detección de duplicados
│   ├── normalize.py      # normalización de texto y atributos
│   ├── search.py         # BFS, Greedy Best-First y heurística
│   ├── abc_analysis.py   # segmentación ABC
│   ├── repositories.py   # PostgreSQL, Neo4j, MongoDB
│   └── __main__.py       # línea de comandos
├── sql/                  # extensión del esquema, datos semilla, consultas
├── cypher/               # consultas Cypher del grafo
├── mongo/                # consultas sobre la bitácora (.js y .py)
├── scripts/crear_bd_178823.sh
├── tests/                # 26 pruebas (unitarias + integración con PostgreSQL)
└── evidencias/
```

## Cómo ejecutarlo

```bash
cd item/agentes/178823
pip install -r requirements.txt
export PGHOST=localhost PGUSER=postgres PGPASSWORD=postgres
export PG_DSN="host=localhost dbname=erp_item_178823 user=postgres password=postgres"
bash scripts/crear_bd_178823.sh        # schema del equipo + extensión + semilla

python -m pytest -v tests              # pruebas
python -m sku_sentinel demo            # escenarios completos -> evidencias/demo_178823.md

# Con Neo4j y MongoDB (opcional; sin ellos usa Item_Compatibility y un .jsonl)
export NEO4J_URI=bolt://localhost:7687 NEO4J_USER=neo4j NEO4J_PASSWORD=...
export MONGO_URI=mongodb://localhost:27017
python -m sku_sentinel cargar-grafo
python -m sku_sentinel sustituto SSD-1TB-NVME 20 --compatible-con MB-B650
python -m sku_sentinel evaluar mi_articulo.json
python -m sku_sentinel auditar --indexar
```

`demo` espera una base recién creada, porque los escenarios dan de alta SKUs nuevos.

## Evidencias

| Archivo | Contenido |
|---|---|
| `evidencias/demo_178823.md` / `.json` | Las 6 altas, 3 conversiones, sustituto BFS vs Greedy, ABC y auditoría |
| `evidencias/pytest_178823.txt` | 26 pruebas en verde |
| `evidencias/postgres_178823.txt` | Salida de `sql/03_consultas_sentinel_178823.sql` |
| `evidencias/decisiones_178823.jsonl` | Bitácora de decisiones (cuando no hay MongoDB) |

En GitHub Actions (`.github/workflows/agente_sku_sentinel_178823.yml`), el agente corre con PostgreSQL 16, Neo4j 5 y MongoDB 7. Ahí se agregan `carga_grafo_178823.txt`, `cypher_178823.txt` y `mongo_178823.txt`, que se descargan en el artifact `evidencias-sku-sentinel-178823`.
