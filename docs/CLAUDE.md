# Claude Code 工作手册

本文件是给 AI 代理（特别是 Claude Code）的入口说明。如果你是人类读者，请先读 `README.md` 和 `QUICKSTART.md`。

---

## 工程单一事实来源 (SSoT)

工程中有**三个权威文档不应被其他来源覆盖**：

1. **`docs/PARAMETERS.json`** — 所有参数的元数据、来源、代码位置、拟合步骤，含 `paper_errata` 字段和 `critical_review_findings` 区。**事实层**。
2. **`docs/PARAMETER_SOP.md`** — 参数获取的标准作业流程（SOP）。**流程层**。
3. **`docs/CRITICAL_REVIEW.md`** — 批判性审查结果：论文错误、已知局限、作用域限制、升级路径。**诊断层**。

当任何 MD 文档、代码注释、或用户问题与这三个文档冲突时，**以这三个为准**。

---

## 任务路由表

用户若提出以下类型的问题，请按指向执行：

| 用户问题模式 | 首先查阅 | 然后可能需要 |
| --- | --- | --- |
| "参数 X 怎么来的" | `docs/PARAMETERS.json` 的对应 entry | 代码的 `code_location` 字段指向 |
| "参数 X 的数值为什么与论文不一样" | `docs/PARAMETERS.json` 里该参数的 `paper_errata` | `docs/CRITICAL_REVIEW.md § E/S 小节` |
| "模型能用于场景 Y 吗 (快充/低温/大容量)" | `docs/CRITICAL_REVIEW.md § 三作用域卡片` | 相关 C/S 小节的升级路径 |
| "某个老化实验需要做什么" | `docs/PARAMETERS.json::experiments` | `docs/PARAMETER_SOP.md` 对应 EXP-* 小节 |
| "怎么拟合 Y 参数" | `docs/PARAMETERS.json::fit_steps::FIT-*` | `docs/PARAMETER_SOP.md §四` 的对应 SOP |
| "模型公式 Z 是什么" | `docs/02_model_overview.md §8` 公式-代码对照表 | 论文 PDF |
| "怎么换到新电池体系" | `docs/PARAMETER_SOP.md §五` 最小实验方案 | `docs/06_parameter_sourcing.md §5` + `CRITICAL_REVIEW.md` 升级路径 |
| "模型输入/输出的含义" | `docs/03_inputs_guide.md` / `docs/04_outputs_guide.md` | — |
| "搭环境 / 安装问题" | `QUICKSTART.md` | `docs/01_setup_guide.md` |
| "运行 / 调试问题" | `examples/smoke_test.py` 先跑 | 再看 `tests/test_basic.py` |

---

## 核心规则（不可违反）

### R1: 修改参数信息时的顺序

```
改 PARAMETERS.json  →  改代码  →  改相关 MD
```

**不能**只改某个 MD 文档里的描述而不更新 JSON。JSON 是事实层，MD 是解释层。

### R2: 拟合工作流的严格顺序

老化参数拟合 **必须** 按以下顺序：

```
FIT-4a (日历, 含 R_SEI)  →  FIT-4b (循环 knee 前, 关 plating)  →  FIT-4c (knee, 只调 k_LP)
```

**绝对禁止**：
- 在 FIT-4b 中解冻 `R_SEI`（论文明确 R_SEI 从日历数据识别）
- 在 FIT-4b 中保留 plating 激活（会污染 k_SEI_cyc 估计）
- 在 FIT-4c 中解冻 FIT-4a 或 FIT-4b 的任何参数

### R3: 电阻 LUT 的语义

三张电阻 LUT（`R_s_LUT`, `R_NE_LUT`, `R_PE_LUT`）**只代表 fresh-cell 数据**，老化期间不重测。老化影响通过：

```
R_i(t) = R_i^0 · f_{R,i}(t)      # 论文式 (43)
```

其中 $f_{R,i}$ 由模型内部的退化状态变量（$Q_\text{LAM,*}, Q_\text{SEI,NE}, Q_\text{PLA,NE}$）**自动推导**，见 `aging_kinetics.py::f_R_NE, f_R_PE`。

唯一需从老化实验拟合的电阻相关参数是 `R_SEI`（在 FIT-4a 中）。

### R4: 关于 `R_NE_0`

`R_NE_0` 是一个**从 R_NE_LUT 派生的标量**（在 50% SOC, C/3 处取值），而不是独立自由参数。
每次替换 `R_NE_LUT` 时必须重新计算 `R_NE_0`（当前代码未自动化此步，是已知 TODO）。

### R5: 文档一致性协议

对 `PARAMETERS.json` 或任何 `docs/*.md` 的**结构性修改**（新增/删除
章节、参数、FIT 步骤、EXP 实验），执行以下流程：

**1. 扫描阶段（编辑前）**

在 `docs/` 目录对下列关键词执行 grep，列出命中文件与行号：

- 参数名变更 → grep 该参数名（含 snake_case 和 LaTeX 形式）
- FIT-* 变更 → grep "FIT-N" 及其所有输入 EXP-* 编号
- EXP-* 变更 → grep "EXP-N" 及其所有产出参数名

**2. 确认阶段**

把扫描结果呈给用户，列出：
- 需要同步修改的文件（含建议改动）
- 仅被提及无需改动的文件
- **等待用户确认范围后，再进入编辑**

**3. 编辑阶段**

先改 `PARAMETERS.json`（事实层），再改 MD（解释层），最后改代码
（实现层）。顺序见 R1。

**4. 验收阶段**

- 对同一批关键词再次 grep，确认新内容无矛盾
- `pytest tests/ -v` 全绿
- `git diff --stat` 呈给用户
- **禁止自动 commit**

**违反本规则的典型症状**：某个概念在 A 文档说 X，在 B 文档说 Y，
在 JSON 里什么也没说。这是 2026-04 之前的状态，R5 就是为了防止回退。

---

## 代码导航

```
libquiv_aging/                  核心包
├── constants.py                物理常数
├── lookup_tables.py            半电池 OCV + 电阻 LUT 插值
├── aging_kinetics.py           全部老化速率律 + 电阻退化因子
├── cell_model.py               EquivCircuitCell (DAE→ODE, solve_ivp)
├── panasonic_ncr18650b.py      NCA/G 参数工厂 (论文默认值)
├── lfp_graphite.py (TODO)      LFP/G 参数工厂模板
└── data/                       .dat / .mat / .csv 数据文件

examples/
├── smoke_test.py               最简功能验证 (~10s 跑完)
├── figure7_simulation.py       完整复现论文 Figure 7
└── analysis_template.py        用户自定义分析的起点

scripts/ (SOP-5 规范, 待生成)
├── build_halfcell_dat.py       EXP-B1/B2 数据 → .dat
├── build_resistance_mat.py     EXP-B4 GITT 数据 → .mat
├── fit_electrode_balance.py    FIT-1 (LR, OFS)
├── fit_rc_transient.py         FIT-2 (C1, C2)
├── fit_resistance_distribution.py  FIT-3
├── fit_ic_to_dms.py            RPT C/40 → (LLI, LAM_PE, LAM_NE) 抽取 (SOP-4.5)
├── fit_calendar.py             FIT-4a (含 R_SEI!)
├── fit_cycle_preknee.py        FIT-4b
└── fit_knee.py                 FIT-4c (只调 k_LP)

tests/
└── test_basic.py               15 个回归测试

docs/                           文档 (读 README.md 找入口)
```

---

## 常见错误自查（给 AI 代理）

执行任务前，**自我检查**：

- [ ] 涉及参数的问题：是否查了 `PARAMETERS.json` 对应 entry？
- [ ] 涉及拟合的任务：是否按 FIT-4a → 4b → 4c 顺序？
- [ ] 修改了参数：是否同时更新了 `PARAMETERS.json`、代码、相关 MD？
- [ ] 计算内阻演化：是否明白老化因子 $f_{R,i}$ 自动应用，不需要手动叠加？
- [ ] 给用户建议做 GITT：是否说明只测 fresh cell，不重复？
- [ ] 修改了 PARAMETERS.json 结构或 MD 章节：是否按 R5 做了
      扫描-确认-编辑-验收四步？

执行任务后，**运行检查**：

```bash
pytest tests/ -v                 # 必须全通过
python examples/smoke_test.py    # 必须全通过
```

如有回归，立即 `git diff` 定位原因。

---

## 建议的 user-Claude 对话起点

给人类用户的建议（读给他们听/copy-paste 给他们）：

### 首次进入工程
> "Claude, 按 `docs/CLAUDE.md` 的路由表读完 `PARAMETERS.json` 和 `PARAMETER_SOP.md`, 然后用 5 句话总结这个工程的核心工作流，并告诉我你目前知道什么、不知道什么。"

### 做一个具体的拟合任务
> "Claude, 我有 EXP-E 数据在 `experiments/EXP-E/`, 格式符合 `PARAMETER_SOP.md §3.2` 的 RPT CSV 规范。按 `PARAMETERS.json::fit_steps::FIT-4a` 的流程生成 `scripts/fit_calendar.py` 并运行, 把结果写到 `libquiv_aging/my_lfp_cell.py` 里。"

### 验证工作一致性
> "Claude, 对照 `PARAMETERS.json`, 扫描 `libquiv_aging/my_lfp_cell.py` 中所有参数值, 列出: 1) 与 paper_value_NCA_G 一致的; 2) 已替换为我的实验值的; 3) 仍为 placeholder 的 TODO。"

---

## 版本纪要

| 日期 | 变更 |
| --- | --- |
| 2026-04-20 | 初版。建立 PARAMETERS.json 作为 SSoT。修正 R_SEI 在 FIT-4a 而非 FIT-4b 的历史错误。 |
| 2026-04-21 | 新增 R5 文档一致性协议。起因：FIT-3 小节缺失事件暴露了跨文档协调机制的空白。 |
