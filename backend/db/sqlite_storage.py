"""Reusable SQLite storage class.

Mirrors the conventions of VTPermStorage but for SQLite.
Pattern:
  storage = SQLiteStorage("data/gtm.sqlite")
  storage.run_script_file("db/schema.sql")
  row = storage.get_one("companies", {"domain": "example.com"})
  rows = storage.get_many("companies", {"status": "new"}, limit=50, order_by="created_at DESC")
  cid = storage.insert_one("companies", {"name": "X", "domain": "x.com"})
  storage.update_one("companies", {"id": cid}, {"status": "enriched"})
  storage.delete_one("companies", {"id": cid})

Notes:
- A single connection with check_same_thread=False + Lock keeps writes serialized.
- Rows are returned as plain dicts (not sqlite3.Row).
- query dicts use equality only. For richer filtering use raw execute().
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Sequence


class SQLiteStorage:
    def __init__(self, db_path: str, *, foreign_keys: bool = True, wal: bool = True) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
            isolation_level=None,  # autocommit; we manage txn explicitly
        )
        self._conn.row_factory = sqlite3.Row
        if foreign_keys:
            self._conn.execute("PRAGMA foreign_keys = ON")
        if wal:
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")

    # ----- low level -----
    def execute(self, sql: str, params: Sequence | dict | None = None) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params or [])

    def executemany(self, sql: str, seq_of_params: Iterable[Sequence | dict]) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.executemany(sql, seq_of_params)

    def executescript(self, sql_script: str) -> None:
        with self._lock:
            self._conn.executescript(sql_script)

    def run_script_file(self, path: str) -> None:
        sql = Path(path).read_text(encoding="utf-8")
        self.executescript(sql)

    def fetchone(self, sql: str, params: Sequence | dict | None = None) -> dict | None:
        cur = self.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None

    def fetchall(self, sql: str, params: Sequence | dict | None = None) -> list[dict]:
        cur = self.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    # ----- transactions -----
    def begin(self) -> None:
        with self._lock:
            self._conn.execute("BEGIN")

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def rollback(self) -> None:
        with self._lock:
            self._conn.rollback()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ----- helpers -----
    @staticmethod
    def _where(query: dict | None) -> tuple[str, list]:
        if not query:
            return "", []
        clauses, params = [], []
        for k, v in query.items():
            if v is None:
                clauses.append(f"{k} IS NULL")
            else:
                clauses.append(f"{k} = ?")
                params.append(v)
        return " WHERE " + " AND ".join(clauses), params

    # ----- CRUD -----
    def get_one(self, table: str, query: dict | None = None, *, columns: str = "*") -> dict | None:
        where, params = self._where(query)
        return self.fetchone(f"SELECT {columns} FROM {table}{where} LIMIT 1", params)

    def get_many(
        self,
        table: str,
        query: dict | None = None,
        *,
        columns: str = "*",
        order_by: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict]:
        where, params = self._where(query)
        sql = f"SELECT {columns} FROM {table}{where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        if offset is not None:
            sql += f" OFFSET {int(offset)}"
        return self.fetchall(sql, params)

    def count(self, table: str, query: dict | None = None) -> int:
        where, params = self._where(query)
        row = self.fetchone(f"SELECT COUNT(*) AS c FROM {table}{where}", params)
        return int(row["c"]) if row else 0

    def insert_one(self, table: str, set_object: dict) -> int:
        cols = list(set_object.keys())
        placeholders = ",".join(["?"] * len(cols))
        sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
        if not cols: return 0
        cur = self.execute(sql, [set_object[c] for c in cols])
        return int(cur.lastrowid or 0)

    def insert_many(self, table: str, rows: Sequence[dict]) -> int:
        if not rows:
            return 0
        cols = list(rows[0].keys())
        placeholders = ",".join(["?"] * len(cols))
        sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
        params = [[r.get(c) for c in cols] for r in rows]
        cur = self.executemany(sql, params)
        return cur.rowcount or 0

    def upsert_one(
        self,
        table: str,
        set_object: dict,
        *,
        conflict_cols: Sequence[str],
        update_cols: Sequence[str] | None = None,
    ) -> int:
        """INSERT ... ON CONFLICT(conflict_cols) DO UPDATE. Returns affected row count."""
        cols = list(set_object.keys())
        placeholders = ",".join(["?"] * len(cols))
        if update_cols is None:
            update_cols = [c for c in cols if c not in conflict_cols]
        update_clause = ",".join(f"{c}=excluded.{c}" for c in update_cols) or f"{cols[0]}={cols[0]}"
        sql = (
            f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT({','.join(conflict_cols)}) DO UPDATE SET {update_clause}"
        )
        if not cols: return 0
        cur = self.execute(sql, [set_object[c] for c in cols])
        return cur.rowcount or 0

    def update_one(self, table: str, query: dict, set_object: dict) -> int:
        if not set_object:
            return 0
        set_cols = list(set_object.keys())
        set_clause = ",".join(f"{c}=?" for c in set_cols)
        where, where_params = self._where(query)
        params = [set_object[c] for c in set_cols] + where_params
        cur = self.execute(f"UPDATE {table} SET {set_clause}{where}", params)
        return cur.rowcount or 0

    def delete_one(self, table: str, query: dict) -> int:
        where, params = self._where(query)
        if not where:
            raise ValueError("delete_one requires a non-empty query")
        cur = self.execute(f"DELETE FROM {table}{where}", params)
        return cur.rowcount or 0

    def exists(self, table: str, query: dict) -> bool:
        return self.get_one(table, query, columns="1") is not None
