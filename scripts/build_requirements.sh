#!/bin/bash
# ============================================================================
# build_requirements.sh — 从 environment-frozen.yml 生成 requirements.txt
# ============================================================================
#
# Usage:
#   bash scripts/build_requirements.sh
#
# 前置条件:
#   - Python 3.11 可用 (conda activate libquiv-aging 或系统 python3.11)
#   - pyyaml 已安装 (conda 环境自带)
#   - 工作目录为项目根目录 (含 environment-frozen.yml)
#
# 输出:
#   requirements.txt (项目根目录)
#
# 逻辑:
#   1. 解析 environment-frozen.yml 的 dependencies 列表
#   2. 过滤 conda 专属包 (C 库、系统包、bootstrap、macOS 专用等)
#   3. 将 conda 包名映射为 PyPI 包名
#   4. 以 == 严格锁定版本, 输出 pip 格式
# ============================================================================

set -euo pipefail

FROZEN_YML="environment-frozen.yml"
OUTPUT="requirements.txt"

if [ ! -f "$FROZEN_YML" ]; then
    echo "ERROR: $FROZEN_YML not found. Run from project root." >&2
    exit 1
fi

python3 << 'PYEOF'
import yaml
import sys
from datetime import date

FROZEN_YML = "environment-frozen.yml"
OUTPUT = "requirements.txt"

# ── Filter sets ──────────────────────────────────────────────────────────────

FILTER_BOOTSTRAP = {"python", "pip", "setuptools", "wheel"}

FILTER_SYSTEM = {
    "_openmp_mutex", "ca-certificates", "openssl", "ncurses", "readline",
    "tk", "bzip2", "freetype", "krb5", "lcms2", "lerc", "llvm-openmp",
    "openjpeg", "pthread-stubs", "qhull", "yaml", "zeromq", "zlib-ng",
    "zstd", "python_abi", "xorg-libxau", "xorg-libxdmcp",
}

FILTER_MACOS = {"appnope", "pyobjc-core", "pyobjc-framework-cocoa"}

FILTER_CONDA_META = {
    "bleach-with-css", "brotli", "brotli-bin", "cached_property",
    "jsonschema-with-format-nongpl", "matplotlib-base",
    "prompt_toolkit", "typing_extensions",
}

# 如后续发现真正 conda-only 的包, 加入此集合并附理由注释。
# 2026-04-24 spot check 验证原有 4 个候选均在 PyPI 存在:
#   pytokens (black 依赖), backports.zstd, rfc3987-syntax,
#   python-librt → librt (mypyc runtime, NAME_MAP 映射)。
FILTER_CONDA_ONLY: set = set()

# tzdata (IANA data, not the Python wrapper python-tzdata)
FILTER_IANA = {"tzdata"}

# ── Conda→PyPI name mapping ─────────────────────────────────────────────────

NAME_MAP = {
    "brotli-python": "Brotli",
    "python-fastjsonschema": "fastjsonschema",
    "python-librt": "librt",
    "python-tzdata": "tzdata",
    "nbconvert-core": "nbconvert",
    "importlib_resources": "importlib-resources",
    "ipython_pygments_lexers": "ipython-pygments-lexers",
    "mypy_extensions": "mypy-extensions",
    "prometheus_client": "prometheus-client",
    "pure_eval": "pure-eval",
    "stack_data": "stack-data",
    "typing_utils": "typing-utils",
    "jupyter_client": "jupyter-client",
    "jupyter_console": "jupyter-console",
    "jupyter_core": "jupyter-core",
    "jupyter_events": "jupyter-events",
    "jupyter_server": "jupyter-server",
    "jupyter_server_terminals": "jupyter-server-terminals",
    "jupyterlab_pygments": "jupyterlab-pygments",
    "jupyterlab_server": "jupyterlab-server",
    "jupyterlab_widgets": "jupyterlab-widgets",
}

# ── Parse and filter ─────────────────────────────────────────────────────────

with open(FROZEN_YML) as f:
    data = yaml.safe_load(f)

deps = data.get("dependencies", [])

kept = []

for d in deps:
    if isinstance(d, dict):
        continue  # skip pip: sub-section (libquiv-aging self-reference)
    name, version = d.split("=", 1)
    version = version.lstrip("=")

    if name in FILTER_BOOTSTRAP:
        continue
    if name.startswith("lib"):
        continue
    if name in FILTER_SYSTEM:
        continue
    if name in FILTER_MACOS:
        continue
    if name in FILTER_CONDA_META:
        continue
    if name in FILTER_CONDA_ONLY:
        continue
    if name in FILTER_IANA:
        continue

    pypi_name = NAME_MAP.get(name, name)
    kept.append((pypi_name, version))

# ── Write output ─────────────────────────────────────────────────────────────

with open(OUTPUT, "w") as f:
    f.write(f"# Generated from {FROZEN_YML} on {date.today().isoformat()}\n")
    f.write("# Target: Linux x86_64, Python 3.11\n")
    f.write("# For installation on offline workstation via internal pip mirror\n")
    f.write(f"# DO NOT edit manually. Regenerate via scripts/build_requirements.sh\n")
    f.write("#\n")
    f.write("# For development dependencies on online machines, use:\n")
    f.write("#   pip install -e \".[dev]\"\n")
    f.write("\n")
    for name, ver in sorted(kept, key=lambda x: x[0].lower()):
        f.write(f"{name}=={ver}\n")

print(f"✓ Wrote {len(kept)} packages to {OUTPUT}")
PYEOF

echo "✓ $OUTPUT generated."
