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
ALLOWED_FUNCTIONS = {"defined"}

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
    type: Literal["number", "boolean", "enum"]
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


class MachineProfile(BaseModel):
    id: str
    name: str
    rate_default: float
    axes: list[Axis]
    derived: list[DerivedVar] = Field(default_factory=list)
    rules: list[Rule]
    default_result: str
    default_reason: str = ""
    avg_at_payout_medals: Optional[float] = None
    notes: Optional[str] = None

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
