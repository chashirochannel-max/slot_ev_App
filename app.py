"""スロット天井ボーダー計算アプリ - Streamlitエントリポイント。

認証 → 免責表示 → 機種選択 → 動的フォーム → 判定 → 収支目安 → 実戦ログ、
という一連の流れをここでつなぐ。判定ロジックや機種データはengine/・
profiles/側に閉じており、ここでは薄い配線のみを行う。
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from engine.profile_loader import ProfileValidationError, load_all_profiles
from engine.rules import evaluate
from services.sheets_log import SheetsLogError, append_log, pending_count, record_outcome, retry_pending
from ui.forms import render_form
from ui.picker import get_selected_profile, render_header_image, render_machine_picker
from ui.result_view import render_ev, render_result

PROFILES_DIR = Path(__file__).parent / "profiles"
DISCLAIMER = "本ツールは情報整理を目的とし、実際の遊技判断は自己責任で行ってください。"


def check_password() -> bool:
    if st.session_state.get("authenticated"):
        return True

    st.title("🎰 天井ボーダー計算")
    password = st.text_input("パスワード", type="password")
    if st.button("ログイン", type="primary"):
        expected = st.secrets.get("app_password")
        if expected and password == expected:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    return False


def render_log_section(profile_id: str) -> None:
    st.divider()
    with st.expander("実戦を終えたら:結果を記録する"):
        log_id = st.text_input("記録ID(判定後に表示されたIDを入力)", value=st.session_state.get("last_log_id", ""))
        win = st.checkbox("AT当選あり")
        payout = st.number_input("獲得差枚(任意)", min_value=0.0, step=100.0)
        if st.button("結果を記録する"):
            if not log_id:
                st.error("記録IDを入力してください")
            else:
                try:
                    record_outcome(log_id, win, payout or None)
                    st.success("結果を記録しました")
                except SheetsLogError as exc:
                    st.error(str(exc))

    queue_size = pending_count()
    if queue_size:
        st.warning(f"未送信のログが{queue_size}件あります(通信が回復したら再送してください)")
        if st.button("ログを再送する"):
            succeeded, remaining = retry_pending()
            st.info(f"{succeeded}件送信しました。残り{remaining}件です")


def main() -> None:
    st.set_page_config(page_title="天井ボーダー計算", page_icon="🎰", layout="centered")

    if not check_password():
        return

    st.warning(DISCLAIMER)

    try:
        profiles = load_all_profiles(PROFILES_DIR)
    except ProfileValidationError as exc:
        st.error(f"機種プロファイルの読み込みに失敗しました: {exc}")
        return

    if not profiles:
        st.error("機種プロファイルが見つかりません。")
        return

    if len(profiles) > 1:
        profile = get_selected_profile(profiles)
        if profile is None:
            render_machine_picker(profiles)
            return
        if st.button("← 機種を変更"):
            del st.session_state["selected_profile_id"]
            st.rerun()
    else:
        profile = profiles[0]

    render_header_image(profile)
    st.subheader(profile.name)

    axis_values = render_form(profile)

    if axis_values is not None:
        judgement = evaluate(profile, axis_values)
        render_result(judgement)

        investment_yen = st.number_input("現在の投資額(円・任意)", min_value=0.0, step=100.0)
        render_ev(judgement, investment_yen)

        try:
            log_id = append_log(profile.id, axis_values, judgement.result, judgement.rule_id)
            st.session_state["last_log_id"] = log_id
            st.caption(f"実戦ログに記録しました(ID: {log_id[:8]}...)")
        except SheetsLogError as exc:
            st.info(str(exc))

    render_log_section(profile.id)


if __name__ == "__main__":
    main()
