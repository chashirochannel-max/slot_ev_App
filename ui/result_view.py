"""判定結果・根拠・期待値の表示。"""
from __future__ import annotations

import streamlit as st

from engine.profile_loader import MachineProfile
from engine.rules import JudgementResult, lookup_ev_detail

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


def render_ev(profile: MachineProfile, judgement: JudgementResult, investment_yen: float) -> None:
    """機種プロファイルのev_lookups各系統の期待値(円)を表示する。

    このモジュール自体は「どの名前の値がいくつか」を表示するだけで、その中身
    (どのテーブルをどう参照して算出したか)は一切関知しない。機種が複数系統の
    期待値(例:AT間天井とCZ間天井)を持つ場合は、profile.ev_lookupsの数だけ
    横並びで表示する。ev_lookupsを持たない機種では何も表示しない。

    値が求まらなかった系統(入力範囲外・未入力等)も欄ごと消さず、「ー」+理由を
    表示する。判定結果が「様子見」になった際に、期待値欄まで丸ごと消えると
    「本当に再計算されたのか」が分からず不安になるため(2026年9月、光さんの
    指摘を受けて対応)。
    """
    if not profile.ev_lookups:
        return

    entries = []
    for cfg in profile.ev_lookups:
        value = judgement.derived_values.get(cfg.result_key)
        note = None
        if value is None:
            _, note = lookup_ev_detail(cfg, profile, judgement.derived_values)
        entries.append((cfg.label or cfg.result_key, value, note))

    cols = st.columns(len(entries))
    for col, (label, value, note) in zip(cols, entries):
        with col:
            if value is None:
                st.metric(label, "ー")
                if note:
                    st.caption(f"⚠️ {note}")
            else:
                delta = f"¥{value - investment_yen:,.0f}" if investment_yen else None
                st.metric(label, f"¥{value:,.0f}", delta=delta)

    st.caption("攻略サイト公開の期待値データ(設定1想定)を参照した目安です。公式情報ではありません。")
    st.caption("意思決定は「残り期待値」ベースで。ここまでの投資済み額に判断を引っ張られないよう注意してください。")
    if investment_yen:
        st.caption(f"参考:現在の投資額 ¥{investment_yen:,.0f}(上のdeltaは期待値との差額)")

    if profile.ev_policy_note:
        st.info(f"🕐 **この数値を実現する前提(正しいヤメ時)**\n\n{profile.ev_policy_note}")
