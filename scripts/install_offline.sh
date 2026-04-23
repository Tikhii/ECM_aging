#!/bin/bash
# ============================================================================
# install_offline.sh — libquiv-aging 离线安装 (依赖内部 pip 镜像可达)
# ============================================================================
#
# 目标: Linux x86_64, Python 3.11, Ubuntu 20.04+
#
# 前置条件:
#   - python3.11 已安装 (Ubuntu 20.04 需通过 deadsnakes PPA 或内部 apt 镜像)
#   - pip 的 index-url 已由 IT 配置为内部镜像站
#   - 当前目录为项目根目录 (含 requirements.txt 和 pyproject.toml)
#
# 用法:
#   bash scripts/install_offline.sh
#
# 安装完成后:
#   bash scripts/verify_install.sh
# ============================================================================

set -euo pipefail

if ! command -v python3.11 &> /dev/null; then
    echo "ERROR: python3.11 not found." >&2
    echo "On Ubuntu 20.04, install via deadsnakes PPA or internal apt mirror." >&2
    exit 1
fi

if [ ! -f requirements.txt ]; then
    echo "ERROR: requirements.txt not found. Run from project root." >&2
    exit 1
fi

echo "Creating virtual environment..."
python3.11 -m venv .venv
source .venv/bin/activate

echo "Upgrading pip, setuptools, wheel..."
pip install --upgrade pip setuptools wheel

echo "Installing pinned dependencies from requirements.txt..."
pip install -r requirements.txt

echo "Installing libquiv-aging in editable mode..."
pip install -e .

echo ""
echo "Install complete. Run scripts/verify_install.sh to validate."
