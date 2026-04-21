"""
check_parameter_consistency.py
===============================
扫描 docs/PARAMETERS.json，验证所有参数的 code_location 字段在源码中确实存在。

运行: python scripts/check_parameter_consistency.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


# Locate workspace root
ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "docs" / "PARAMETERS.json"

with open(JSON_PATH) as f:
    spec = json.load(f)

failures: list[str] = []


def check_code_location(loc: str) -> str | None:
    """
    Validate code_location such as:
      - 'file.py::field'
      - 'ClassName.field'  (class attribute)
      - 'ModuleName.CONSTANT'
    Returns error message if not found, None if OK.
    """
    # Strip parenthetical comments first
    loc_clean = re.sub(r"\(.*?\)", "", loc).strip()

    # Parse file vs field
    if "::" in loc_clean:
        filename, rest = loc_clean.split("::", 1)
        field = rest.split()[0] if rest.split() else rest
    elif "." in loc_clean:
        # Assume it's ClassName.field — search in all .py under libquiv_aging
        parts = loc_clean.split(".")
        field = parts[-1]
        # Ignore class name prefix in search, just grep for field anywhere
        filename = None
    else:
        return f"cannot parse '{loc}'"

    # Build candidate files
    if filename:
        candidates = [ROOT / "libquiv_aging" / filename, ROOT / filename]
    else:
        candidates = list((ROOT / "libquiv_aging").glob("*.py"))

    patterns = [
        rf"\b{re.escape(field)}\s*=",
        rf"\b{re.escape(field)}\s*:",
        rf"def\s+{re.escape(field)}\b",
        rf"class\s+{re.escape(field)}\b",
    ]

    for src in candidates:
        if not src.exists():
            continue
        content = src.read_text()
        if any(re.search(p, content) for p in patterns):
            return None  # Found

    return f"field '{field}' not found in any source file"


# ------------- Run checks ---------------
for p in spec["parameters"]:
    name = p["name"]
    loc = p.get("code_location", "")
    if not loc:
        continue
    # Skip data-file locations
    if "libquiv_aging/data/" in loc or "aging_kinetics." in loc:
        continue

    err = check_code_location(loc)
    if err:
        failures.append(f"  [{name}] {err}  (spec: {loc})")


# ------------- Check fit_steps ↔ parameters cross-reference ---------------
fit_step_ids = set(spec["fit_steps"].keys())
for p in spec["parameters"]:
    fs = p.get("fit_step")
    if fs:
        # Extract just the FIT-N[a-c] prefix
        m = re.match(r"(FIT-\d+[a-z]?)", fs)
        if m and m.group(1) not in fit_step_ids:
            failures.append(f"  [{p['name']}] unknown fit_step '{m.group(1)}' in '{fs}'")
        elif not m:
            failures.append(f"  [{p['name']}] cannot parse fit_step '{fs}'")

for fid, fspec in spec["fit_steps"].items():
    for fit_param in fspec.get("fits", []):
        if fit_param not in {p["name"] for p in spec["parameters"]}:
            failures.append(f"  [{fid}] fits unknown parameter '{fit_param}'")
    for exp in fspec.get("requires_experiments", []):
        if exp not in spec["experiments"]:
            failures.append(f"  [{fid}] unknown experiment '{exp}'")


# ------------- Report ---------------
if failures:
    print("=" * 60)
    print(f"❌ FAILED — {len(failures)} inconsistency issues:")
    print("=" * 60)
    for f in failures:
        print(f)
    sys.exit(1)
else:
    n_params = len(spec["parameters"])
    n_fits = len(spec["fit_steps"])
    n_exps = len(spec["experiments"])
    print(f"✅ OK — {n_params} params, {n_fits} fit steps, {n_exps} experiments all consistent.")
    sys.exit(0)
