# SPEC: Degradation Mode Aging Rate Law Inversion (FIT-4a/b/c)

**Status**: Spec frozen 2026-05-01 (子阶段 1 of `release/v0.7.0-fit4`).
**Assignee**: Claude Code (子阶段 2 实装 `libquiv_aging/dm_aging_fit.py`, 子阶段 3 CLI `scripts/fit_dm_aging.py`, 子阶段 4 测试 `tests/test_dm_aging.py`).
**Blocks**: 老化预测端到端能力 (paper Mmeka 2025 全栈复现 + 反演).
**Depends on**: SPEC_ic_analysis.md frozen 输出 (per-RPT JSON), `libquiv_aging/aging_kinetics.py` SSoT, `docs/PARAMETERS.json::fit_steps::FIT-4a/4b/4c`.

---

## §1. Purpose and Boundary

FIT-4 是 IC analysis 输出 (per-RPT (LLI, LAM_PE, LAM_NE) 三元组时间序列) 的下游消费阶段, 把 RPT 时间序列反演为 paper Mmeka 2025 §Degradation Mechanisms rate law 的 rate constants. 沿用现状 `fit_steps::FIT-4a/4b/4c` 命名空间 (calendar / cycle / knee, 子阶段 0 裁定 A):

- **FIT-4a (calendar)**: 拟合 calendar rate constants from EXP-E (`k_SEI_cal`, `k_LAM_PE_cal`, `gamma_PE`, `R_SEI`, `E_a_SEI`). Rate law: paper Eq. 36 (SEI calendar 项), Eq. 40 (LAM_PE calendar 项), Eq. 45 (NE 电阻退化因子).
- **FIT-4b (cycle, pre-knee)**: 拟合 cycle rate constants from EXP-F (`k_SEI_cyc`, `k_LAM_PE_cyc`, `k_LAM_NE_cyc`); `parameters_frozen` = 全部 FIT-4a 产出. Rate law: paper Eq. 36 (SEI cycle 项), Eq. 40 (LAM_PE cycle 项), Eq. 41 (LAM_NE cycle, paper k_cal=0).
- **FIT-4c (knee)**: 1D `scipy.optimize.minimize_scalar` 拟合 `k_LP` from EXP-G; `parameters_frozen` = FIT-4a + FIT-4b 全部产出. Rate law: paper Eq. 39 (Butler-Volmer plating, irreversible via `max(0, BV)`).

不在本 SPEC 范围:
- 重新做 IC analysis (留 SPEC_ic_analysis frozen).
- 拟合 paper Eq. 42 `LLI_PE` (paper 设为 0, 工程沿用).
- 拟合 paper Eq. 46 `f_R,s` (paper 设为 1, 工程沿用).
- cell_type 派发 (本 release 仅校准 NCR18650B).

### 1.1 Paper 已知简化与笔误明文登记 (FIT-4 沿用)

下表 6 条均不在 FIT-4 中再做选择性修正; 实施按既定路径处理. 详见 `docs/CRITICAL_REVIEW.md` 对应小节 (paper errata 与 simplifications 已在 v0.5.3 之前事实层登记完毕, 本 SPEC 仅作引用并标注 FIT-4 实施后果).

| # | 类别 | 内容 | 工程实施后果 | 权威路径 |
|---|---|---|---|---|
| 1 | 简化 | `V_LP_eq = 0 V` 静态镀锂起始电位 (paper §Irreversible plating 自承) | 快充 (>1C) / 低温 (<15°C) 外推失准; FIT-4c 仅在 NCR18650B DST 协议域内可信 | `CRITICAL_REVIEW.md §S2`; `aging_kinetics.py::PlatingParameters` docstring |
| 2 | 简化 | `f_R,s = 1` (R_s 不退化, paper Eq. 46) | 末期极化被低估; FIT-4c 预测 knee 位置可能略后推 | `CRITICAL_REVIEW.md §C3`; `aging_kinetics.py::f_Rs` |
| 3 | 简化 | 仅 SEI 项有 Arrhenius (paper Eq. 36); LAM_PE/LAM_NE/plating 无温度依赖 | <15°C 或 >40°C 外推失准; FIT-4b/4c 不能在 EXP-F/G 训练域之外做温度外推 | `CRITICAL_REVIEW.md §S3`; `aging_kinetics.py::SEIParameters` docstring |
| 4 | 笔误 | paper Table I.b 把 `k_NE^SEI,cal` 印为 4.2e-22 A²·s (差 20 个数量级) | 工程已纠正为 4.2e-2 A²·s (`aging_kinetics.py::SEIParameters.k_cal` 注释); FIT-4a 拟合产出按正确量级写回 PARAMETERS.json | `CRITICAL_REVIEW.md §E1` |
| 5 | 笔误 | paper §Calendar degradation 文字把 `k_NE^SEI,cyc` 误列入 calendar rate constants | FIT-4a 实施按 Table I.b + Eq. 36 calendar 项对齐 (calendar 部分对应 `k_SEI^cal·exp(-α_f·F·V_NE/RT)`, 不含 cyc) | `CRITICAL_REVIEW.md §E2` |
| 6 | 隐性耦合 | `R_NE_0 ↔ R_NE_LUT` 同步约束 (R4 rule) | FIT-4 不重新计算 R_NE_0; 由 `param_specs/<cell>__mmeka2025.params.json` 提供 (50% SOC, C/3 LUT 派生); `R_NE_LUT` 一旦更新, R_NE_0 必须人手重派, 否则 NE 电阻轨迹偏置 | `docs/CLAUDE.md` R4; `aging_kinetics.py::ResistanceAgingParameters` docstring |

---

## §2. Data Contract (per §0.6 数据自动化 + 留痕原则)

### 2.1 Input

CLI 入口 `scripts/fit_dm_aging.py` 接受 cell-level raw data 根目录 `--cell-dir <path>`. 该目录必须包含:

**(a) Per-RPT IC analysis 输出 JSON**

路径: `<cell-dir>/RPT_<NN>/ic_output.json` (NN = 两位 RPT 序号, e.g. `RPT_03`).

Schema 同 SPEC_ic_analysis frozen 输出 (per `scripts/fit_ic_to_dms.py::_build_output_payload`):

- 必填字段: `LLI_Ah`, `LAM_PE_Ah`, `LAM_NE_Ah` (float, Ah); `LLI_std_Ah`, `LAM_PE_std_Ah`, `LAM_NE_std_Ah` (float, Ah).
- `fit_quality`: `rmse_V`, `r_squared`, `n_points`, `converged` (bool), `marginal_quality` (bool), `bounds_hit` (list[str]).
- `metadata`: provenance 段 (input_file, cell_type, timestamp, git_commit, input_file_hash, algorithm).

上游质量信号传递规则: 见 §3.4.

**(b) Cell-level RPT 调度 metadata CSV**

路径: `<cell-dir>/cell_<cell_id>_rpt.csv` (沿用 `scripts/fit_ic_to_dms.py:18` 既有惯例 + `DATA-E005` cross_refs 命名).

必填列 (按 stage 区分):

| 列名 | 类型 | 单位 | 必填 stage | 说明 |
|---|---|---|---|---|
| `rpt_index` | int | — | all | joins to `RPT_<NN>/` 子目录索引 |
| `EFC` | float | cycles | all | cumulative equivalent full cycles since BoL (calendar 段 EFC=0) |
| `time_s` | float | s | all | cumulative time since BoL |
| `T_storage_K` | float | K | all | 段平均温度 (calendar = 静置 T; cycle = 循环 T_avg) |
| `SOC_storage` | float | [0,1] | 4a | calendar 段静置 SOC (cycle 段可填段 SOC 中点或 NaN) |
| `cap_loss_Ah` | float | Ah | 4b, 4c | C_nominal - C_RPT (RPT C/40 实测总放电量, **独立于 IC 输出**, 用于 4b S3 与 4c) |
| `phase` | str | — | optional | "calendar" / "cycle"; 如缺省, 全部 RPT 参与 stage 拟合 |
| `c40_charge_filename`, `c40_discharge_filename` | str | — | optional | IC analysis 上游引用 (DATA-E005 cross_refs); FIT-4 不直接消费 |

CLI **不接受** 用户合并的 metadata CSV、预处理 JSON、或 `--rpt-records-json` 类参数. 缺失或格式偏差时按 stage 抛 `FIT4*-E005` (4a) / `FIT4B-E004` (4b) / `FIT4C-E003` (4c) 错误码并落 `_debug/` snapshot.

### 2.2 Output

各 stage 落盘三个**独立** result JSON 到 `<out>/`:

- `<out>/fit4a_calendar_result.json` — `FIT4ACalendarResult` 序列化
- `<out>/fit4b_cycle_result.json` — `FIT4BCycleResult` 序列化 (含 S3 字段, N3 落点)
- `<out>/fit4c_knee_result.json` — `FIT4CKneeResult` 序列化

各 result JSON 字段总集:

```
{
  "<rate constants 字段>": float,    # e.g., k_SEI_cal, k_SEI_cyc, k_LP
  "rate_constants_std": {<param>: float},   # Hessian 协方差; LinAlgError fallback NaN
  "fit_quality": {
    "rmse_LLI_Ah": float, "r2_LLI": float,
    "rmse_LAM_PE_Ah": float, "r2_LAM_PE": float,
    "rmse_LAM_NE_Ah": float, "r2_LAM_NE": float,
    "n_rpt": int, "converged": bool,
    "marginal_quality": bool,    # 任一度量在 marginal 区间
    "pass_overall": bool,         # 三度量都 PASS
    "bounds_hit": list[str]
  },
  "warnings": list[str],          # W-code 字符串 + 上游 ICA marginal_quality / bounds_hit 传播
  "metadata": {
    "input_hash": str,            # sha256 of cell-dir 文件树
    "git_commit": str,
    "timestamp": str,             # ISO-8601 UTC
    "libquiv_aging_version": str,
    "algorithm": str              # "scipy.optimize.least_squares (trf, bounds=...); Hessian covariance"
  }
}
```

FIT-4b 特有 S3 字段 (N3 落点):

```
"cap_loss_self_consistency": {
  "rel_error_max": float,           # max_i |cap_loss_model_i - cap_loss_obs_i| / cap_loss_obs_i
  "pass": bool,                      # rel_error_max < 0.05
  "marginal": bool,                  # 0.05 ≤ rel_error_max ≤ 0.10
  "rpt_indices_compared": list[int]
}
```

FIT-4c 特有字段:

```
"k_LP": float,
"k_LP_std": float,                  # 1D numerical Hessian, fallback NaN
"knee_efc_predicted": float         # forward 求解 cap_loss(EFC) 二阶导极值
```

### 2.3 Debug snapshot (留痕原则)

E-code 抛出时, CLI 在 exit 前 (即 `sys.exit(exit_code)` 之前) 落盘 `<out>/_debug/<error_code>_<UTC_timestamp>.json`:

```
{
  "error_code": "FIT4B-E007",
  "error_message": "...",
  "stage": "calendar" | "cycle" | "knee",
  "input_summary": {
    "cell_dir": str,
    "n_rpt": int,
    "rpt_records_brief": [{"rpt_index": int, "EFC": float, "time_s": float, "T_storage_K": float, "LLI_Ah": float, ...}]
  },
  "initial_guess": {<param>: float},
  "convergence_history": [    # 后 10 步 (若 optimizer 未启动则空)
    {"iteration": int, "cost": float, "grad_norm": float, "rate_constants_snapshot": {...}}
  ],
  "metadata": {<同 result JSON metadata 段>}
}
```

W-code (warn 级别) **默认不触发** `_debug/` snapshot; 警告内容写入 result JSON `warnings` 字段. CLI flag `--debug-on-warning` 可强制 W-code 也落 snapshot, 默认关闭.

**不**预先落盘 RPT 元数据聚合后的 `list[RPTRecord]`. 若 debug 需要, CLI 加 `--save-intermediate` flag 写到 `<out>/_intermediate/rpt_records.json`. 不入 SPEC 强制项.

**不**引入跨阶段汇总 JSON (`fit4_summary.json`) — §0.6 反过度构造. 若将来频繁需要跨阶段视图, 加 `scripts/summarize_fit4.py` 后处理脚本, 不入主 pipeline.

---

## §3. Algorithm

### 3.1 Forward Model SSoT

Rate law SSoT 是 `libquiv_aging/aging_kinetics.py`. Paper §Degradation Mechanisms Eqs. 36-46 是物理追溯锚点, 不在 SPEC 中重写公式. 各 stage 调用的 SSoT 函数:

| Stage | SSoT functions | Paper Eqs |
|---|---|---|
| FIT-4a (calendar) | `I_SEI_NE` (calendar 项, k_cyc=0), `I_LAM_PE` (calendar 项), `f_R_NE` | 36 (calendar), 40 (calendar), 45 |
| FIT-4b (cycle) | `I_SEI_NE` (cycle 项, calendar frozen), `I_LAM_PE` (cycle 项), `I_LAM_NE` (cycle, paper k_cal=0) | 36 (cycle), 40 (cycle), 41 |
| FIT-4c (knee) | `I_PLA_NE` (Butler-Volmer, max(0, BV)) | 39 |

Forward 通用框架 `EquivCircuitCell` (paper Eqs. 1-30 cell DAE) 在 cost_fn 中被复用, FIT-4 只调老化 rate constants, 不动 cell 模型.

### 3.2 Optimizer

Paper 是 manual tuning (§Calendar/Cycle/Rate-dependent plating 各 "manually adjusting" 1-4 个参数). **本工程升级到自动拟合**, 与 SPEC_ic_analysis 同 design pattern:

- **FIT-4a / FIT-4b**: `scipy.optimize.least_squares(method="trf", bounds=...)` + `result.jac` Hessian 协方差 (`cov = sigma2 · inv(J.T @ J)`, `sigma2 = SSE / (N - n_params)`); `np.linalg.LinAlgError` fallback `std = NaN`. 与 ICA precedent 一致.
- **FIT-4c**: 1D `scipy.optimize.minimize_scalar` (沿用 PARAMETERS.json::fit_steps::FIT-4c::method); `k_LP_std` 通过 numerical Hessian 估计 (`(d²cost/dk²)⁻¹ · sigma²`), 非有限时 fallback NaN.

三阶段共用还是独立函数: 共用 inner solver helper (e.g., `_run_least_squares(cost_fn, x0, bounds) -> (x_hat, std_dict, fit_quality_dict)`) 减少重复; 各 stage 的 cost_fn 独立 (调用对应 SSoT 函数集合). 顶层公共 API (`fit_calendar_aging` / `fit_cycle_aging` / `fit_knee_location`) 各 stage 独立函数, 便于子阶段 4 单独测试.

### 3.3 Sub-fits 顺序 (R2 / R3 / R4 强制)

```
FIT-4a (calendar)
  ├ EXP-E (cell stored at 多 SOC × 多 T)
  ├ free: {k_SEI_cal, k_LAM_PE_cal, gamma_PE, R_SEI, E_a_SEI}
  ├ frozen: cell_factory + Tier I/II/III 参数 + R_NE_0 (R4)
  └ output: fit4a_calendar_result.json + (E-code 时) _debug/
        ↓ R2 强制: FIT-4a 全部产出 frozen, k_LP=0 (FIT4B-E001/E002)
FIT-4b (cycle)
  ├ EXP-F (cell cycled)
  ├ free: {k_SEI_cyc, k_LAM_PE_cyc, k_LAM_NE_cyc}
  ├ frozen: FIT-4a 全部产出 + Tier I/II/III + k_LP=0
  ├ S3: cap_loss self-consistency rel_error < 10% (N3 落点)
  └ output: fit4b_cycle_result.json (含 S3 字段) + (E-code 时) _debug/
        ↓ R2 强制: FIT-4a + FIT-4b 全部产出 frozen (FIT4C-E001)
FIT-4c (knee)
  ├ EXP-G (cell cycled past knee)
  ├ free: {k_LP}
  ├ frozen: 全部上游
  └ output: fit4c_knee_result.json + (E-code 时) _debug/
```

R3 (resistance LUT 仅 fresh-cell): 三 stage cost_fn 内部 forward 仿真时, `R_s_LUT` / `R_NE_LUT` / `R_PE_LUT` 不重测; 老化期间电阻通过 `f_R_PE`, `f_R_NE`, `f_Rs` 因子自动应用. FIT-4a 拟合 `R_SEI` 是唯一从老化数据识别的电阻参数.

R4 (R_NE_0 派生): FIT-4 不重新派生 R_NE_0; 由 spec 提供 (50% SOC, C/3 取自 LUT 的标量). FIT-4 cost_fn 把 R_NE_0 作为 `ResistanceAgingParameters` 字段引用, 不作为 free parameter.

### 3.4 Internal sub-steps (S1 / S2 / S3, 各 stage 内部 pipeline)

每 stage 内部按相同三步 pipeline (S3 仅 FIT-4b):

**S1 RPT 元数据聚合**

`aggregate_rpt_records(cell_dir, stage) -> list[RPTRecord]` 扫描 `<cell-dir>/RPT_<NN>/ic_output.json` + `<cell-dir>/cell_<id>_rpt.csv`, by `rpt_index` joining. 在内存返回 `list[RPTRecord]`; 不落盘 (除 `--save-intermediate`).

**Upstream IC analysis 质量信号传递规则**:
- `bounds_hit` 命中 (ICA-W002) 或 `converged=False` 的 RPT 数据点在 cost_fn 中以 `LLI_std_Ah` / `LAM_PE_std_Ah` / `LAM_NE_std_Ah` 倒数加权 (`weight_i = 1/std_i^2`), 不直接排除.
- `marginal_quality=True` 的 RPT 不影响权重, 但其 ICA-W001 字符串写入 result JSON `warnings` 字段供下游审计.
- 若 ≥ 30% 的 RPT 命中 `bounds_hit` 或 `converged=False`, 抛 `FIT4*-E005` (4a) / `FIT4B-E004` / `FIT4C-E003` (上游数据 unsuitable for FIT-4 反演).

**S2 rate constants 反推**

各 stage 对应 SSoT 函数 forward 仿真 + scipy 优化, 按 §3.2. 异常处理:
- `result.status ≤ 0` 或 Hessian 非有限 → 抛 `FIT4*-E006` (4a) / `FIT4B-E005` / `FIT4C-E004`.
- `fit_quality` 落入 FAIL 区间 (§4) → 抛 `FIT4*-E007` (4a) / `FIT4B-E006` / `FIT4C-E005`.
- bounds_hit (距 bound 边界 < 1% 量级) → 写 `FIT4*-W002` 到 `warnings` (warn 级别, 不阻塞).
- marginal fit_quality → 写 `FIT4*-W001` 到 `warnings`.

**S3 cap_loss self-consistency 验证 (仅 FIT-4b, N3 落点)**

S2 产出 cycle rate constants → `EquivCircuitCell` forward 跨 cell EFC 时间轴 → 模型 `cap_loss_model(EFC_i)` 序列 → vs `cap_loss_Ah` 实测 (来自 `cell_<id>_rpt.csv`, RPT C/40 总放电量, **独立于 IC 输出**).

`rel_error_max = max_i |cap_loss_model_i - cap_loss_obs_i| / cap_loss_obs_i`.

- `rel_error_max > 0.10` → 抛 `FIT4B-E007` (S3 FAIL, 物理一致性问题).
- `0.05 ≤ rel_error_max ≤ 0.10` → 写 `FIT4B-W001` marginal flag, 不阻塞.
- `rel_error_max < 0.05` → PASS, 落入 result JSON `cap_loss_self_consistency` 段.

S3 N3 物理依据见 §8.

### 3.5 Bounds (NCR18650B 校准, 起步值)

具体数字由子阶段 2 实证微调 (核对 PARAMETERS.json::parameters::k_*::paper_value_NCA_G); 起步范围 (paper Table I.b 量级, 跨度 2-3 个数量级):

| Stage | Parameter | Bounds | Paper 量级 |
|---|---|---|---|
| 4a | `k_SEI_cal` | [1e-4, 1.0] A²·s | 4.2e-2 (Table I.b 纠正后) |
| 4a | `k_LAM_PE_cal` | [1e-12, 1e-7] A | paper Table I.b |
| 4a | `gamma_PE` | [0, 30] /V | paper Table I.b |
| 4a | `R_SEI` | [0.1, 5.0] (无因次) | 0.66 |
| 4a | `E_a_SEI` | [40000, 80000] J/mol | 55500 (若 EXP-E 温度点 < 3 抛 FIT4A-E002, free→fixed) |
| 4b | `k_SEI_cyc` | [1e-4, 1.0] F | paper Table I.b |
| 4b | `k_LAM_PE_cyc` | [1e-12, 1e-6] | paper Table I.b |
| 4b | `k_LAM_NE_cyc` | [1e-14, 1e-8] | paper Table I.b |
| 4c | `k_LP` | [1e-12, 1e-6] A | paper Table I.b |

bounds_hit (距 bound 边界 < 1% 量级) 触发 `FIT4*-W002`. bounds 设计反映模型适用域; 命中通常意味着 cell 已超出 paper alawa regime (CEI 主导 / 严重 plating), 不应通过简单放宽 bound 修复.

---

## §4. Fit-quality Thresholds (NCR18650B 校准)

阈值依据:
- paper Table I.b 量级 (NCR18650B 标称 3.35 Ah)
- paper Mmeka 2025 Fig. 6c (143 EFC: LLI=0.13 Ah, LAM_PE=0.08 Ah, LAM_NE=0.04 Ah, cap_loss=0.11 Ah)
- ICA precedent (`RMSE_FAIL_V=0.020`, `R2_FAIL=0.99` in V/Q domain)
- FIT-2 precedent (`RMSE_FAIL_V=5 mV`, `R2_FAIL=0.95`)

| 度量 | PASS | MARGINAL (W001) | FAIL (E007 / E006 / E005) |
|---|---|---|---|
| R² (LLI(t), LAM_PE(t), LAM_NE(t) 各自独立) | > 0.99 | 0.95 ≤ R² ≤ 0.99 | < 0.95 |
| RMSE (LLI / LAM_PE / LAM_NE in Ah, 各自独立) | < 0.02 | 0.02 ≤ RMSE ≤ 0.05 | > 0.05 |
| FIT-4b S3 cap_loss self-consistency `rel_error_max` | < 0.05 | 0.05 ≤ rel_error ≤ 0.10 | > 0.10 (FIT4B-E007) |

R² 走相对量, 跨 cell_type 稳健 (自带方差归一). RMSE 走绝对量, 基于 NCR18650B 量级 (老化 LLI 范围 0.05-0.20 Ah; 0.02 Ah 是 paper 量级 ~10%, 0.05 Ah 是 ~25%).

`fit_quality.marginal_quality = (任一度量在 marginal 区间)`; `fit_quality.pass_overall = (三度量都 PASS)`.

NCR18650B 之外 cell_type 接入由该 cell_type 的 SPEC 扩展或 fit_steps 子条目覆盖, 本 release 不实施 cell_type 派发.

**子阶段 1 SPEC frozen 起步值不允许 TBD**: 上表数字为起步固定值, 子阶段 2 实施过程若发现校准偏差, 通过 ADR 升级而非默改 SPEC.

---

## §5. Sub-fits Sequencing (R2 强制重申)

执行序: `FIT-4a → FIT-4b → FIT-4c`. 各 stage 入口前的 `parameters_frozen` 检查由 R2 错误码强制 (现状 `FIT4B-E001`, `FIT4B-E002`, `FIT4C-E001` 已覆盖, 不重发新 code).

CLI 实施: `--stage calendar | cycle | knee | all`. `--stage all` 串行调用三 stage, autoload 上一阶段 result JSON 作为 frozen 参数; 任一 stage E-code 抛出则后续 stage 跳过. 各 stage 独立 CLI 调用允许重跑单 stage (e.g., 仅 FIT-4c 用上游已存的 fit4a/fit4b result.json).

---

## §6. Output Schema

详见 §2.2 与 §2.3.

约束总结:
- **三 result JSON 是科学结论的原子单位**, 直接服务于"各衰减模式贡献分析"目标. 不预先汇总, 不强制中间状态落盘.
- **失败时强制落 `_debug/` snapshot**, 含输入摘要 + 初值 + 收敛历史, 离线服务器事后追溯无需重跑.
- **provenance metadata 段**强制每个 result JSON 都含, 沿用 v0.5.2 IC analysis 惯例 (`get_git_commit_hash` / `hash_file` / `RunArtifactWriter` from `libquiv_aging/fitting.py`).

---

## §7. Acceptance Tests T1-T5

子阶段 4 实施 `tests/test_dm_aging.py`. 详细签名由子阶段 4 实证决定; 范围如下:

| # | 主题 | 期望 |
|---|---|---|
| T1 | Forward-only 单 EFC 点 | 给定 rate constants → SSoT (`I_SEI_NE` / `I_LAM_PE` / `I_LAM_NE` / `I_PLA_NE`) → LLI/LAM 增量与 paper Eqs. 36/40/41 解析公式一致 (numerical 1e-10 tolerance) |
| T2 | Round-trip synthetic | rate constants → forward (生成 RPT 时间序列 ground truth) → `fit_calendar/cycle/knee_aging` → 反推值 vs ground truth 在 1σ-2σ 内, 三 stage 独立 round-trip |
| T3 | Hessian 协方差 | T2 case `rate_constants_std` 报告非 NaN; 故意触发 `LinAlgError` (e.g. 单点退化数据) → fallback NaN std (R3 / ICA precedent 同) |
| T4 | **Paper Fig. 6c 实测数据 (FIT-4b S3 N3 落点)** | 用 paper Mmeka 2025 Fig. 6c 数字 (143 EFC: LLI=0.13 / LAM_PE=0.08 / LAM_NE=0.04 / cap_loss=0.11 Ah, sum=0.25, ratio=2.27) 反推 cycle rate constants, S3 `cap_loss_self_consistency.pass = True` (rel_error < 10%) |
| T5 | 错误码 + bounds_hit | 各 FIT4A/B/C-E*/W* 错误码合理触发: raw data 缺失 (E005/E004/E003 §0.6 例外路径), 不收敛 (E006/E005/E004), fit_quality FAIL (E007/E006/E005), S3 FAIL (FIT4B-E007), bounds_hit (W002), marginal_quality (W001) |

可加 T6 `aggregate_rpt_records` 单独测试 (mock cell-dir → `RPTRecord` list); 是否单列由子阶段 4 实证决定.

T4 是 v0.5.3 N3 entry 从"消费方约束"升级到"已贯彻"的最关键测试: paper Fig. 6c 数字现在终于在 FIT-4b S3 子步骤真正落地为可执行测试.

---

## §8. N3 Caveat (Explicit)

**FIT-4b 内部 S3 cap_loss self-consistency 子步骤**是 v0.5.3 N3 entry 的真正贯彻落点. SPEC 内部明文约束:

> DMs (LLI, LAM_PE, LAM_NE) 时间序列与 cap_loss 时间序列**各自独立拟合**, 不通过 sum constraint 联系. FIT-4b S3 子步骤验证两条独立测量曲线 (DMs 来自 IC analysis, cap_loss 来自 RPT C/40 总放电量) 的物理一致性, **不要求** sum(DMs) = cap_loss.

### 8.1 物理依据 (paper §Model reduction, page 14 原文)

> "When LLI occurs, this range narrows to X_PE ≈ 0.2…0.7 due to reduced lithium availability. If additional LAM_PE occurs, the stoichiometry range expands again to X_PE ≈ 0.2…0.9. As a result, the cell can cycle over a wider stoichiometry range, leading to an increase in capacity."

X_PE stoichiometry 循环范围被 LLI 窄化, 又被 LAM_PE 扩展 — 这是 sum(DMs) ≠ cap_loss 非线性关系的 paper 内部物理机制. 与 Dubarry & Anseán 2022 Front. Energy Res. 10:1023555 跨多化学体系 best practices 系统性观察一致 (详见 `docs/UPGRADE_LITERATURE/ic_analysis_methodology_review.md §3.3 Item 7`). `docs/CRITICAL_REVIEW.md §N3` 已详细登记 (paper Fig. 6c 143 EFC 数字 sum=0.25 / cap_loss=0.11 / ratio=2.27).

### 8.2 FIT-4b S3 实施

- `cap_loss_model(EFC)` = `EquivCircuitCell` forward 仿真 under fitted cycle rate constants 输出的 cell capacity 损失轨迹.
- `cap_loss_obs(EFC)` = `cell_<id>_rpt.csv::cap_loss_Ah` 列 (RPT C/40 实测 C_nominal - C_RPT, **独立**于 IC analysis 三元组).
- `rel_error_max = max_i |cap_loss_model_i - cap_loss_obs_i| / cap_loss_obs_i`.
- 阈值: PASS < 5%, MARGINAL 5-10%, FAIL > 10% (FIT4B-E007).

### 8.3 Out of scope for S3

- 不动 IC analysis 算法 (留 SPEC_ic_analysis frozen).
- 不要求 sum(DMs) 与 cap_loss 一致 (违反 N3 物理事实).
- 不在 FIT-4a (calendar) 实施 S3 (paper Fig. 6c 数字落在 cycle window; calendar window 的 cap_loss self-consistency 留作 v0.8+ 评估, 本 release 不实施).

---

## References

- paper Mmeka, Dubarry, Bessler 2025, J. Electrochem. Soc. 172:080538: §Degradation Mechanisms (Eqs. 36-46), §Calendar/Cycle/Rate-dependent plating, §Model reduction (page 14, X_PE stoichiometry range), Table I.b, Fig. 6c.
- `libquiv_aging/aging_kinetics.py` — rate law SSoT (`I_SEI_NE`, `I_PLA_NE`, `I_LAM_PE`, `I_LAM_NE`, `f_R_PE`, `f_R_NE`, `f_Rs`).
- `libquiv_aging/ic_analysis.py` + `scripts/fit_ic_to_dms.py` — FIT-4 输入产出 (SPEC_ic_analysis frozen).
- `libquiv_aging/fitting.py` — 通用基础设施 (`PreflightError`, `numerical_hessian_2x2`, `estimate_uncertainty_2var`, `RunArtifactWriter`, `get_git_commit_hash`, `hash_file`).
- `docs/PARAMETERS.json::fit_steps::FIT-4a / FIT-4b / FIT-4c` — 现状 entry; 子阶段 5/6 升级 `method` / `error_codes` 字段为本 SPEC 实施后实证.
- `docs/PARAMETER_SOP.md §SOP-4` — 流程层 (如何执行); 本 SPEC 是契约层 (必须满足什么).
- `docs/CRITICAL_REVIEW.md §E1 / §E2 / §S2 / §S3 / §C3 / §N3` — paper 简化与笔误事实层.
- `docs/error_codes_registry.json` — FIT4A/4B/4C/SOLVE/IDENT scope (本 SPEC 配套子阶段 1 同步扩展).
- `docs/CLAUDE.md` R2 / R3 / R4 / R5 — 拟合顺序与电阻 LUT 语义.
- `CLAUDE.md` (repo root) §0.6 — 数据自动化 + 留痕原则 (本 SPEC §2 实施载体).

**End of SPEC_dm_aging.**
