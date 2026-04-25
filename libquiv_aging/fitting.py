"""
fitting.py
==========
FIT 脚本系列的共享基础设施, 不含特定 FIT 步骤的算法。

当前由 FIT-1 (scripts/fit_electrode_balance.py) 使用, 未来 FIT-2/3 加入时
若该模块超过 600 行再考虑拆分。

提供:
- PreflightError + preflight_material_spec / preflight_csv: 前置检查
- compute_rmse / compute_r_squared / numerical_hessian_2x2 /
  estimate_uncertainty_2var: 拟合诊断量
- make_value_with_provenance / write_back_to_material_spec: spec 写回
- get_git_commit_hash / hash_file: provenance 工具
- RunArtifactWriter: runs/{run_id}/ 目录管理 + 三份 artifact 写出
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import warnings
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import numpy as np
import pandas as pd


# ============================================================================
# Valid status values (from material.schema.v1.json)
# ============================================================================

_VALID_STATUSES = frozenset([
    "pending_fit", "fitted", "manually_set",
    "literature_default", "convention", "datasheet",
])


# ============================================================================
# 前置检查
# ============================================================================

class PreflightError(Exception):
    """preflight 失败时抛出, 携带错误码标识。"""

    def __init__(self, code: str, message: str, exit_code: int):
        self.code = code
        self.message = message
        self.exit_code = exit_code
        super().__init__(f"[{code}] {message}")


def preflight_material_spec(
    spec_path: Path,
    required_fields: list[str],
) -> dict:
    """加载材料 spec 并验证必填字段非 null。

    Parameters
    ----------
    spec_path : Path
        材料 spec JSON 文件路径。
    required_fields : list[str]
        例如 ['dX_PE_alawa', 'dX_NE_alawa', 'X0_PE', 'X0_NE']

    Returns
    -------
    dict
        加载好的 spec dict (供调用方使用)。

    Raises
    ------
    PreflightError
        FIT1-E001 if any required field's value is null.
    FileNotFoundError
        If the spec file does not exist.
    """
    with open(spec_path) as f:
        spec = json.load(f)

    missing = []
    for field in required_fields:
        if field not in spec:
            missing.append(f"{field} (字段不存在)")
        elif spec[field].get("value") is None:
            missing.append(f"{field} (value=null, status={spec[field].get('status')})")

    if missing:
        raise PreflightError(
            "FIT1-E001",
            f"材料 spec 中以下字段缺失或 value 为 null: {', '.join(missing)}。"
            f"请对照 PARAMETER_SOP.md §一.2 SOP-1 填入。",
            exit_code=80,
        )
    return spec


def preflight_csv(
    csv_path: Path,
    required_columns: list[str],
    min_rows: int = 50,
    soc_min: float = 0.05,
    soc_max: float = 0.95,
) -> pd.DataFrame:
    """加载 EXP-X CSV, 验证列名、行数、SOC 覆盖范围。

    Parameters
    ----------
    csv_path : Path
        CSV 文件路径。
    required_columns : list[str]
        必须存在的列名。
    min_rows : int
        最小行数要求。
    soc_min, soc_max : float
        SOC 列必须覆盖 [soc_min, soc_max] 范围 (即 min(SOC) <= soc_min
        且 max(SOC) >= soc_max)。仅当 'SOC' 在 required_columns 中时检查。

    Returns
    -------
    pd.DataFrame

    Raises
    ------
    PreflightError
        具体错误码由错误类型决定。
    FileNotFoundError
        If the CSV file does not exist.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV 文件不存在: {csv_path}")

    df = pd.read_csv(csv_path)

    missing_cols = [c for c in required_columns if c not in df.columns]
    if missing_cols:
        raise PreflightError(
            "DATA-E001",
            f"CSV 缺少必填列: {missing_cols}。存在的列: {list(df.columns)}",
            exit_code=20,
        )

    if len(df) < min_rows:
        raise PreflightError(
            "DATA-E001",
            f"CSV 行数不足: {len(df)} < {min_rows}",
            exit_code=20,
        )

    if "SOC" in required_columns:
        soc = df["SOC"]
        if soc.min() > soc_min or soc.max() < soc_max:
            raise PreflightError(
                "DATA-E001",
                f"SOC 覆盖不足: [{soc.min():.3f}, {soc.max():.3f}], "
                f"要求覆盖 [{soc_min}, {soc_max}]",
                exit_code=20,
            )

    return df


# ============================================================================
# 拟合诊断量
# ============================================================================

def compute_rmse(residuals: np.ndarray) -> float:
    """RMSE = sqrt(mean(residuals^2))"""
    return float(np.sqrt(np.mean(residuals ** 2)))


def compute_r_squared(y_pred: np.ndarray, y_obs: np.ndarray) -> float:
    """R^2 = 1 - SS_res / SS_tot"""
    ss_res = np.sum((y_obs - y_pred) ** 2)
    ss_tot = np.sum((y_obs - np.mean(y_obs)) ** 2)
    if ss_tot == 0.0:
        return 1.0 if ss_res == 0.0 else 0.0
    return float(1.0 - ss_res / ss_tot)


def numerical_hessian_2x2(
    loss_fn,
    x_opt: np.ndarray,
    args: tuple,
    h: float = 1e-4,
) -> np.ndarray:
    """有限差分计算 2x2 Hessian。仅适用于 2 维优化。

    Parameters
    ----------
    loss_fn : callable
        loss_fn(x, *args) -> float
    x_opt : np.ndarray
        最优点 (2,)
    args : tuple
        传给 loss_fn 的额外参数
    h : float
        步长

    Returns
    -------
    np.ndarray
        2x2 Hessian 矩阵

    Raises
    ------
    np.linalg.LinAlgError
        若数值不稳定。
    """
    H = np.zeros((2, 2))
    f0 = loss_fn(x_opt, *args)

    for i in range(2):
        for j in range(i, 2):
            x_pp = x_opt.copy()
            x_pm = x_opt.copy()
            x_mp = x_opt.copy()
            x_mm = x_opt.copy()

            x_pp[i] += h
            x_pp[j] += h
            x_pm[i] += h
            x_pm[j] -= h
            x_mp[i] -= h
            x_mp[j] += h
            x_mm[i] -= h
            x_mm[j] -= h

            H[i, j] = (
                loss_fn(x_pp, *args)
                - loss_fn(x_pm, *args)
                - loss_fn(x_mp, *args)
                + loss_fn(x_mm, *args)
            ) / (4.0 * h * h)
            H[j, i] = H[i, j]

    # Sanity check: diagonal should be positive for a minimum
    if H[0, 0] <= 0 or H[1, 1] <= 0:
        raise np.linalg.LinAlgError(
            f"Hessian diagonal non-positive: [{H[0,0]:.6e}, {H[1,1]:.6e}]"
        )

    return H


def estimate_uncertainty_2var(
    loss_fn,
    x_opt: np.ndarray,
    args: tuple,
    n_data: int,
    residual_sse: float,
) -> tuple[float, float]:
    """基于 Hessian 近似计算 2 个参数的标准差。

    cov = sigma_residual^2 * inv(H/2)
    sigma_i = sqrt(diag(cov)[i])

    Parameters
    ----------
    loss_fn : callable
        loss_fn(x, *args) -> float (SSE, not MSE)
    x_opt : np.ndarray
        最优点 (2,)
    args : tuple
        传给 loss_fn 的额外参数
    n_data : int
        数据点数
    residual_sse : float
        残差平方和 (loss_fn 在最优点的返回值)

    Returns
    -------
    (sigma_param1, sigma_param2) : tuple[float, float]
        若 Hessian 不正定, 返回 (NaN, NaN) 并打印警告。
    """
    try:
        H = numerical_hessian_2x2(loss_fn, x_opt, args)
    except np.linalg.LinAlgError as e:
        warnings.warn(f"Hessian 计算失败, 不确定度不可用: {e}")
        return (float("nan"), float("nan"))

    n_params = 2
    dof = max(n_data - n_params, 1)
    sigma_sq = residual_sse / dof

    try:
        H_half = H / 2.0
        cov = sigma_sq * np.linalg.inv(H_half)
    except np.linalg.LinAlgError:
        warnings.warn("Hessian 奇异, 不确定度不可用。")
        return (float("nan"), float("nan"))

    d0 = cov[0, 0]
    d1 = cov[1, 1]
    if d0 < 0 or d1 < 0:
        warnings.warn(
            f"协方差对角线为负 [{d0:.6e}, {d1:.6e}], 不确定度不可用。"
        )
        return (float("nan"), float("nan"))

    return (float(np.sqrt(d0)), float(np.sqrt(d1)))


# ============================================================================
# Spec 写回
# ============================================================================

def make_value_with_provenance(
    value: float,
    status: str,
    fit_step: str | None = None,
    fit_source: str | None = None,
    fit_script_version: str | None = None,
    fit_r_squared: float | None = None,
    uncertainty: float | None = None,
    last_modified_at: str | None = None,
) -> dict:
    """构造一个完整的 value_with_provenance 对象。

    last_modified_at 默认为当前 UTC 时间 (ISO 8601)。
    status 必须在 schema 允许的枚举值中, 否则 ValueError。
    """
    if status not in _VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of {sorted(_VALID_STATUSES)}"
        )
    if last_modified_at is None:
        last_modified_at = datetime.now(timezone.utc).isoformat()

    return {
        "value": value,
        "status": status,
        "fit_step": fit_step,
        "fit_source": fit_source,
        "fit_script_version": fit_script_version,
        "fit_r_squared": fit_r_squared,
        "uncertainty": uncertainty,
        "last_modified_at": last_modified_at,
    }


def write_back_to_material_spec(
    spec_path: Path,
    updates: dict[str, dict],
) -> None:
    """把若干字段更新写回材料 spec 文件。

    Parameters
    ----------
    spec_path : Path
        材料 spec JSON 文件路径。
    updates : dict[str, dict]
        字段名 -> 新的 value_with_provenance dict。
        例如 {'LR': {...}, 'OFS': {...}}

    Steps:
    1. 读取现有 spec
    2. 应用更新
    3. 同时更新顶层 last_modified_at
    4. 验证 schema (失败则不写文件, 抛 ValueError)
    5. 原子写文件 (先写 .tmp 再 rename)
    """
    with open(spec_path) as f:
        spec = json.load(f)

    for field_name, new_value in updates.items():
        spec[field_name] = new_value

    spec["last_modified_at"] = datetime.now(timezone.utc).isoformat()

    # Validate against schema before writing
    schema_path = _find_material_schema(spec_path)
    with open(schema_path) as f:
        schema = json.load(f)
    try:
        jsonschema.validate(instance=spec, schema=schema)
    except jsonschema.ValidationError as e:
        raise ValueError(
            f"Schema validation failed after applying updates: {e.message}"
        ) from e

    # Atomic write: write to .tmp then rename
    tmp_path = spec_path.with_suffix(".tmp")
    with open(tmp_path, "w") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp_path.rename(spec_path)


def _find_material_schema(spec_path: Path) -> Path:
    """Locate material.schema.v1.json relative to spec_path's project."""
    current = spec_path.resolve().parent
    while current != current.parent:
        candidate = current / "schemas" / "material.schema.v1.json"
        if candidate.exists():
            return candidate
        current = current.parent
    raise FileNotFoundError(
        "Cannot find schemas/material.schema.v1.json in any parent directory "
        f"of {spec_path}"
    )


# ============================================================================
# Provenance 工具
# ============================================================================

def get_git_commit_hash() -> str:
    """返回当前 git HEAD 的 commit hash。

    若无 git 或不在 git 仓库中, 返回 'unknown'。
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "unknown"


def hash_file(path: Path) -> str:
    """返回文件内容的 SHA-256 短哈希 (前 12 字符)。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


# ============================================================================
# Run artifact 写出
# ============================================================================

class RunArtifactWriter:
    """创建 runs/{run_id}/ 目录并写 fit_config.json, fit_report.md,
    fit_diagnostic.json 三份文件。

    Usage::

        writer = RunArtifactWriter('fit1', 'panasonic_ncr18650b')
        writer.write_config(cli_args, spec_hashes, csv_hash)
        writer.write_report_md(fit_summary)
        writer.write_diagnostic_json(full_data)
        print(f"Artifacts: {writer.run_dir}")
    """

    def __init__(
        self,
        run_id_prefix: str,
        cell_type: str,
        base_dir: Path = Path("runs"),
    ):
        """run_id 格式: {YYYYmmdd_HHMMSS}_{run_id_prefix}_{cell_type}"""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.run_id = f"{ts}_{run_id_prefix}_{cell_type}"
        self.run_dir = base_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def write_config(
        self,
        cli_args: dict,
        spec_hashes: dict,
        csv_hash: str,
    ) -> None:
        """fit_config.json: CLI 参数原样回显 + 输入文件 hash"""
        config = {
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cli_args": _make_serializable(cli_args),
            "input_hashes": {
                "spec": spec_hashes,
                "csv": csv_hash,
            },
            "git_commit": get_git_commit_hash(),
        }
        self._write_json("fit_config.json", config)

    def write_report_md(self, fit_summary: dict) -> None:
        """fit_report.md: 人类可读 markdown 格式。"""
        lines = [
            f"# FIT Report: {self.run_id}",
            "",
            f"**Timestamp**: {fit_summary.get('timestamp', 'N/A')}",
            f"**Cell type**: {fit_summary.get('cell_type', 'N/A')}",
            f"**Fit step**: {fit_summary.get('fit_step', 'N/A')}",
            "",
            "## Input",
            f"- Material spec: {fit_summary.get('material_spec', 'N/A')}",
            f"- EXP CSV: {fit_summary.get('exp_csv', 'N/A')}",
            "",
            "## Results",
        ]

        for param_name, param_data in fit_summary.get("parameters", {}).items():
            val = param_data.get("value", "N/A")
            sigma = param_data.get("uncertainty", "N/A")
            lines.append(f"- **{param_name}** = {val} +/- {sigma}")

        lines.extend([
            "",
            "## Acceptance",
            f"- RMSE: {fit_summary.get('rmse', 'N/A')}",
            f"- R-squared: {fit_summary.get('r_squared', 'N/A')}",
            f"- Verdict: {fit_summary.get('verdict', 'N/A')}",
            "",
            "## Optimizer",
            f"- Converged: {fit_summary.get('converged', 'N/A')}",
            f"- Iterations: {fit_summary.get('n_iterations', 'N/A')}",
            f"- Message: {fit_summary.get('optimizer_message', 'N/A')}",
        ])

        if fit_summary.get("warnings"):
            lines.extend(["", "## Warnings"])
            for w in fit_summary["warnings"]:
                lines.append(f"- {w}")

        lines.append("")
        (self.run_dir / "fit_report.md").write_text("\n".join(lines))

    def write_diagnostic_json(self, full_data: dict) -> None:
        """fit_diagnostic.json: 机器可读完整诊断数据。"""
        self._write_json("fit_diagnostic.json", full_data)

    def _write_json(self, filename: str, data: dict) -> None:
        path = self.run_dir / filename
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            f.write("\n")


def _make_serializable(obj):
    """Convert Path and other non-JSON types for serialization."""
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_serializable(v) for v in obj]
    return obj
