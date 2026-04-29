"""Reusable file helpers: text, JSON, CSV, paths."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Iterable, Iterator


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def ensure_parent(path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def read_text(path: str | Path, default: str | None = None) -> str | None:
    p = Path(path)
    if not p.exists():
        return default
    return p.read_text(encoding="utf-8")


def write_text(path: str | Path, content: str) -> None:
    p = ensure_parent(path)
    p.write_text(content, encoding="utf-8")


def read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str | Path, data: Any, indent: int | None = 2) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent, default=str)


def read_csv_dicts(path: str | Path) -> list[dict[str, str]]:
    p = Path(path)
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def iter_csv_dicts(path: str | Path) -> Iterator[dict[str, str]]:
    p = Path(path)
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield dict(row)


def write_csv_dicts(path: str | Path, rows: Iterable[dict[str, Any]], fieldnames: list[str] | None = None) -> int:
    rows_list = list(rows)
    if not rows_list and not fieldnames:
        return 0
    if fieldnames is None:
        fieldnames = list(rows_list[0].keys())
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows_list:
            writer.writerow(row)
    return len(rows_list)


def file_exists(path: str | Path) -> bool:
    return Path(path).exists()


def file_size(path: str | Path) -> int:
    p = Path(path)
    return p.stat().st_size if p.exists() else 0


def remove_file(path: str | Path) -> bool:
    p = Path(path)
    if p.exists():
        p.unlink()
        return True
    return False


def list_files(path: str | Path, pattern: str = "*") -> list[Path]:
    p = Path(path)
    if not p.exists():
        return []
    return sorted(p.glob(pattern))
