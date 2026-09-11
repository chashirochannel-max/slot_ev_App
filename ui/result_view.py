"""判定結果・根拠・収支目安の表示。"""
from __future__ import annotations

import streamlit as st

from engine.profile_loader import MachineProfile
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


def render_payout_estimate(profile: MachineProfile, bet_rate: float, investment_yen: float) -> None:
    if not profile.avg_at_payout_medals:
        return
    payout_yen = profile.avg_at_payout_medals * bet_rate
    st.metric("回収ライン目安(AT1回あたり)", f"¥{payout_yen:,.0f}")
    st.caption(
        f"想定差枚 {profile.avg_at_payout_medals:.0f}枚 × 枚単価 ¥{bet_rate:.2f} の簡易概算(精密なEV計算ではありません)"
    )
    st.caption("意思決定は「残り期待値」ベースで。ここまでの投資済み額に判断を引っ張られないよう注意してください。")
    if investment_yen:
        st.caption(f"参考:現在の投資額 ¥{investment_yen:,.0f}")
