-- =====================================================================
-- Agente SKU Sentinel & Data Steward - 178823
-- Extensión del esquema item/schema/schema.sql (Item_Master, Inventory_*)
-- Propuesta de mejora del Agente 1: atributos técnicos normalizados,
-- Category, SubstituteGroup y campos financieros/planificación que el
-- agente necesita para validar el maestro.
-- Requiere: item/schema/schema.sql
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Nuevas columnas en Item_Master
-- ---------------------------------------------------------------------
ALTER TABLE Item_Master
    ADD COLUMN IF NOT EXISTS ItemName            VARCHAR(150),
    ADD COLUMN IF NOT EXISTS ItemType            VARCHAR(30),
    ADD COLUMN IF NOT EXISTS Category            VARCHAR(40),
    ADD COLUMN IF NOT EXISTS SubstituteGroup     VARCHAR(40),
    ADD COLUMN IF NOT EXISTS TechnicalAttributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS StandardCost        NUMERIC(14,4) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS ListPrice           NUMERIC(14,4) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS SafetyStock         NUMERIC(14,4) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS IsCritical          BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS AbcClass            CHAR(1),
    ADD COLUMN IF NOT EXISTS StructuralKey       TEXT;

ALTER TABLE Item_Master
    ADD CONSTRAINT ck_item_itemtype CHECK (ItemType IS NULL OR ItemType IN
        ('Materia Prima', 'Subensamble', 'Producto Terminado', 'Consumible', 'Servicio')),
    ADD CONSTRAINT ck_item_costs    CHECK (StandardCost >= 0 AND ListPrice >= 0 AND SafetyStock >= 0),
    ADD CONSTRAINT ck_item_abc      CHECK (AbcClass IS NULL OR AbcClass IN ('A', 'B', 'C'));

-- Clave estructural irrepetible: la calcula el agente a partir de Category y
-- de los atributos clave. Los artículos heredados sin clave quedan en NULL
-- hasta que el agente los audite.
CREATE UNIQUE INDEX IF NOT EXISTS ux_item_structural_key
    ON Item_Master (StructuralKey) WHERE StructuralKey IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_item_category ON Item_Master (Category);
CREATE INDEX IF NOT EXISTS ix_item_attrs ON Item_Master USING GIN (TechnicalAttributes);

-- ---------------------------------------------------------------------
-- 2. Catálogos que forman los dominios del CSP
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS UoM_Catalog (
    UoMCode       VARCHAR(10) PRIMARY KEY,
    Description   VARCHAR(60) NOT NULL,
    AllowsDecimal BOOLEAN NOT NULL DEFAULT FALSE
);

-- Reglas por categoría: tipos y unidades permitidas, atributos clave para
-- detectar duplicados y atributos obligatorios.
CREATE TABLE IF NOT EXISTS Category_Rule (
    Category            VARCHAR(40) PRIMARY KEY,
    AllowedItemTypes    TEXT[] NOT NULL,
    AllowedUoM          TEXT[] NOT NULL,
    KeyAttributes       TEXT[] NOT NULL,
    RequiredAttributes  TEXT[] NOT NULL DEFAULT '{}',
    Keywords            TEXT[] NOT NULL DEFAULT '{}'   -- palabras que identifican la categoría en texto libre
);

-- Dominio de cada atributo técnico: lista cerrada de valores o patrón regex
CREATE TABLE IF NOT EXISTS Attribute_Domain (
    Category      VARCHAR(40) NOT NULL REFERENCES Category_Rule(Category),
    Attribute     VARCHAR(40) NOT NULL,
    AllowedValues TEXT[],
    Pattern       TEXT,
    PRIMARY KEY (Category, Attribute),
    CHECK (AllowedValues IS NOT NULL OR Pattern IS NOT NULL)
);

-- ---------------------------------------------------------------------
-- 3. Conversiones de unidad por artículo (EVT-302 UoMConversionAddedEvent)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Item_UoM_Conversion (
    ItemID    INT NOT NULL REFERENCES Item_Master(ItemID) ON DELETE RESTRICT,
    FromUoM   VARCHAR(10) NOT NULL REFERENCES UoM_Catalog(UoMCode),
    ToUoM     VARCHAR(10) NOT NULL REFERENCES UoM_Catalog(UoMCode),
    Factor    NUMERIC(18,8) NOT NULL CHECK (Factor > 0),   -- 1 FromUoM = Factor ToUoM
    CreatedAt TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (ItemID, FromUoM, ToUoM),
    CHECK (FromUoM <> ToUoM)
);

-- ---------------------------------------------------------------------
-- 4. Relaciones de compatibilidad y sustitución (fuente del grafo Neo4j)
--    COMPATIBLE_WITH: componente -> ensamble/tarjeta con la que funciona
--    SUBSTITUTE_FOR:  componente -> componente que puede reemplazar
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Item_Compatibility (
    ItemID            INT NOT NULL REFERENCES Item_Master(ItemID) ON DELETE RESTRICT,
    RelatedItemID     INT NOT NULL REFERENCES Item_Master(ItemID) ON DELETE RESTRICT,
    Relation          VARCHAR(20) NOT NULL CHECK (Relation IN ('COMPATIBLE_WITH', 'SUBSTITUTE_FOR')),
    PRIMARY KEY (ItemID, RelatedItemID, Relation),
    CHECK (ItemID <> RelatedItemID)
);

-- ---------------------------------------------------------------------
-- 5. Bandeja de revisión: altas que el agente dejó pendientes o rechazó
--    (ItemDataQualityCheckEvent)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Sentinel_Review (
    ReviewID      SERIAL PRIMARY KEY,
    ProposedSKU   VARCHAR(50) NOT NULL,
    Operation     VARCHAR(10) NOT NULL CHECK (Operation IN ('ALTA', 'CAMBIO')),
    Payload       JSONB NOT NULL,
    Decision      VARCHAR(20) NOT NULL CHECK (Decision IN ('APROBADO', 'PENDIENTE_REVISION', 'RECHAZADO')),
    Reasons       JSONB NOT NULL DEFAULT '[]'::jsonb,
    SuggestedSKU  VARCHAR(50),
    Status        VARCHAR(10) NOT NULL DEFAULT 'ABIERTA' CHECK (Status IN ('ABIERTA', 'CERRADA')),
    CreatedAt     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_review_open ON Sentinel_Review (Status, Decision);
