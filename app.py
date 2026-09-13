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
from ui.breakeven import has_multi_cycle_breakeven, render_cycle_breakeven_section
from ui.forms import render_form
from ui.picker import get_selected_profile, render_header_image, render_machine_picker
from ui.result_view import render_ev, render_result

PROFILES_DIR = Path(__file__).parent / "profiles"
DISCLAIMER = "本ツールは情報整理を目的とし、実際の遊技判断は自己責任で行ってください。"


def check_password() -> bool:
    """パスワード認証。

    Streamlitからは真のWebAuthn/FaceID連携はできない(Pythonからブラウザの
    生体認証APIを直接呼び出す手段がない)ため、代わりにiPhone Safari標準の
    「パスワードを保存」→次回以降はFace ID/Touch IDでオートフィル、という
    iCloudキーチェーンの仕組みに乗る形にする。これが機能するには
    (1) 本物の<form>としてPOSTする(st.formはそう描画される)、
    (2) パスワード欄にautocomplete="current-password"を付ける、
    の2点が必要。初回ログイン後にSafariが「パスワードを保存しますか?」と
    聞いてこない場合は、設定アプリの「パスワード」から手動で
    このサイト用に登録すれば、以降はFace IDでの自動入力が有効になる。
    """
    if st.session_state.get("authenticated"):
        return True

    st.title("🎰 天井ボーダー計算")
    with st.form("login_form"):
        password = st.text_input(
            "パスワード",
            type="password",
            autocomplete="current-password",
        )
        submitted = st.form_submit_button("ログイン", type="primary")
    if submitted:
        expected = st.secrets.get("app_password")
        if expected and password == expected:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    st.caption(
        "iPhoneでログイン後に「パスワードを保存」の確認が出ない場合は、"
        "設定アプリ→パスワード→このサイトを手動登録すると、次回以降は"
        "Face ID/Touch IDでの自動入力が使えるようになります。"
    )
    return False


def render_log_section(profile_id: str, *, show_change_machine: bool) -> None:
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

    if show_change_machine:
        st.divider()
        if st.button("← 別の機種を選ぶ", use_container_width=True):
            del st.session_state["selected_profile_id"]
            st.rerun()


def main() -> None:
    st.set_page_config(page_title="天井ボーダー計算", page_icon="🎰", layout="centered")

    if not check_password():
        return

    st.caption(f"⚠️ {DISCLAIMER}")

    try:
        profiles = load_all_profiles(PROFILES_DIR)
    except ProfileValidationError as exc:
        st.error(f"機種プロファイルの読み込みに失敗しました: {exc}")
        return

    if not profiles:
        st.error("機種プロファイルが見つかりません。")
        return

    multi_machine = len(profiles) > 1
    if multi_machine:
        profile = get_selected_profile(profiles)
        if profile is None:
            render_machine_picker(profiles)
            return
    else:
        profile = profiles[0]

    render_header_image(profile)
    st.subheader(profile.name)

    if has_multi_cycle_breakeven(profile):
        with st.expander("周期別のプラス転換ゲーム数を見る"):
            render_cycle_breakeven_section(profile)

    axis_values = render_form(profile)

    if axis_values is not None:
        judgement = evaluate(profile, axis_values)
        render_result(judgement)

        investment_yen = st.number_input("現在の投資額(円・任意)", min_value=0.0, step=100.0)
        render_ev(profile, judgement, investment_yen)

        try:
            log_id = append_log(profile.id, axis_values, judgement.result, judgement.rule_id)
            st.session_state["last_log_id"] = log_id
            st.toast(f"実戦ログに記録しました(ID: {log_id[:8]}...)", icon="📝")
            st.caption(f"記録ID: {log_id[:8]}...")
        except SheetsLogError as exc:
            st.info(str(exc))

    render_log_section(profile.id, show_change_machine=multi_machine)


if __name__ == "__main__":
    main()
