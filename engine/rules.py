"""機種非依存の判定エンジン。

機種固有の分岐は一切ここに書かない。すべてMachineProfile(YAML由来)の
derived式・rules式、および期待値テーブル(tables/ev_lookup)として表現され、
このモジュールは式の評価とテーブル参照という汎用処理のみを行う。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from simpleeval import simple_eval

from engine.profile_loader import EVLookupConfig, MachineProfile

# profile_loader.ALLOWED_FUNCTIONS と対になる実装。
SIMPLEEVAL_FUNCTIONS = {"defined": lambda value: value is not None, "max": max, "min": min}


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

    for ev_lookup in profile.ev_lookups:
        value, _ = lookup_ev_detail(ev_lookup, profile, names)
        names[ev_lookup.result_key] = value

    for rule in profile.rules:
        if simple_eval(rule.condition, names=names, functions=SIMPLEEVAL_FUNCTIONS):
            return JudgementResult(result=rule.result, reason=rule.reason, rule_id=rule.id, derived_values=names)

    return JudgementResult(
        result=profile.default_result,
        reason=profile.default_reason,
        rule_id="default",
        derived_values=names,
    )


def lookup_ev_detail(
    cfg: EVLookupConfig, profile: MachineProfile, names: dict[str, Any]
) -> tuple[Optional[float], Optional[str]]:
    """profile.tablesを参照して期待値(または任意の連続値)を求める汎用ルックアップ。

    table_select_axisの真偽でテーブル群(例:据え置き/リセット)を選び、rate_axisの
    値でテーブル(例:交換レート)を選ぶ。行はcycle_axisで完全一致するものに絞り、
    その中でgame_count_axisの値を挟む2点間を線形補間する。下端(先頭行未満)は
    先頭行の値にクランプするが、上端(最終行超過)はクランプせずNoneを返す
    (テーブルが尽きた先を機械的に延長すると、周期の変わり目付近で実際には
    下がっているかもしれない区間を誤って高く見せるリスクがあるため)。
    必要な軸の値が欠けている、または該当行が1つもない場合もNoneを返す
    (呼び出し側のrulesで「判定不可」を表現できるようにするため)。

    戻り値は (値, Noneだった場合の理由文) のタプル。理由文はUI側(result_view.py)
    が「なぜ期待値が出ないのか」をユーザーに示すために使う。値が求まった場合は
    理由文は常にNone。

    1つの機種プロファイルが複数系統の天井カウンターを持つ場合(例:AT間天井と
    CZ間天井が別管理)、profile.ev_lookupsに複数のEVLookupConfigを並べ、それぞれ
    別のresult_keyで結果を公開する。どちらを採用するか(例:高い方を使う)は
    rules側の条件式でmax()等を使って機種プロファイルごとに決める。
    """
    select_flag = names.get(cfg.table_select_axis)
    rate_key = names.get(cfg.rate_axis)
    cycle_value = names.get(cfg.cycle_axis)
    game_count_value = names.get(cfg.game_count_axis)
    if select_flag is None or rate_key is None or cycle_value is None or game_count_value is None:
        return None, "必要な入力(周期数・ゲーム数・交換レート等)が未入力です。"

    table_group = cfg.table_select_true if select_flag else cfg.table_select_false
    rows = profile.tables.get(table_group, {}).get(rate_key)
    if not rows:
        return None, f"「{rate_key}」の期待値データがこの機種プロファイルにありません。"

    target_cycle = int(round(float(cycle_value)))
    cycle_rows = sorted((row for row in rows if row[1] == target_cycle), key=lambda row: row[0])
    if not cycle_rows:
        return None, f"周期{target_cycle}の期待値データが出典にありません。"

    value = _interpolate(cycle_rows, float(game_count_value))
    if value is None:
        max_g = cycle_rows[-1][0]
        return None, (
            f"入力されたゲーム数({game_count_value:.0f}G)が、この周期のデータ範囲"
            f"(〜{max_g:.0f}G)を超えています。出典データが尽きた先は不明なため、"
            "この系統の期待値は表示できません。"
        )
    return value, None


def _interpolate(rows: list[tuple[float, int, float]], game_count: float) -> Optional[float]:
    """該当周期の行の間はそのまま線形補間する。下端(先頭行未満)は攻略サイトの
    最小G地点の値をそのまま使う(先頭行はcycle番号自体をダミーG値に使った
    「周期到達直後」の行で、実際の入力Gがこれを下回ることは実運用上ない)。

    上端(最終行超過)はNoneを返し、クランプしない。理由: 周期の変わり目が
    近い状態ほど、この機種特有の非単調な期待値変化(有利モードの逐次否定に
    よる一時的な低下)が起きうるため、データが尽きた先の値を機械的に
    延長すると、実際には下がっている可能性がある区間を「上がったまま」と
    誤って見せてしまう危険がある。範囲外は「わからない」として呼び出し側の
    ev_missingルールに様子見判定を委ねる。
    """
    if game_count <= rows[0][0]:
        return rows[0][2]
    if game_count > rows[-1][0]:
        return None

    for (g0, _, v0), (g1, _, v1) in zip(rows, rows[1:]):
        if g0 <= game_count <= g1:
            if g1 == g0:
                return v0
            t = (game_count - g0) / (g1 - g0)
            return v0 + t * (v1 - v0)

    return rows[-1][2]
