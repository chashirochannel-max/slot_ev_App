"""機種非依存の判定エンジン。

機種固有の分岐は一切ここに書かない。すべてMachineProfile(YAML由来)の
derived式・rules式、および期待値テーブル(tables/ev_lookup)として表現され、
このモジュールは式の評価とテーブル参照という汎用処理のみを行う。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

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

    if profile.ev_lookup is not None:
        names[profile.ev_lookup.result_key] = _lookup_ev(profile, names)

    for rule in profile.rules:
        if simple_eval(rule.condition, names=names, functions=SIMPLEEVAL_FUNCTIONS):
            return JudgementResult(result=rule.result, reason=rule.reason, rule_id=rule.id, derived_values=names)

    return JudgementResult(
        result=profile.default_result,
        reason=profile.default_reason,
        rule_id="default",
        derived_values=names,
    )


def _lookup_ev(profile: MachineProfile, names: dict[str, Any]) -> Optional[float]:
    """profile.tablesを参照して期待値(または任意の連続値)を求める汎用ルックアップ。

    table_select_axisの真偽でテーブル群(例:据え置き/リセット)を選び、rate_axisの
    値でテーブル(例:交換レート)を選ぶ。行はcycle_axisで完全一致するものに絞り、
    その中でgame_count_axisの値を挟む2点間を線形補間する。範囲外は両端でクランプ
    する。必要な軸の値が欠けている、または該当行が1つもない場合はNoneを返す
    (呼び出し側のrulesで「判定不可」を表現できるようにするため)。
    """
    cfg = profile.ev_lookup
    if cfg is None:
        return None

    select_flag = names.get(cfg.table_select_axis)
    rate_key = names.get(cfg.rate_axis)
    cycle_value = names.get(cfg.cycle_axis)
    game_count_value = names.get(cfg.game_count_axis)
    if select_flag is None or rate_key is None or cycle_value is None or game_count_value is None:
        return None

    table_group = cfg.table_select_true if select_flag else cfg.table_select_false
    rows = profile.tables.get(table_group, {}).get(rate_key)
    if not rows:
        return None

    target_cycle = int(round(float(cycle_value)))
    cycle_rows = sorted((row for row in rows if row[1] == target_cycle), key=lambda row: row[0])
    if not cycle_rows:
        return None

    return _interpolate(cycle_rows, float(game_count_value))


def _interpolate(rows: list[tuple[float, int, float]], game_count: float) -> float:
    if game_count <= rows[0][0]:
        return rows[0][2]
    if game_count >= rows[-1][0]:
        return rows[-1][2]

    for (g0, _, v0), (g1, _, v1) in zip(rows, rows[1:]):
        if g0 <= game_count <= g1:
            if g1 == g0:
                return v0
            t = (game_count - g0) / (g1 - g0)
            return v0 + t * (v1 - v0)

    return rows[-1][2]
