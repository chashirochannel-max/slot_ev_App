"""機種プロファイル(YAML)の読み込みと構造検証。

判定エンジン(rules.py)は機種固有の値を一切ハードコードしない。新機種は
profiles/ 配下にYAMLを1つ追加するだけで対応できることを目的とした設計。
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, Field, model_validator

# derived/axis condition/rule condition の式中で参照を許可する関数名。
# simpleeval側にも同じ名前で関数を登録すること(engine/rules.py参照)。
ALLOWED_FUNCTIONS = {"defined", "max", "min"}

# 式の中で使用を禁止する構文ノード。属性アクセス・添字アクセス・ラムダ・
# 内包表記・importなどは軸の値がすべてnumber/boolean/Noneである前提では
# 不要であり、simpleevalの攻撃面を狭めるために静的に弾く。
_DISALLOWED_NODE_TYPES = (
    ast.Attribute,
    ast.Subscript,
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.Import,
    ast.ImportFrom,
)


class ProfileValidationError(ValueError):
    """機種プロファイルYAMLの構造・式が不正な場合に送出される。"""


class Axis(BaseModel):
    key: str
    label: str
    # "integer"はゲーム数・周期数・回転数など小数を持たない値(タップ操作・
    # スマホのテンキー表示に向く)。"number"は小数を許容する値(現状未使用だが
    # 将来のレート等のために残す)。
    type: Literal["number", "integer", "boolean", "enum"]
    default: Any = None
    optional: bool = False
    condition: Optional[str] = None
    options: Optional[list[str]] = None


class DerivedVar(BaseModel):
    key: str
    expr: str


class Rule(BaseModel):
    id: str
    condition: str
    result: str
    reason: str = ""


class EVLookupConfig(BaseModel):
    """期待値テーブル参照の設定。テーブルの実データ(tables)は機種ごとに異なるが、
    参照ロジック自体(どの軸でテーブルを選び、どの軸で行を引き、結果をどの名前で
    公開するか)は機種非依存の汎用機構としてengine側に実装する。"""

    table_select_axis: str  # boolean軸。値によってtable_select_true/falseのどちらのテーブル群を使うか選ぶ
    table_select_true: str
    table_select_false: str
    rate_axis: str  # tables[group]のキー(交換レート等)を選ぶ軸
    cycle_axis: str  # テーブル行の整数キー(周期数など)
    game_count_axis: str  # テーブル行の連続値キー(ゲーム数など)。行間は線形補間する
    result_key: str = "ev_yen"  # 参照結果をnamesに公開する名前。derived/rulesから参照できる
    label: Optional[str] = None  # UI表示用ラベル。省略時はresult_keyをそのまま使う
    # table_select_true/falseが異なるテーブル群を指す場合(例:設定変更後/通常時で
    # 参照テーブルが変わる機種)、機種選択カードの損益分岐ゲーム数をどちらの状態の
    # ものか明示するための表示ラベル。true==falseの機種(状態による分岐がない)では
    # 未設定のままでよい。
    table_true_label: Optional[str] = None
    table_false_label: Optional[str] = None


class MachineProfile(BaseModel):
    id: str
    name: str
    header_image: Optional[str] = None  # assets/配下の画像への相対パス。光さんが自分で用意したものを置く
    summary: Optional[str] = None  # 機種選択カードに表示する短い特徴説明(1〜2行程度)
    axes: list[Axis]
    derived: list[DerivedVar] = Field(default_factory=list)
    # 機種によっては天井カウンターが複数系統ある(例:AT間天井とCZ間天井が別管理)ため
    # リストで持つ。各エントリのresult_keyで別々の名前としてnamesに公開されるので、
    # 複数系統をどう合成するか(例:max()で高い方を採用)はderived側で機種プロファイル
    # ごとに自由に書ける。1系統しかない機種は要素数1のリストになる。
    ev_lookups: list[EVLookupConfig] = Field(default_factory=list)
    # tables[group][rate_key] = [(game_count, cycle, ev_yen), ...]
    tables: dict[str, dict[str, list[tuple[float, int, float]]]] = Field(default_factory=dict)
    rules: list[Rule]
    default_result: str
    default_reason: str = ""
    notes: Optional[str] = None
    # ev_yen等が「どこまで打ち続けた場合の期待値か」(自然当選/天井到達まで打ち切り、
    # AT終了後は追加で粘らずヤメる、等)を出典サイトの記載に基づいて短く要約した
    # もの。結果画面でEVと一緒に表示し、「この数値通りに動くための正しいヤメ時」を
    # 光さんが確認できるようにする(2026年9月の指摘を受けて追加)。
    ev_policy_note: Optional[str] = None

    @model_validator(mode="after")
    def _validate_expressions(self) -> "MachineProfile":
        known_names: set[str] = {axis.key for axis in self.axes}

        for axis in self.axes:
            if axis.condition:
                _check_expr(axis.condition, known_names, context=f"axis '{axis.key}'.condition")

        for derived in self.derived:
            _check_expr(derived.expr, known_names, context=f"derived '{derived.key}'.expr")
            if derived.key in known_names:
                raise ProfileValidationError(
                    f"derived key '{derived.key}' collides with an existing axis or derived key"
                )
            known_names = known_names | {derived.key}

        # ev_lookupsはderivedの後(rulesの前)に評価される(engine/rules.py参照)ため、
        # 参照先はaxesだけでなくderivedで定義した値でもよい。
        for i, cfg in enumerate(self.ev_lookups):
            for axis_ref, field_name in (
                (cfg.table_select_axis, "table_select_axis"),
                (cfg.rate_axis, "rate_axis"),
                (cfg.cycle_axis, "cycle_axis"),
                (cfg.game_count_axis, "game_count_axis"),
            ):
                if axis_ref not in known_names:
                    raise ProfileValidationError(
                        f"ev_lookups[{i}].{field_name} references undefined name '{axis_ref}'"
                    )
            if cfg.table_select_true not in self.tables or cfg.table_select_false not in self.tables:
                raise ProfileValidationError(
                    f"ev_lookups[{i}].table_select_true/false must both be keys of `tables`"
                )
            # true/falseで参照テーブルが異なる(=状態によって期待値が変わる)場合、
            # 機種選択カードの損益分岐表示がどちらの状態を指すか分からなくなる事故を
            # 防ぐため、表示ラベルの設定を必須にする。
            if cfg.table_select_true != cfg.table_select_false and not (
                cfg.table_true_label and cfg.table_false_label
            ):
                raise ProfileValidationError(
                    f"ev_lookups[{i}]: table_select_true ('{cfg.table_select_true}') and "
                    f"table_select_false ('{cfg.table_select_false}') differ, so table_true_label "
                    "and table_false_label must both be set for the picker card to show which "
                    "state each breakeven line describes."
                )
            if cfg.result_key in known_names:
                raise ProfileValidationError(
                    f"ev_lookups[{i}].result_key '{cfg.result_key}' collides with an existing name"
                )
            known_names = known_names | {cfg.result_key}

        for rule in self.rules:
            _check_expr(rule.condition, known_names, context=f"rule '{rule.id}'.condition")

        return self


def _check_expr(expr: str, known_names: set[str], *, context: str) -> None:
    """derived/rule条件式が、既知の軸・derived変数と許可関数だけを参照しているか検証する。

    未定義変数の参照(=derivedの定義順ミスや循環参照、typo)をロード時点で
    検出しfail-fastさせることで、実戦中の予期しないエラーを防ぐ。
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ProfileValidationError(f"{context}: invalid expression syntax: {expr!r} ({exc})") from exc

    for node in ast.walk(tree):
        if isinstance(node, _DISALLOWED_NODE_TYPES):
            raise ProfileValidationError(
                f"{context}: disallowed syntax {type(node).__name__} in expression: {expr!r}"
            )
        if isinstance(node, ast.Name) and node.id not in known_names and node.id not in ALLOWED_FUNCTIONS:
            raise ProfileValidationError(
                f"{context}: references undefined name '{node.id}' (known: {sorted(known_names)}). "
                "derived/rule expressions may only reference axes, or derived values defined earlier in the list."
            )


def load_profile(path: Path | str) -> MachineProfile:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProfileValidationError(f"{path}: invalid YAML: {exc}") from exc

    try:
        return MachineProfile.model_validate(raw)
    except ProfileValidationError:
        raise
    except Exception as exc:
        raise ProfileValidationError(f"{path}: {exc}") from exc


def load_all_profiles(profiles_dir: Path | str) -> list[MachineProfile]:
    profiles_dir = Path(profiles_dir)
    return [load_profile(p) for p in sorted(profiles_dir.glob("*.yaml"))]
