"""機種非依存の判定エンジン。

機種固有の分岐は一切ここに書かない。すべてMachineProfile(YAML由来)の
derived式・rules式として表現され、このモジュールは式を評価するだけ。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from simpleeval import simple_eval

from engine.profile_loader import MachineProfile

# profile_loader.ALLOWED_FUNCTIONS と対になる実装。
SIMPLEEVAL_FUNCTIONS = {"defined": lambda value: value is not None}


@dataclass
class JudgementResult:
    result: str
    reason: str
    rule_id: str
    derived_values: dict[str, Any] = field(default_factory=dict)


def evaluate(profile: MachineProfile, axis_values: dict[str, Any]) -> JudgementResult:
    names: dict[str, Any] = dict(axis_values)

    for derived in profile.derived:
        names[derived.key] = simple_eval(derived.expr, names=names, functions=SIMPLEEVAL_FUNCTIONS)

    for rule in profile.rules:
        if simple_eval(rule.condition, names=names, functions=SIMPLEEVAL_FUNCTIONS):
            return JudgementResult(result=rule.result, reason=rule.reason, rule_id=rule.id, derived_values=names)

    return JudgementResult(
        result=profile.default_result,
        reason=profile.default_reason,
        rule_id="default",
        derived_values=names,
    )
