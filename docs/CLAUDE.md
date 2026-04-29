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
| "现场脚本报错" | `docs/07_offline_runbook.md` 对应错误码 | 需外带走 `08_consultation_protocol.md` |
| "外带诊断给 Claude" | `docs/08_consultation_protocol.md §4` 模板 | — |
| "新建一个 cell type" | `docs/PARAMETER_SOP.md §二.0` | `material_specs/`, `param_specs/` 下复制模板 |
| "机制模型升级" | `libquiv_aging/model_versions/` 新增模块 | 同步新增 `schemas/params_<new_version>.schema.v*.json` |
| "离线环境安装" | `docs/09_offline_bundle_guide.md` | `scripts/install_offline.sh` |
| "拟合电极平衡 LR/OFS" | `scripts/fit_electrode_balance.py` | `docs/PARAMETER_SOP.md §三.1` |
| "拟合 RC 弛豫电容 C1/C2" | `scripts/fit_rc_transient.py` | `docs/PARAMETER_SOP.md §三.2` |
| "做 IC 分析提取退化模式" | `docs/SPEC_ic_analysis.md` | `docs/PARAMETER_SOP.md §SOP-4.5` |
| "RC 拓扑不够用 / 长弛豫拟合差" | `docs/CRITICAL_REVIEW.md` C7 | `docs/UPGRADE_LITERATURE/fractional_order_RC.md` |
| "了解 IC 分析的学术合理性 / 潜在改进 / 文献入口" | docs/CRITICAL_REVIEW.md N2/N3 | docs/UPGRADE_LITERATURE/ic_analysis_methodology_review.md |

---

## 术语约定

本节定义 libquiv-aging 工程权威文档与规则体系中反复使用的术语的
精确含义。规则引用这些术语时, 以本节定义为准。

### "入库" (in-repo)

指文件已通过 `git commit` 进入某个分支的提交历史。

- `git add` 只是 staging, 文件进入索引但未入库
- 工作树中存在但未 `git add` 的文件不入库
- 已 `git add` 但未 `git commit` 的文件不入库
- 仅当 `git log --follow <path>` 能追溯到该文件时, 视为入库

在 R1/R5/R6 的事实层一致性要求下, **未入库文件不能被视作可依赖的
前置条件**。如一个错误码的 cross_refs 指向某文件, 该文件必须入库;
如某任务声称 "X 已生成", 生成者有责任说明是否已入库。

### "事实层" (Single Source of Truth, SSoT)

指下列文档:
- `docs/PARAMETERS.json` (参数事实层)
- `docs/error_codes_registry.json` (错误码事实层)

这两份 JSON 是所有参数与错误码元信息的权威来源。修改它们必须走
R1 (参数) 或 R6 (错误码) 规定的因果顺序。

### "派生层" (derived)

指从事实层展开而成的人类可读文档, 主要是:
- `docs/PARAMETER_SOP.md`
- `docs/07_offline_runbook.md`

允许手工精修排版与叙事, 但关键结构性字段 (trigger / consequence /
cross_refs / script_behavior / 等) 必须与事实层一致。不一致时以
事实层为准。

### "工作树" vs "HEAD" vs "索引"

- **工作树** (working tree): 当前磁盘上的文件状态
- **索引** (index / staging area): `git add` 后的待 commit 状态
- **HEAD**: 当前分支最新 commit 指向的快照

判断 "某文件当前是什么状态" 时, 三者不可混淆。特别注意:
- 判断 "历史上该文件是否存在过某种错误" → 查 HEAD 或更早 commit
  (用 `git show <commit>:<path>` 或 `git log -p <path>`)
- 判断 "当前工作流是否会引入错误" → 查工作树与索引
- 不要用工作树的状态反推历史

示例 (来自 2026-04-23 事故): 当 Claude Code 报告
"现有 environment.yml 是 name=base", 该判断基于工作树。若此时仓库
HEAD 上的 environment.yml 实为规范版 (name=libquiv-aging), 则工作树
的错误状态是本次会话引入的, 不是 "预先存在的不一致"。

---

## 破坏性命令清单

下列命令在错误使用时会无声覆盖权威文档或环境描述文件, 造成数据
丢失或语义漂移。执行前必须核对目标路径, 执行后必须 `git status`
验证未意外波及其他文件。

### `conda env export`

- **破坏性**: 默认输出到 stdout。若 redirection 写错目标, 会覆盖
  任意已存在的 YAML 文件。
- **规范**: 必须先 `conda activate <目标 env>`, 且 redirection 目标
  必须是 `environment-frozen.yml` (机器导出层), **禁止写入**
  `environment.yml` (人写维护层)。
- **验证**:
  ```
  head -3 environment-frozen.yml    # 第一行应为 name: <目标 env>
  git status                         # environment.yml 不应 modified
  ```

### `git checkout <path>` / `git restore <path>`

- **破坏性**: 覆盖工作树, 丢失未 commit 的修改。
- **规范**: 执行前先 `git diff <path>` 查看要丢失什么, 确认后再 restore。

### `rm <path>` (对 tracked 文件)

- **破坏性**: 删除工作树文件。若该文件已 tracked, 需后续 `git rm`
  才能反映到 index; 若未 tracked, 则彻底丢失。
- **规范**: 对 untracked 文件执行 `rm` 前, 先 `cat <path>` 或
  `git status` 确认文件身份与内容。

(后续遇到新的破坏性命令模式, 按本格式追加条目)

---

## Claude Code 协作规范

### Claude Code 的默认授权边界

在执行涉及 git / 文件系统 / 环境的改动任务时, Claude Code 的授权
默认**不包括**:
- `git add` (staging 是人的语义选择)
- `git commit` (入库是人的最终决策)
- `git tag` (tag 是 "可进入离线区" 的准入标志, 必须人签发)
- `conda create` / `conda install` (环境构建是人控制的副作用链起点)
- 删除任何 tracked 文件 (信息损失不可逆)

任务单中若未明示授予上述权限, Claude Code 应在执行前停下并请求
人工确认。本约束优先于任务单的字面效率考量。

### 允许 (且鼓励) 的超范围行为

Claude Code 在执行改动任务时, **允许并鼓励**主动审查以下内容,
即使该审查超出任务字面范围:

- 前置条件的真实性 (声称 "已入库" 的文件是否真的 tracked)
- 被改动文件的语义正确性 (内容是否匹配其声明的用途)
- 相邻文件的一致性 (改动是否使相邻权威文档变得矛盾)
- git 历史状态 (HEAD / index / 工作树是否处于可预期的关系)

此类审查反馈应以**警告**形式呈现在任务完成报告中, Claude Code
**不应**据此自行采取纠正动作。由人决定是否接受警告并推进修复。

理由: 2026-04-23 的 P0 事故中, Claude Code 两次通过超范围审查
拦截了潜在错误 (git untracked 状态、base env 误导出)。此行为模式
从 "偶发善意" 固化为 "预期责任", 可降低事故率而不破坏授权边界。

### 与 R5 的关系

本节列出的 Claude Code 默认授权边界, 与 R5 验收阶段的 git 条款
"禁止自动 git add / commit / tag" 语义一致。R5 为规则条文 (强制力),
本节为行为指引 (机制解释)。两处表述冲突时以 R5 为准。

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
- **禁止自动 git add / commit / tag**

  `git add` 是 staging 的语义选择 ("我认可这个改动准备入 commit"),
  `git commit` 是入库的最终决策, `git tag` 是 "可进入离线区"
  的准入标志。三者都是需要人手授权的动作, Claude Code 应完成
  文件修改后停下, 把 `git diff` 或 `git status` 呈给用户,
  由用户决定是否 stage / commit / tag。

**违反本规则的典型症状**：某个概念在 A 文档说 X，在 B 文档说 Y，
在 JSON 里什么也没说。这是 2026-04 之前的状态，R5 就是为了防止回退。

### R6: 错误码登记与 runbook 一致性

修改错误码必须按：

```
改 docs/error_codes_registry.json
    →  改 docs/07_offline_runbook.md
    →  改 scripts/ 中对应 error raise
```

编号一经发放不复用，不再使用的条目标记 `status=deprecated`
（`deprecated_note` 指向替代码）。

`07_offline_runbook.md` 中 `trigger/consequence/cross_refs/script_behavior`
与 registry 不一致时，**以 registry 为准**。registry 是事实层，runbook
是解释层，这一层级关系与 R1 中 PARAMETERS.json ↔ MD 的关系同构。

外带诊断到在线 Claude 时走 `docs/08_consultation_protocol.md` §4 的观测
笔记模板；该模板与 registry 的 `escalation` 字段互锁，两者有任一修改必须
同步。

### R7: Cell Type 创建顺序

新建一个 cell type 必须按以下顺序：

```
改 material_specs/ 和 param_specs/ (事实层)
  → 必要时改 libquiv_aging/model_versions/ (新增机制版本, 仅当当前版本不适用时)
  → 运行 FIT-X 脚本自动回写 spec (不手工编辑 fit 产出字段)
  → 写对应 cell type 的测试和 examples (解释层)
```

**禁止**：
- 在 `libquiv_aging/` 下创建新的 `*_cell.py` 硬编码工厂（除非是极罕见的测试辅助用途并在 docstring 明确标记）
- 手工编辑 spec 文件中 `status=fitted` 的字段的 `value`（这些字段只能由 FIT-X 脚本回写）

R7 与 R1 在形式上类似（事实层优先），专门覆盖 cell type 创建这一高频场景。

### R8: README 与 release 同步

每次打 release/vX.Y.0 tag 之前, README.md 必须经过审查。如果本次
release 引入的改动属于以下任一类:
- 新公共 API (导出函数 / 类 / 命令行脚本)
- 新目录结构 (新顶层目录如 schemas/, material_specs/)
- 新工作流入口 (新 tag 命名约定、新 air-gapped 流程)
- 新概念 (cell type、机制版本路由、双 spec 架构等)

则 README.md 的更新必须作为 release 任务包的一个独立子阶段, 与代码 /
文档 / 错误码改动同等优先级, 不视为"事后想起来再做"的可选项。

QUICKSTART.md 同样适用本规则, 因其本质是 README.md 的精简执行版。

docs/vX.Y.Z patch 不强制更新 README, 但若该 patch 修复了 README 中
描述的功能, 则需同步。

**成员扩展**: R8 不仅适用于 README.md 和 QUICKSTART.md。下列"对外
项目对象"同属 R8 范畴, 但触发条件独立于上述四类:

- **LICENSE / NOTICE**: 触发条件为许可证变更、归属变更、版权年份切换、
  法律来源链变化 (上游许可证升级、论文或数据集许可证变更)
- **pyproject.toml `description` 字段**: 触发条件为工程定位变化 (例如
  从 "Python port" 升级为 "Python implementation with extensions") 或
  关键引用变化 (主论文 DOI / 上游归属调整)

这些成员不在每次 release 强制审查, 但相应触发条件出现时必须同步更新,
优先级与 README/QUICKSTART 相同。

R8 与 R5 (文档一致性协议) 的关系: R5 覆盖内部权威文档之间的一致性,
R8 覆盖项目对外形象与代码状态之间的一致性。两者互补不冲突。

R8 与 R1-R7 共同构成本工程的工作流契约。R1-R6 管模型与代码正确性,
R7 管 cell type 创建顺序, R8 管对外文档同步。

---

## 代码导航

```
libquiv_aging/                  核心包
├── constants.py                物理常数
├── lookup_tables.py            半电池 OCV + 电阻 LUT 插值
├── aging_kinetics.py           全部老化速率律 + 电阻退化因子
├── cell_model.py               EquivCircuitCell (DAE→ODE, solve_ivp)
├── cell_factory.py             通用双 spec 加载器 (create_cell_from_specs)
├── fitting.py                   FIT 脚本系列共享基础设施
├── relaxation_fitting.py       FIT-2 RC 弛豫内核 (RELAXATION_MODELS dispatch)
├── ic_analysis.py              IC 分析: RPT C/40 → (LLI, LAM_PE, LAM_NE) 反演 (SOP-4.5)
├── panasonic_ncr18650b.py      兼容层, 实际参数在 material_specs/ 和 param_specs/ 下
├── model_versions/             机制模型版本路由
│   ├── __init__.py             版本注册表
│   └── mmeka2025.py            当前机制的组装逻辑
└── data/                       .dat / .mat / .csv 数据文件

examples/
├── smoke_test.py               最简功能验证 (~10s 跑完)
├── figure7_simulation.py       完整复现论文 Figure 7
└── analysis_template.py        用户自定义分析的起点

scripts/
├── fit_electrode_balance.py    FIT-1: LR/OFS 拟合 (已实现)
├── build_halfcell_dat.py       EXP-B1/B2 数据 → .dat (待生成)
├── build_resistance_mat.py     EXP-B4 GITT 数据 → .mat (待生成)
├── fit_rc_transient.py         FIT-2: C1/C2 RC 弛豫拟合 (已实现, 双指数, dispatch 可扩展)
├── fit_resistance_distribution.py  FIT-3
├── fit_ic_to_dms.py            RPT C/40 → (LLI, LAM_PE, LAM_NE) 抽取 (SOP-4.5, 已实现)
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
- [ ] 改了错误码：是否按 R6 顺序改 registry → runbook → scripts，
      且未复用已发放的编号？

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
| 2026-04-23 | 新增 R6 错误码登记与 runbook 一致性。落盘 `docs/error_codes_registry.json` + `07_offline_runbook.md` + `08_consultation_protocol.md` 三件套（tag: docs/v0.2.0-offline-workflow）。**偏离记录**：本次任务单的 D.3 请求把新规则编号为 R5，但 2026-04-21 已存在 R5（文档一致性协议）；为保护已提交工作并保持编号不复用的原则，新规则改编为 R6。|
| 2026-04-23 | v0.2.2 meta 教训制度化: 新增"术语约定"、"破坏性命令清单"、"Claude Code 协作规范"三小节。R5 验收阶段的"禁止自动 commit"条款扩展为"禁止自动 git add / commit / tag", 措辞同步更新。 |
| 2026-04-24 | v0.2.3 离线工作流落地: 内部 pip 镜像单轨制, 新增 `docs/09_offline_bundle_guide.md` 与配套 scripts (`build_requirements.sh`, `install_offline.sh`, `verify_install.sh`)。 |
| 2026-04-24 | v0.2.4 清理整顿: 奥卡姆剃刀原则首次应用。08 consultation protocol 追加适用范围声明, IDENT-Wxxx 标记为 draft, 09 offline bundle guide 删减未来扩展段落。详见 MIGRATION_NOTES §十三。 |
| 2026-04-25 | v0.3.0 cell type 抽象层落地: 双 spec 架构 + 机制模型版本化。新增 `schemas/`, `material_specs/`, `param_specs/` 目录。`panasonic_ncr18650b.py` 重构为兼容层。新增 `create_cell_from_specs` 作为多 cell type 的统一入口。详见 MIGRATION_NOTES §十四。 |
| 2026-04-25 | v0.4.0 第一阶段: FIT-1 电极平衡拟合脚本落地。新增 `scripts/fit_electrode_balance.py` 和 `libquiv_aging/fitting.py` 基础设施。错误码扩展 FIT1-Exxx/W001。详见 MIGRATION_NOTES §十五。 |
| 2026-04-25 | v0.4.1 工作流升级: 新增 R8 规则把 README/QUICKSTART 同步纳入 release 流程。详见 MIGRATION_NOTES §十六。 |
| 2026-04-25 | v0.4.2 SPEC 提升: 把 docs/TODO_ic_analysis.md 升级为 docs/SPEC_ic_analysis.md, 同步引用与接口约定。详见 MIGRATION_NOTES §十七。 |
| 2026-04-26 | v0.4.3 R8 成员扩展: 落地 LICENSE 和 NOTICE 文件, 把 LICENSE/NOTICE/pyproject.toml description 正式纳入 R8 范畴, 各自触发条件独立于 README/QUICKSTART 的四类触发。同步清理 pyproject.toml authors 占位符。 |
| 2026-04-26 | v0.5.0 FIT-2 RC 弛豫拟合落地: 新增 `scripts/fit_rc_transient.py` 与 `libquiv_aging/relaxation_fitting.py` (dispatch 模式准备升级路径)。错误码扩展 FIT2-Exxx/W001。`CRITICAL_REVIEW.md` 新增 C7 (RC 拓扑对长弛豫的不足) 与 `docs/UPGRADE_LITERATURE/fractional_order_RC.md` 升级文献入口。详见 MIGRATION_NOTES §十八。 |
| 2026-04-26 | v0.5.1 派生层语义辐射修复: EXP-C deprecated for FIT-2, PARAMETERS.json 三处字段 + SPEC_ic_analysis Status + PARAMETER_SOP §3.1/§3.3 + README 目录结构图同步。详见 MIGRATION_NOTES §十九。 |
| 2026-04-28 | v0.5.2 IC analysis 落地: 兑现 frozen SPEC_ic_analysis 契约。新增 `libquiv_aging/ic_analysis.py` + `scripts/fit_ic_to_dms.py` + `tests/test_ic_analysis.py` (22 用例) + 错误码 ICA scope (E001/E002/E003/W001/W002)。三核心架构决策: Path B algebraic forward + dual brentq + bracket 增强、fit_quality 阈值文献依据 (SOP §3.2 + Birkl 2017 + Phantom LAM 2024)、IC 输出不回写 spec (per-RPT 独立 JSON 供 FIT-4 消费)。子阶段 4 T4 阻塞由 paper Fig. 6c 物理印证, T4 改写为 cap_loss self-consistency。详见 MIGRATION_NOTES §二十。 |
