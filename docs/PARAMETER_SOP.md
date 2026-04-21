# Parameter Sourcing Standard Operating Procedure (SOP)

**单一事实来源（Single Source of Truth）**：所有参数元数据由 [`PARAMETERS.json`](./PARAMETERS.json) 定义。本文档是该 JSON 的**人类可读解释**和**操作流程**。

> ⚠️ **给 Claude Code 的关键指令**：
> 1. 任何关于"某参数的来源/实验/拟合步骤"的问题，**必须首先查 `PARAMETERS.json`** ，不要依赖其他 MD 文档里的段落描述。
> 2. 其他 MD 文档中若与 `PARAMETERS.json` 冲突，以 JSON 为准。
> 3. 若需修改参数信息（例如换电池体系），**先改 JSON，再改代码，最后更新相关 MD**。

---

## 一、参数层级速查（由 `PARAMETERS.json` 派生）

| 层级 | 定义 | 参数数 | 代表 |
| --- | --- | --: | --- |
| **I** | 从 datasheet 读或约定值 | 10 | `C_nominal_Ah`, `V_max`, `V_min`, `X0_PE/NE`, `X_LAM_PE/NE`, `alpha_LP`, `V_LP_eq`, `alpha_f_SEI`, `k_LAM_NE_cal` |
| **II** | Fresh cell 测量后作为 LUT / 静态值 | 5 | `V_PE_0_curve`, `V_NE_0_curve`, `R_s_LUT`, `R_NE_LUT`, `R_PE_LUT` |
| **II-derived** | 从 II 级 LUT 派生的标量 | 1 | `R_NE_0`（用于 `f_R,NE` 的归一化） |
| **II-literature** | 从文献直接取用 | 2 | `v_rel_PE_coeff`, `v_rel_NE_coeff` |
| **III** | 1–2 个标量的轻度拟合 | 5 | `LR`, `OFS`, `C1`, `C2`, `fractionR1toRs` |
| **IV_calendar** | 日历老化数据拟合 | 6 | `k_SEI_cal`, `E_a_SEI`, `k_LAM_PE_cal`, `gamma_PE`, **`R_SEI`**, `R_NE_0` |
| **IV_cycle** | 循环老化（knee 前）拟合 | 3 | `k_SEI_cyc`, `k_LAM_PE_cyc`, `k_LAM_NE_cyc` |
| **IV_knee** | 循环老化（knee 后）拟合 | 1 | `k_LP` |

### 关键事实（必读）

1. **所有 LUT 只在 fresh cell 测一次**：$V_\text{PE}^0, V_\text{NE}^0, R_s, R_\text{NE}, R_\text{PE}$ 都是 fresh-cell 的静态表。老化期间**不再重新测量**。
2. **$R_\text{SEI}$ 从日历老化数据拟合，不是循环老化**。论文 p.12 原话：
   > "The resistance increase (panel b) is predicted well by the simulation, despite the fact that all resistance-related aging parameters were taken from the calendar degradation study."
   
   原因：日历条件下 $Q_\text{PLA,NE} = 0$，内阻演化完全来自 SEI + LAM，$R_\text{SEI}$ 可唯一识别。
3. **$R_\text{NE}^0$ 不是独立自由参数**，它应从 fresh cell 的 $R_\text{NE}^0(I, X_\text{NE})$ LUT 在 (C/3, 50% SOC) 处取值。每次替换 LUT 后必须重新派生（代码需提供工具函数；见 §四 TODO）。
4. **内阻必须在 RPT 中测量**：否则 $R_\text{SEI}$ 无法拟合。具体要求见 `PARAMETERS.json::experiments::EXP-E::CRITICAL`。

---

## 二、实验 DOE（Design of Experiments）

按论文的参数化顺序，实验分为 10 个独立模块：

### Fresh cell 基础表征（EXP-A, B1–B4, C, D）

| ID | 名称 | 电池数 | 时长 | 产出参数 |
| --- | --- | --: | --- | --- |
| **EXP-A** | C/40 完整充放电 | 2 | ~80 h | `C_nominal_Ah`, 全电池 OCV |
| **EXP-B1** | PE 半电池 OCV | 4 (coin) | 2 周 | `V_PE_0_curve` → `.dat` 文件 |
| **EXP-B2** | NE 半电池 OCV | 4 (coin) | 2 周 | `V_NE_0_curve` → `.dat` 文件 |
| **EXP-B3** | Fresh cell EIS | 1 | 1 h | `R_s_LUT`（常数） |
| **EXP-B4** | GITT（电阻 map） | 1 | 1–2 周 | `R_NE_LUT`, `R_PE_LUT` → `.mat` 文件 |
| **EXP-C** | 电流阶跃弛豫 | 1 | 4 h | `C1`, `C2` |
| **EXP-D** | 动态协议验证 | 1 | 1 h | `fractionR1toRs` 等 |

### 老化实验（EXP-E, F, G）

| ID | 名称 | 电池数 | 时长 | 产出参数 | 关键要求 |
| --- | --: | --: | --- | --- | --- |
| **EXP-E** | 日历老化 | ≥4 最小（推荐 18） | 6–15 月 | `k_SEI_cal, E_a, k_LAM_PE_cal, γ_PE, R_SEI` | 每次 RPT 必测 IR |
| **EXP-F** | 循环老化（knee 前） | ≥2（推荐 6） | 1–3 月 | `k_SEI_cyc, k_LAM_PE_cyc, k_LAM_NE_cyc` | 每 30–50 EFC 做 RPT |
| **EXP-G** | 循环老化（knee 后） | 同 EXP-F | +3–6 月 | `k_LP` | 跑到 ~70% 容量 |

**每次 RPT 的标准流程**（`PARAMETERS.json::experiments::EXP-E::CRITICAL`）：

```
1) C/5 完整充放电   → 得到当前实际容量 C(t)
2) IR 脉冲 或 EIS   → 得到当前内阻 R(t)    ← 不能省！R_SEI 依赖
3) C/40 慢速充放电  → V_cell(SOC) 曲线
4) IC 分析（用 alawa 或等效工具） → LLI(t), LAM_PE(t), LAM_NE(t)
```

---

## 三、数据存储格式规范

### 3.1 Fresh cell 表征数据

| 数据类型 | 格式 | 存放位置 | 标准列/字段 |
| --- | --- | --- | --- |
| 半电池 OCV | `.dat` (alawa 格式) | `libquiv_aging/data/{material}Alawa.dat` | 3 列：`x`, `dH [J/mol]`, `dS [J/mol/K]`；`*` 开头为注释 |
| 电阻 LUT | `.mat` | `libquiv_aging/data/{name}Resistances.mat` | 3 个 (1001×2001) 矩阵：`RsAlawa`, `RNEAlawa`, `RPEAlawa` |
| 全电池 OCV | `.csv` | `experiments/EXP-A/{cell_id}_ocv.csv` | 列：`time_s, V_cell, I_A, Q_Ah, SOC` |
| 阶跃响应 | `.csv` | `experiments/EXP-C/{cell_id}_step.csv` | 列：`time_s, V_cell, I_A` |

**`.dat` 文件示例（alawa 格式）**：
```
* Electrode material: LFP
* Source: my C/40 half-cell test on 2026-xx-xx
* Sample: LFP-G-cell-02, XW1234
* x []          dH [J/mol]      dS [J/mol/K]
0.0000000       -1249.390       0.000000
0.0009700       -1466.854       0.000000
...
```

### 3.2 老化实验数据（每次 RPT 一行）

**推荐格式**：单一 CSV，每个 cell + 每次 RPT 一行：

路径：`experiments/{EXP-E|F|G}/{cell_id}_rpt.csv`

| 列名 | 单位 | 备注 |
| --- | --- | --- |
| `time_s` | s | 老化总时长（日历）或总测试时间（循环） |
| `EFC` | - | 仅循环老化需要（= ∫\|I\|dt / (2C₀)） |
| `T_storage_K` | K | 存储温度（日历老化用） |
| `SOC_storage` | 0..1 | 存储 SOC（日历老化用） |
| `C_measured_Ah` | Ah | C/5 测得的容量 |
| `R_IR_mOhm` | mΩ | IR 脉冲或 EIS 高频实部 |
| `LLI_Ah` | Ah | IC 分析得 |
| `LAM_PE_Ah` | Ah | IC 分析得 |
| `LAM_NE_Ah` | Ah | IC 分析得 |

### 3.3 目录约定

```
my_project/
├── libquiv_aging_py/                # 本工程
│   └── libquiv_aging/data/          # Fresh-cell LUT 放这里
│       ├── MyGraphiteAlawa.dat
│       ├── MyCathodeAlawa.dat
│       └── MyResistances.mat
│
└── experiments/                     # 你的实验数据
    ├── EXP-A/
    │   └── cell_01_fullcycle_C40.csv
    ├── EXP-B1/
    │   └── halfcell_PE_coin_03_C40.csv     # 还需经脚本转成 .dat
    ├── EXP-C/
    │   └── cell_01_step_50SOC.csv
    ├── EXP-E/
    │   ├── cell_E1_rpt.csv          # 每个 cell 一个 RPT 历史文件
    │   ├── cell_E2_rpt.csv
    │   └── metadata.csv             # 每个 cell 的 (T, SOC, 其他元数据)
    ├── EXP-F/
    │   └── cell_F1_rpt.csv
    └── EXP-G/
        └── cell_G1_rpt.csv
```

---

## 四、拟合工作流（SOP）

按严格顺序执行。每步有**前置条件**、**可机读的拟合命令**、**验收标准**。

### SOP-0: 环境准备

前置：
- 已按 `QUICKSTART.md` 完成安装
- conda 环境 `libquiv-aging` 已激活
- `pytest tests/` 通过

验收：
```bash
python -c "import libquiv_aging; from libquiv_aging import create_panasonic_ncr18650b; c=create_panasonic_ncr18650b(); c.init(0.5); print(c.C/3600)"
# 应输出 ~3.42
```

---

### SOP-1: 直测参数（Tier I）

**目标**：填入 `C_nominal_Ah, V_max, V_min, X0_PE, X0_NE` 等。

**数据输入**：EXP-A 数据 + datasheet

**操作**：
1. 从 EXP-A 的 CSV 计算放电总电荷，得 `C_nominal_Ah`
2. 从 datasheet 读 `V_max, V_min`
3. `X0_PE, X0_NE` 按默认约定（0.95, 0.01），除非半电池数据显示不同

**输出**：新参数工厂骨架 `libquiv_aging/{my_cell}.py`

**验收**：
```python
cell = create_my_cell()
cell.init(SOC=0.5)
assert 0.95 * C_nominal_Ah_measured < cell.C / 3600 < 1.05 * C_nominal_Ah_measured
```

---

### SOP-2: 构建 Fresh-Cell LUT（Tier II）

**目标**：生成 `.dat`（半电池 OCV）和 `.mat`（电阻）文件。

**前置**：SOP-1 完成；EXP-B1–B4 数据已收集。

#### 子步 2.1 —— 半电池 OCV → `.dat`

**输入**：`experiments/EXP-B1/halfcell_PE_coin_XX_C40.csv`（含 `Ah`, `V_vs_Li`）

**脚本**：`scripts/build_halfcell_dat.py`（SOP-5 会生成）

**验收**：
```python
from libquiv_aging.lookup_tables import HalfCellThermo, default_data_path
ht = HalfCellThermo.from_dat_file("libquiv_aging/data/MyPEAlawa.dat")
dH, dS = ht.interp_dH_dS(0.5)
V0 = -dH / 96485.0
# 应与你在 SOC=50% 附近测得的 V_vs_Li 一致（±50 mV）
```

#### 子步 2.2 —— 电阻 LUT → `.mat`

**输入**：EXP-B4 GITT 数据（稀疏 SOC × C-rate → R 矩阵）

**脚本**：`scripts/build_resistance_mat.py`（SOP-5 会生成）

**关键步骤**：
1. 用 `scipy.interpolate.RegularGridInterpolator` 把稀疏数据插值到 1001×2001 网格
2. **三个矩阵的拆分**：若无半电池 GITT，用 EIS Nyquist 图把总电阻拆成 $R_s$（高频实轴）、$R_\text{NE}^\text{dyn}$（第一半圆直径）、$R_\text{PE}^\text{dyn}$（第二半圆直径）

**验收**：
```python
from libquiv_aging.lookup_tables import ResistanceLUTs
luts = ResistanceLUTs.from_mat_file("libquiv_aging/data/MyResistances.mat")
R_NE_at_50SOC_C3 = luts.interp_RNE(c_rate=-1/3, X_ne=0.5)
# 应在 10-100 mΩ·Ah 范围
```

#### 子步 2.3 —— 派生 `R_NE_0`

**操作**：
```python
R_NE_0 = luts.interp_RNE(c_rate=-1/3, X_ne=0.5) / C_nominal_Ah
# 乘以 1/CN 因为 LUT 值是按 CN 归一化存储的
```

**代码位置**：应写进参数工厂 `create_my_cell(R_NE_0=R_NE_0, ...)`。

---

### SOP-3: 轻度拟合（Tier III）

**目标**：拟合 `LR`, `OFS`, `C1`, `C2`。

#### FIT-1: LR + OFS（电极平衡）

**前置**：SOP-2 子步 2.1 完成

**输入**：
- 全电池 OCV：`experiments/EXP-A/cell_01_fullcycle_C40.csv`
- PE / NE 半电池 OCV：已在 `.dat` 文件里

**脚本**：`scripts/fit_electrode_balance.py`（SOP-5 会生成）

**算法**：`scipy.optimize.minimize(loss, x0=[1.0, 2.0], method='Nelder-Mead')`，`loss = SSE(V_cell_model - V_cell_exp)`

**验收**：
```python
rmse_V = np.sqrt(np.mean((V_cell_model - V_cell_exp)**2))
assert rmse_V < 0.020  # 20 mV
```

**写回**：更新参数工厂中 `LR=...`, `OFS=...`。

#### FIT-2: C1, C2（RC 时间常数）

**前置**：SOP-2 完成

**输入**：EXP-C 阶跃响应 CSV

**算法**：`scipy.optimize.curve_fit` 拟合 `V(t) = V_inf + A1*exp(-t/τ1) + A2*exp(-t/τ2)`；然后 `C_i = τ_i / R_i`。

**验收**：目视观察拟合曲线与测量曲线重合；或 RMSE < 5 mV。

**如果没数据**：使用论文默认 `C1=949, C2=3576`，稳态误差 < 5%，可进入下一阶段。

#### FIT-3: 电阻分配（fractionR1toRs, fractionR2toRs）

**前置**：SOP-2 完成（需要 `R_NE_LUT`, `R_PE_LUT` 已就位）

**输入**：EXP-D 的 DST 首循环数据 `experiments/EXP-D/cell_01_dst_firstcycle.csv`（列：`time_s, V_cell, I_A`）

**脚本**：`scripts/fit_resistance_distribution.py`（SOP-5 会生成）

**算法**：
1. 粗扫：`fractionR1toRs ∈ [0.1, 0.9]` 步长 0.1，`fractionR2toRs ∈ [0.1, 0.9]` 步长 0.1（9×9 = 81 点）
2. 精扫或 Nelder-Mead：围绕粗扫最优点 ±0.1，步长 0.02，`bounds=(0.05, 0.95)`
3. 目标函数：`V_cell(t)` RMSE

**验收**：
- RMSE < 20 mV 为理想
- RMSE 在 30–50 mV 区间属于已知 RC 模型限制（paper Fig. 3d 在 ~250 s 的电压阶跃），不应继续压低
- 参见 `CRITICAL_REVIEW.md` 相关条目

**如果没数据**：使用论文默认 `0.5 / 0.5`，误差可控，可进入下一阶段。

**特别提醒**：`PARAMETERS.json::parameters::fractionR1toRs::notes` 原话——

> "Despite the 0.5 value looking like a default, it is in fact a FIT RESULT for this specific cell."

不要让读者误以为 `0.5` 是硬编码默认值；它是论文针对 Panasonic NCR18650B 的拟合结果，新体系仍须走 FIT-3。

---

### SOP-4: 老化参数拟合（Tier IV，分 3 步）

**这是最复杂的部分。必须严格按以下顺序执行**，否则参数识别会退化。

#### FIT-4a: 日历老化 → `k_SEI_cal, E_a, k_LAM_PE_cal, γ_PE, R_SEI`

**前置**：
- SOP-1, 2, 3 完成
- EXP-E 数据已整理成 `cell_Ex_rpt.csv`（含 `time_s, C_measured_Ah, R_IR_mOhm, LLI_Ah, LAM_PE_Ah`）
- **关键**：至少一个温度的数据；若有多温度则 `E_a` 可自动识别，否则 `E_a` 固定为 55500 J/mol

**脚本**：`scripts/fit_calendar.py`（见 SOP-5）

**算法**：
```python
from scipy.optimize import minimize
# 参数向量 (log 空间): [log10(k_SEI_cal), log10(k_LAM_PE_cal), gamma_PE, log10(R_SEI), E_a]
# 目标：同时匹配 Capacity(t), IR(t), LLI(t), LAM_PE(t)

def loss(params_log, exp_data):
    # 对每个 (T, SOC) 条件, 运行仿真, 计算 4 条曲线的 normalized MSE
    # 返回加权和
    ...

res = minimize(loss, x0=[np.log10(0.04), np.log10(1e-11), 3.0, np.log10(0.66), 55000],
               method='Nelder-Mead', options={'xatol': 0.01, 'fatol': 0.01, 'maxiter': 200})
```

**关键约束**：
- IR(t) 曲线必须被拟合 → `R_SEI` 才能识别
- 若实验数据只有单温度，把 `E_a` 固定为 `55500`，减少自由度

**验收**：
```
Capacity RMSE < 1.5%
IR RMSE      < 10%
LLI RMSE     < 0.02 Ah
LAM_PE RMSE  < 0.01 Ah
```

**写回**：更新 `aging.sei.k_cal`, `aging.sei.Ea`, `aging.lam_pe.k_cal`, `aging.lam_pe.gamma`, `aging.resistance_aging.R_SEI`。

#### FIT-4b: 循环老化（knee 前）→ `k_SEI_cyc, k_LAM_PE_cyc, k_LAM_NE_cyc`

**前置**：
- FIT-4a 完成，**所有电阻相关参数（含 R_SEI）冻结**
- EXP-F 数据整理好（含 `EFC, LLI_Ah, LAM_PE_Ah, LAM_NE_Ah`）

**脚本**：`scripts/fit_cycle_preknee.py`

**关键设置**：
```python
# 必须关掉 plating
cell.aging.plating.k_LP = 0.0
# 所有电阻参数 = FIT-4a 结果, 不再调
cell.aging.resistance_aging.R_SEI = R_SEI_from_4a
```

**算法**：
```python
# 参数向量: [log10(k_SEI_cyc), log10(k_LAM_PE_cyc), log10(k_LAM_NE_cyc)]
# 目标：同时匹配 LLI(EFC), LAM_PE(EFC), LAM_NE(EFC) at pre-knee region

res = minimize(
    loss_cycle_preknee,
    x0=[np.log10(0.47), np.log10(2.7e-3), np.log10(3.87e-4)],
    ...
)
```

**验收**（论文 Fig. 6 精度）：
```
LLI RMSE      < 0.03 Ah (at pre-knee)
LAM_PE RMSE   < 0.03 Ah
LAM_NE RMSE   < 0.02 Ah
Capacity RMSE < 2% at EFC=150
```

#### FIT-4c: Knee 位置 → `k_LP`

**前置**：FIT-4a, 4b 完成；EXP-G 数据（knee 已出现）

**脚本**：`scripts/fit_knee.py`

**关键设置**：所有其他参数冻结，只调 `k_LP`。

**算法**：
```python
from scipy.optimize import minimize_scalar
# 1D 搜索 log10(k_LP) 使 knee 出现时机匹配
def loss_knee(log_k_LP):
    cell.aging.plating.k_LP = 10 ** log_k_LP
    # 跑到 500+ EFC, 找 capacity 跌到 95% 的 EFC
    knee_EFC_sim = find_knee(...)
    return abs(knee_EFC_sim - knee_EFC_exp)

res = minimize_scalar(loss_knee, bracket=(-5, -2), method='brent')
k_LP_fit = 10 ** res.x
```

**验收**：
```
|knee_EFC_sim - knee_EFC_exp| < 30 EFC
```

---

### SOP-5: 辅助脚本一览

按 SOP 流程生成脚本。Claude Code 应按需创建：

| 脚本 | 位置 | 用途 | 调用 |
| --- | --- | --- | --- |
| `build_halfcell_dat.py` | `scripts/` | CSV → alawa `.dat` | `python scripts/build_halfcell_dat.py --input X.csv --output Y.dat --material PE` |
| `build_resistance_mat.py` | `scripts/` | GITT CSV → `.mat` | `python scripts/build_resistance_mat.py --input gitt.csv --CN 3.0 --output R.mat` |
| `fit_electrode_balance.py` | `scripts/` | FIT-1 | `python scripts/fit_electrode_balance.py --fullcell ocv.csv --pe-dat PE.dat --ne-dat NE.dat` |
| `fit_rc_transient.py` | `scripts/` | FIT-2 | `python scripts/fit_rc_transient.py --step step.csv` |
| `fit_resistance_distribution.py` | `scripts/` | FIT-3 | `python scripts/fit_resistance_distribution.py --dst experiments/EXP-D/cell_01_dst_firstcycle.csv` |
| `fit_calendar.py` | `scripts/` | FIT-4a | `python scripts/fit_calendar.py --rpt-dir experiments/EXP-E/` |
| `fit_cycle_preknee.py` | `scripts/` | FIT-4b | `python scripts/fit_cycle_preknee.py --rpt-dir experiments/EXP-F/` |
| `fit_knee.py` | `scripts/` | FIT-4c | `python scripts/fit_knee.py --rpt-dir experiments/EXP-G/` |

---

## 五、LFP / 石墨 体系的最小实验方案

根据 `PARAMETERS.json::minimal_viable_experiments`，三档方案：

### 方案 A：仅 fresh cell 仿真（无老化预测）
**需要**：`EXP-A, EXP-B1, EXP-B2, EXP-B4`
**时长**：~1 个月
**能做**：电压预测、电流预测、SOC 估计验证
**不能做**：任何老化预测

### 方案 B：基础老化预测（最小可行）
**需要**：方案 A + `EXP-F, EXP-G`
**时长**：~5–7 个月
**妥协**：
- 无日历数据 → `k_SEI_cal, E_a, k_LAM_PE_cal, γ_PE, R_SEI` 固定到文献值或 NCA/G 默认
- 循环拟合只能得 `k_SEI_cyc, k_LAM_NE_cyc, k_LP`（LFP 下 `k_LAM_PE_cyc` 可设 0）
- **内阻预测精度退化**（因为 R_SEI 没拟合）

### 方案 C：全方案（高置信度）
**需要**：方案 B + `EXP-B3, EXP-C, EXP-E`
**时长**：~12–15 个月
**优势**：全部参数可拟合；多温度外推可靠

---

## 六、给 Claude Code 的标准指令模板

当你（用户）需要 Claude Code 帮忙做拟合工作时，可按以下模板组织请求：

### 模板 1：查询参数信息
> "请查 `docs/PARAMETERS.json` 中 `<参数名>` 的条目，告诉我它的 tier、实验来源、代码位置和拟合步骤。"

### 模板 2：执行拟合步骤
> "按 `docs/PARAMETER_SOP.md` 的 FIT-4a 流程执行：我的数据在 `experiments/EXP-E/`，每个 CSV 是一个 cell，列名符合 SOP §3.2。请生成 `scripts/fit_calendar.py` 并运行，把结果写回 `libquiv_aging/my_lfp_cell.py`。"

### 模板 3：诊断拟合结果
> "拟合完 FIT-4b 后 LLI 的 RMSE 是 0.05 Ah，超过 SOP 的验收标准 0.03 Ah。按 `PARAMETERS.json::fit_steps::FIT-4b::parameters_frozen` 检查哪些参数被错误解冻了，并给我一份诊断报告。"

### 模板 4：新体系部署
> "我要把模型迁移到 LFP/G 体系。按 `PARAMETER_SOP.md §五` 的方案 B 准备参数工厂 `libquiv_aging/lfp_graphite.py`，所有未拟合参数用 `PARAMETERS.json::paper_value_NCA_G` 值作为 placeholder 并加 TODO 注释。"

### 模板 5：参数完整性检查
> "对 `libquiv_aging/my_cell.py` 做完整性检查：逐个对比 `PARAMETERS.json` 的每个 parameter entry，列出哪些已赋值、哪些仍是默认、哪些需要实验数据。"

---

## 七、版本管理建议

每次拟合结果更新时，建议创建一个 `parameterization_history/` 目录存档：

```
parameterization_history/
├── 2026-04-20_initial/
│   ├── PARAMETERS_snapshot.json       # 当时的参数值
│   ├── my_lfp_cell.py                  # 当时的参数工厂
│   ├── fit_report.md                   # 拟合残差汇总
│   └── figures/                        # 对比图
└── 2026-07-15_with_calendar_data/
    └── ...
```

Claude Code 可被要求："对比 `parameterization_history/2026-04-20_initial/PARAMETERS_snapshot.json` 和当前 `libquiv_aging/my_lfp_cell.py`，列出参数变化。"

---

## 八、本 SOP 的维护

本 SOP 是动态文档。每当发现：
- 论文理解有误
- 代码接口变化
- 新的拟合策略

必须**同时**更新：
1. `docs/PARAMETERS.json`（事实层）
2. 本文件（流程层）
3. 相关代码（实现层）

**禁止**：只改 MD 文档不改 JSON。这是之前文档不一致的根本原因。

---

## 九、版本纪要

| 日期 | 变更 |
| --- | --- |
| 2026-04-21 | 补上 FIT-3 小节。R5 流程下首个跨文档协调任务。 |
| 2026-04-21 | FIT-3 补上"脚本"字段（`fit_resistance_distribution.py`，SOP-5 会生成）。修正上一轮字段结构遗漏。 |
