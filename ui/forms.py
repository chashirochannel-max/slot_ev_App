"""機種プロファイルのaxesから動的に入力フォームを生成する。

機種ごとに専用画面をコーディングしない。スマホ縦画面・片手タップ操作を
前提に、入力項目を最小限に保つ。
"""
from __future__ import annotations

from typing import Any

import streamlit as st
from simpleeval import simple_eval

from engine.profile_loader import Axis, MachineProfile


def render_form(profile: MachineProfile) -> dict[str, Any] | None:
    """axesを上から順に描画する。conditionを満たさない軸はNoneのまま
    (キー自体は必ず存在させる。derived式のdefined()判定に必要なため)。
    「判定する」が押されたときだけ入力値dictを返し、それ以外はNone。
    """
    values: dict[str, Any] = {}

    for axis in profile.axes:
        if axis.condition and not _condition_met(axis.condition, values):
            values[axis.key] = None
            continue
        values[axis.key] = _render_axis_input(axis)

    submitted = st.button("判定する", type="primary", use_container_width=True)
    return values if submitted else None


def _condition_met(condition: str, values: dict[str, Any]) -> bool:
    try:
        return bool(simple_eval(condition, names=values, functions={}))
    except Exception:
        # 条件式評価に失敗した場合は、入力項目を隠して判断を誤らせるより
        # 表示する側に倒す(安全側フォールバック)。
        return True


def _render_axis_input(axis: Axis) -> Any:
    if axis.type == "boolean":
        default = bool(axis.default) if axis.default is not None else False
        return st.checkbox(axis.label, value=default, key=axis.key)

    if axis.type == "number":
        if axis.optional:
            provided = st.checkbox(f"{axis.label}を入力する", value=False, key=f"{axis.key}__provided")
            if not provided:
                return None
            default = float(axis.default) if axis.default is not None else 0.0
            return st.number_input(axis.label, value=default, step=1.0, key=axis.key)
        default = float(axis.default) if axis.default is not None else 0.0
        return st.number_input(axis.label, value=default, step=1.0, key=axis.key)

    if axis.type == "enum":
        options = axis.options or []
        default_index = options.index(axis.default) if axis.default in options else 0
        return st.selectbox(axis.label, options, index=default_index, key=axis.key)

    raise ValueError(f"unsupported axis type: {axis.type}")
