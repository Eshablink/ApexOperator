from dataclasses import dataclass
from enum import Enum
from typing import Callable


class ScenarioSeverity(str, Enum):
    REQUIRED = "REQUIRED"
    ADVISORY = "ADVISORY"


@dataclass(frozen=True)
class EvalResult:
    scenario_id: str
    passed: bool
    severity: ScenarioSeverity
    detail: str


@dataclass(frozen=True)
class EvalScenario:
    scenario_id: str
    description: str
    severity: ScenarioSeverity
    check: Callable[[], str | None]

    def run(self) -> EvalResult:
        try:
            detail = self.check()
            return EvalResult(
                scenario_id=self.scenario_id,
                passed=detail is None,
                severity=self.severity,
                detail=detail or "passed",
            )
        except Exception as exc:
            return EvalResult(
                scenario_id=self.scenario_id,
                passed=False,
                severity=self.severity,
                detail=f"{type(exc).__name__}: {exc}",
            )
