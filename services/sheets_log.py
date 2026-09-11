"""実戦ログのGoogle Sheets永続化。

Streamlit Community Cloudはアプリ再起動(スリープ復帰・再デプロイ)で
ローカルファイルが消えるため、無料で永続化できるGoogle Sheetsをログの
保存先に採用する。機種が増えてもログ構造を変えずに済むよう、axesの値は
まるごとJSON文字列として1カラムに保存する汎用フォーマットにしている。

行の追跡には行番号ではなくUUID(log_id)を使う。st.session_stateの行番号
保持はセッション消失(タブ再読み込み・コンテナスリープ)に弱いため、
「結果を記録」の更新はlog_id列を検索して行う。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADER = ["log_id", "timestamp", "machine_id", "axes_json", "judged_result", "rule_id", "win", "payout_medals"]

_PENDING_QUEUE_KEY = "sheets_pending_queue"


class SheetsLogError(Exception):
    """Sheetsへの読み書きに失敗した場合に送出される。呼び出し側は判定機能自体は
    継続動作させ、このエラーはログ機能の失敗としてユーザーに通知するのみとする。"""


@st.cache_resource(show_spinner=False)
def _get_client() -> gspread.Client:
    creds = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=SCOPES)
    return gspread.authorize(creds)


def _get_worksheet() -> gspread.Worksheet:
    client = _get_client()
    sheet = client.open_by_key(st.secrets["sheet_id"])
    worksheet = sheet.sheet1
    if worksheet.row_values(1) != HEADER:
        worksheet.update("A1", [HEADER])
    return worksheet


def append_log(machine_id: str, axis_values: dict[str, Any], judged_result: str, rule_id: str) -> str:
    """判定1回分をログに1行追記し、発行したlog_idを返す。書き込みに失敗しても
    例外は送出するが、呼び出し側で再送キューに積んだ後なので判定機能自体は継続できる。"""
    log_id = uuid.uuid4().hex
    row = [
        log_id,
        datetime.now(timezone.utc).isoformat(),
        machine_id,
        json.dumps(axis_values, ensure_ascii=False),
        judged_result,
        rule_id,
        "",
        "",
    ]
    try:
        _get_worksheet().append_row(row, value_input_option="USER_ENTERED")
    except Exception as exc:
        _queue_pending("append", row)
        raise SheetsLogError(f"ログの記録に失敗しました(通信状況をご確認ください。再送キューに保持しました): {exc}") from exc
    return log_id


def record_outcome(log_id: str, win: bool, payout_medals: float | None) -> None:
    """既存ログ行(log_id列で特定)に結果(当選有無・獲得枚数)を追記更新する。"""
    payload = {"log_id": log_id, "win": win, "payout_medals": payout_medals}
    try:
        worksheet = _get_worksheet()
        cell = worksheet.find(log_id, in_column=1)
        if cell is None:
            raise SheetsLogError(f"log_id={log_id} がシート内に見つかりませんでした")
        worksheet.update(f"G{cell.row}:H{cell.row}", [["当選" if win else "非当選", payout_medals or ""]])
    except SheetsLogError:
        _queue_pending("update", payload)
        raise
    except Exception as exc:
        _queue_pending("update", payload)
        raise SheetsLogError(f"結果の更新に失敗しました(通信状況をご確認ください。再送キューに保持しました): {exc}") from exc


def list_today_pending_logs(machine_id: str) -> list[dict[str, Any]]:
    """本日分・かつまだ結果未記入(winが空欄)のログを返す。セッションが切れて
    log_idを失った場合のフォールバック選択用。"""
    worksheet = _get_worksheet()
    records = worksheet.get_all_records()
    today = datetime.now().date().isoformat()
    return [
        record
        for record in records
        if str(record.get("timestamp", "")).startswith(today)
        and record.get("machine_id") == machine_id
        and not record.get("win")
    ]


def _queue_pending(kind: str, payload: Any) -> None:
    queue = st.session_state.setdefault(_PENDING_QUEUE_KEY, [])
    queue.append({"kind": kind, "payload": payload})


def pending_count() -> int:
    return len(st.session_state.get(_PENDING_QUEUE_KEY, []))


def retry_pending() -> tuple[int, int]:
    """再送キューの内容を再送する。(成功件数, 残件数)を返す。"""
    queue = st.session_state.get(_PENDING_QUEUE_KEY, [])
    remaining: list[dict[str, Any]] = []
    succeeded = 0
    for item in queue:
        try:
            worksheet = _get_worksheet()
            if item["kind"] == "append":
                worksheet.append_row(item["payload"], value_input_option="USER_ENTERED")
            elif item["kind"] == "update":
                payload = item["payload"]
                cell = worksheet.find(payload["log_id"], in_column=1)
                if cell is None:
                    raise SheetsLogError("log_id not found on retry")
                worksheet.update(
                    f"G{cell.row}:H{cell.row}",
                    [["当選" if payload["win"] else "非当選", payload["payout_medals"] or ""]],
                )
            succeeded += 1
        except Exception:
            remaining.append(item)
    st.session_state[_PENDING_QUEUE_KEY] = remaining
    return succeeded, len(remaining)
