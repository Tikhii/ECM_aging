#!/bin/bash
# ============================================================================
# verify_install.sh — 验证 libquiv-aging 离线安装是否成功
# ============================================================================
#
# 前置条件:
#   - 已执行 scripts/install_offline.sh
#   - venv 已激活: source .venv/bin/activate
#
# 用法:
#   bash scripts/verify_install.sh
# ============================================================================

set -euo pipefail

if [ -z "${VIRTUAL_ENV:-}" ]; then
    echo "ERROR: venv not activated. Run: source .venv/bin/activate" >&2
    exit 1
fi

echo "Checking Python version..."
PYVER=$(python --version 2>&1)
echo "  $PYVER"
if [[ "$PYVER" != *"3.11"* ]]; then
    echo "ERROR: Expected Python 3.11.x, got $PYVER" >&2
    exit 1
fi

echo "Checking import..."
python -c "import libquiv_aging; print('  import OK')"

echo "Running tests..."
pytest tests/ -v

echo "Running smoke test..."
python examples/smoke_test.py

echo ""
echo "Verification complete."
