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

→ 数据契约违规见 `docs/07_offline_runbook.md §2`（`DATA-Exxx` 系列）。

**每次 RPT 的标准流程**

RPT 协议对日历老化（EXP-E）和循环老化（EXP-F/G）**共用同一套步骤**，以保证两组
数据可比、可用于交叉验证。不同实验对各步骤的"必要性"不同，详见下文 §二.3。

#### §二.0 — Cell Type 创建流程

新 cell type 的参数化按以下步骤，先于各 EXP-X 实验开始前完成：

**第一步：复制示例 spec 为模板**

```bash
cp material_specs/panasonic_ncr18650b.material.json \
   material_specs/<my_cell>.material.json
cp param_specs/panasonic_ncr18650b__mmeka2025.params.json \
   param_specs/<my_cell>__mmeka2025.params.json
```

**第二步：编辑材料 spec，填入已知的本征参数**

- `C_nominal_Ah`, `V_max`, `V_min`: 从电池数据手册填入，`status=datasheet`
- `X0_PE`, `X0_NE`, `dX_PE_alawa`, `dX_NE_alawa`: 查 alawa 数据库或按 `literature_default` 填论文值
- `LR`, `OFS`: 留 `value=null`, `status=pending_fit`，待 FIT-1 产出
- `anode_thermo_dat`, `cathode_thermo_dat`: 指向对应材料的 `.dat` 文件（若无，走 EXP-B1/B2 生成）
- `mvol_*_mode`: 根据电极材料选 `standard` 或 `custom`

**第三步：编辑参数 spec，更新 material_spec_ref 并留空所有 value**

- `material_spec_ref`: 更新为 `<my_cell>.material.json` 的路径
- 大部分参数 `value=null`, `status=pending_fit`，待 FIT-4a/4b/4c 产出
- `convention` 类参数（`alpha_f`, `alpha_LP`, `V_LP_eq` 等）直接填论文值，`status=convention`

**第四步：运行 FIT-0 到 FIT-4c 各阶段脚本**

每个脚本成功后自动回写对应 spec 文件的字段，`status` 从 `pending_fit` 变为 `fitted`，附带 `fit_source`, `fit_r_squared` 等 provenance 信息。

**第五步：加载 cell 并运行测试**

```python
from libquiv_aging import create_cell_from_specs
cell = create_cell_from_specs(
    "material_specs/<my_cell>.material.json",
    "param_specs/<my_cell>__mmeka2025.params.json"
)
cell.init(0.5)
# ... 你的仿真和验证代码 ...
```

#### §二.1 — RPT 四步骤

```
(1) C/5 完整充放电   → 当前实际容量 C(t)
(2) 内阻测量         → 当前内阻 R(t)
(3) C/40 慢速充放电  → V_cell(SOC) 曲线
(4) IC 分析          → LLI(t), LAM_PE(t), LAM_NE(t)
                       （用 scripts/fit_ic_to_dms.py 自动完成，见 §SOP-4.5）
```

#### §二.2 — 内阻测量方法选择

论文 Eq. 30 用 C/3 与 C/5 放电曲线在 50% SOC 处的割线定义 IR，是作者"无 
脉冲、无 EIS 数据"情况下的权宜。本工程**推荐**按下述顺序选择方法：

1. **IR 脉冲（默认方案）**：标准化协议 —— 50% SOC、25°C、1C 脉冲 10 s 或 30 s，
   取脉冲起始瞬时电压降除以电流。工业通用，与 Dubarry 2014 实验口径接近。
2. **EIS（增强方案）**：在 BOL、mid-life、EOL 等 2–3 个关键节点加测 EIS，用作 
   诊断补充（追踪 $R_s$ 是否真不变；分辨率阻抗增长的归属）。不要求每次 RPT 都做。
3. **论文 Eq. 30 割线法**：仅在已有 C/3 + C/5 双放电数据且无脉冲/EIS 设备时使用。

关键点：$R_\text{SEI}$ 拟合只对**相对增长曲线**敏感，不对绝对 IR 值敏感。方法一致 
比方法"正确"更重要。同一工程内所有 RPT 必须用同一种 IR 方法。

#### §二.3 — 各步骤在不同实验中的必要性

| 步骤 | EXP-E（日历）| EXP-F/G（循环）|
| --- | --- | --- |
| (1) C/5 容量 | 强烈建议 | 强烈建议（knee 检测依赖）|
| (2) 内阻 | **必须**：FIT-4a 的 $R_\text{SEI}$ 依赖 | 推荐：验证 FIT-4a 结果可迁移 |
| (3) C/40 + IC | **必须**：LLI/LAM/γ_PE 依赖 | **必须**：LLI/LAM 依赖 |

循环 RPT 内阻若因成本原因省略，FIT-4b 仍可执行（不再拟合 $R_\text{SEI}$，规则 
R2），但失去对 Fig. 6b 式"日历参数预测循环 IR 增长"的独立验证能力。

#### §二.4 — RPT 温度控制（必读）

**所有 cell 的所有 RPT 必须在 25 ± 1°C 下进行**，无论储存温度或循环温度。

理由：RPT 测出的所有指标都对温度敏感。$R_\text{ct}$ 的 Arrhenius 依赖最强，
典型 $E_a \sim 50$ kJ/mol，环境温度偏 10 K 产生的 $R_\text{ct}$ 变化约 1.8 倍，
已超过一年日历老化的内阻信号幅度。且模型的电阻 LUT 和 $R_\text{SEI}$ 均不含 
温度依赖项（见 `CRITICAL_REVIEW.md` C1、S3 条和 `scope_of_validity`），必须 
通过实验侧控温来满足模型假设。

**具体要求**：

1. 储存/循环条件 ≠ RPT 条件。从存储箱或循环架取出后，先于 **25°C 环境静置 ≥ 4 
   小时**（约 5 倍 18650 自由对流热时间常数）再开始 RPT。条件允许时，把 cell 
   在 25°C 恒温炉过夜。
2. RPT 期间 cell 表面贴**热电偶**记录实际温度。C/5 自发热典型 2–5°C 表面温升、
   5–10°C 芯体温升，必须有记录以便事后审查/修正。
3. RPT 完成后**尽快放回**原储存/循环条件，避免污染时间簿记。
4. RPT 之间**不切换 channel/cycler/夹具**（见 §二.5）。

**不接受的替代方案**：
- 在 $T_\text{storage}$ 下做 RPT 并对 IR 做 Arrhenius 后修正。虽然 IR 可修正， 
  但 C/40 + IC 分析对温度的敏感性是**非线性形状扭曲**（Graphite 阶梯峰的位移 
  和高度随 T 变化不均匀），单纯乘法修正无法消除，会把温度污染传递到 FIT-4a/b 
  拟合参数中，不可接受。此议题在 2026-04-22 讨论中已评估并否决。

#### §二.5 — RPT 质量控制（设备 hygiene）

老化实验周期 6–15 月，期间设备漂移与老化信号同量级（~5%）。以下规则强制执行：

1. **固定工站**：每颗 cell 的所有 RPT 走**同一台 cycler、同一个 channel**。不允许 
   cell_E1 本次走 channel 3、下次走 channel 7。并行化需要多 channel 时，固定 
   每颗 cell 的 channel 归属并记录在 `experiments/.../metadata.csv` 中。
2. **固定夹具**：18650 保持器、弹簧针、四线制连接方式全部锁定。接触电阻变动 
   1 mΩ 即相当于 ~2–3% IR 误差（18650 IR 典型 30–50 mΩ）。
3. **BOL/EOL 参考 cell 标定**：实验开始和结束时，各用**一颗全新参考 cell**
   （从未参与老化，单独在 25°C、50% SOC 标定箱存放）跑一遍所有 channel。标定 
   偏差进入后处理线性校正。
4. **哨兵 cell**：老化 cell 组内指定**一颗最温和条件的 cell**（例如 25°C、50% 
   SOC 日历组）作为"老化之外漂移"的基线。其 $C(t)$ 和 $R(t)$ 轨迹异常跳变即 
   指示设备问题而非电池老化。
5. **记录元数据**：`experiments/.../metadata.csv` 每颗 cell 至少记录：
   `cell_id, channel_id, fixture_id, T_storage_K, SOC_storage, start_date, notes`。

---

## 三、数据存储格式规范

### 3.1 Fresh cell 表征数据

| 数据类型 | 格式 | 存放位置 | 标准列/字段 |
| --- | --- | --- | --- |
| 半电池 OCV | `.dat` (alawa 格式) | `libquiv_aging/data/{material}Alawa.dat` | 3 列：`x`, `dH [J/mol]`, `dS [J/mol/K]`；`*` 开头为注释 |
| 电阻 LUT | `.mat` | `libquiv_aging/data/{name}Resistances.mat` | 3 个 (1001×2001) 矩阵：`RsAlawa`, `RNEAlawa`, `RPEAlawa` |
| 全电池 OCV | `.csv` | `experiments/EXP-A/{cell_id}_ocv.csv` | 列：`time_s, V_cell, I_A, Q_Ah, SOC` |
| ~~阶跃响应 (deprecated v0.5.0)~~ | `.csv` | `experiments/EXP-C/{cell_id}_step.csv` | 列：`time_s, V_cell, I_A`。**已被 EXP-B4 GITT 弛豫替代用于 FIT-2,见 PARAMETERS.json::experiments::EXP-C deprecated 字段**。 |
| GITT 弛豫 (FIT-2) | `.csv` | `experiments/EXP-B4/{cell_id}_relaxation.csv` | 列：`time_s [s], voltage_V [V], current_pre_step_A [A], soc_at_step [0..1], t_step_s [s]` (后三列每行同值, 表示单脉冲) |

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
| `ic_analysis_fit_quality` | - | IC 分析 rmse_V，质量指标（<15 mV 为可接受）|
| `ic_analysis_timestamp` | ISO8601 | 该次 RPT 的 IC 分析运行时间 |

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
    ├── EXP-B4/
    │   └── cell_01_relaxation.csv     # GITT 弛豫,FIT-2 输入 (v0.5.0+)
    ├── EXP-C/                         # deprecated for FIT-2 since v0.5.0
    │   └── cell_01_step_50SOC.csv     # 历史协议,见 PARAMETERS.json EXP-C deprecated 字段
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

1. **三张 LUT 的分工**（重要，勿混淆）：
   - `RsAlawa`（$R_s$）：**来自 EXP-B3**（全电池 EIS 高频实轴截距）。
     半电池 GITT 无法产出 $R_s$，因为 $R_s$ 是全电池性质（电解液体相 + 集流体 + 
     引线 + 接触阻抗），半电池结构完全不同。
   - `RNEAlawa`（$R_\text{NE}^0(I, X_\text{NE})$）：来自 EXP-B4 **负极**半电池 GITT。
   - `RPEAlawa`（$R_\text{PE}^0(I, X_\text{PE})$）：来自 EXP-B4 **正极**半电池 GITT。

2. 用 `scipy.interpolate.RegularGridInterpolator` 把稀疏 GITT 数据插值到 1001×2001 
   网格。

3. **退路：无半电池 GITT 时的拆分**。如果只能做全电池 GITT，可用 EIS Nyquist 图 
   辅助拆分总电阻：$R_s$ 取高频实轴截距，$R_\text{NE}^\text{dyn}$ 取第一半圆直径
   （典型归属，取决于体系），$R_\text{PE}^\text{dyn}$ 取第二半圆直径。此路线精度低，
   仅在成本受限时使用。

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

→ 失败时参见 `docs/07_offline_runbook.md §10`（`IDENT-W002` 系列）。

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

**Spec 回写**：FIT-1 成功后，回写 `material_specs/<cell>.material.json` 中的 `LR` 和 `OFS` 字段：`value` 填拟合值，`status` 从 `pending_fit` 改为 `fitted`，填入 `fit_step="FIT-1"`, `fit_source`, `fit_script_version`, `fit_r_squared`。

**实际脚本**: `scripts/fit_electrode_balance.py`

**CLI 用法**:
```
python scripts/fit_electrode_balance.py \
    --material-spec material_specs/<cell>.material.json \
    --exp-a-csv experiments/EXP-A/cell_<id>_fullcycle_C40.csv
```

**可选参数**:
- `--preflight-only`: 仅做前置检查不拟合 (此模式下 `--exp-a-csv` 可省略)
- `--dry-run`: 用合成数据反演, 验证脚本逻辑
- `--require-pending`: 严格模式, 仅当 LR/OFS 为 pending_fit 时执行
- `--temperature`: OCV 合成参考温度, 默认 298.15K
- `--maxiter`: scipy 最大迭代次数, 默认 500

成功后, LR 和 OFS 自动写回材料 spec, status 变为 fitted, 含完整
provenance (fit_source, fit_r_squared, uncertainty 等)。运行产物保存在
`runs/{YYYYmmdd_HHMMSS}_fit1_{cell_type}/` 目录, 含 `fit_config.json`,
`fit_report.md`, `fit_diagnostic.json` 三份文件。

**错误码** (见 `docs/07_offline_runbook.md §3 FIT1`):
- FIT1-E001: 材料 spec dX/X0 字段未填
- FIT1-E002: RMSE > 50 mV 失败档
- FIT1-E003: 优化器未收敛
- FIT1-W001: RMSE 在 20-50 mV marginal 区间 (warn 级别, spec 仍写回)

**关于 OFS 的可识别性**：LR 和 OFS 在 V_cell(SOC) 数据上有强共线性，OFS 的独立识别依赖 EXP-A 数据在 stage transition 等局部特征处的覆盖。若拟合后 OFS uncertainty 量级与 OFS 值本身相当（如 σ_OFS / OFS > 10%），建议把 OFS 固定到 datasheet 或 alawa 默认值，只拟合 LR。详见 docs/CRITICAL_REVIEW.md N1。

#### FIT-2: C1, C2（RC 时间常数）

**前置**：FIT-1 完成 (LR/OFS 已 fitted, 用于 SOC↔X_NE/X_PE 化学计量映射), 且
`param_specs/<cell>__mmeka2025.params.json::resistance_mat` 指向有效 .mat 文件。

→ 失败时参见 `docs/07_offline_runbook.md §4 FIT2`。

**输入**：EXP-B4 GITT 弛豫 CSV (列契约见 §三.2 数据契约表):
- `time_s` 绝对时间秒
- `voltage_V` 电池端电压 V
- `current_pre_step_A` 脉冲终止前的恒定电流 A (整列必须相同)
- `soc_at_step` 脉冲发生时的 SOC ∈ [0,1] (整列必须相同)
- `t_step_s` 脉冲终止时刻的绝对时间 s (整列必须相同)

数据要求: 弛豫窗口至少应覆盖到 V(t) 接近 V_inf 的段, 经验上 ≥ 5·tau2 (tau2
约 30-100 s)。窗口截断过早会触发 FIT2-W001 / FIT2-E003。

**脚本**：`scripts/fit_rc_transient.py`

**CLI 用法**:
```
python scripts/fit_rc_transient.py \
  --material-spec material_specs/<cell>.material.json \
  --params-spec param_specs/<cell>__mmeka2025.params.json \
  --exp-b4-csv experiments/EXP-B4/<cell>_relaxation.csv \
  [--relaxation-model two_exponential] \
  [--temperature 298.15] \
  [--require-pending] [--preflight-only] [--dry-run]
```

**算法**：
1. `scipy.optimize.curve_fit` 拟合两指数 `V(t) = V_inf + A1*exp(-t/tau1) + A2*exp(-t/tau2)`,
   tau1<tau2 在拟合后强制排序
2. 用 `param_specs/...::resistance_mat` 提供的 LUT 在 `(C_rate=I_pre/C_nominal, X_NE)` 与
   `(C_rate, X_PE)` 处插值, 得到 `R_NE`, `R_PE` (T_ref 仅写入 fit_report 元数据)
3. tau-to-R 双候选映射:
   - 候选 A: tau1↔R_NE, tau2↔R_PE → C1 = tau1/R_NE, C2 = tau2/R_PE
   - 候选 B: tau2↔R_NE, tau1↔R_PE → C1 = tau2/R_NE, C2 = tau1/R_PE
   - 选择标准: 幅值 RSS = (A_NE - (-I_pre·R_NE))^2 + (A_PE - (-I_pre·R_PE))^2 较小者
4. 若两候选 RSS 差异 <10%, 触发 FIT2-W001 (映射边缘), 仍写回选定候选, 但 fit_report
   持久化双候选 C1/C2 与各自 RSS

**验收**：
- 通过: RMSE ≤ 1 mV 且 R² ≥ 0.95
- marginal (FIT2-W001, exit 93): 1 mV < RMSE ≤ 5 mV, 仍写回, 但 fit_r_squared 反映
- fail (FIT2-E003, exit 92): RMSE > 5 mV 或 R² < 0.95, 拒绝写回, 残差呈系统性时
  指向 docs/CRITICAL_REVIEW.md C7 升级路径 (docs/UPGRADE_LITERATURE/fractional_order_RC.md)

**升级接口预留**：`--relaxation-model` 当前只接受 `two_exponential`。未来引入分数阶 RC
/ Mittag-Leffler / DRT 时, 在 `libquiv_aging/relaxation_fitting.py::RELAXATION_MODELS`
追加新的拟合函数即可, CLI 与脚本接口保持兼容。详见 §C7 与升级文献。

**如果没数据**：保留 spec 中 `manually_set` 状态的 paper 默认 (NCR18650B: C1≈949,
C2≈3576), 标记 status 不变, 不假装走过 FIT-2。

**Spec 回写**：FIT-2 成功后, 回写 `param_specs/<cell>__mmeka2025.params.json` 中的
`C1`, `C2` 字段: `status` 改为 `fitted`, 附 `fit_step="FIT-2"` 及完整 provenance,
并附 `relaxation_metadata` 子对象 (含 model, T_ref_K, soc_at_step, I_pre_A, C_rate,
X_NE, X_PE, R_NE_LUT, R_PE_LUT, tau1_s, tau2_s, A1_V, A2_V, V_inf_V, mapping,
alternate_*, amplitude_rss_*, mapping_marginal)。运行产物保存在
`runs/{YYYYmmdd_HHMMSS}_fit2_{cell_type}/` 目录, 含 `fit_config.json`,
`fit_report.md`, `fit_diagnostic.json`。

**错误码** (见 `docs/07_offline_runbook.md §4 FIT2`):
- FIT2-E001 (exit 90): 弛豫 CSV 列名/单位/单脉冲一致性违规
- FIT2-E002 (exit 91): curve_fit 未收敛或协方差非有限
- FIT2-E003 (exit 92): RMSE 或 R² 越过失败阈值, 残差系统性时指向 C7 升级
- FIT2-W001 (exit 93): RMSE 在 marginal 区间或 tau-to-R 映射两候选 RSS 差异 <10%

#### FIT-3: 电阻分配（fractionR1toRs, fractionR2toRs）

**前置**：SOP-2 完成（需要 `R_NE_LUT`, `R_PE_LUT` 已就位）

→ 失败时参见 `docs/07_offline_runbook.md §10`（`IDENT-W002` 系列；bound 命中常见于 FIT-3 搜索区间）。

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

**Spec 回写**：FIT-3 成功后，回写 `param_specs/<cell>__mmeka2025.params.json` 中的 `fractionR1toRs`, `fractionR2toRs` 字段：`status` 改为 `fitted`，附 `fit_step="FIT-3"` 及 provenance 信息。

**命名提醒**：参数名 `fractionR1toRs` / `fractionR2toRs` 中的 "toRs" 是 MATLAB 原版的历史遗迹，**不表示与 $R_s$ 的语义关系**。这两个参数控制的是电极电阻（R_NE / R_PE）内部的 static/dynamic 劈分，与串联电阻 $R_s$ 独立。详见 `06_parameter_sourcing.md §3.3`。

---

### SOP-4: 老化参数拟合（Tier IV，分 3 步）

**这是最复杂的部分。必须严格按以下顺序执行**，否则参数识别会退化。

#### FIT-4a: 日历老化 → `k_SEI_cal, E_a, k_LAM_PE_cal, γ_PE, R_SEI`

**前置**：
- SOP-1, 2, 3 完成
- EXP-E 数据已整理成 `cell_Ex_rpt.csv`（含 `time_s, C_measured_Ah, R_IR_mOhm, LLI_Ah, LAM_PE_Ah`）
- **关键**：至少一个温度的数据；若有多温度则 `E_a` 可自动识别，否则 `E_a` 固定为 55500 J/mol

→ 失败时参见 `docs/07_offline_runbook.md §6`（`FIT4A-Exxx` 系列）。

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

**Spec 回写**：FIT-4a 成功后，回写 `param_specs/<cell>__mmeka2025.params.json` 中的 `k_SEI_cal`, `E_a_SEI`, `k_LAM_PE_cal`, `gamma_PE`, `R_SEI` 字段：`status` 改为 `fitted`，附 `fit_step="FIT-4a"`, `fit_source`, `fit_script_version`, `fit_r_squared` 等 provenance 信息。

#### FIT-4b: 循环老化（knee 前）→ `k_SEI_cyc, k_LAM_PE_cyc, k_LAM_NE_cyc`

**前置**：
- FIT-4a 完成，**所有电阻相关参数（含 R_SEI）冻结**
- EXP-F 数据整理好（含 `EFC, LLI_Ah, LAM_PE_Ah, LAM_NE_Ah`）

→ 失败时参见 `docs/07_offline_runbook.md §7`（`FIT4B-Exxx` 系列）。

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

**Spec 回写**：FIT-4b 成功后，回写 `param_specs/<cell>__mmeka2025.params.json` 中的 `k_SEI_cyc`, `k_LAM_PE_cyc`, `k_LAM_NE_cyc` 字段：`status` 改为 `fitted`，附 `fit_step="FIT-4b"` 及 provenance 信息。

#### FIT-4c: Knee 位置 → `k_LP`

**前置**：FIT-4a, 4b 完成；EXP-G 数据（knee 已出现）

→ 失败时参见 `docs/07_offline_runbook.md §8`（`FIT4C-Exxx` 系列）。

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

**Spec 回写**：FIT-4c 成功后，回写 `param_specs/<cell>__mmeka2025.params.json` 中的 `k_LP` 字段：`status` 改为 `fitted`，附 `fit_step="FIT-4c"` 及 provenance 信息。

---

### SOP-4.5: IC 分析提取 DMs（FIT-4a/b 的前置数据处理）

**目标**：把每次 RPT 的 C/40 V(Q) 曲线转换为 (LLI, LAM_PE, LAM_NE) 三元组，
供 FIT-4a 和 FIT-4b 使用。

**前置**：
- SOP-2 子步 2.1 完成（半电池 OCV `.dat` 文件已生成）
- 目标 cell 的参数工厂可用（例如 `create_panasonic_ncr18650b`）
- RPT 的 C/40 数据已存为 CSV，列含 `Q_Ah` 和 `V_cell_V`

**脚本**：`scripts/fit_ic_to_dms.py`（实现见 `docs/SPEC_ic_analysis.md`）

**调用**：

```bash
for cell in experiments/EXP-E/cell_*; do
  for rpt_csv in ${cell}/RPT*_C40.csv; do
    python scripts/fit_ic_to_dms.py \
      --aged-data ${rpt_csv} \
      --cell-type panasonic_ncr18650b \
      --output ${rpt_csv%.csv}_dms.json
  done
done
```

**产物**：每次 RPT 得到一个 `*_dms.json`，含 (LLI_Ah, LAM_PE_Ah, LAM_NE_Ah) 
+ 1σ 误差棒 + 拟合质量指标。这些 JSON 聚合后填入 `cell_XX_rpt.csv` 的 
`LLI_Ah, LAM_PE_Ah, LAM_NE_Ah` 列，供 FIT-4a/b 读取。

**方法论依据**：Dubarry & Anseán 2022, Front. Energy Res. 10:1023555。算法 
细节、验收标准、out-of-scope 项见 `docs/SPEC_ic_analysis.md`。

**验收**：
- `pytest tests/test_ic_analysis.py` 全部通过
- 在 fresh cell 的 C/40 数据（EXP-A）上运行，recovered DMs 均 < 0.01 Ah
- 输出 JSON 的 `fit_quality.converged` 为 true

---

### SOP-5: 辅助脚本一览

按 SOP 流程生成脚本。Claude Code 应按需创建：

| 脚本 | 位置 | 用途 | 调用 |
| --- | --- | --- | --- |
| `build_halfcell_dat.py` | `scripts/` | CSV → alawa `.dat` | `python scripts/build_halfcell_dat.py --input X.csv --output Y.dat --material PE` |
| `build_resistance_mat.py` | `scripts/` | GITT CSV → `.mat` | `python scripts/build_resistance_mat.py --input gitt.csv --CN 3.0 --output R.mat` |
| `fit_electrode_balance.py` | `scripts/` | FIT-1 | `python scripts/fit_electrode_balance.py --fullcell ocv.csv --pe-dat PE.dat --ne-dat NE.dat` |
| `fit_rc_transient.py` | `scripts/` | FIT-2 (C1, C2 RC 弛豫) | `python scripts/fit_rc_transient.py --material-spec material_specs/<cell>.material.json --params-spec param_specs/<cell>__mmeka2025.params.json --exp-b4-csv experiments/EXP-B4/<cell>_relaxation.csv` |
| `fit_resistance_distribution.py` | `scripts/` | FIT-3 | `python scripts/fit_resistance_distribution.py --dst experiments/EXP-D/cell_01_dst_firstcycle.csv` |
| `fit_ic_to_dms.py` | `scripts/` | RPT C/40 → (LLI, LAM_PE, LAM_NE) | `python scripts/fit_ic_to_dms.py --aged-data ... --cell-type panasonic_ncr18650b --output ...` |
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
**准备**：按 §二.0 步骤先创建 spec 文件，再按各 EXP-X 采集数据并跑 FIT-X 脚本。

### 方案 B：基础老化预测（最小可行）
**需要**：方案 A + `EXP-F, EXP-G`
**时长**：~5–7 个月
**妥协**：
- 无日历数据 → `k_SEI_cal, E_a, k_LAM_PE_cal, γ_PE, R_SEI` 固定到文献值或 NCA/G 默认
- 循环拟合只能得 `k_SEI_cyc, k_LAM_NE_cyc, k_LP`（LFP 下 `k_LAM_PE_cyc` 可设 0）
- **内阻预测精度退化**（因为 R_SEI 没拟合）
**准备**：按 §二.0 步骤先创建 spec 文件，再按各 EXP-X 采集数据并跑 FIT-X 脚本。

### 方案 C：全方案（高置信度）
**需要**：方案 B + `EXP-B3, EXP-E`
**时长**：~12–15 个月
**优势**：全部参数可拟合；多温度外推可靠
**准备**：按 §二.0 步骤先创建 spec 文件，再按各 EXP-X 采集数据并跑 FIT-X 脚本。

> EXP-C 与 EXP-D 不属于上述任何方案，按需补充：EXP-C 在无 GITT 设备时回退使用（自 v0.5.0 起 FIT-2 的主输入已切换为 EXP-B4 GITT 弛豫）；EXP-D 在动态响应精度要求高时补做（FIT-3 的 fractionR1toRs / fractionR2toRs 输入）。

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
| 2026-04-22 | fractionR*toRs 命名陷阱澄清（方案 β）。§3.3 补两层分配的区分与物理依据；§2.2.3 加反向指引；PARAMETERS.json notes + cell_model.py docstring 同步警示。不改字段名，保留 MATLAB 对照链。 |
| 2026-04-29 | §五 方案 C 修订：去掉 EXP-C，与 PARAMETERS.json::minimal_viable_experiments::aging_prediction_robust 同步。修订动机：外部版 EXPERIMENT SOP v1.2 发布前一致性检查中发现内部 JSON 与 MD 矛盾，以 JSON 真源裁定。EXP-C 自 v0.5.0 已 deprecated for FIT-2，留作 GITT 不可行时的回退选项。 |
