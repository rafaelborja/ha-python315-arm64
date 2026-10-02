"""HA Lite gate helper: print the SQLite DDL (CREATE TABLE + CREATE INDEX) of every recorder table from the installed
db_schema.py, then SCHEMA_VERSION and the SQLAlchemy dialects the import loaded. Run in a separate process
(python3.15 recorder_ddl.py) before and after replacing the recorder files; the DDL must not change."""
import sys

from sqlalchemy.dialects import sqlite
from sqlalchemy.schema import CreateIndex, CreateTable

from homeassistant.components.recorder import db_schema as s

d = sqlite.dialect()
for t in sorted(s.Base.metadata.sorted_tables, key=lambda t: t.name):
    print(str(CreateTable(t).compile(dialect=d)).strip())
    for ix in sorted(t.indexes, key=lambda i: i.name or ""):
        print(str(CreateIndex(ix).compile(dialect=d)).strip())
print("SCHEMA_VERSION", s.SCHEMA_VERSION)
print("sqlalchemy.dialects loaded:",
      sorted({m.split(".")[2] for m in sys.modules if m.startswith("sqlalchemy.dialects.") and m.count(".") >= 2}))
