# 工程交接纪要 (Migration Notes)

本文件汇总 libquiv-aging Python 移植工程从 2026 年 4 月建立至今的全部关键决策、权威结论和工作流约定。目的是让一个全新的对话（无论是新账号、新 Project，还是隔了很长时间回到工程）能够在五分钟内达到等同的上下文深度。

读完本文件之后，配合 `docs/PARAMETERS.json`、`docs/PARAMETER_SOP.md`、`docs/CRITICAL_REVIEW.md` 和 `docs/CLAUDE.md` 四份权威文档，即可完整接手后续工作。

---

## 一、工程的起点与目标

本工程是将 Mmeka、Dubarry、Bessler 于 2025 年在 Journal of The Electrochemical Society 第 172 卷第 080538 号发表的《Physics-Informed Aging-Sensitive Equivalent Circuit Model for Predicting the Knee in Lithium-Ion Batteries》完整移植到 Python 的实现。原论文提供了配套的 MATLAB 源代码，发布在 Zenodo 存档编号 10.5281/zenodo.15833031，许可为 CC BY-NC 4.0。

该模型的核心价值在于将一个普通的等效电路模型（ECM）与物理信息化的老化子模型耦合，使同一套代码既能做短时仿真（给电流算电压），又能跟踪五个独立的退化机理在电池全生命周期中的演化，并能预测容量衰减曲线上的拐点（knee）。工程的最终目的是让使用者能够在真实电池数据的基础上，对模型做参数化、扩展到新的化学体系、并接入 BMS 算法做闭环研究。

本工程的目标用户工作环境是 macOS 配合 VS Code 与 Claude Code。工程采用 conda 管理依赖，环境定义在 `environment.yml` 中，环境名为 `libquiv-aging`，Python 版本固定为 3.11。

---

## 二、工程的核心架构决策

### 代码层

MATLAB 源码的单文件 `LIBquivAging.m` 被重构为五个单一职责的 Python 模块：`constants.py` 承载物理常数；`lookup_tables.py` 负责半电池 OCV 与电阻查找表的加载和插值；`aging_kinetics.py` 实现五个老化速率律和电阻退化因子；`cell_model.py` 是 `EquivCircuitCell` 主类，实现 DAE 到 ODE 的转换和 scipy 积分；`panasonic_ncr18650b.py` 是面向 NCR18650B 电池的参数工厂。

MATLAB 原版使用 `ode23t` 求解 18 维 DAE。Python 移植中改用 `scipy.integrate.solve_ivp` 的 BDF 方法，并通过在每次 ODE 右端求解代数方程（求 I、V、SOC 等），把系统降为 12 维显式 ODE。对代数约束的求解采用 Newton warm-start 加 brentq 兜底策略。查找表插值针对性能关键路径做了标量化优化（`_interp_scalar`），使一次完整 DST 放电的墙钟时间降至约 30 秒，略快于原 MATLAB 实现。

### 文档层

工程采用三层文档体系。事实层由 `docs/PARAMETERS.json` 独占，包含所有参数的来源、代码位置、拟合步骤、paper errata 字段以及批判性审查结果索引；流程层由 `docs/PARAMETER_SOP.md` 承担，规定七个实验（EXP-A 至 EXP-G）、七个拟合步骤（FIT-0 至 FIT-4c）和 RPT 数据格式；诊断层由 `docs/CRITICAL_REVIEW.md` 承载，记录论文错误、作用域卡片、升级路径。四份权威文档的顶层是 `docs/CLAUDE.md`，给 AI 代理提供任务路由表。

面向人类读者的叙事性文档（`docs/01_setup_guide.md` 至 `docs/06_parameter_sourcing.md`）是上述权威文档的解释和扩展。任何时候叙事文档与权威文档冲突，以权威文档为准。

这种分层决定是从一次早期失败中总结出来的：最初把参数信息散落在多个 md 文档中，导致 R_SEI 被错误地归到循环老化拟合步骤，而论文明确说它来自日历老化拟合。此后建立了"修改参数信息必须先改 JSON，再改代码，最后更新 MD"的强制顺序，由 `docs/CLAUDE.md` 的 R1 规则固化。

---

## 三、必须严格遵守的三条规则

### 规则 R1：参数信息的修改顺序

任何涉及参数的改动，必须按"改 `PARAMETERS.json` → 改代码 → 改相关 MD"的顺序进行。禁止只改某个 MD 叙述而不更新 JSON。这是事实一致性的唯一保证。

### 规则 R2：老化参数的拟合顺序

老化参数必须按 FIT-4a、FIT-4b、FIT-4c 的严格顺序拟合。FIT-4a 处理所有日历老化参数，包括 `k_SEI_cal`、`E_a`、`k_LAM_PE_cal`、`γ_PE` 和 `R_SEI`。FIT-4b 处理循环参数 `k_SEI_cyc`、`k_LAM_PE_cyc`、`k_LAM_NE_cyc`，此步骤中 plating 必须关闭（`k_LP = 0`），且所有 FIT-4a 的参数（特别是 `R_SEI`）必须冻结。FIT-4c 只调一个参数 `k_LP`，其他全部冻结。

这个顺序的物理依据来自论文第 12 页的原话："The resistance increase is predicted well by the simulation, despite the fact that all resistance-related aging parameters were taken from the calendar degradation study." 日历条件下 `Q_PLA_NE = 0`，内阻增长纯来自 SEI 和 LAM，因此 `R_SEI` 能被唯一识别。在循环数据上拟合 `R_SEI` 不仅多余，还会因为和 plating 耦合而产生多解。

### 规则 R3：电阻 LUT 的语义

三张电阻查找表（`R_s_LUT`、`R_NE_LUT`、`R_PE_LUT`）只代表 fresh-cell 的数据，老化期间绝不重新测量。老化对电阻的影响完全通过公式 `R_i(t) = R_i^0 · f_{R,i}(t)`（论文 Eq. 43）表达，其中退化因子 `f_{R,i}` 由模型内部的状态变量 `Q_LAM_*`、`Q_SEI_NE`、`Q_PLA_NE` 自动推导。唯一从老化实验拟合的电阻相关参数是 `R_SEI`，它在 FIT-4a 中与其他日历参数一同识别。

另有一个派生量 `R_NE_0` 是从 `R_NE_LUT` 在 50% SOC、C/3 工况点取值后归一化得到的锚点标量。每次替换 `R_NE_LUT`（例如切换到新电池体系）时必须同步更新 `R_NE_0`。当前代码把它作为独立输入（在 `panasonic_ncr18650b.py` 中硬编码为 `0.018236`），这是一个已知的隐性耦合，TODO 标记已加。

---

## 四、批判性审查的关键发现

对原论文做了一轮严格审查，识别出两类共十二条问题，全部记录在 `docs/CRITICAL_REVIEW.md` 和 `docs/PARAMETERS.json::critical_review_findings` 中。

最重要的两条是已确认的论文错误。第一条是 `k_SEI_cal` 在 Table Ib 被印为 `4.2 × 10⁻²²` A²·s，但 MATLAB 源码使用 `0.0419625 ≈ 4.2 × 10⁻²` A²·s。通过对 Eq. 36 的量纲分析、MATLAB 源码核验、以及前向仿真复现 Fig. 4c，可以确认代码值是对的，论文值是排版错误，很可能是 `10⁻²` 中的 `²` 在排版时被重复成 `⁻²²`。此错误已在 `SEIParameters.k_cal` 的 docstring 中以注释标明，任何从论文 Table Ib 直接取值的下游使用者都会得到完全错误的结果。第二条是论文第 10 页正文把 `k_SEI,cyc` 误写到日历参数列表中，而 Tables 是正确的，JSON 和本工程文档都以 Tables 为准。

其余十条属于已知的简化假设，每一条都有明确的作用域限制和升级路径。其中最需要注意的是 `V_LP_eq = 0 V` 这个静态镀锂平衡电位假设：同一个作者团队（Dubarry 为高级作者）在 2024 年发表的 Batteries 10:408 明确指出这个静态假设"在稳态之外不成立"，并提出了动态修正。Mmeka 2025 论文未采用这个修正。因此对于快充（大于 1C）、低温（低于 15°C）或高倍率放电场景，本模型的 knee 预测精度会下降。代码中已加 `TODO(v2)` 标记，`V_LP_eq` 字段预留了支持 callable 的升级接口。

另外还需特别提醒的是工程假设温度恒定（等温模型）。对 18650 单体在 DST 工况下的 5 到 10 K 瞬态温升没有刻画，在 `E_a = 55.5 kJ/mol` 的灵敏度下，这相当于 1.8 倍的 SEI 速率偏差。对大容量电池组或无温控的真实车辆应用，必须先加入热耦合才能用。

所有已知的作用域限制汇总在 `CRITICAL_REVIEW.md §三` 的"作用域卡片"小节，以及 `PARAMETERS.json::scope_of_validity` 字段中。使用模型前务必查阅。

---

## 五、参数分级与实验体系

模型的 34 个参数按获取难度分为四级。第一级是从 datasheet 读或按约定设定的参数，共 10 个，包括名义容量、电压上下限、初始化学计量等。第二级是通过实验测量后作为查找表使用的参数，共 5 个，即三张电阻 LUT 和两条半电池 OCV 曲线。第三级是通过 1 到 2 个标量的轻度拟合得到的参数，共 5 个，包括负载比 LR、偏移 OFS、RC 电容 C1 C2、电阻劈分因子。第四级是需要长周期老化实验拟合的参数，共 10 个，是整个工程中获取难度最高的部分。

实验体系由七个独立模块组成。EXP-A 是 fresh cell 的 C/40 完整放电，产出名义容量和全电池 OCV。EXP-B1 和 EXP-B2 是拆解 fresh cell 后组装 CR2032 半电池做 C/40 测试，分别产出 PE 和 NE 的半电池 OCV 曲线。EXP-B3 是 fresh cell 的 EIS 测量，产出串联电阻。EXP-B4 是 GITT 扫描，产出 NE 和 PE 的二维电阻查找表。EXP-C 是电流阶跃弛豫测试，用于拟合 RC 时间常数。EXP-D 是 fresh cell 上一圈完整的 DST 协议，用于拟合电阻劈分因子。EXP-E 是日历老化，需要多温度和多 SOC 条件长期储存六到十五个月，每次 RPT 必测内阻。EXP-F 和 EXP-G 是循环老化，前者到 knee 前的 150 到 200 EFC，后者继续到容量跌至 70%。

对于新体系（例如 LFP-石墨），`PARAMETERS.json::minimal_viable_experiments` 给出了三档方案。最小 fresh-cell 方案只需 EXP-A、B1、B2、B4；可预测老化的最小方案加 EXP-F 和 EXP-G；完整方案加 EXP-B3、C 和 E。

---

## 六、与 Claude Code 的工作流分工

经过多轮对话验证，工程形成了明确的分工原则。来这里（Web chat）讨论的适合场景是：论文理解与对比、新物理机制的设计决策、SOP 本身的修订、跨文献的方法论对比、重大工程决策。交给 Claude Code 的适合场景是：按已有 SOP 执行具体拟合、调试代码报错、运行仿真、生成和修改脚本、解读实际数据。

一个实用的判断标准是："答案是否已经在硬盘里"。如果答案可以从 `PARAMETERS.json`、`PARAMETER_SOP.md`、`CRITICAL_REVIEW.md` 或代码中机械地读出或推导出来，就交给 Claude Code。如果答案需要新的外部信息（最新文献、论文 PDF、架构判断），就来这里。如果架构清楚但落地涉及大量代码改动，两边接力：这里讨论方案，Claude Code 执行。

典型的扩展任务（例如"加入温度耦合"或"实现 Beck 2024 的动态 V_LP_eq"）应当走这样的流程：先在这里讨论论文依据、接口设计、对现有测试的影响、文档同步计划，输出一份"实施任务单"；然后把任务单交给 Claude Code 在本地逐项实施，运行回归测试，提交改动。

---

## 七、验证状态

最新一次清点（2026-04-21）时，工程状态如下：pytest 15 个用例全部通过，耗时约 23 秒；`scripts/check_parameter_consistency.py` 验证 39 条参数、7 个拟合步骤、10 个实验的 JSON 与代码引用全部一致；`examples/smoke_test.py` 正常输出；`examples/figure7_simulation.py` 在 ACC_FACTOR 为 100、三循环的快速模式下约一分钟完成，容量衰减从 3.42 Ah 降到 3.22 Ah，符合论文 Fig. 7 的定性特征。

已打包的最新版本（zip 约 18 MB，36 个文件）包含完整代码、文档、测试和示例，conda 环境定义就绪，可按 `QUICKSTART.md` 在 Mac 上十分钟内恢复运行。

---

## 八、已识别但尚未实现的扩展

以下扩展在代码中有 `TODO(v2)` 标记或在 `CRITICAL_REVIEW.md` 升级路径中有明确记录，是可能的下一步工作方向。

关于镀锂：实现 Beck et al. 2024（Batteries 10:408）的动态 `V_LP_eq(T, c_Li+)` 修正函数。`PlatingParameters.V_LP_eq` 字段预留为 callable 接口。

关于 Arrhenius：为 plating、LAM_PE、LAM_NE 速率分别加入独立的激活能字段。当前只有 SEI 有 Arrhenius，这限制了温度外推的有效性。

关于电阻退化：实现 `f_{R,s}(Q_SEI, Q_LAM)`，让串联电阻也随老化增长。post-mortem 文献显示 R_s 在全生命周期会增长 10% 到 30%，影响 knee 预测时机。

关于 `R_NE_0` 自动派生：添加 `derive_R_NE_0()` 工具函数，从任意 `R_NE_LUT` 在 50% SOC、C/3 工况点自动取值，消除当前的隐性耦合。

关于 C0_PE 自动校正：当前 `C0_PE` 公式包含两个经验修正因子 `/0.973 * 1.0275`，是论文作者手动拟合得到的。应提供 `scripts/fit_C0_PE_correction.py` 让新体系能自动完成这一步。

关于热耦合：加入 lumped 热模型，使 T 成为一个微分状态变量，支持大容量电池组和无温控工况的仿真。

关于 LFP-石墨体系的落地：`docs/06_parameter_sourcing.md §6` 给出了 `create_lfp_graphite_cell()` 参数工厂的代码骨架和实验方案。真正变成源文件 `libquiv_aging/lfp_graphite.py` 是下一个落地任务。

关于自动化拟合脚本：`scripts/` 目录目前只有一致性检查脚本，SOP-5 规定的七个脚本（`build_halfcell_dat.py`、`build_resistance_mat.py`、`fit_electrode_balance.py` 等）均待生成。

---

## 九、给新对话的起步指令

建议新对话（无论在这里还是在 Project 里）的第一条消息采用以下格式：

"请通读 docs/CLAUDE.md、docs/PARAMETERS.json、docs/PARAMETER_SOP.md、docs/CRITICAL_REVIEW.md、docs/MIGRATION_NOTES.md 这五份文档。然后用不超过十句话告诉我：你理解这个工程是做什么的；你识别到的三条核心规则是什么；你准备如何响应我后续的问题；你当前还不清楚需要我补充的信息是什么。"

如果回答准确覆盖了上述四点，说明上下文成功迁移，可以直接进入具体工作。如果有偏差，根据偏差补充说明或调整权威文档。

---

## 版本记录

| 日期 | 变更 |
| --- | --- |
| 2026-04-21 | 初版。汇总从工程建立到 `PARAMETERS.json v2.0` 和 `CRITICAL_REVIEW.md` 发布的全部关键决策。 |
