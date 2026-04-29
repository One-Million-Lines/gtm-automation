"""ModuleResult — what every module returns."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ModuleResult:
    success: bool
    input_count: int = 0
    output_count: int = 0
    failed_count: int = 0
    message: Optional[str] = None
    data: dict = field(default_factory=dict)

    @classmethod
    def ok(
        cls,
        *,
        input_count: int = 0,
        output_count: int = 0,
        failed_count: int = 0,
        message: Optional[str] = None,
        data: Optional[dict] = None,
    ) -> "ModuleResult":
        return cls(
            success=True,
            input_count=input_count,
            output_count=output_count,
            failed_count=failed_count,
            message=message,
            data=data or {},
        )

    @classmethod
    def fail(cls, msg: str, *, failed_count: int = 0, data: Optional[dict] = None) -> "ModuleResult":
        return cls(
            success=False,
            failed_count=failed_count,
            message=msg,
            data=data or {},
        )
