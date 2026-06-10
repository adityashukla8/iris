from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from sdk.models import EvalResult, IrisEvent


class EvalPlugin(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    tier: ClassVar[int] = 1  # 1=core, 2=agent-specific, 3=roadmap

    @abstractmethod
    async def evaluate(self, event: IrisEvent) -> EvalResult | None:
        """
        Evaluate an IrisEvent. Return None to signal the evaluator is not
        applicable to this event (e.g. Surgical Phase eval when no phase is set).
        """

    def is_applicable(self, event: IrisEvent) -> bool:
        """Override to gate activation on event fields."""
        return True
