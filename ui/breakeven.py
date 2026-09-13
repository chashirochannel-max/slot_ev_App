"""損益分岐ゲーム数(期待値がプラスに転じるG数)の計算。

機種選択カード(picker.py)と機種詳細画面の両方で使う共通ロジック。手打ちの
要約文はテーブル改訂のたびにズレるリスクがあるため、実際のtablesデータから
毎回計算し直す。
"""
from __future__ import annotations

import streamlit as st

from engine.profile_loader import MachineProfile


def pick_rate_key(profile: MachineProfile, rate_axis_key: str, rate_tables: dict) -> str | None:
    """どの交換レート(等価/5.6枚現金等)で計算するかを、判定フォーム側の
    exchange_rate軸のdefault値と必ず一致させる。片方が等価で楽観的、もう片方が
    5.6枚現金で保守的、のようにズレると、見た目の目安と実際の判定結果が
    食い違って見える(2026年9月に光さんが実戦で遭遇した混乱の原因)。
    """
    axis_default = next(
        (axis.default for axis in profile.axes if axis.key == rate_axis_key),
        None,
    )
    return axis_default if axis_default in rate_tables else next(iter(rate_tables), None)


def find_breakeven(rows: list[tuple[float, int, float]]) -> float | None:
    """周期を固定した上でgame_count昇順に並んだ行から、期待値がプラスに
    転じるgame_countを線形補間で求める。範囲内で一度もプラスに転じない場合は
    Noneを返す。"""
    if not rows:
        return None
    if rows[0][2] > 0:
        return rows[0][0]
    for (g0, _, v0), (g1, _, v1) in zip(rows, rows[1:]):
        if v0 <= 0 < v1:
            if v1 == v0:
                return g0
            t = -v0 / (v1 - v0)
            return g0 + t * (g1 - g0)
    return None


def _text_for_breakeven(breakeven: float | None) -> str:
    if breakeven is None:
        return "手持ちデータの範囲内ではプラス転換なし"
    return f"約{breakeven:.0f}G以上でプラス目安"


def cycle_breakeven_rows(
    profile: MachineProfile, table_key: str, rate_axis_key: str
) -> tuple[str | None, list[tuple[int, str]]]:
    """指定したtablesグループについて、周期ごとの損益分岐ゲーム数を計算する。

    周期が1種類しかない機種(dummy_cycle=1等、モンキーターンV以外の現行の
    全機種)では要素数1のリストを返す。戻り値は (使用した交換レート名, 行のリスト)。
    """
    rate_tables = profile.tables.get(table_key, {})
    if not rate_tables:
        return None, []
    rate_key = pick_rate_key(profile, rate_axis_key, rate_tables)
    if rate_key is None:
        return None, []
    all_rows = rate_tables[rate_key]
    if not all_rows:
        return rate_key, []

    distinct_cycles = sorted({row[1] for row in all_rows})
    rows_by_cycle = []
    for cycle in distinct_cycles:
        rows = sorted((row for row in all_rows if row[1] == cycle), key=lambda row: row[0])
        rows_by_cycle.append((cycle, _text_for_breakeven(find_breakeven(rows))))
    return rate_key, rows_by_cycle


def base_cycle_breakeven_text(profile: MachineProfile, table_key: str, rate_axis_key: str) -> str | None:
    """機種選択カード用:最初の周期(最小cycle値)だけの損益分岐テキストを返す。
    複数周期を持つ機種では、その旨を「(N周期目基準)」として明記する。
    """
    rate_key, rows_by_cycle = cycle_breakeven_rows(profile, table_key, rate_axis_key)
    if rate_key is None or not rows_by_cycle:
        return None
    base_cycle, text = rows_by_cycle[0]
    suffix = f"({base_cycle}周期目基準)" if len(rows_by_cycle) > 1 else ""
    return f"{suffix}[{rate_key}]{text}"


def has_multi_cycle_breakeven(profile: MachineProfile) -> bool:
    """render_cycle_breakeven_sectionが何かしら表示する内容を持つかどうか。
    空のexpanderを出さないための事前チェック用。"""
    for cfg in profile.ev_lookups:
        for table_key in {cfg.table_select_true, cfg.table_select_false}:
            _, rows = cycle_breakeven_rows(profile, table_key, cfg.rate_axis)
            if len(rows) > 1:
                return True
    return False


def render_cycle_breakeven_section(profile: MachineProfile) -> None:
    """機種詳細画面向け:周期が2つ以上ある機種について、周期ごとの損益分岐
    ゲーム数を一覧表示する(光さんの要望:1周期目だけでなく2周期目以降は
    何ゲームからプラスになるかも見たい、に対応)。

    周期が1つしかない機種(dummy_cycle=1で運用している現行の大半の機種)では
    機種選択カードの1行と重複するだけなので、何も表示しない。
    """
    for cfg in profile.ev_lookups:
        label = cfg.label or cfg.result_key
        if cfg.table_select_true == cfg.table_select_false:
            groups = [(None, None, cfg.table_select_false)]
        else:
            groups = [
                ("orange", cfg.table_true_label, cfg.table_select_true),
                ("blue", cfg.table_false_label, cfg.table_select_false),
            ]

        computed = [
            (color, state_label, *cycle_breakeven_rows(profile, table_key, cfg.rate_axis))
            for color, state_label, table_key in groups
        ]
        if not any(len(rows) > 1 for _, _, _, rows in computed):
            continue

        st.markdown(f"**{label}:周期別のプラス転換ゲーム数**")
        for color, state_label, rate_key, rows in computed:
            if rate_key is None or not rows:
                continue
            badge = f":{color}-badge[{state_label}] " if state_label else ""
            st.caption(f"{badge}[{rate_key}]")
            for cycle, text in rows:
                st.caption(f"・{cycle}周期目: {text}")
