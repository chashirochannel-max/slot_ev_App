#!/bin/bash
# Claude Code クラウドセッション開始時に依存パッケージを入れる(ローカルでは何もしない)
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# システムのPython(Debian管理パッケージ)と衝突しないよう、プロジェクト内の.venvに入れる
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --quiet --disable-pip-version-check \
  -r requirements.txt pytest ruff

echo "export VIRTUAL_ENV=\"$CLAUDE_PROJECT_DIR/.venv\"" >> "$CLAUDE_ENV_FILE"
echo "export PATH=\"$CLAUDE_PROJECT_DIR/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
echo "export PYTHONPATH=\"$CLAUDE_PROJECT_DIR\"" >> "$CLAUDE_ENV_FILE"
