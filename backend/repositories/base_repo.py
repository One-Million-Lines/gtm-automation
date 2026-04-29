"""Tiny base repository on top of SQLiteStorage.

Handles JSON field (de)serialization and auto-updated_at.
"""
from __future__ import annotations

from typing import Any, Iterable

from db.sqlite_storage import SQLiteStorage
from vtutils.misc import from_json, to_json


class BaseRepo:
    table: str = ""
    json_fields: tuple[str, ...] = ()
    pk: str = "id"
    has_updated_at: bool = True

    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage
        # Cache column list for has_updated_at + safe inserts
        self._columns: set[str] | None = None

    # ----- column introspection -----
    @property
    def columns(self) -> set[str]:
        if self._columns is None:
            rows = self.storage.fetchall(f"PRAGMA table_info({self.table})")
            self._columns = {r["name"] for r in rows}
        return self._columns

    # ----- (de)serialization -----
    def _encode(self, data: dict) -> dict:
        if not data:
            return data
        out = dict(data)
        for f in self.json_fields:
            if f in out and not isinstance(out[f], (str, type(None))):
                out[f] = to_json(out[f])
        # drop unknown columns silently to keep callers loose
        cols = self.columns
        return {k: v for k, v in out.items() if k in cols}

    def _decode(self, row: dict | None) -> dict | None:
        if not row:
            return row
        for f in self.json_fields:
            if f in row:
                row[f] = from_json(row[f])
        return row

    def _decode_many(self, rows: list[dict]) -> list[dict]:
        for r in rows:
            self._decode(r)
        return rows

    # ----- CRUD -----
    def get(self, id_: int) -> dict | None:
        return self._decode(self.storage.get_one(self.table, {self.pk: id_}))

    def find_one(self, query: dict | None = None) -> dict | None:
        return self._decode(self.storage.get_one(self.table, query))

    def find(
        self,
        query: dict | None = None,
        *,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict]:
        return self._decode_many(
            self.storage.get_many(
                self.table, query, order_by=order_by, limit=limit, offset=offset
            )
        )

    def count(self, query: dict | None = None) -> int:
        return self.storage.count(self.table, query)

    def exists(self, query: dict) -> bool:
        return self.storage.exists(self.table, query)

    def create(self, data: dict) -> int:
        return self.storage.insert_one(self.table, self._encode(data))

    def create_many(self, rows: Iterable[dict]) -> int:
        encoded = [self._encode(r) for r in rows]
        return self.storage.insert_many(self.table, encoded)

    def update(self, id_: int, data: dict) -> int:
        if not data:
            return 0
        payload = self._encode(data)
        if self.has_updated_at and "updated_at" in self.columns and "updated_at" not in payload:
            # Use SQL function via raw execute to avoid binding "CURRENT_TIMESTAMP" as a string.
            set_cols = list(payload.keys())
            assignments = [f"{c}=?" for c in set_cols] + ["updated_at=CURRENT_TIMESTAMP"]
            params = [payload[c] for c in set_cols] + [id_]
            cur = self.storage.execute(
                f"UPDATE {self.table} SET {','.join(assignments)} WHERE {self.pk}=?",
                params,
            )
            return cur.rowcount or 0
        return self.storage.update_one(self.table, {self.pk: id_}, payload)

    def delete(self, id_: int) -> int:
        return self.storage.delete_one(self.table, {self.pk: id_})

    def upsert_one(
        self, data: dict, *, conflict_cols: tuple[str, ...], update_cols: tuple[str, ...] | None = None
    ) -> int:
        return self.storage.upsert_one(
            self.table, self._encode(data), conflict_cols=conflict_cols, update_cols=update_cols
        )
