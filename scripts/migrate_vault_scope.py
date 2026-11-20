"""
ServerGen AI — SQLite Schema Migration for Role Vaults.
Adds `vault_scope` column to `documents` and `document_chunks` if missing.
"""

import sqlite3
from pathlib import Path

db_path = Path("servergen-ai.db")
if not db_path.exists():
    print(f"Database {db_path} does not exist yet. It will be created on first startup.")
    exit(0)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. Documents table
doc_cols = [r[1] for r in cursor.execute("PRAGMA table_info(documents)").fetchall()]
print("Current documents columns:", doc_cols)
if "vault_scope" not in doc_cols:
    cursor.execute("ALTER TABLE documents ADD COLUMN vault_scope VARCHAR(50) NOT NULL DEFAULT 'all'")
    print("SUCCESS: Added 'vault_scope' to 'documents' table")
else:
    print("Column 'vault_scope' already present in 'documents'")

# 2. Document Chunks table
chunk_cols = [r[1] for r in cursor.execute("PRAGMA table_info(document_chunks)").fetchall()]
print("Current document_chunks columns:", chunk_cols)
if "vault_scope" not in chunk_cols:
    cursor.execute("ALTER TABLE document_chunks ADD COLUMN vault_scope VARCHAR(50) NOT NULL DEFAULT 'all'")
    print("SUCCESS: Added 'vault_scope' to 'document_chunks' table")
else:
    print("Column 'vault_scope' already present in 'document_chunks'")

conn.commit()
conn.close()
print("Migration completed successfully.")
