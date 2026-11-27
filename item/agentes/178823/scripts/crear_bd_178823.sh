#!/usr/bin/env bash
# Crea una base limpia con el esquema del equipo (item/schema/schema.sql),
# la extensión del agente 178823 y los datos semilla.
# Variables: PGHOST, PGPORT, PGUSER, PGPASSWORD (opcionales), DB (default erp_item_178823)
set -euo pipefail
AG="$(cd "$(dirname "$0")/.." && pwd)"
ITEM="$(cd "$AG/../.." && pwd)"
DB="${DB:-erp_item_178823}"

psql -v ON_ERROR_STOP=1 -q -d postgres -c "DROP DATABASE IF EXISTS $DB" -c "CREATE DATABASE $DB"
for f in "$ITEM/schema/schema.sql" \
         "$AG/sql/01_extension_sentinel_178823.sql" \
         "$AG/sql/02_seed_sentinel_178823.sql"; do
  echo ">> ${f#"$ITEM"/}"
  psql -v ON_ERROR_STOP=1 -q -d "$DB" -f "$f" > /dev/null
done
echo "Base $DB lista"
