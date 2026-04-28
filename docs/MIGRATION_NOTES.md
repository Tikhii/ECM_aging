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

## 十、离线工作流三阶段分离（2026-04-23 架构决策）

工程从"单体对话"模式演进为 air-gapped 三阶段分离：离线区（Claude Code + 本地
脚本 + 原始数据），外带区（仅工程师手工贴到在线对话的文本），在线区（Claude
网页端，用于架构与方法学级讨论）。边界由 `docs/08_consultation_protocol.md`
§2 白名单和 §3 黑名单确定，原始数据与任何参数绝对数值禁止越过离线↔在线边界。
此分离的根本动机是对话日志的长期可缓存性与账号层上下文泄露风险；三阶段分离
把数据留在离线区，同时保留在线咨询能力。

错误码 registry 被刻意设计为独立文件 `docs/error_codes_registry.json`，不并入
`PARAMETERS.json`。理由是语义纯洁性：`PARAMETERS.json` 回答"有什么参数、从哪
里来"，registry 回答"什么会出错、怎么拦截、什么时候升级"。两者的修改节奏与
引用者集合完全不重合，强行合并会产生虚假耦合；独立 registry 让 R1（参数层
修改顺序）与 R6（错误码修改顺序）两条规则在事实层上不相互缠绕。

`--export-public` 最终采用"脚本生成 bundle + 终端 y/N 确认 + 审计副本"而非
"要求工程师手工复制粘贴"。讨论中评估过手工粘贴方案的"人眼过一遍"价值，结论
是重复性手工抄写会让工程师 desensitize、粘贴板残留会引入意外泄露、而自动化
+ 多层硬约束（20 行/2 KB 上限、Schema 白名单、`_public_` 文件名标记、SHA256
审计）提供比手工抄写更可靠的拦截。该人因分析写入 `08_consultation_protocol.md §5.6`。

---

## 十一、2026-04-23 P0 事故与 meta 教训

本节记录 2026-04-23 将离线工作流落地到 environment-frozen.yml 的过程中
暴露的规则系统边界漏洞。事故本身已在当日对话中完整走完事故—回滚—
修复—制度化的全流程; 本节存底, 供未来会话快速理解 v0.2.1 标签之前
发生过什么。

事故的直接触发是一条 `conda env export --no-builds > environment-frozen.yml`
命令在未激活 libquiv-aging 环境的情况下执行, 默认 base 环境被导出,
内容完全不含项目依赖。更严重的是, 同一日的另一次误操作导致
`conda env export` 覆盖了 `environment.yml` 本身, 将仓库中手写的
规范版替换为机器生成的 base 环境 dump。两处错误同时存在时, 由于
事实层与工作树状态严重不一致, Claude 基于 Claude Code 的报告做出
了 "environment.yml 是预先存在的历史遗留错误" 的错误判断, 并据此
推了错误的 Commit 2 计划, 直到 `git status` 输出暴露了
`environment.yml` 被工作树修改这一关键事实, 才得以拦下。

事故最终通过 `git restore environment.yml` + 正确激活环境后重新导出
`environment-frozen.yml` 的路径修复, 并以 v0.2.1-env-frozen-locked
标签固化。完整 commit 链条保持四层单一职责 (ignore .claude → env
baseline → clear TODO → tag), 事故过程本身未在 git 历史中留下噪音。

从本次事故沉淀的四条教训均已制度化: "入库" 的精确定义、
`conda env export` 的破坏性语义、"历史遗留" 判断必须基于 HEAD
而非工作树、Claude Code 超范围审查前置条件的正向行为, 均写入
CLAUDE.md 对应小节。R5 验收阶段的 git 条款也在本轮同步从 "禁止
自动 commit" 扩展为 "禁止自动 git add / commit / tag", 以反映
Claude Code 在事故中的实际拦截点 (它拒绝 git add 的理由正是对
原 R5 条款的合理扩展解读)。此外, Claude Code 在本次事故中两次
主动发挥了拦截作用, 这两种行为已在 CLAUDE.md "允许的超范围行为"
一节中明确鼓励, 从偶发善意转为制度预期。

---

## 十二、离线工作流 v0.2.3: 从 air-gapped 到内部 pip 镜像单轨制 (2026-04-24)

v0.2.0 的离线工作流架构基于完全 air-gapped 假设——即离线工作站与任何网络
完全隔离，所有依赖必须以物理介质搬运。在实际落地过程中发现，目标工作站处于
受控内部网络中，可以访问企业内部 pip 镜像站。这一事实改变了依赖交付的最优
路径：不再需要在打包机上下载几百 MB 的 wheel 归档并通过 U 盘搬运，而是让
离线工作站直接从内部镜像拉取依赖。物理传输带宽限制使大文件交付不现实是放弃
重量路径的直接原因；更深层的原因是基础设施责任边界的明确——pip 镜像的可用性
由 IT 部门保障，在工程项目内部做冗余备份既不经济也不属于工程的职责范围。

这一方案迁移使 `environment-frozen.yml` 的职责发生了转变。在完全 air-gapped
假设下，frozen.yml 的最终用途是生成 wheel 归档（提供二进制包本身）；在内部
pip 镜像方案下，frozen.yml 的用途变为声明精确版本号。`requirements.txt` 从
frozen.yml 通过 `scripts/build_requirements.sh` 机器派生，翻译 conda 包名为
pip 格式，过滤 conda 专属的 C 库和系统包，严格保留 `==` 版本锁定。两份文件
的一致性由脚本而非人工维护保证。放弃 frozen.yml 而非转变其职责的方案被否决，
因为 frozen.yml 仍然是联网 macOS 开发机上 conda 环境的权威快照，且 ENV-E001
错误码的检测语义依赖它作为基线。

配套新增的三个脚本构成完整的操作链：`build_requirements.sh` 在联网机上从
frozen.yml 生成 requirements.txt，`install_offline.sh` 在离线机上一键创建
venv 并安装全部依赖，`verify_install.sh` 验证安装是否正确。完整的部署文档
写入 `docs/09_offline_bundle_guide.md`。

---

## 十三、2026-04-24 v0.2.4 清理整顿: 奥卡姆剃刀原则的应用

v0.2.3 落地后, 一次回顾性评估揭示了 P0 到 P1-A 阶段积累的几处
过度工程。这些过度工程在当时的约束假设下 (完全 air-gapped、未来
可能扩展到多平台、fit 脚本将产生大量可识别性诊断) 是合理的, 但
在实际工作环境约束清晰化之后 (Ubuntu 20.04 单一目标、内部 pip
镜像可达、数据外带几乎无可能、fit 脚本尚未存在故其错误码为纯
预测), 它们成为了不为当前任何实际需求服务的基础设施负担。

本批次清理识别并处理了四项失配。08_consultation_protocol.md
追加了适用范围声明, 明确它适用于稀少的跨 air-gap 疑难讨论, 而
非日常故障处置, 心智上从 "主流程" 降级为 "应急通道"; 职责不变,
用户预期对齐。error_codes_registry.json 中 IDENT-W001/W002/W003
三条可识别性警告码的 status 从 active 改为 draft, 因为它们的
trigger 条件未经实际 fit 脚本验证, 保持 active 会让 registry
看起来比实际能力更完整, 造成假信号。09_offline_bundle_guide.md
删减了 "未来扩展路径" 一节, 因为当前实验室配置已锁定, 为假想
的 ARM Linux 或 Windows 目标预留规划不符合 YAGNI 原则。

本次清理不涉及规则体系变更, 不影响任何已完成的功能。它是对
文档语义分层的精修, 使权威文档的心智模型更贴近实际工作流。
奥卡姆剃刀原则在本项目中被首次显式应用: 不为未验证的设计做精
修, 不为未来可能需要的功能预先构建接口。未来若再发现类似失配,
按本次先例处理。

---

## 十四、2026-04-25 v0.3.0 cell type 抽象层

v0.2.4 清理之后，工作流面临的第一个真实科学任务是让新的 LFP/G 电池能在同一套代码下参数化。原有 `panasonic_ncr18650b.py` 作为硬编码参数工厂，每增加一个 cell type 都要新建一个类似的 Python 模块，且每份模块中参数都以 Python 源码形式存在，违反 R1 "改 JSON 再改代码" 的精神。v0.3.0 引入 cell type 抽象层彻底解决这个问题。

核心设计是**双 spec 架构**：材料 spec 承载物理本征量（半电池 OCV 数据文件路径、电极平衡参数、化学计量范围等），schema 稳定，跨 cell type 只是数值填不同；参数 spec 承载唯象量（老化速率常数、电阻分配、初始退化状态等），schema 按机制模型版本化，当前版本是 mmeka2025，未来 C3 升级路径（R_s 退化）或 S2 升级路径（动态镀锂）将产出新 schema 版本，旧版本保留为学术历史。这种分层服从奥卡姆剃刀，用"是否需要 schema 版本化"这一工程判据切分文件，物理本征/非本征作为字段级元数据保留但不影响加载逻辑。

一个 cell 实例由一对 spec 引用唯一确定，通过 `create_cell_from_specs(material_path, params_path)` 加载。加载器内部完成 schema 验证、派生量计算（C0_PE、C0_NE、Q0_SEI_NE 等由原字段和 FIT-0 修正因子派生）、机制版本路由、AgingModel 组装、电阻闭包构造。机制版本路由由 `libquiv_aging/model_versions/` 下的子模块承担，未来新机制版本只需新增一个子模块和一份对应的 params schema，不修改加载器也不动已有 spec 文件。

`panasonic_ncr18650b.py` 保留为兼容层，内部调用 `create_cell_from_specs` 并指向包含的两份 spec，保证外部 API（`create_panasonic_ncr18650b()`）和所有 22 项既有测试行为完全等价。这是唯一允许保留的"硬编码工厂"形式，且仅作为示例的便捷入口。新 R7 规则明确禁止为其他 cell type 创建类似模块，统一走 spec 路径。

---

## 十五、v0.4.0 第一阶段: FIT-1 电极平衡拟合脚本 (2026-04-25)

v0.3.0 完成了 cell type 抽象层基础设施, 但还缺一件关键拼图: 让 FIT
步骤的输出实际写入 spec 文件。在 v0.3.0 之前, LR 和 OFS 等 fitting
产出都是论文作者手工硬编码到 panasonic_ncr18650b.py 中。v0.3.0 引入
material spec 后, 这些字段以 manually_set status 进入 spec 但没有
脚本作为产出端。v0.4.0 第一阶段填补这个缺口, 实施 FIT 脚本系列的
第一个成员: FIT-1 电极平衡拟合。

FIT-1 选择作为模板的理由经过几轮讨论后定型: 它的双变量结构 (LR,
OFS) 与后续 FIT-2 (C1, C2) 和 FIT-3 (fractionR1toRs, fractionR2toRs)
同构, 内部循环完全代数化 (open_circuit_voltage 合成, 不需 cell 仿真),
计算量小 (1-2 秒), 物理意义清晰, 在工作流中是必选步骤。FIT-0 因为
是单变量且可选 (论文修正因子通常直接复用), 推到 v0.4.x 后期或不做。

实施过程中产出两份代码资产: `scripts/fit_electrode_balance.py` 是
FIT-1 主脚本和 CLI 入口; `libquiv_aging/fitting.py` 是 FIT 脚本系列的
共享基础设施, 含 preflight 检查、value_with_provenance 构造、spec
原子写回、numerical Hessian 估计、git/file hash provenance、run
artifact 写出等通用工具。FIT-2/3 实施时直接复用该模块。

工作流上, 每次 FIT-1 成功执行会产生三层效应: 第一是材料 spec 中
LR 和 OFS 字段的更新, 含完整 fitting provenance (fit_step="FIT-1",
fit_source 指向 EXP-A CSV 的 hash, fit_script_version 是 git commit,
fit_r_squared 和 uncertainty 反映质量); 第二是 `runs/{run_id}/` 目录
下的三份运行产物, 不入 git 但可手动归档; 第三是 stdout 的人类可读
摘要。这套机制为 FIT-2/3/4 提供了完整模板。

特别说明 marginal 档 (FIT1-W001): 当 RMSE 在 20-50mV 之间, 拟合通过
但质量低于推荐阈值。脚本仍写回 spec 但 fit_r_squared 字段记录此次
拟合质量, 供未来审计。这是按 v0.3.0 的"R² 单一 fitted status"决策
落地的: 不引入 fitted_marginal enum, marginal 信号通过 fit_r_squared
隐式表达。

OFS 弱可识别性: 实施过程中, dry-run 测试暴露了 FIT-1 的一个真实物理
限制: LR 和 OFS 在 V_cell(SOC) 数据上存在强共线性。OFS 仅通过
(1 - OFS/100) 因子影响 X_PE 的 SOC 范围 (2% OFS 对应 0.98, 2.5% 对应
0.975), 这种小幅缩放可被 LR 通过反向调整 X_NE 范围吸收。OFS 的独立
可识别性依赖半电池 OCV 在 stage transition 等特定 X 值处的局部特征。
100 点均匀采样的合成数据下, LR 反演相对误差 0.04% 但 OFS 反演相对误差
达 3.8%, dry-run 容差据此调整为 LR 0.5%、OFS 20%、RMSE < 2mV。真实
EXP-A C/40 数据 (几千点, 在 stage transition 附近自然采样更密) 可能
表现更好, 但本阶段未验证。这一发现已作为 N1 条目加入
`docs/CRITICAL_REVIEW.md`, 并在 `docs/PARAMETER_SOP.md §三.1` 末尾
给出工作流警示 (若 σ_OFS / OFS > 10%, 考虑固定 OFS, 只拟合 LR)。
FIT-1 未来可加 `--fix-OFS` 选项, 作为 v0.4.x patch。

错误码方面, 新增 FIT1-Exxx 系列占用 exit code 80-89 块, FIT2/3 预留
90-109。registry 现有 ENV/DATA/FIT4A/FIT4B/FIT4C/SOLVE/IDENT 七个
作用域扩展为八个 (新增 FIT1)。schema 的 patternProperties 和 scope
enum 同步扩展。runbook 章节相应重新编号 (新增 §3 FIT1, 原 §3-§7
顺延为 §4-§8)。

---

## 十六、v0.4.1 R8 规则: README 与 release 同步 (2026-04-25)

v0.4.0 完成后审视项目对外形象时发现 README.md 和 QUICKSTART.md 自
v0.1 时代以来从未更新过, 完全没有反映 v0.2-v0.4 的所有变化。具体过时
内容包括: 工程特点中的"5 个模块"实际为 8+ 个、"15 个测试"实际为 69 个、
目录结构缺 schemas/ material_specs/ param_specs/ scripts/ 几个 v0.3
之后的核心目录、文档导航缺 06-09 + MIGRATION_NOTES + error_codes_*
等共计 6 份新文档, 完全没有 v0.3 双 spec 架构、v0.4 FIT 脚本系列、
八层 tag 阶梯等核心叙事。

根因诊断: R1-R7 规则系统覆盖了模型正确性 (R1, R2, R3, R4) 和内部
文档自洽性 (R5, R6, R7), 但没有任何规则覆盖"项目对外整体一致性"。
README 属于项目对外形象层, 它不影响模型跑得对不对、不影响代码能不能
运行, 所以一直被任务驱动的工作流忽略。这是一个工作流类别缺陷, 不是
单一文件疏漏。

修复方案分两层。短期是 v0.4.1 patch 把 README 和 QUICKSTART 一次性
更新到 v0.4.0 后的状态。长期是新增 R8 规则把 README/QUICKSTART 同步
正式纳入每次 minor release 的任务包, 与代码改动同等优先级。R8 的
触发条件明确列出"新公共 API、新目录结构、新工作流入口、新概念"四类
改动, 任一发生即要求 README 更新作为 release 子阶段。docs/vX.Y.Z
patch 一般不触发 R8 (除非 patch 修复了 README 中描述的功能), 维持
patch 的轻量性质。

R8 与 R5 的边界划分清楚: R5 管内部权威文档之间的一致性 (PARAMETERS.json
↔ 代码 ↔ MD 内部文档), R8 管项目对外形象与代码状态之间的一致性
(README/QUICKSTART ↔ 实际功能)。两者互补, 不冲突也不重叠。

本规则的潜在扩展: 未来可能发现 LICENSE、CONTRIBUTING.md、pyproject.toml
description 等"对外项目对象"也存在类似问题。如发现, 在 R8 基础上扩
展成员清单, 不另立新规则。

> 状态更新 (v0.4.3, 2026-04-26): LICENSE、NOTICE、pyproject.toml description
> 已落实为 R8 成员, 各自触发条件记录在 `docs/CLAUDE.md` R8 §成员扩展。
> CONTRIBUTING.md 仍为潜在扩展, 待项目首次接受外部贡献时再落地。

---

## 十七、v0.4.2 SPEC_ic_analysis 提升 (2026-04-25)

v0.4.1 完成后, 一次例行盘点暴露了 docs/TODO_ic_analysis.md 这份文件的真实
性质。表面看它是一个待办清单, 文件名为 TODO_ic_analysis.md; 但实质内容是
一份冻结于 2026-04-22 的完整实施规格 (spec), 含 Step 0 reconnaissance 命令、
forward model 数学推导、objective function、initial guess heuristic、
optimizer 配置 + bounds、Module API + 三个函数签名、CLI script + 输入输出
schema、5 个 acceptance tests、performance target、numerical subtleties、
out-of-scope 项。它在 docs/PARAMETER_SOP.md §SOP-4.5、§SOP-5 表格、§3.2 RPT
CSV schema 等三处已被作为权威规格引用, 内容也已在 2026-04-22 documentation
PR 中纳入 SOP 体系。文件存在于 docs/ 目录约三天, 但因为文件名 TODO 后缀的
误导, 既不被 README 视为对外文档展示, 也未被 CLAUDE.md 任务路由表收录。

这暴露了一个比 R8 (README 同步) 更微妙的工作流盲点: **已冻结的、跨多个
release 的实施计划如何持续可见**。MIGRATION_NOTES.md 记录已完成的演化历史,
权威文档记录当前状态, 但项目缺少"已规划但待实施的 backlog"的台账。如果不
是这次盘点偶然发现, TODO_ic_analysis.md 可能在 FIT-4a/4b 实施时才被重新
注意, 那时距其冻结已经数周到数月。

修复方案是 v0.4.2 patch 把文件升级为 SPEC: git mv 重命名为 SPEC_ic_analysis.md,
顶部 Status 段落明确标注"Spec frozen, pending v0.5.0 implementation",
Module API 段中三个函数签名从 v0.3.0 之前的 `cell_factory: Callable` 接口更新
为 v0.3.0+ 双 spec 接口 `material_spec_path + params_spec_path`, CLI 段落
增加注释说明 `--cell-type` 与 spec 路径的映射关系, 以及五处文件名引用
(SOP §SOP-4.5 两处 + PARAMETERS.json deferred_extensions + CLAUDE.md 任务路由
表新增一行 + 版本纪要追加一行)。

这次发现没有立即引出 R9 规则。理由是: R9 候选已经有"信息不对称协作约定"在前面排队
但被判定为不应固化 (临时基础设施不应进入工程权威文档), 暂时只有"backlog 文档台账"
单一候选。R9 的引入需要至少两次类似盲点暴露才有制度化价值, 单次发现作为元教训
记录在 MIGRATION_NOTES 中即可。如果未来再发现类似的"冻结文档但被工作流忽略"事件,
届时再制度化为 R9 ("backlog 文档台账维护")。

本次 patch 同时验证了一个更小的元教训: 文件命名约定带有真实工程语义。`TODO_*.md`
和 `SPEC_*.md` 在工程师心智中是不同性质的文件, 误用会产生持续的注意力税。
未来类似的命名升级 (例如 `WIP_*.md` → `DRAFT_*.md` → `SPEC_*.md` → `IMPLEMENTED_*.md`)
应在文件性质变化时及时执行, 而不是等到下一次盘点。

---

## 十八、v0.5.0 FIT-2 RC 弛豫拟合落地 (2026-04-26)

### 18.1 任务范畴与边界

FIT-2 在 v0.4.0 已写入 `PARAMETERS.json::fit_steps::FIT-2` 但脚本是占位; 本次
v0.5.0 把脚本 (`scripts/fit_rc_transient.py`) 与拟合内核
(`libquiv_aging/relaxation_fitting.py`) 实装。任务包覆盖六个子阶段:
1) 错误码事实层扩展 (FIT2-Exxx/W001), 2) 脚本主流程, 3) 测试 (内核单测 +
端到端集成), 4) 文档同步 (PARAMETERS.json finding, CRITICAL_REVIEW C7,
PARAMETER_SOP §三.2, 07 runbook §4, CLAUDE.md, 升级文献入口),
5) 验证, 6) 完成报告。本节聚焦设计决策, 实现细节走代码与 spec。

### 18.2 三个核心架构决策

**18.2.1 C6 → C7 全工程重映射**

进入本任务时, `CRITICAL_REVIEW.md` 已存在 C6_knee_mechanism_scope。RC 拓扑
不足是新发现, 编号上有两个选择:
- A: 复用 C6 编号 (扩大 C6 语义)
- B: 新建 C7, 保留 C6

选 B。理由: C6 是关于 knee 的 scope-of-validity 警示, 与 RC 拓扑物理上无关;
合并会让 finding 的诊断焦点稀释。`CRITICAL_REVIEW.md` 路由表与版本日志
同步增加 C7 行, `PARAMETERS.json::critical_review_findings` 新增
`C7_RC_topology_inadequacy_for_long_relaxation` 记录 (与 C7 章节互锁,
满足 R5 派生层一致性要求)。

**18.2.2 RELAXATION_MODELS dispatch 模式而非硬编码 two_exponential**

CLI 的 `--relaxation-model` 参数是 dispatch 表 key, 默认
`two_exponential`, 当前唯一注册项。后续 fractional-order / Mittag-Leffler /
DRT 升级 (见 `docs/UPGRADE_LITERATURE/fractional_order_RC.md`) 通过新增
注册项实现, 不需改 CLI 主流程, 也不需改 spec writeback 逻辑 (`fitting.py::
write_back_to_spec` 是模型无关的)。

权衡: 提前引入 dispatch 增加一次性复杂度 (一个 dict + 一个 getter), 但
避免了后续升级时把 fit 函数重写一遍。判断依据: C7 是已识别的、近期可达的
升级方向, 不是远期假设, 结构性投资合理。这是奥卡姆剃刀的反向应用 — 当
后续路径已明且邻近, 不预先抽象会让升级时引入更多回归风险。

**18.2.3 tau→R 双候选映射 + amplitude RSS 选择 + 歧义警告**

two_exponential 拟合返回 (tau1, tau2), 但 RC 拓扑里 tau1 可能锚到 R_NE 或
R_PE (取决于哪个电极的 RC 时常数更短)。脚本同时计算两候选映射:
candidate_A = (tau1↔R_NE, tau2↔R_PE), candidate_B = (tau1↔R_PE, tau2↔R_NE),
对每个候选用 LUT 查到的 R_NE/R_PE 计算预期振幅 (A1, A2), 与拟合得到的
振幅做 RSS 比较, 选 RSS 小者为 chosen, 另一个为 alternate。当
|RSS_chosen - RSS_alt| / max < 10% 时触发 FIT2-W001 (mapping_marginal=true)。
该字段持久化到 `relaxation_metadata`, FIT-3/4 在见到 mapping_marginal 时应
放宽 C1/C2 拟合权重。

权衡: 不让用户手选映射方向是关键 — 所有判别必须由 LUT + 数据驱动, 否则
C1/C2 就成了人工调参的载体, 失去 R7 工作流约束的物理意义。

### 18.3 spec writeback: relaxation_metadata 嵌入而非新字段

`schemas/params_mmeka2025.schema.v1.json` 的 value_with_provenance 在
v0.3.0 已设 `additionalProperties: true`。本次直接利用此口子把
`relaxation_metadata` (含 model name, tau_chosen, mapping label,
mapping_marginal, rmse, r_squared) 嵌入 C1/C2 的 entry, 不需要 schema
迁移。这与 `additionalProperties: true` 设计原意一致: 拟合产出的诊断
信息属于"伴随数据", 不应升格为顶层字段污染 schema 的核心契约。

### 18.4 与 R5/R6/R8 的对齐路径

- **R6** (错误码先行): `error_codes.schema.json` 双扩展 (`scope.enum` +
  `patternProperties` regex), 然后 registry 添加 FIT2-E001..E003/W001
  (含完整 11 字段), 然后 runbook 派生 §4 FIT-2, 然后脚本 raise 点
  使用对应 exit code。先 fact 后 derived 的因果链未被绕过。
- **R5** (派生层一致性): runbook §4-§9 整体重编号 (FIT2 插入引发
  FIT4A/B/C/SOLVE/IDENT 顺移), `PARAMETER_SOP.md` 中所有指向 runbook
  的章节号引用同步刷新。
- **R8** (对外文档同步): README.md FIT 步骤状态行, QUICKSTART.md 测试
  数与脚本清单, 同 release 任务包内更新。

### 18.5 经验留痕

本次任务把 "升级路径" 从内部 backlog 提升为入库文档 (`docs/UPGRADE_LITERATURE/
fractional_order_RC.md`)。理由: C7 finding 的可信度依赖于"升级路径不是
画饼"的可证伪性。把候选模型与必读文献写入 repo 等于给后续 v0.6+ 的
评估任务留下了可追溯的入口, 比把这些信息散落在 CRITICAL_REVIEW.md 的
"建议" 段更易被未来的人 (或 AI) 找到。这是 v0.4.2 SPEC 提升经验
(§十七) 在 backlog 文档上的一次延伸应用。

---

## 十九、v0.5.1 派生层语义辐射修复 (2026-04-26)

v0.5.0-fit2 完成后做了一次全面状态审计 (Project Knowledge GitHub 集成
sync 后的检索), 暴露 v0.5.0 任务包执行时 R5 派生层一致性的一处实质漏洞。

### 19.1 漏洞性质

FIT-2 实施改用 EXP-B4 GITT 弛豫数据源 (替换原 EXP-C 阶跃响应), 这是一个
"输入实验切换"动作。任务包正确更新了 `PARAMETERS.json::fit_steps::FIT-2`
的 `requires_experiments` 字段, 但**未同步更新**:

- `PARAMETERS.json::experiments::EXP-C::outputs` (仍含 C1/C2)
- `PARAMETERS.json::parameters::C1/C2::experiment` (仍写 EXP-C)
- `PARAMETERS.json::minimal_viable_experiments::for_aging_prediction_robust`
  (仍含 EXP-C 而非 EXP-B4 用于 RC 的语义)
- `docs/SPEC_ic_analysis.md` 的 Status 行 (仍写 "pending v0.5.0",
  但 v0.5.0 已被 FIT-2 占用)
- `docs/PARAMETER_SOP.md §3.1 / §3.3` (CSV 格式表与目录约定)
- `docs/README.md` 目录结构图 tests/ 和 scripts/ 两段 (R8 同步执行
  不彻底, 只改了文字说明, 目录树未同步)

这些字段都是 fit_steps::FIT-2 的"语义辐射"目标——它们引用同一组实验和
参数, 但分属不同的派生层。FIT-2 修改触发的连锁反应未被任务包 §4 文档
同步段全面捕获。

### 19.2 元教训

R5 协议要求"扫→确→编→验"四步, 但扫描阶段的 grep 关键词如何**全面**
覆盖语义辐射目标, 是一个未明确建立的规范。本次失察的根因是:

- 扫描时只 grep 了直接关键词 (`FIT-2`, `C1`, `C2`)
- 未 grep 间接关键词 (`EXP-C` 作为旧数据源在所有引用它的字段中)
- 未做"输入实验切换"专项审视 (任何 fit_steps::FIT-X::requires_experiments
  的修改都需要扫描所有标注 `experiment: EXP-X-old` 的派生字段)

这与 v0.4.2 SPEC 提升时识别的 "TODO_*.md → SPEC_*.md 命名升级语义辐射"
是同根问题。两次都暴露了"修改一个权威字段, 派生字段未自动同步"的工作流
盲点。

### 19.3 制度化决策

**不立即引入 R9 规则**。理由:

- R5 协议本身要求"扫描-确认"的覆盖性, 本次失察不是规则缺失, 而是**规则
  执行细节不够具体**。引入 R9 会与 R5 重复
- 更合适的做法是在 R5 的 "扫描阶段" 描述中**显式补充**"语义辐射目标"
  概念, 即修改 fit_steps / experiments / parameters 等核心结构时, 必须
  把所有以这些结构为引用源的字段都纳入扫描

**待办**: 下次 docs/CLAUDE.md 修订时, 在 R5 协议 "1. 扫描阶段" 段中加入
"语义辐射目标"小节, 列出已知的辐射模式 (fit_steps↔experiments↔parameters
三角, README↔QUICKSTART, 等)。本次 v0.5.1 patch 不动 CLAUDE.md, 把这
一改进留给下次更轻量的文档治理 patch 做。

### 19.4 EXP-C 命运决策

PARAMETERS.json 的 EXP-C 字段从 "active" 改为 "deprecated for FIT-2",
保留实验定义本身但 outputs 改为空, 新增 deprecated_* 元数据字段。理由:

- R6 错误码协议精神 "编号一经发放不复用" 推广到实验编号
- 完全删除会破坏历史 git history 中对 EXP-C 的引用解析
- 若未来 EXP-B4 GITT 协议在某些 cell type 下不可行, EXP-C 的简化阶跃
  响应仍可作为 fallback (但需要新任务包扩展 FIT-2 接受 EXP-C 列契约,
  本 patch 不做)

### 19.5 PARAMETER_SOP.md 与 README.md 同步

PARAMETER_SOP.md §3.1 数据格式表 EXP-C 行加 deprecated 标记, §3.3 目录
约定加 EXP-B4 行并对 EXP-C 加 deprecated 注释。README.md 目录结构图的
tests/ 段加 test_relaxation_fitting.py 和 test_fit_rc_transient.py 两
行 (并将测试数 69 → 87), scripts/ 段加 fit_rc_transient.py 行。

06_parameter_sourcing.md §3.2 仍引用 EXP-C 阶跃响应作为 RC 拟合数据源,
但因其是叙事性文档 (R1 协议中"叙事文档与权威文档冲突时以权威为准"),
本 patch 不动, 留给下次大整理或 IC analysis 任务包附带处理。

CLAUDE.md 代码导航段的 "tests/test_basic.py 15 个回归测试" 描述也是
v0.2.x 时代过期内容, 同样推迟到下次治理 patch。

### 19.6 经验留痕

本次审计的触发条件是 Project Knowledge GitHub 集成完成 sync 后的全面
检索, 这种检索在以前 (集成不可用时) 成本极高, 现在变成日常可用工具。
未来每次 release tag 落定后值得固定执行一次类似审计, 把派生层不一致
问题在第一时间捕获, 不积累到下下次 release 才发现。

---

## 二十、v0.5.2 IC analysis 落地 (2026-04-28)

### 20.1 任务范畴与边界

`docs/SPEC_ic_analysis.md` 在 v0.4.2 (§十七) 升格为冻结契约 (frozen
2026-04-22),v0.5.0 / v0.5.1 期间该 SPEC 标注 "pending v0.5.0" 但
v0.5.0 被 FIT-2 占用,SPEC 兑现延迟到 v0.5.2。本任务包覆盖八个子阶段:

0) reconnaissance — 对 cell_model / lookup_tables / cell_factory
   做接口扫描,据 findings 选择 `synthesize_V_ocv` 实现路径
1) 错误码事实层扩展 — schema scope.enum 加 ICA,registry 写入
   ICA-E001/E002/E003/W001/W002 五条目
2) 内核实装 — `libquiv_aging/ic_analysis.py` 提供 `synthesize_V_ocv`
   forward、`heuristic_initial_guess`、`analyze_ic` 三层 API
3) CLI 实装 — `scripts/fit_ic_to_dms.py` 5 参数,JSON + 2×2 PNG,
   matplotlib lazy import
4) 测试 — `tests/test_ic_analysis.py` 22 用例 (T1-T5 acceptance + 错误码
   集成 + 子阶段 2 v2 helper 防回归)
5) R8 同步 — README / QUICKSTART / docs/CLAUDE.md 三处目录树 + 测试数
6) 元教训留痕 — 本节
7) 验证 — 全 suite 109 passed
8) 完成报告

本节聚焦三个核心架构决策、§十九 元教训正面应用、错误码 ICA scope
引入、子阶段 4 T4 阻塞与论文 Fig. 6c 物理印证。实现细节走代码与
spec。

### 20.2 Step 0 reconnaissance findings

子阶段 0 做了四组 grep,关键发现:

- `EquivCircuitCell.open_circuit_voltage_cell()` **不直接可复用**:返回
  当前 SOC 单点 float,内部依赖 `_aging_calibrate_SOC` 中 2 次 brentq。
  扫描 Q grid 触发 N×2 brentq → 单次 forward 秒级,违反 SPEC 性能目标
  (<2s/RPT)。
- `lookup_tables.py::open_circuit_voltage(X_ne, X_pe, T, ...)` 是干净的
  vectorized 原语,接受 numpy 数组,返回 `(V0, dS_NE, dS_PE, V0_PE,
  V0_NE)`,内部 `interp_dH_dS` 线性插值。这是 Path B 的天然落点。
- `HalfCellThermo.interp_dH_dS(X)` 对 X<0/X>1 做 silent clamp 而非返回
  inf。SPEC forward model 期望 X 越界返 inf 残差,故 ic_analysis 必须
  在调用前显式 X 域检查 — 边界处理由 caller 负责,**非接口冲突**。
- `_derive_C0_PE/NE/Q0_SEI_NE` 模块级函数签名与 SPEC 一致,可直接复用,
  返回 A·s 单位需 /3600 → Ah。

四 finding 共同支持 Path B (algebraic vectorized + 显式 X 域 inf
传播),与任务包推荐路径一致,但理由更硬:不是"解耦更适合 pure
forward"的理想化叙述,而是"`init()` 含 brentq → Path A 性能不可达"
的硬约束。这一 reconnaissance-driven 路径选择是子阶段 4 §十九 元教训
"实证驱动"在 v0.5.2 任务包内的首次正面应用 — 在写代码前先扫码再决策。

### 20.3 三个核心架构决策

#### 20.3.1 `synthesize_V_ocv` 路径选择: Path B + dual brentq + bracket 增强

子阶段 2 第一次实施(单 brentq 锚定 V_max 端)在自检测试中暴露
`spec X0 + paper Eq. 22 SEI 减项使 V_min 端 X_NE ≈ -0.008` 的非物理
状态:`brentq window` 不能假设 dQ=0 ↔ V_min。

第二次修订改用 **dual brentq** (V_min + V_max 各一次),对齐
`scripts/fit_electrode_balance.py::_calibrate_soc_bounds` 的成熟做法,
并新增 `_bracket_dQ_for_voltage(target_V)` 辅助函数 — 41 点物理可行
dQ 域采样找首个 sign-change pair,给 brentq 提供干净 bracket,
**避免 `f(a)*f(b)>0` 错误**。

权衡: FIT-1 的 _calibrate_soc_bounds 是 fresh-cell 一次性 calibration,
不需要 bracket 增强;IC analysis 优化器会把 (LAM_PE, LAM_NE, LLI) 推到
alawa regime 边界,brentq window 必须 fail-fast 到整条 inf 残差。这是
对 FIT-1 框架的鲁棒性增强,不是抽象重复。性能实测 ~3.9 ms/eval (含
spec re-load),远低于 SPEC <10 ms/eval 阈值。

子阶段 2 v2 进一步抽出 `_fresh_state_model_capacity_Ah(art)` 复用同一
dual-brentq + bracket 路径(fail-safe fallback C_nominal),让
`heuristic_initial_guess` 不再依赖外部猜测的 fresh-cell 容量。这一抽离
也是 Step 0 reconnaissance "查清现有原语再决定要不要新增" 的延伸应用。

#### 20.3.2 fit_quality 阈值的文献依据

CLI quality gating 用四个阈值:

```
RMSE_FAIL_V    = 0.020   # >20 mV → ICA-E003 (exit 102)
RMSE_MARGINAL_V= 0.015   # 15-20 mV → ICA-W001 (exit 103)
R2_FAIL        = 0.99    # <0.99 → ICA-E003
R2_MARGINAL    = 0.999   # 0.99-0.999 → ICA-W001
```

依据链:

- `docs/PARAMETER_SOP.md §3.2` 的 `ic_analysis_fit_quality` 字段约定
  "<15 mV 为可接受",对应 marginal 下限 15 mV
- `docs/PARAMETER_SOP.md` 中 FIT-1 的 RMSE_FAIL=50 mV 是单调强约束,
  IC 分析针对 IR 已扣除的 C/40 平台,残差应远更小,故 FAIL 收紧到 20
  mV(2.5 倍 marginal 余量,经验门槛但与 Birkl 2017 IC 分析典型残差
  数量级一致)
- R² 0.99 / 0.999 双阈值参照 Phantom LAM 2024 IC 分析综述对 stage
  feature 清晰度的判别 — 0.99 以下意味着主峰位置都拟合不准,0.999 以上
  才能对 LAM_NE 这类弱可识别模式给出有意义的协方差

阈值不是 paper Mmeka 2025 直接给定值,而是 SPEC 起草时对 SOP §3.2
+ Birkl 2017 + Phantom LAM 2024 三处文献综合推导。本次 v0.5.2 落地
仅消费这些阈值,未做调校。

#### 20.3.3 IC 分析输出**不回写 spec**

与 FIT-1/FIT-2 的关键工程差异: IC 分析产出 `(LLI, LAM_PE, LAM_NE)`
**不是 SSoT 参数**,是某个具体 RPT 数据点的诊断结果。多个 RPT 会产生
多组 DMs(对应不同 EFC / 时间),写回 spec 会要么覆盖既有值、要么需要
引入时间索引数组扩展 schema。

决策:IC 分析输出独立 JSON (per RPT),供下游 FIT-4a/4b 消费 — FIT-4
的拟合输入是 (EFC, LLI(EFC), LAM_PE(EFC), LAM_NE(EFC)) 时间序列,
聚合多 JSON 是 FIT-4 任务包的职责,不是 IC 分析的。

这与 SPEC §3 接口约定一致 (输出独立 JSON,schema 含 fit_quality +
metadata 而非 spec writeback path),也是 R7 工作流约束精神的体现:
spec 字段只能由 FIT-X 回写,而 IC 分析在 FIT-X 编号体系中**没有
对应位置**(SOP-4.5 是 FIT-4 的前置数据准备,不是独立 FIT 步骤)。

### 20.4 §十九 元教训正面应用 + v0.5.0 R8 漏项暴露

#### 20.4.1 语义辐射目标主动扫描 — 无新失察

§十九 提出"R5 扫描阶段需引入语义辐射目标"概念。本任务在 SPEC 落地前
做了三轮主动扫描:

1. **错误码 scope** (子阶段 1): grep `error_codes.schema.json::scope.enum`
   全部已知 scope,确认 ICA 是**新 scope** 而非已有 FIT4A/4B 等的
   sub-scope,registry 与 runbook §X 同步插入新条目。
2. **目录树同步** (子阶段 5): grep README + QUICKSTART + docs/CLAUDE.md
   三文件,确认 87 用例 / FIT-1/FIT-2/IC 三处"已实现"标注同步。
3. **派生层一致性** (子阶段 5): grep `ic_analysis.py` / `fit_ic_to_dms`
   / `test_ic_analysis.py` 出现次数,符合任务包指标 (≥2/≥2/==1)。

无新派生层失察,§十九 元教训本次任务正面应用。

#### 20.4.2 v0.5.0 R8 验收漏项暴露

子阶段 5 同步 README 时发现:v0.5.0 release (FIT-2 落地) 把
`libquiv_aging/relaxation_fitting.py` 入库,但 README 与 docs/CLAUDE.md
的 `libquiv_aging/` 目录树**未追加该文件**。任务包指令"在
relaxation_fitting.py 后插入 ic_analysis.py 一行"隐含假设其已存在,
位置坐标无法落实。

判断:**同补 v0.5.0 漏项与本子阶段新增**,符合 docs/CLAUDE.md
"Claude Code 协作规范" 超范围审查段(警告呈现 + 保守修复)。

根因: R8 验收 grep 模板只检查"文件名是否在 README 出现",未检查"目录
树位置是否准确"。`relaxation_fitting.py` 在 v0.5.0 commit 中只被
工作流概览段提及一次(`scripts/fit_rc_transient.py` 与
`libquiv_aging/relaxation_fitting.py` 并列),未被 libquiv_aging/ 目录树
段独立列出。"出现 ≥1 次"通过了 R8 验收,但目录树仍不完整。

留待未来 R8 治理 patch 处理:把 R8 grep 模板扩展为"目录树位置 + 文件
名出现"双重检查。本任务不动 R8 规则文本,仅记录该弱点。

### 20.5 错误码 ICA scope 引入

ICA scope 引入是本任务首个事实层动作,先于代码:

- `error_codes.schema.json::scope.enum` 追加 `ICA`,
  `patternProperties` regex 已是 `^ICA-(E\\d{3}|W\\d{3})$` 兼容形式,
  无需扩展
- `error_codes_registry.json` 添加 ICA-E001 (input validation, exit 100)
  / E002 (optimizer failure, 101) / E003 (quality fail, 102) / W001
  (quality marginal, 103) / W002 (bounds_hit, 104)。其中 ICA-E002
  cross_refs 在子阶段 1 写为 TODO 占位,子阶段 3 CLI 落地后回填 →
  `scripts/fit_ic_to_dms.py`
- `docs/07_offline_runbook.md` §X 新增 ICA 子段,与 registry 11 字段
  互锁 (trigger / consequence / cross_refs / script_behavior /
  immediate_action / followup / escalation 等)
- `08_consultation_protocol.md` 观测笔记模板 escalation 字段已是
  通用占位,不需 ICA-specific 调整 (符合 R6 "registry 是事实层,
  其他文档是派生层"原则)

R6 因果链 (registry → runbook → 脚本 raise) 未被绕过。CLI exit code
100/101/102/103/104 与 registry 完全对齐,优先级 104 (W002) > 103
(W001) > 0 (pass) 在 CLI 主流程显式实现。

### 20.6 子阶段 4 T4 阻塞与 paper Fig. 6c 物理印证

任务包 §4.1 T4 写作 "sum(DMs) ≈ cap_loss within 10%",子阶段 4 实施时
3 个 case 实测 ratio 1.66 / 2.29 / 2.97 — 偏差是 2-3 倍而非 ±10%,远
超 2σ 容差。停下报告。

用户回顾 paper Mmeka 2025 §"Cycle degradation" 实测 (143 EFC):

```
sum(DMs) = LAM_PE 0.08 + LAM_NE 0.04 + LLI 0.13 = 0.25 Ah
measured cap_loss = 0.11 Ah → ratio 2.27
```

paper 原文显式警告:

> "the sum of the degradation modes (0.25 Ah) exceeds the measured
> capacity loss at the full-cell level (Fig. 6a) ... highlighting the
> nonlinear relationship between various degradation modes and overall
> capacity loss."

实测 ratio 与 paper 实验同量级 → forward model **物理正确**,任务包
T4 断言"sum 守恒"是物理直觉错误。

T4 改写为 cap_loss self-consistency: 反演 DMs 走同一 forward model
得到 cap_loss_hat,与真值 cap_loss_truth (同 forward 算出) 比较,
rel_error < 10%。捕捉"DMs 内部分配错误"类 bug 比 sum 等式更严格,
与 T2 (单点估计) / T3 (协方差) 语义不重叠。

paper Fig. 6c 现象作为"sum(DMs) ≠ cap_loss 非线性关系"暂记录到测试
docstring 与本节,**不**升级到 `PARAMETERS.json::critical_review_findings`
作为新 N 条目 — 决策延迟到 v0.6+ patch (见 §20.7)。

### 20.7 决策记录与延迟登记项

#### 20.7.1 R9 候选 #5 (实证驱动校验) 与 #4 合并

§十九 已有 R9 候选 #4 "R5 扫描阶段语义辐射目标显式补充"。子阶段 2
第一次单 brentq 失败 + 子阶段 4 T4 阻塞,共同暴露另一类问题:**起草
权威指令 (web chat 算法决策、任务包测试断言) 时,必须基于实证而非
概念推导**。子阶段 2 单 brentq 是 web chat 端凭 paper 公式推导的算法
方案,实测 X_NE 越界后改为 dual brentq;子阶段 4 T4 是任务包凭物理
直觉写的"sum 守恒",实测 ratio 2-3x 后改为 self-consistency。

判断: R9 候选 #5 与 #4 在精神上同源 — 都是"修改/起草权威指令时,必须
基于实证而非概念推导"。建议合并为统一的"实证驱动校验" R9 候选,等
**第二次类似事件再触发制度化**。本任务正面应用 (Step 0 reconnaissance
+ 子阶段 2 实测决策 + 子阶段 4 阻塞报告),不构成新事件。

#### 20.7.2 paper Fig. 6c critical_review 升级延迟

paper Fig. 6c "sum(DMs) ≠ cap_loss 非线性关系"作为 N 条目登记到
`PARAMETERS.json::critical_review_findings` 的优势:

- paper 自己警告的已知现象,不是文献争议(高可信度)
- 直接影响 FIT-4a/b 拟合策略物理预期(下游消费者需感知)
- 与现有 N1 (OFS 弱可识别性) 同类(类型对齐)

倾向**升级**,但本任务不做。理由:

- v0.5.2 任务包明确 §6 "不修改 critical_review_findings"
- 升级动作走 R1 (PARAMETERS.json) + R5 (派生层扫描)流程,需独立的
  扫描-确认-编辑-验收四步,不能搭便车塞进 v0.5.2
- 当前唯一已知消费方 (FIT-4) 尚未实施,登记后验证路径不可达,会成为
  无人维护的死字段

留给 v0.6.0 FIT-4 任务包做并入处理 (FIT-4 启动时再补登 N 条目 +
fit_steps::FIT-4 的 cross_refs 引用),同时也避免本任务变成
"docs/PARAMETERS.json patch + IC 分析" 的混合任务包。

#### 20.7.3 `libquiv_aging_version` 硬编码

`scripts/fit_ic_to_dms.py` 当前用 `LIBQUIV_AGING_VERSION = "1.0.0"`
硬编码常量写入 JSON metadata。子阶段 3 已识别这是 release 不会自动
跟随的工程债务,推迟到 v0.6+ 改用
`importlib.metadata.version("libquiv-aging")`。本任务不修,因为:

- 修改触发 schema 兼容性确认 + 跨脚本复用 (FIT-1/FIT-2 是否也该改?)
- 当前 "1.0.0" 在 JSON 中可被消费方识别为"未自动更新版本"信号,不影响
  IC 分析功能

#### 20.7.4 R8 grep 模板弱点

§20.4.2 暴露的 R8 grep 模板"目录树位置 + 文件名出现"双重检查不足。
留给未来 R8 治理 patch 做正式条款,本任务不动 R8 规则文本(任务包
明确不在 v0.5.2 范畴)。

### 20.8 经验留痕

本次 IC analysis 落地是 v0.4.2 SPEC 提升 (§十七) 后第一次真正兑现
frozen SPEC 契约,流程上的几个验证:

- frozen SPEC 给出**接口契约**(参数定义 / 误差码 scope / JSON schema)
  让八子阶段任务包能按部就班分发,无需在实施中反复回头改 SPEC
- Step 0 reconnaissance 的"先扫码再写代码"是 §十九 元教训的实施级
  应用 — 把"实证驱动"从 R5 文档协议向下传到代码协议
- 子阶段 2 自检测试发现 X^0 引用约定差异 (paper SOC=1 reference vs
  spec V_min reference),通过 docstring 显式记录两套约定;这是
  v0.4.2 SPEC 提升预留的 "X^0 convention clarification" 占位条款
  (frozen SPEC 当时只标注"两个文献口径,实施时决断")在落地时的兑现
- 子阶段 4 T4 阻塞 → paper Fig. 6c 印证 → cap_loss self-consistency
  改写 是一个完整的"任务包描述错误 → 实证发现 → 测试改写 + 决策记录
  + 延迟登记"链条,可作为未来类似阻塞的样本

下一个值得固定的工作流: v0.5.2 完成后做一次类似 §十九 的"全状态
审计",检索 SPEC_ic_analysis 在所有派生文档中的引用是否完整、错误
码 scope 表是否与代码 raise 点一一对应、`heuristic_initial_guess`
等公开 API 在 README/CLAUDE.md 是否被遗漏。这一审计在本任务包子阶段
5 + 子阶段 7 已部分覆盖,作为 release 最后的 sanity check 值得固化为
默认动作 (§十九 §19.6 已提议,本任务再次应用)。

---

## 版本记录

| 日期 | 变更 |
| --- | --- |
| 2026-04-21 | 初版。汇总从工程建立到 `PARAMETERS.json v2.0` 和 `CRITICAL_REVIEW.md` 发布的全部关键决策。 |
| 2026-04-23 | 追加 §十。记录 air-gapped 三阶段分离、独立 error code registry、`--export-public` 人因分析三项架构决策。对应 tag `docs/v0.2.0-offline-workflow`。 |
| 2026-04-23 | 追加 §十一。v0.2.2 meta 教训制度化 (术语约定 / 破坏性命令清单 / Claude Code 协作规范), R5 验收阶段 git 条款扩展。详见 §十一。 |
| 2026-04-24 | 追加 §十二。v0.2.3 离线工作流落地: 从 air-gapped 假设迁移到内部 pip 镜像单轨制, 新增 `09_offline_bundle_guide.md` 与配套 scripts。 |
| 2026-04-24 | 追加 §十三。v0.2.4 清理整顿: 奥卡姆剃刀原则首次显式应用, 修正 08/error_codes_registry/09 三处过度工程。 |
| 2026-04-25 | 追加 §十四。v0.3.0 cell type 抽象层落地: 双 spec 架构 + model_versions 路由 + panasonic 兼容层。 |
| 2026-04-25 | 追加 §十五。v0.4.0 第一阶段: FIT-1 电极平衡拟合脚本落地, libquiv_aging/fitting.py 基础设施就位。 |
| 2026-04-25 | 追加 §十六。v0.4.1 R8 规则: README 与 release 同步, 工作流类别缺陷的修复机制。 |
| 2026-04-25 | 追加 §十七。v0.4.2 SPEC 提升: TODO_ic_analysis.md → SPEC_ic_analysis.md, 暴露 backlog 文档可见性盲点。 |
| 2026-04-26 | 追加 §十八。v0.5.0 FIT-2 RC 弛豫拟合落地: dispatch 模式准备升级路径, C6→C7 重映射, tau→R 双候选 + 歧义警告。 |
| 2026-04-26 | 追加 §十九。v0.5.1 派生层语义辐射修复: EXP-C deprecated for FIT-2, SPEC_ic_analysis Status 更新, PARAMETER_SOP §3.1/§3.3 同步, README 目录结构图 tests/ + scripts/ 段补齐。元教训: R5 扫描阶段需引入"语义辐射目标"概念。 |
| 2026-04-28 | 追加 §二十。v0.5.2 IC analysis 落地 (frozen SPEC 兑现): `libquiv_aging/ic_analysis.py` + `scripts/fit_ic_to_dms.py` + `tests/test_ic_analysis.py` (22 用例) + 错误码 ICA scope (E001/E002/E003/W001/W002)。三决策: Path B + dual brentq + bracket、fit_quality 阈值文献依据、不回写 spec。子阶段 4 T4 阻塞由 paper Fig. 6c "sum(DMs) ≠ cap_loss 非线性关系"印证 forward model 物理正确,T4 改写为 cap_loss self-consistency。R9 候选 #5 (实证驱动校验) 与 #4 合并,等第二次事件制度化。R8 grep 模板弱点 (v0.5.0 漏 relaxation_fitting.py 在目录树) 同步补齐。|
