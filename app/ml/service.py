"""ML boundary.

The investigation system depends on this Protocol, never on the concrete
detector. That is what allows the ML implementation to be replaced (separate
service, different model) without touching the application layer.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MLService(Protocol):
    @property
    def model_version(self) -> str: ...

    def describe(self) -> dict[str, Any]: ...

    def predict(self, observations: list[dict], *, include_features: bool = False) -> dict: ...
