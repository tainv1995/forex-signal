from dataclasses import dataclass, field
from typing import Any

from app.core.enums import Direction, StrategyName, Timeframe


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    strategy: StrategyName
    direction: Direction
    confidence: float
    timeframe: Timeframe
    reason: str
    levels: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
        if self.direction is Direction.NEUTRAL and self.confidence > 0.5:
            raise ValueError("NEUTRAL direction should not carry high confidence")


def neutral_result(
    strategy: StrategyName,
    timeframe: Timeframe,
    reason: str,
    metadata: dict[str, Any] | None = None,
) -> AnalysisResult:
    return AnalysisResult(
        strategy=strategy,
        direction=Direction.NEUTRAL,
        confidence=0.0,
        timeframe=timeframe,
        reason=reason,
        metadata=metadata or {},
    )
