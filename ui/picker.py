"""複数機種プロファイルからの選択画面(カード形式)。"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from engine.profile_loader import MachineProfile


def render_header_image(profile: MachineProfile) -> None:
    if profile.header_image and Path(profile.header_image).exists():
        st.image(profile.header_image, use_container_width=True)


def _breakeven_text(profile: MachineProfile, table_key: str) -> str | None:
    """指定したtablesグループについて「何ゲームから期待値がプラスに転じるか」を
    機械的に計算する。手打ちの要約文だと数値が古くなるリスクがあるため、実際の
    tablesデータから毎回計算し直す(手打ちのprofile.summaryとは役割を分けている)。

    テーブルが周期等で複数系統に分かれている場合、単純にgame_countだけで
    全行をソートすると異なる周期の行が混ざって意味のない交差点を拾って
    しまう(例:周期5のごく早いゲーム数の行が周期1より先に来てしまう)ため、
    最小のcycle値(=最初の周期、モンキーターンVなら1周期目)に絞って計算する。
    """
    rate_tables = profile.tables.get(table_key, {})
    if not rate_tables:
        return None
    rate_key = "等価" if "等価" in rate_tables else next(iter(rate_tables), None)
    if rate_key is None:
        return None
    all_rows = rate_tables[rate_key]
    if not all_rows:
        return None

    distinct_cycles = {row[1] for row in all_rows}
    base_cycle = min(distinct_cycles)
    rows = sorted((row for row in all_rows if row[1] == base_cycle), key=lambda row: row[0])
    if not rows:
        return None

    breakeven = _find_breakeven(rows)
    suffix = f"({base_cycle}周期目基準)" if len(distinct_cycles) > 1 else ""
    if breakeven is None:
        return f"{suffix}手持ちデータの範囲内ではプラス転換なし"
    return f"{suffix}約{breakeven:.0f}G以上でプラス目安"


def _breakeven_lines(profile: MachineProfile) -> list[str]:
    """機種選択カードに表示する損益分岐ラインの一覧を組み立てる。

    table_select_true/falseが同じテーブル群を指す機種(状態による分岐がない)は
    1行のみ。異なるテーブル群を指す機種(設定変更後/通常時などで期待値が変わる)
    は、どちらの状態の数値かをバッジで明示した2行を出す(光さんの指摘:
    据え置き前提の数値とリセット前提の数値を混同すると「一日中粘れる良台」に
    見えてしまう、という誤読を防ぐため)。
    """
    lines: list[str] = []
    for cfg in profile.ev_lookups:
        label = cfg.label or cfg.result_key
        if cfg.table_select_true == cfg.table_select_false:
            text = _breakeven_text(profile, cfg.table_select_false)
            if text:
                lines.append(f"・{label}: {text}")
            continue

        true_text = _breakeven_text(profile, cfg.table_select_true)
        if true_text:
            lines.append(f":orange-badge[{cfg.table_true_label}] {label}: {true_text}")
        false_text = _breakeven_text(profile, cfg.table_select_false)
        if false_text:
            lines.append(f":blue-badge[{cfg.table_false_label}] {label}: {false_text}")
    return lines


def _find_breakeven(rows: list[tuple[float, int, float]]) -> float | None:
    if rows[0][2] > 0:
        return rows[0][0]
    for (g0, _, v0), (g1, _, v1) in zip(rows, rows[1:]):
        if v0 <= 0 < v1:
            if v1 == v0:
                return g0
            t = -v0 / (v1 - v0)
            return g0 + t * (g1 - g0)
    return None


def render_machine_picker(profiles: list[MachineProfile]) -> None:
    """機種をカードから選ばせ、選択結果をst.session_stateに保存する。
    選択後はst.rerun()で再描画されるので、この関数自体は値を返さない。
    """
    st.subheader("機種を選択")
    st.caption("カードの数値目安を見てから、機種を選んで詳しい期待値を試算してください。")
    cols = st.columns(2)
    for i, profile in enumerate(profiles):
        with cols[i % 2]:
            with st.container(border=True):
                render_header_image(profile)
                st.markdown(f"**{profile.name}**")

                if profile.summary:
                    st.caption(profile.summary)

                for line in _breakeven_lines(profile):
                    st.caption(line)

                if st.button("選ぶ", key=f"pick_{profile.id}", use_container_width=True):
                    st.session_state["selected_profile_id"] = profile.id
                    st.rerun()


def get_selected_profile(profiles: list[MachineProfile]) -> MachineProfile | None:
    selected_id = st.session_state.get("selected_profile_id")
    return next((p for p in profiles if p.id == selected_id), None)
