"""VariantAllocator service (File 18).

Allocates a lead to one of the variants of an experiment.
Pluggable default pattern (mirrors Files 15/16/17).
"""
from __future__ import annotations

import hashlib
import random
from typing import Protocol


class VariantAllocator(Protocol):
    name: str

    def allocate(self, experiment: dict, variants: list[dict], lead_id: int) -> dict: ...


def _cumulative_pick(variants: list[dict], position: float) -> dict:
    """position in [0, 1)."""
    weights = [max(float(v.get("weight") or 0.0), 0.0) for v in variants]
    total = sum(weights)
    if total <= 0:
        return variants[0]
    target = position * total
    acc = 0.0
    for v, w in zip(variants, weights):
        acc += w
        if target < acc:
            return v
    return variants[-1]


class HashVariantAllocator:
    name = "hash"

    def allocate(self, experiment: dict, variants: list[dict], lead_id: int) -> dict:
        if not variants:
            raise ValueError("no variants")
        key = f"{int(experiment['id'])}:{int(lead_id)}".encode("utf-8")
        h = hashlib.sha256(key).digest()
        # Use the first 8 bytes as a uint64 → fraction in [0, 1).
        n = int.from_bytes(h[:8], "big")
        position = n / float(1 << 64)
        return _cumulative_pick(variants, position)


class RandomVariantAllocator:
    name = "random"

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def allocate(self, experiment: dict, variants: list[dict], lead_id: int) -> dict:
        if not variants:
            raise ValueError("no variants")
        return _cumulative_pick(variants, self._rng.random())


class FakeVariantAllocator:
    name = "fake"

    def __init__(self, forced_variant_index: int = 0) -> None:
        self.forced_variant_index = int(forced_variant_index)

    def allocate(self, experiment: dict, variants: list[dict], lead_id: int) -> dict:
        if not variants:
            raise ValueError("no variants")
        idx = max(0, min(self.forced_variant_index, len(variants) - 1))
        return variants[idx]


# ============================================================================
# Pluggable default
# ============================================================================
_default_allocator: VariantAllocator | None = None


def set_default_variant_allocator(allocator: VariantAllocator | None) -> None:
    global _default_allocator
    _default_allocator = allocator


def get_default_variant_allocator() -> VariantAllocator:
    global _default_allocator
    if _default_allocator is None:
        _default_allocator = HashVariantAllocator()
    return _default_allocator


def allocate_variant(
    experiment: dict, variants: list[dict], lead_id: int,
    *, allocator: VariantAllocator | None = None,
) -> dict:
    return (allocator or get_default_variant_allocator()).allocate(
        experiment, variants, lead_id,
    )
