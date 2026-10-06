from dataclasses import dataclass
from typing import Iterable

from apexoperator.evaluation.models import EvalResult, EvalScenario, ScenarioSeverity


@dataclass(frozen=True)
class EvalReport:
    results: tuple[EvalResult, ...]

    @property
    def required_total(self) -> int:
        return sum(r.severity is ScenarioSeverity.REQUIRED for r in self.results)

    @property
    def required_passed(self) -> int:
        return sum(
            r.severity is ScenarioSeverity.REQUIRED and r.passed
            for r in self.results
        )

    @property
    def overall_passed(self) -> bool:
        return self.required_passed == self.required_total

    def score(self) -> float:
        return (
            self.required_passed / self.required_total
            if self.required_total
            else 1.0
        )


def run_scenarios(scenarios: Iterable[EvalScenario]) -> EvalReport:
    return EvalReport(tuple(scenario.run() for scenario in scenarios))
