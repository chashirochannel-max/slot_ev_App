"""判定結果・根拠・期待値の表示。"""
from __future__ import annotations

import streamlit as st

from engine.rules import JudgementResult

_RESULT_STYLE = {
    "続行推奨": ("success", "🟢"),
    "様子見": ("warning", "🟡"),
    "見送り": ("error", "🔴"),
}


def render_result(judgement: JudgementResult) -> None:
    style, icon = _RESULT_STYLE.get(judgement.result, ("info", "ℹ️"))
    getattr(st, style)(f"{icon} **{judgement.result}**\n\n{judgement.reason}")

    if judgement.derived_values.get("carryover_mismatch"):
        st.warning(
            "⚠️ 据え置きの前提に対して、現在の周期数が前日の最終周期数より少なくなっています。"
            "途中でリセットされたか、他の方がAT当選した可能性があります。周期数の見え方を再確認してください。"
        )

    current_point = judgement.derived_values.get("current_point")
    if current_point is not None:
        st.caption(f"参考:現在の激走ポイント {current_point:.0f}pt(判定には使用していません)")


def render_ev(judgement: JudgementResult, investment_yen: float) -> None:
    """機種プロファイルのev_lookupで算出した期待値(円)を表示する。

    このモジュール自体はev_yenという名前の値を表示するだけで、その中身
    (どのテーブルをどう参照して算出したか)は一切関知しない。機種プロファイルが
    ev_lookupを持たない場合は何も表示しない。
    """
    ev_yen = judgement.derived_values.get("ev_yen")
    if ev_yen is None:
        return

    st.metric("期待値(設定1想定)", f"¥{ev_yen:,.0f}")
    st.caption("攻略サイト公開の期待値データ(設定1想定)を参照した目安です。公式情報ではありません。")
    st.caption("意思決定は「残り期待値」ベースで。ここまでの投資済み額に判断を引っ張られないよう注意してください。")
    if investment_yen:
        st.caption(f"参考:現在の投資額 ¥{investment_yen:,.0f}")
