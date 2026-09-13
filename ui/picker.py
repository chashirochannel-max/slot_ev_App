"""複数機種プロファイルからの選択画面(カード形式)。"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from engine.profile_loader import MachineProfile
from ui.breakeven import base_cycle_breakeven_text, has_multi_cycle_breakeven, render_cycle_breakeven_section


def render_header_image(profile: MachineProfile) -> None:
    if profile.header_image and Path(profile.header_image).exists():
        st.image(profile.header_image, use_container_width=True)


def _breakeven_lines(profile: MachineProfile) -> list[str]:
    """機種選択カードに表示する損益分岐ラインの一覧を組み立てる。

    table_select_true/falseが同じテーブル群を指す機種(状態による分岐がない)は
    1行のみ。異なるテーブル群を指す機種(設定変更後/通常時などで期待値が変わる)
    は、どちらの状態の数値かをバッジで明示した2行を出す(光さんの指摘:
    据え置き前提の数値とリセット前提の数値を混同すると「一日中粘れる良台」に
    見えてしまう、という誤読を防ぐため)。

    複数周期を持つ機種(モンキーターンV等)では最初の周期の値のみを表示する
    (カードは一覧性重視のため)。周期ごとの内訳は機種詳細画面で確認できる。
    """
    lines: list[str] = []
    for cfg in profile.ev_lookups:
        label = cfg.label or cfg.result_key
        if cfg.table_select_true == cfg.table_select_false:
            text = base_cycle_breakeven_text(profile, cfg.table_select_false, cfg.rate_axis)
            if text:
                lines.append(f"・{label}: {text}")
            continue

        true_text = base_cycle_breakeven_text(profile, cfg.table_select_true, cfg.rate_axis)
        if true_text:
            lines.append(f":orange-badge[{cfg.table_true_label}] {label}: {true_text}")
        false_text = base_cycle_breakeven_text(profile, cfg.table_select_false, cfg.rate_axis)
        if false_text:
            lines.append(f":blue-badge[{cfg.table_false_label}] {label}: {false_text}")
    return lines


def render_machine_picker(profiles: list[MachineProfile]) -> None:
    """機種をカードから選ばせ、選択結果をst.session_stateに保存する。
    選択後はst.rerun()で再描画されるので、この関数自体は値を返さない。
    """
    st.subheader("機種を選択")
    st.caption("各カードの「損益分岐の目安を見る」で数値目安を確認できます。機種を選ぶと詳しい期待値を試算できます。")
    cols = st.columns(2)
    for i, profile in enumerate(profiles):
        with cols[i % 2]:
            with st.container(border=True):
                render_header_image(profile)
                st.markdown(f"**{profile.name}**")

                if profile.summary:
                    st.caption(profile.summary)

                lines = _breakeven_lines(profile)
                if lines:
                    with st.expander("損益分岐の目安を見る"):
                        for line in lines:
                            st.caption(line)

                # モンキーターンVのような複数周期を持つ機種は、機種を選ぶ前の
                # このカードの時点で周期ごとの内訳も確認できるようにする
                # (光さんの要望:機種詳細画面まで進まなくても見たい)。
                if has_multi_cycle_breakeven(profile):
                    with st.expander("周期別のプラス転換ゲーム数を見る"):
                        render_cycle_breakeven_section(profile)

                if st.button("選ぶ", key=f"pick_{profile.id}", use_container_width=True):
                    st.session_state["selected_profile_id"] = profile.id
                    st.rerun()


def get_selected_profile(profiles: list[MachineProfile]) -> MachineProfile | None:
    selected_id = st.session_state.get("selected_profile_id")
    return next((p for p in profiles if p.id == selected_id), None)
