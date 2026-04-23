# 离线 Runbook (Offline Runbook)

> 本文件由 `docs/error_codes_registry.json` 派生。正文可手工精修,
> 但 **trigger / consequence / cross_refs / script_behavior** 四项必须与
> registry 一致。不一致时以 registry 为准 (见 CLAUDE.md 核心规则 R6)。
>
> 所有条目禁止出现参数绝对数值: 触发阈值一律用量级表达 (例如 "缺失率量级 30%"
> 而非 "缺失率 > 32.4%")。这与 `docs/08_consultation_protocol.md` §2/§3 的
> 外带信息白名单保持一致。

---

## §0 使用说明

### 0.1 本文件适用场景

**适用**: 现场 (离线/air-gapped 区) 脚本报错或参数拟合出现异常时, 工程师按错误码
在本手册中查条目, 按"现场可选处置"做自我修复; 若仍无法解决, 才按 "何时升级到
在线咨询" 的指引, 用 `docs/08_consultation_protocol.md` §4 的观测笔记模板把
**非敏感元信息**外带到在线 Claude 对话。

**不适用**: 本手册不用于排查 pytest 测试红灯, 不用于说明论文物理细节 (见
`docs/CRITICAL_REVIEW.md`), 不用于代替 SOP (见 `docs/PARAMETER_SOP.md`)。

### 0.2 错误码命名规范

```
{SCOPE}-{LEVEL}{NUMBER}
  SCOPE  ∈ {ENV, DATA, FIT4A, FIT4B, FIT4C, SOLVE, IDENT}
  LEVEL  ∈ {E (error 停机), W (warn 继续), I (info 提示)}
  NUMBER = 3 位数字, 每个 (SCOPE, LEVEL) 组合内部唯一, 一经发放不复用
```

示例: `FIT4A-E003` = FIT-4a 作用域第 3 个 error 级错误。

`deprecated` 状态的条目必须保留编号不删除, 并在 `deprecated_note` 中指向替代码。

### 0.3 与 registry 的关系

本文件的每个条目对应 `docs/error_codes_registry.json::codes::{CODE}` 的一条记录。
registry 是事实层 (fact layer), 本文件是解释层 (explanation layer)。任何修改必
须先改 registry、再改本文件、再改 `scripts/` 中的 error raise 点 —— 顺序由
CLAUDE.md R6 强制。

### 0.4 条目正文格式

每条按如下固定骨架展开 registry 字段:

- **触发条件** ← registry.trigger
- **物理/方法学后果** ← registry.consequence
- **权威文档交叉引用** ← registry.cross_refs (bullet list)
- **现场可选处置** ← registry.remediation (numbered list)
- **脚本应当行为** ← registry.script_behavior (退出码 + action + 打印编号)
- **何时升级到在线咨询** ← registry.escalation (指向 08_consultation_protocol.md 对应章节)

---

## §1 环境与依赖类错误 (ENV)

### ENV-E001: Conda 环境哈希与冻结环境不匹配

**触发条件**
当前激活环境的包集合哈希与 `environment-frozen.yml` 中记录的哈希不一致; 任意一
个被模型代码 import 的核心包 (numpy/scipy/pandas/jsonschema) 主次版本号偏离基
准即视为不匹配。

**物理/方法学后果**
数值求解器行为、BDF 步长控制、插值器实现可能随版本漂移, 导致老化轨迹与论文
Fig. 7 基准偏差无法归因到科学变量, 污染所有下游拟合的可复现性。

**权威文档交叉引用**
- `QUICKSTART.md §环境激活`
- `docs/01_setup_guide.md §conda 环境`
- `environment.yml`
- `environment-frozen.yml`

**现场可选处置**
1. 先确认 `conda env list` 输出中确为 libquiv-aging 环境被激活。
2. 若版本偏离 minor 级, 用 `conda env update -f environment-frozen.yml --prune` 回滚。
3. 若偏离 major 级, 重新 `conda env create` 创建干净环境。
4. 记录偏离原因 (系统级升级 / 手工 pip / OS 层 brew 污染) 到 `runs/{run_id}/env.diff`。

**脚本应当行为**
exit code 10, refuse, 打印本条目编号 (`[ENV-E001]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 3 — 环境漂移`。

---

## §2 数据契约类错误 (DATA)

### DATA-E001: RPT CSV 列名或单位不符 SOP §3.2

**触发条件**
`experiments/EXP-{E,F,G}/` 下任一 `cell_*_rpt.csv` 缺失 `PARAMETER_SOP.md §3.2`
表格中列出的必填列, 或列单位头 (Ah / mΩ / K / ISO8601) 与 SOP 不一致。

**物理/方法学后果**
FIT-4a/b 在读取阶段静默插入 NaN 或做错误单位换算, 后果是 k_SEI_cal 量级错误被
当成拟合结果报告, 下游所有老化预测失真。

**权威文档交叉引用**
- `docs/PARAMETER_SOP.md §3.2 老化实验数据 (每次 RPT 一行)`
- `docs/PARAMETERS.json::experiments::EXP-E`
- `docs/PARAMETERS.json::experiments::EXP-F`
- `docs/PARAMETERS.json::experiments::EXP-G`

**现场可选处置**
1. 用 `pandas.read_csv(...).dtypes` 比对 §3.2 表格, 打印首个不匹配列。
2. 如只是单位错 (Ohm vs mΩ), 在加载侧补 1e3 缩放并写回, 不要在拟合侧修。
3. 如缺列, 回溯实验原始导出脚本, 重新生成。

**脚本应当行为**
exit code 20, refuse, 打印本条目编号 (`[DATA-E001]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 1 — 数据契约违规`。

### DATA-E002: .dat 文件 x 列非单调或越界

**触发条件**
`libquiv_aging/data/*Alawa.dat` 或用户替换的半电池文件, x 列存在非严格单调递
增段, 或任一 x 值落出 `[0, 1]` 区间。

**物理/方法学后果**
HalfCellThermo 插值将返回未定义行为 (重复 x 处 dH/dS 斜率奇异或插值器抛异常),
下游 V_PE_0 / V_NE_0 曲线被污染, LR/OFS 拟合多解。

**权威文档交叉引用**
- `docs/PARAMETER_SOP.md §3.1 Fresh cell 表征数据 (alawa 格式)`
- `libquiv_aging/lookup_tables.py::HalfCellThermo`
- `docs/PARAMETERS.json::parameters::V_PE_0_curve`
- `docs/PARAMETERS.json::parameters::V_NE_0_curve`

**现场可选处置**
1. 先 `awk '!/^*/ {print $1}' file.dat | sort -c` 定位首个逆序行。
2. 若是实验合并时 x 方向连接错, 用 `build_halfcell_dat.py` 重新生成。
3. 若是数值漂移导致极短反转, 保留原始 CSV, 修正脚本, 不要手工改 .dat。

**脚本应当行为**
exit code 21, refuse, 打印本条目编号 (`[DATA-E002]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 1 — 数据契约违规`。

### DATA-E003: 电阻 .mat 形状不是 1001×2001

**触发条件**
`libquiv_aging/data/*.mat` 中 `RsAlawa` / `RNEAlawa` / `RPEAlawa` 任一矩阵形状
与论文约定 1001×2001 不符。

**物理/方法学后果**
ResistanceLUTs 的 `RegularGridInterpolator` 会按错误轴解释 `(I, X)` 顺序, 导致
R_NE_0 派生值错一个量级, 全生命周期 IR 预测失真。

**权威文档交叉引用**
- `docs/PARAMETER_SOP.md §2.2 电阻 LUT → .mat`
- `libquiv_aging/lookup_tables.py::ResistanceLUTs`
- `docs/PARAMETERS.json::parameters::R_s_LUT`
- `docs/PARAMETERS.json::parameters::R_NE_LUT`
- `docs/PARAMETERS.json::parameters::R_PE_LUT`

**现场可选处置**
1. 在 `build_resistance_mat.py` 中打印矩阵 shape 做断言。
2. 重新运行 GITT 到 LUT 转换, 确认 I 轴 (2001 点) 与 X 轴 (1001 点) 未互换。
3. 若来自 MATLAB 原版, 确认 `scipy.io.loadmat` 未做转置。

**脚本应当行为**
exit code 22, refuse, 打印本条目编号 (`[DATA-E003]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 1 — 数据契约违规`。

→ 数据契约违规的统一外带模板见 `docs/08_consultation_protocol.md §4`。

---

## §3 FIT-4a 相关错误 (FIT4A)

### FIT4A-E001: Tier I/II/III 参数存在未填 placeholder

**触发条件**
进入 FIT-4a 前, 参数工厂中任一 Tier I/II/III 参数 (`LR`, `OFS`, `C1`, `C2`,
`fractionR*toRs`, 半电池 `.dat`, 电阻 `.mat`, `R_NE_0`) 仍为 `PARAMETERS.json`
的 `paper_value_NCA_G` 默认或显式 placeholder。

**物理/方法学后果**
日历拟合的 `k_SEI_cal` / `R_SEI` / `gamma_PE` 被迫去补偿 fresh-cell 表征的误差,
产出的 IV_calendar 参数在新体系下不可迁移, 还会掩盖 Tier II/III 的实测缺口。

**权威文档交叉引用**
- `docs/PARAMETER_SOP.md §四 FIT-4a 前置条件`
- `docs/PARAMETERS.json::fit_steps::FIT-4a`
- `docs/CLAUDE.md 规则 R2`

**现场可选处置**
1. 运行 `python scripts/check_parameter_consistency.py` 获取未填参数名单。
2. 按 SOP §五 方案 A/B/C 判断是否可用 NCA/G 默认做临时 placeholder, 并记录审计标签。
3. 在不可替代的 Tier II 缺失情况下 (如半电池 OCV), 不进入 FIT-4a, 回到 SOP-2。

**脚本应当行为**
exit code 30, refuse, 打印本条目编号 (`[FIT4A-E001]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 2 — 拟合前置条件不足`。

### FIT4A-E002: EXP-E 温度点过少, E_a 不可识别

**触发条件**
EXP-E 数据集覆盖的独立储存温度数 < 3, 但参数向量仍把 `E_a_SEI` 作为自由量。

**物理/方法学后果**
Arrhenius 斜率退化为一个点或两点线性, `E_a` 与 `k_SEI_cal` 完全共线, 最小化器
会在两者之间自由分摊误差, 返回看似收敛但统计不可识别的结果。

**权威文档交叉引用**
- `docs/PARAMETER_SOP.md §四 FIT-4a: 单温度策略`
- `docs/PARAMETERS.json::experiments::EXP-E`
- `docs/PARAMETERS.json::parameters::E_a_SEI`

**现场可选处置**
1. 把 `E_a_SEI` 固定到 Reniers 2019 范围 (50–60 kJ/mol 量级), 在拟合配置里从
   free 改为 fixed。
2. 记录固定值来源到 `runs/{run_id}/fit_config.json`。
3. 在下次老化实验设计时补齐 ≥3 个温度点。

**脚本应当行为**
exit code 31, refuse, 打印本条目编号 (`[FIT4A-E002]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 2 — 拟合前置条件不足`。

### FIT4A-E003: IR 列缺失率过高

**触发条件**
EXP-E 的 `cell_*_rpt.csv` 中 `R_IR_mOhm` 列缺失率量级达到 30% 或以上 (即约 1/3
的 RPT 没有测 IR)。

**物理/方法学后果**
`R_SEI` 的唯一识别性依赖 IR(t) 轨迹的连续采样, 大面积缺失会让最小化器靠剩余
LLI/LAM_PE 残差反推, 落入 S2 (V_LP_eq) 与 C3 (R_s 非退化) 的假设陷阱, 参数失去
物理意义。

**权威文档交叉引用**
- `docs/PARAMETER_SOP.md §二.3 各步骤在不同实验中的必要性`
- `docs/PARAMETERS.json::experiments::EXP-E::CRITICAL`
- `docs/CRITICAL_REVIEW.md C3 R_s 非退化`

**现场可选处置**
1. 若缺失集中在某段时间 (如设备维护期), 在 `fit_config` 中明确屏蔽该时间窗。
2. 若缺失随机散布, 把 `R_SEI` 从 free 改为 fixed=paper_value (0.66 量级) 并记录。
3. 补测 IR (脉冲或 EIS) 是最优路径。

**脚本应当行为**
exit code 32, refuse, 打印本条目编号 (`[FIT4A-E003]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 2 — 拟合前置条件不足`。

### FIT4A-E004: SOC 覆盖不全, k_SEI_cal 与 k_LAM_PE_cal 共线

**触发条件**
EXP-E 的储存 SOC 点全部集中在 SOC > 0.5 或全部 SOC < 0.5 之一的半段。

**物理/方法学后果**
SEI 速率对 SOC 的依赖与 LAM_PE 速率对 SOC 的依赖在单半段内形状相近, 两个 k 参
数线性相关, 拟合器无法分离它们; 估计值会随初值移动, 不具识别性。

**权威文档交叉引用**
- `docs/PARAMETER_SOP.md §四 FIT-4a: DOE 覆盖`
- `docs/PARAMETERS.json::experiments::EXP-E`
- `docs/PARAMETERS.json::parameters::k_SEI_cal`
- `docs/PARAMETERS.json::parameters::k_LAM_PE_cal`

**现场可选处置**
1. 冻结 `k_LAM_PE_cal` 至 `paper_value_NCA_G` 作为 placeholder 并打印审计注释。
2. 在下一批 EXP-E 扩充中补上另一半段的 SOC 点 (至少一个 SOC < 0.3 或 > 0.7)。
3. 不要试图用更复杂的正则化代替 DOE 覆盖。

**脚本应当行为**
exit code 33, refuse, 打印本条目编号 (`[FIT4A-E004]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 2 — 拟合前置条件不足`。

---

## §4 FIT-4b 相关错误 (FIT4B)

### FIT4B-E001: 检测到 FIT-4a 参数被解冻

**触发条件**
进入 FIT-4b 前, 参数向量里出现任一属于 FIT-4a 产出的参数 (`k_SEI_cal`,
`k_LAM_PE_cal`, `gamma_PE`, `R_SEI`, `E_a_SEI`) 处于 free 状态。

**物理/方法学后果**
直接违反 CLAUDE.md R2 老化参数拟合顺序。`R_SEI` 若在循环数据上重新拟合会与
plating/LAM 的 IR 贡献耦合, 产生非物理多解, 回归到本工程 2026-04 前的已废弃状态。

**权威文档交叉引用**
- `docs/CLAUDE.md 规则 R2`
- `docs/PARAMETER_SOP.md §四 FIT-4b: 关键设置`
- `docs/PARAMETERS.json::fit_steps::FIT-4b::parameters_frozen`
- `docs/MIGRATION_NOTES.md §三 规则 R2`

**现场可选处置**
1. 在 `fit_cycle_preknee.py` 入口打印冻结清单与自由清单, 用户目视核对。
2. 把 `fit_config` 中 FIT-4a 产出参数显式标 `frozen: true`。
3. 拒绝执行, 不允许通过 `--force` 绕过。

**脚本应当行为**
exit code 40, refuse, 打印本条目编号 (`[FIT4B-E001]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 4 — R2 顺序违规`。

### FIT4B-E002: k_LP 未被置零

**触发条件**
进入 FIT-4b 主循环前, `PlatingParameters.k_LP` 不是恒等 0 (含小量扰动)。

**物理/方法学后果**
FIT-4b 的 LLI 残差里混入了 plating 贡献, `k_SEI_cyc` 估计被向上推, 后续 FIT-4c
对 `k_LP` 的一维搜索变成两参数共线问题; 实际体现是 knee 预测时机显著偏早。

**权威文档交叉引用**
- `docs/CLAUDE.md 规则 R2`
- `docs/PARAMETER_SOP.md §四 FIT-4b: 关键设置`
- `docs/PARAMETERS.json::fit_steps::FIT-4b`

**现场可选处置**
1. 在脚本进入 minimize 前显式 `cell.aging.plating.k_LP = 0.0`。
2. 在 `fit_config` 里把 plating 整段标记 disabled。
3. 拟合完再把 `k_LP` 留给 FIT-4c。

**脚本应当行为**
exit code 41, refuse, 打印本条目编号 (`[FIT4B-E002]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 4 — R2 顺序违规`。

### FIT4B-E003: 循环数据尚未进入 plateau, knee 前数据不足

**触发条件**
EXP-F 的最大 EFC 量级明显低于 paper 预期的 pre-knee 段上限 (NCR18650B 约 O(100)
EFC), 或 LLI 轨迹尚未脱离初始 SEI 快速段进入线性区。

**物理/方法学后果**
cycle aging 的三个 k 参数此时仍在被 SEI 成膜瞬态主导, 拟合结果会把瞬态误读为
长期速率, 外推到 knee 时严重低估老化速率。

**权威文档交叉引用**
- `docs/PARAMETER_SOP.md §四 FIT-4b: 数据要求`
- `docs/PARAMETERS.json::experiments::EXP-F`

**现场可选处置**
1. 继续运行 EXP-F 直到 LLI 斜率变化量级降到原初始段的 1/10 以下。
2. 若工期受限, 冻结 `k_LAM_NE_cyc` 到 `paper_value` 并缩小自由度。
3. 禁止用 `ACC_FACTOR` 人为加速到 plateau, 会污染温度假设。

**脚本应当行为**
exit code 42, refuse, 打印本条目编号 (`[FIT4B-E003]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 2 — 拟合前置条件不足`。

---

## §5 FIT-4c 相关错误 (FIT4C)

### FIT4C-E001: 除 k_LP 外任一参数未冻结

**触发条件**
进入 FIT-4c 前, 除 `PlatingParameters.k_LP` 之外的任意一个老化参数 (任一
FIT-4a/4b 产出) 处于 free。

**物理/方法学后果**
FIT-4c 一维搜索退化为多维非凸问题, 违反 CLAUDE.md R2 第三条, 产出的 `k_LP` 不
能被解读为论文意义下的 knee 定位参数。

**权威文档交叉引用**
- `docs/CLAUDE.md 规则 R2`
- `docs/PARAMETER_SOP.md §四 FIT-4c: 关键设置`
- `docs/PARAMETERS.json::fit_steps::FIT-4c::parameters_frozen`

**现场可选处置**
1. 在 `fit_knee.py` 入口做 sweep, 把除 `k_LP` 外一切老化参数显式标 frozen。
2. 打印冻结清单做人工核对。
3. 拒绝执行, 不允许通过 `--force` 绕过。

**脚本应当行为**
exit code 50, refuse, 打印本条目编号 (`[FIT4C-E001]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 4 — R2 顺序违规`。

### FIT4C-E002: 数据未跨越 knee, k_LP 不可识别

**触发条件**
EXP-G 的容量轨迹尚未落到 knee 下游 (典型量级: 容量尚未降至初始 ~80% 以下),
或总 EFC 低于 paper 预期 knee 位置的 1/2。

**物理/方法学后果**
knee 位置的判别统计依赖 `capacity(EFC)` 曲线二阶导出现极值, 数据不跨越 knee 时
这个极值不存在, `minimize_scalar` 会返回搜索边界值, 被误解释为 `k_LP` 拟合结果。

**权威文档交叉引用**
- `docs/PARAMETER_SOP.md §四 FIT-4c: 数据要求`
- `docs/PARAMETERS.json::experiments::EXP-G`
- `docs/PARAMETERS.json::parameters::k_LP`

**现场可选处置**
1. 继续 EXP-G 直至容量跌入 knee 下游。
2. 不要外推: 在 knee 未出现前把 `k_LP` 保持 `paper_value` placeholder。
3. 若是 `ACC_FACTOR` 造成的假 knee, 关闭 `ACC_FACTOR` 再评估。

**脚本应当行为**
exit code 51, refuse, 打印本条目编号 (`[FIT4C-E002]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 2 — 拟合前置条件不足`。

---

## §6 数值求解器类错误 (SOLVE)

### SOLVE-E001: scipy solve_ivp BDF 积分失败

**触发条件**
任一 `cell.CC/CV/CP` 调用返回的 `OdeResult.status < 0`, 即 BDF 在剩余步长内无法
收敛或遇到事件函数异常。

**物理/方法学后果**
积分失败意味着 DAE 降为 ODE 的 Newton 内层在某个时刻发散, 后续状态变量不再可
信; 若被静默忽略, 拟合器会把数值失败当作物理信号。

**权威文档交叉引用**
- `docs/MIGRATION_NOTES.md §二 代码层 (solve_ivp BDF + Newton + brentq)`
- `libquiv_aging/cell_model.py::EquivCircuitCell 积分主循环`

**现场可选处置**
1. 打印 `result.message` 与 `t_events`, 定位首个失败时刻。
2. 检查失败点附近 V/I 是否越出 `[V_min, V_max]`: 若越界应回退到 event 驱动的
   `break_criterion`。
3. 把 `rtol` 下调一个量级重试, 同时确保 `atol` 与状态量纲匹配。

**脚本应当行为**
exit code 60, refuse, 打印本条目编号 (`[SOLVE-E001]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 5 — 求解器数值异常`。

### SOLVE-E002: 代数约束 Newton 与 brentq 兜底均失败

**触发条件**
`solve_algebraic_constraint` 里 Newton warm-start 失败后, brentq 兜底在给定括号
内无符号变化或二分到达迭代上限仍未达到 `xtol`。

**物理/方法学后果**
意味着某个工况点下 (I, V, SOC) 代数耦合没有实解, 物理上对应电池不能同时满足
CC/CV 设定与 OCV+R 约束; 继续仿真会产生非物理的状态跳变。

**权威文档交叉引用**
- `docs/MIGRATION_NOTES.md §二 代码层 (Newton warm-start + brentq)`
- `libquiv_aging/cell_model.py`

**现场可选处置**
1. 检查被调模式: CP 在极低 SOC 下容易无解, 应改用 CC 收尾。
2. 确认 `R_s_LUT` 与 `V_max/V_min` 不矛盾 (若 IR·I > V_max-V_OCV 则 CC 充电无解)。
3. 缩小时间步, 让上一步已知解为下一步 warm-start 提供更近初值。

**脚本应当行为**
exit code 61, refuse, 打印本条目编号 (`[SOLVE-E002]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 5 — 求解器数值异常`。

---

## §7 可识别性警告 (IDENT)

> 本节三条警告码 (IDENT-W001/W002/W003) 当前 status 为 draft。
> 它们的 trigger 条件和阈值是基于理论预判的占位规格, 尚未在
> 实际 fit 脚本中验证。P1-B 实施时会据实际代码路径修订。
> 若在当前状态下遇到可识别性疑问, 按 08_consultation_protocol.md
> 走跨 air-gap 咨询, 不要依赖本节的具体阈值数值。

### IDENT-W001: Hessian 条件数量级偏大

**触发条件**
任一 FIT-4* 收敛后, 数值估计的 Hessian 条件数量级 ≥ 1e8。

**物理/方法学后果**
参数协方差矩阵病态, 个别自由度在最小化面上几乎无曲率; 报告出的最优值在数值噪
声放大后无法被下一批数据复现, 误差棒不可信。

**权威文档交叉引用**
- `docs/CRITICAL_REVIEW.md 识别性小节`
- `docs/PARAMETERS.json::fit_steps::FIT-4a`
- `docs/PARAMETERS.json::fit_steps::FIT-4b`

**现场可选处置**
1. 打印特征向量, 定位贡献最大的线性组合; 通常指向
   `k_SEI_cal ↔ k_LAM_PE_cal` 或 `k_SEI_cyc ↔ k_LAM_PE_cyc`。
2. 冻结共线组合中物理先验更强的那个。
3. 扩充 DOE (额外温度/SOC/SOH 点) 是根本解。

**脚本应当行为**
exit code 70, warn, 打印本条目编号 (`[IDENT-W001]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 6 — 识别性警告`。

### IDENT-W002: 参数估计命中边界

**触发条件**
任一自由参数在最优化后距离其 search bound 的距离量级 < 1% of bound 宽度。

**物理/方法学后果**
边界命中表示数据不对该参数提供下推力, 真实最优值可能在 bound 之外, 或 bound 本
身误配。报告的估计值不具置信意义。

**权威文档交叉引用**
- `docs/PARAMETERS.json::fit_steps::FIT-3::search_bounds`
- `docs/PARAMETER_SOP.md §四 FIT-4a/4b: 拟合算法`

**现场可选处置**
1. 放宽对应 bound 一个量级, 重新拟合观察是否仍命中。
2. 若仍命中, 说明模型在该方向 misspecification 或数据不足, 参见 `IDENT-W003`。
3. 把命中事件写入 `runs/{run_id}/fit_report.md` 并标红。

**脚本应当行为**
exit code 71, warn, 打印本条目编号 (`[IDENT-W002]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 6 — 识别性警告`。

### IDENT-W003: 残差自相关系数量级接近 1 (模型 misspecification 迹象)

**触发条件**
对任一目标残差 (Capacity / IR / LLI / LAM) 计算 lag-1 自相关系数, 其量级接近 1
(≳ 0.9)。

**物理/方法学后果**
残差非白噪声表示模型未捕获某个系统性机制; 强行继续拟合会把该机制的缺失伪装
成 `k` 参数的偏差, 使估计值跨 cell 不可迁移。参考 `CRITICAL_REVIEW.md` C1
(isothermal) / C3 (R_s 非退化) 可能是源头。

**权威文档交叉引用**
- `docs/CRITICAL_REVIEW.md C1 / C3`
- `docs/PARAMETERS.json::scope_of_validity`
- `docs/PARAMETER_SOP.md §四 验收标准`

**现场可选处置**
1. 画残差 vs 时间 / EFC 图, 目视确认是单调漂移、周期、还是阶跃。
2. 按形状对照 `CRITICAL_REVIEW.md` 已识别机制列表。
3. 若跨 cell 一致, 上报给 `08_consultation_protocol` 进入在线讨论。

**脚本应当行为**
exit code 72, warn, 打印本条目编号 (`[IDENT-W003]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 6 — 识别性警告`。

---

## §A 附录: 错误码总表

> **此表由 `docs/error_codes_registry.json` 派生**
> (generator: 手工同步, 将来应改为 `scripts/render_runbook_appendix.py` 自动生成)。
> 如果总表与 registry 不一致, 以 registry 为准。

| 编号 | 作用域 | 级别 | 标题 | 退出码 | action | 状态 |
| --- | --- | --- | --- | ---: | --- | --- |
| ENV-E001 | ENV | E | Conda 环境哈希与冻结环境不匹配 | 10 | refuse | active |
| DATA-E001 | DATA | E | RPT CSV 列名或单位不符 SOP §3.2 | 20 | refuse | active |
| DATA-E002 | DATA | E | .dat 文件 x 列非单调或越界 | 21 | refuse | active |
| DATA-E003 | DATA | E | 电阻 .mat 形状不是 1001×2001 | 22 | refuse | active |
| FIT4A-E001 | FIT4A | E | Tier I/II/III 参数存在未填 placeholder | 30 | refuse | active |
| FIT4A-E002 | FIT4A | E | EXP-E 温度点过少, E_a 不可识别 | 31 | refuse | active |
| FIT4A-E003 | FIT4A | E | IR 列缺失率过高 | 32 | refuse | active |
| FIT4A-E004 | FIT4A | E | SOC 覆盖不全, k_SEI_cal 与 k_LAM_PE_cal 共线 | 33 | refuse | active |
| FIT4B-E001 | FIT4B | E | 检测到 FIT-4a 参数被解冻 | 40 | refuse | active |
| FIT4B-E002 | FIT4B | E | k_LP 未被置零 | 41 | refuse | active |
| FIT4B-E003 | FIT4B | E | 循环数据尚未进入 plateau, knee 前数据不足 | 42 | refuse | active |
| FIT4C-E001 | FIT4C | E | 除 k_LP 外任一参数未冻结 | 50 | refuse | active |
| FIT4C-E002 | FIT4C | E | 数据未跨越 knee, k_LP 不可识别 | 51 | refuse | active |
| SOLVE-E001 | SOLVE | E | scipy solve_ivp BDF 积分失败 | 60 | refuse | active |
| SOLVE-E002 | SOLVE | E | 代数约束 Newton 与 brentq 兜底均失败 | 61 | refuse | active |
| IDENT-W001 | IDENT | W | Hessian 条件数量级偏大 | 70 | warn | draft |
| IDENT-W002 | IDENT | W | 参数估计命中边界 | 71 | warn | draft |
| IDENT-W003 | IDENT | W | 残差自相关系数量级接近 1 | 72 | warn | draft |
