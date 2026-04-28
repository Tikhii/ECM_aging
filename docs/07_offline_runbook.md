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
  SCOPE  ∈ {ENV, DATA, FIT1, FIT2, ICA, FIT4A, FIT4B, FIT4C, SOLVE, IDENT}
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

### ENV-E002: pip install 失败: 依赖不在内部镜像索引中

**触发条件**
install_offline.sh 或 pip install -r requirements.txt 执行时,
pip 返回以下错误之一 (且内部镜像站可访问, 排除网络问题):
- "No matching distribution found for \<package\>"
- "Could not find a version that satisfies the requirement \<package\>"
- "Could not find a version that matches \<package\>==\<version\>"

**物理/方法学后果**
离线机无法完成 Python 环境重建, install_offline.sh 中途退出,
.venv 处于不完整状态。依赖链下游包可能连带失败。若强行用
`--no-deps` 跳过会产生缺失依赖的环境, 运行时报 ImportError,
但这是不推荐的处置方式。

**权威文档交叉引用**
- docs/09_offline_bundle_guide.md§五 (已知失败模式与应对)
- docs/PARAMETER_SOP.md§零 (环境重建流程)
- requirements.txt (锁定的版本清单)

**现场可选处置**
1. 确认内部镜像站可访问。在离线机上跑 `python -m pip config list -v`,
   确认 index-url 非空且指向内部镜像。若无配置, 联系 IT 部门修复 pip
   配置, 不要手工编辑 /etc/pip.conf 或用户级配置。
2. 确认缺失包在 PyPI 上真实存在且版本号正确。在联网机上跑
   `pip index versions <package>`, 与 requirements.txt 中锁定的版本对比。
   若 requirements.txt 中版本号有误 (如手工编辑造成), 回联网机重跑
   `scripts/build_requirements.sh` 覆盖生成 requirements.txt, commit 后
   拷到离线机重试。
3. 若包确实存在于 PyPI 但未进入内部镜像白名单: 记录缺失的包名和版本,
   向 IT 提交加入白名单申请, 等待确认入镜像后重试 install_offline.sh。

**不应采取的处置**
- 不应通过放松版本约束 (>= 代替 ==) 绕过错误, 会破坏环境一致性
- 不应用 --no-deps 跳过缺失包, 会让环境不完整
- 不应手工从 PyPI 下载 wheel 传入离线机 (受 50MB 传输限制和安全
  策略双重限制)

**脚本应当行为**
exit code 2, refuse, log 必须含完整 pip 错误输出和缺失包的名称与版本。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md§6` (措辞规范, 若 IT 协调或向联网 Claude
咨询时参考)。

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

## §3 FIT-1 相关错误 (FIT1)

### FIT1-E001: 材料 spec 中 dX 或 X0 字段未填

**触发条件**
执行 `fit_electrode_balance.py` 时, 材料 spec 中 `dX_PE_alawa`, `dX_NE_alawa`,
`X0_PE`, `X0_NE` 任一字段的 value 为 null (status 为 `pending_fit`)。

**物理/方法学后果**
FIT-1 内部循环依赖这些 fresh-cell 本征参数构造 X_PE(SOC) 和 X_NE(SOC) 映射。若任
一字段缺失, 内部循环无法建立, 拟合无意义。

**权威文档交叉引用**
- `docs/PARAMETER_SOP.md §一.2 SOP-1 创建 cell type 骨架`
- `schemas/material.schema.v1.json`
- `material_specs/panasonic_ncr18650b.material.json`

**现场可选处置**
1. 运行 `python -c "import json; s=json.load(open('material_specs/<cell>.material.json')); [print(k, s[k]['value']) for k in ['dX_PE_alawa','dX_NE_alawa','X0_PE','X0_NE']]"` 查看哪个字段为 null。
2. 对照 `PARAMETER_SOP.md §一.2 SOP-1`, 从 datasheet 或 alawa 默认值填入相应字段, status 设为 `datasheet`, `literature_default` 或 `convention`。
3. 重新执行 `fit_electrode_balance.py`。

**脚本应当行为**
exit code 80, refuse, 打印本条目编号 (`[FIT1-E001]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6 例 2 拟合前置条件不足`。

### FIT1-E002: EXP-A OCV 拟合 RMSE 超过失败阈值

**触发条件**
`fit_electrode_balance.py` 完成优化后, RMSE_V > 50 mV 量级。

**物理/方法学后果**
电极平衡参数 LR 和 OFS 的拟合质量已超出可信范围。可能原因: EXP-A 数据本身存在问题
(例如错误的 SOC 标度、非平衡测试如 C/10 而非 C/40); 半电池 OCV 数据 (`.dat` 文件)
不匹配该批次电池的实际化学; 或电池本身已经显著老化, 不应作为 fresh-cell 表征。强行
回写会污染所有下游 FIT 步骤。

**权威文档交叉引用**
- `docs/PARAMETER_SOP.md §三.1 FIT-1 验收标准`
- `docs/PARAMETERS.json::experiments::EXP-A`
- `schemas/material.schema.v1.json`

**现场可选处置**
1. 检查 EXP-A CSV 是否真为 C/40 测试 (准平衡), 而非 C/10 或 C/3 (动力学污染)。
2. 检查半电池 OCV `.dat` 文件是否对应正确的电极材料 (NCA vs LFP vs NMC), 必要时重新做 EXP-B1/B2 并重新生成 `.dat`。
3. 若电池实际已经老化 (从 C_nominal vs 实测放电容量的差异判断), 该 EXP-A 数据不适合做 FIT-1, 需要新 fresh-cell 数据。
4. 排查完成后重新运行。

**脚本应当行为**
exit code 81, refuse, 打印本条目编号 (`[FIT1-E002]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6 例 1 数据契约违规`。

### FIT1-E003: scipy.optimize.minimize 未收敛

**触发条件**
Nelder-Mead 优化器返回 `res.success == False`, 或迭代次数达到 maxiter (500) 仍未收敛。

**物理/方法学后果**
拟合过程未达到稳定最优, 返回的 LR/OFS 值不可信。多见于初值离真值过远、目标函数地形
病态、或数据数值范围异常。

**权威文档交叉引用**
- `docs/PARAMETER_SOP.md §三.1 FIT-1 算法`
- `scripts/fit_electrode_balance.py`

**现场可选处置**
1. 检查 EXP-A 数据的 V_cell 数值范围 (典型 2.5-4.2V), SOC 范围 (典型 0-1)。任一越界提示数据格式问题。
2. 检查材料 spec 中初值 LR=1.04, OFS=2.0 是否对当前电池体系合理。LFP 体系下初值可能要改为 LR=1.05, OFS=3.0。
3. 若初值合理但仍不收敛, 在脚本中加 `--maxiter 2000` 重试。
4. 持续不收敛时上报到 `08_consultation_protocol`。

**脚本应当行为**
exit code 82, refuse, 打印本条目编号 (`[FIT1-E003]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6 例 2 拟合前置条件不足`。

### FIT1-W001: EXP-A OCV 拟合 RMSE 在 marginal 区间

**触发条件**
`fit_electrode_balance.py` 完成优化后, 20 mV <= RMSE_V <= 50 mV 量级。

**物理/方法学后果**
拟合通过失败阈值但低于推荐质量阈值。LR 和 OFS 写回 spec 但 `fit_r_squared` 字段反映
质量较低。下游 FIT-2/3/4 的预测精度可能受影响, 特别是 IR 预测。

**权威文档交叉引用**
- `docs/PARAMETER_SOP.md §三.1 FIT-1 验收标准`
- `schemas/material.schema.v1.json`

**现场可选处置**
1. 若可接受当前精度 (例如初步建模阶段), 继续推进 FIT-2/3 但记录 marginal 状态。
2. 若不可接受, 按 FIT1-E002 的 remediation 路径排查 EXP-A 数据质量。
3. 无论选择哪条, `fit_r_squared` 字段会持久化记录此次拟合质量供未来审计。

**脚本应当行为**
exit code 88, warn, 打印本条目编号 (`[FIT1-W001]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6 例 6 识别性警告`。

---

## §4 FIT-2 相关错误 (FIT2)

### FIT2-E001: RC 弛豫 CSV 列名或单位不符 SOP §三.2

**触发条件**
执行 `fit_rc_transient.py` 时, EXP-B4 弛豫 CSV (`exp_b4_relaxation.csv`) 缺失
SOP §三.2 表格中列出的必填列 (`time_s`, `voltage_V`, `current_pre_step_A`,
`soc_at_step`, `t_step_s`), 或列单位头不一致, 或样本数低于最小阈值 (10 行)。

**物理/方法学后果**
two-exponential 模型需要 t_step 标记切换零点; current_pre_step 决定振幅
A1/A2 的符号与 LUT 查询的 C-rate; soc_at_step 决定查 X_PE/X_NE 的位点。
任一缺失会让 tau→R 反演失去物理锚点, C1/C2 写回参数 spec 时携带错误来源
标签, 污染下游 FIT-3/4 的初值。

**权威文档交叉引用**
- `docs/PARAMETER_SOP.md §三.2 弛豫数据 CSV 模式`
- `docs/PARAMETERS.json::experiments::EXP-B4`
- `scripts/fit_rc_transient.py`

**现场可选处置**
1. 用 `pandas.read_csv(...).dtypes` 比对 SOP §三.2 的列契约, 打印首个不匹配
   列名或缺失列名。
2. 若是单位错 (mV vs V, mA vs A), 在数据导出端修复, 不要在 fit 脚本内做
   隐式换算。
3. 若是行数不足, 检查 GITT 弛豫窗是否被提前裁剪 (典型: 弛豫窗应至少持续
   到 5τ2 量级)。

**脚本应当行为**
exit code 90, refuse, 打印本条目编号 (`[FIT2-E001]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 1 — 数据契约违规`。

### FIT2-E002: scipy.optimize.curve_fit 未收敛或返回非有限协方差

**触发条件**
`fit_two_exponential_relaxation()` 返回 `converged=False`, 或 `pcov` 含
非有限元 (NaN/Inf), 或 sigma 数量级超出工程合理域 (例如 σ_C / C > 量级 1)。

**物理/方法学后果**
返回的 (V_inf, A1, tau1, A2, tau2) 落入数值病态区, 后续 tau→R 双候选映射
失去意义; C1/C2 写回会让 FIT-3/4 的初值携带未识别误差。

**权威文档交叉引用**
- `docs/PARAMETER_SOP.md §三.2 FIT-2 算法`
- `scripts/fit_rc_transient.py`
- `libquiv_aging/relaxation_fitting.py`

**现场可选处置**
1. 检查弛豫数据是否真的进入"两指数可分"状态: 画 V(t) 半对数图, 应能
   看到至少两个时间常数尺度。
2. 若数据只显示单一时间常数, 强行套 two_exponential 会病态; 改用单指数
   预拟合得到初值, 或重新设计 GITT 脉冲幅度让两 RC 时常数都被激发。
3. 调高 `--maxfev` 至 10000 量级重试。
4. 若仍失败, 数据本身可能不适配 RC 拓扑, 走 `FIT2-E003` 升级路径。

**脚本应当行为**
exit code 91, refuse, 打印本条目编号 (`[FIT2-E002]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 2 — 拟合前置条件不足`。

### FIT2-E003: RC 弛豫拟合 RMSE 超过失败阈值

**触发条件**
two_exponential 模型拟合完成后, RMSE_V 超过失败阈值量级 (5 mV) 或
R² 低于 0.95。

**物理/方法学后果**
RC 等效电路 (二阶) 无法描述当前弛豫窗的真实物理。常见原因: 长尾段含
扩散控制成分 (Warburg / CPE), 或界面是分布式 (DRT)。继续写回 C1/C2
会使 FIT-3/4 在仿真中匹配不出 GITT 实测的电压回弹形态。

**权威文档交叉引用**
- `docs/CRITICAL_REVIEW.md C7 RC 拓扑对长弛豫的不足`
- `docs/PARAMETER_SOP.md §三.2 FIT-2 验收标准`
- `docs/UPGRADE_LITERATURE/fractional_order_RC.md`

**现场可选处置**
1. 画残差 vs 时间, 目视确认是单调漂移、对数尾还是阶跃。对数尾常对应
   扩散主导, 应转入升级路径。
2. 缩短弛豫窗到 5τ2 内, 让长尾段不进入拟合; 若窄窗能压住 RMSE, 标注
   `relaxation_metadata.window_truncated_by_user=true` 并接受。
3. 若长窗仍超阈, 不再写回 C1/C2, 而是把数据归档到 `runs/{run_id}/exp_b4/`
   等待 C7 升级 (fractional-order RC 或 DRT)。

**脚本应当行为**
exit code 92, refuse, 打印本条目编号 (`[FIT2-E003]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 2 — 拟合前置条件不足`。

### FIT2-W001: RC 弛豫拟合 RMSE 在 marginal 区间或 tau→R 映射不确定

**触发条件**
拟合 RMSE 落入 marginal 区间 (1 mV ≤ RMSE_V ≤ 5 mV), 或两候选 tau→R
映射 (tau1↔R_NE / tau1↔R_PE) 的振幅 RSS 比值 < 10% (映射歧义)。

**物理/方法学后果**
C1/C2 仍写回 spec, 但 `relaxation_metadata.mapping_marginal=true` 字段
持久化记录歧义。下游 FIT-3/4 应在该字段为 true 时主动放宽 C1/C2 的
拟合权重或重启更宽搜索域。

**权威文档交叉引用**
- `docs/PARAMETER_SOP.md §三.2 FIT-2 验收标准`
- `docs/CRITICAL_REVIEW.md C7 RC 拓扑对长弛豫的不足`
- `scripts/fit_rc_transient.py`

**现场可选处置**
1. 若是 RMSE marginal: 在 fit_report 中标注质量分位, 视后续步骤可接受度
   决定是否补做更高 SOC/温度点的 EXP-B4。
2. 若是映射歧义: 再做一次 EXP-B4 在不同 SOC (例如 0.3 vs 0.7), 用两个
   独立点的 R_NE/R_PE 量级判别 tau1 应锚到哪个电极。
3. 不要靠手工选择压低歧义 — 必须由数据驱动。

**脚本应当行为**
exit code 93, warn, 打印本条目编号 (`[FIT2-W001]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 6 — 识别性警告`。

---

## §5 IC 分析相关错误 (ICA)

### ICA-E001: RPT C/40 CSV 列契约违规或样本不足

**触发条件**
执行 `fit_ic_to_dms.py` 时, 输入 CSV 缺失必填列 (`Q_Ah`, `V_cell_V`),
或样本数量级低于 50 行, 或 Q range 量级低于 1.5 Ah, 或材料/参数 spec
文件不存在。

**物理/方法学后果**
IC analysis 的 quasi-equilibrium forward model 需要 V(Q) 在足够 Q
跨度上有足量样本以分辨 graphite stage 1↔2↔3 features。任一前置条件
破坏会让 `scipy.optimize.least_squares` 在病态目标上收敛到错误最优,
写回的 (LLI, LAM_PE, LAM_NE) 三元组污染下游 FIT-4a/b 拟合的初值与
残差权重。

**权威文档交叉引用**
- `docs/SPEC_ic_analysis.md`
- `docs/PARAMETER_SOP.md §3.2 老化实验数据 (每次 RPT 一行)`
- `docs/PARAMETER_SOP.md §SOP-4.5 IC 分析提取 DMs`

**现场可选处置**
1. 用 `pandas.read_csv(...).dtypes` 检视实际列名, 比对 SPEC 输入契约,
   打印首个不匹配列。
2. 若样本量级不足, 回溯 RPT 导出脚本, 确认 C/40 放电窗未被提前裁剪。
3. 若 Q range 不足 (典型 panasonic ncr18650b 应 ≥ 1.5 Ah 量级),
   检查放电是否到达 V_min 截止条件。
4. 若 spec 文件不存在, 确认 `--cell-type` 与 `material_specs/<cell>.material.json`
   文件名是否对齐, 并按 SOP-1 完成 cell type 骨架。

**脚本应当行为**
exit code 100, refuse, 打印本条目编号 (`[ICA-E001]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 1 — 数据契约违规`。

### ICA-E002: scipy.optimize.least_squares 未收敛或协方差非有限

**触发条件**
`fit_ic_to_dms.py` 调用 `least_squares` 完成后, `result.status` 量级
≤ 0 (未收敛); 或 J^T J 病态使条件数量级 ≥ 1e12; 或 Hessian 反演
返回的 std 含 NaN/Inf。

**物理/方法学后果**
(LLI, LAM_PE, LAM_NE) 估计与误差棒不可信。强行写回会让下游 FIT-4a/b
把数值病态当作真实老化轨迹, k_SEI / k_LAM_* 估计被严重污染。误差棒
不可计算意味着识别性已无从评估。

**权威文档交叉引用**
- `docs/SPEC_ic_analysis.md`
- `scripts/fit_ic_to_dms.py`
- `libquiv_aging/ic_analysis.py`

**现场可选处置**
1. 检查 V(Q) 曲线形态: 是否呈现 graphite stage 1↔2↔3 的清晰特征?
   若曲线过平直或仅显示单一过渡, 数据信噪比不足以支持三参数同时识别。
2. 检查初值: `heuristic_initial_guess` 给出的 LLI / LAM_PE / LAM_NE
   起点是否落在 search bounds 内。若初值离最优过远, 可手动指定
   `--initial-guess` 或扩大 bounds 一个量级。
3. 若仍不收敛, 数据可能不适配本 SPEC 的 quasi-equilibrium 假设
   (例如 RPT 是 C/10 而非 C/40, 残留 IR), 走 ICA-E003 升级路径。
4. 持续不收敛时上报到 `docs/08_consultation_protocol.md`。

**脚本应当行为**
exit code 101, refuse, 打印本条目编号 (`[ICA-E002]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 2 — 拟合前置条件不足`。

### ICA-E003: IC 拟合 RMSE 或 R² 越过失败阈值

**触发条件**
`least_squares` 收敛后, V(Q) 残差 RMSE 量级超过 20 mV,
或 R² 量级低于 0.99。

**物理/方法学后果**
V(Q) 拟合未达 quasi-equilibrium 模型在 alawa regime 内的可信精度。
常见原因: (a) RPT 实际为 C/10 或更高, IR 未消除导致 13–27 mV 量级
系统偏移; (b) cell 已进入非 alawa regime (CEI 主导 / plating-driven
knee), SPEC 假设不适用; (c) CSV 单位错 (Ah vs A·s, V vs mV)。
继续写回 (LLI, LAM_PE, LAM_NE) 会污染 FIT-4a/b 拟合。

**权威文档交叉引用**
- `docs/SPEC_ic_analysis.md`
- `docs/PARAMETER_SOP.md §3.2 老化实验数据 (每次 RPT 一行)`
- `docs/CRITICAL_REVIEW.md`

**现场可选处置**
1. 确认 RPT 是否真为 C/40 (准平衡); C-rate 偏高时残留 IR 在 V(Q)
   上叠加系统偏移。若是, 重做 RPT 或在数据导出端做 IR 校正。
2. 目视 V(Q) 图: graphite stage 1↔2↔3 features 是否清晰可见。features
   模糊提示 cell 已进入非 alawa regime, IC analysis 在此 regime 不
   再适用。
3. 比对 CSV 单位: `Q_Ah` 应为 Ah (不是 A·s), `V_cell_V` 应为 V
   (不是 mV)。任一单位错会让 RMSE 量级偏离两到三个数量级。
4. 数据归档到 `runs/{run_id}/exp_e_failed/`, 不写回 spec, 等待数据
   复测或转入升级路径调研。

**脚本应当行为**
exit code 102, refuse, 打印本条目编号 (`[ICA-E003]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 1 — 数据契约违规`。

### ICA-W001: IC 拟合质量在 marginal 区间

**触发条件**
`least_squares` 收敛后, RMSE 量级落入 15–20 mV 区间, 或 R² 量级
落入 0.99 ≤ R² < 0.999 区间。

**物理/方法学后果**
拟合通过 SOP §3.2 的 "<15 mV 为可接受" 边界但低于优秀质量。
(LLI, LAM_PE, LAM_NE) 仍写回 RPT 级 JSON, 但 `fit_r_squared` /
`rmse_V` 字段反映质量较低。下游 FIT-4a/b 在见到 marginal 标记时应
放宽对该 RPT 数据点的权重。

**权威文档交叉引用**
- `docs/PARAMETER_SOP.md §3.2 老化实验数据 (每次 RPT 一行)`
- `docs/SPEC_ic_analysis.md`

**现场可选处置**
1. 若可接受当前精度 (例如初步建模阶段), 接受 marginal 状态;
   `fit_quality.marginal_quality` 字段持久化质量信号供未来审计。
2. 若不可接受, 按 ICA-E003 的 remediation 路径排查 (RPT C-rate /
   单位 / alawa regime)。
3. JSON metadata 段记录的 `marginal_quality=true` 会被下游 FIT-4a/b
   读取并降权该 RPT。

**脚本应当行为**
exit code 103, warn, 打印本条目编号 (`[ICA-W001]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 6 — 识别性警告`。

### ICA-W002: IC 分析参数命中 search bound

**触发条件**
`least_squares` 收敛后, LLI / LAM_PE / LAM_NE 任一参数距其 search
bound 的距离量级低于 bound 宽度的 1%。

**物理/方法学后果**
对应 DM 实际值可能在 bound 之外 (老化超出 SPEC 假设的 0.3·C 上限),
或 cell 已进入非 alawa regime, bound 即将不适用。报告值不具置信
意义, 误差棒在边界附近也会被截断。

**权威文档交叉引用**
- `docs/SPEC_ic_analysis.md`
- `docs/CRITICAL_REVIEW.md`

**现场可选处置**
1. 若 LLI 命中 0.3·C_nominal 上界: cell 已严重退化, 可能进入
   plating-driven knee; IC analysis 在此 regime 不适用, 进入 FIT-4c
   knee 分析路径而非继续 IC analysis。
2. 若 LAM_PE / LAM_NE 命中上界: 可能进入 CEI 主导 regime, 需要新
   模型 (见 `docs/CRITICAL_REVIEW.md`); 不要简单放宽 bound, 因为
   SPEC 的 bound 设计反映了模型适用域。
3. 把命中事件写入输出 JSON 的 `fit_quality.bounds_hit` 字段, 下游
   FIT-4a/b 应跳过此 RPT 数据点。

**脚本应当行为**
exit code 104, warn, 打印本条目编号 (`[ICA-W002]`)。

**何时升级到在线咨询**
见 `docs/08_consultation_protocol.md §6.例 6 — 识别性警告`。

---

## §6 FIT-4a 相关错误 (FIT4A)

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

## §7 FIT-4b 相关错误 (FIT4B)

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

## §8 FIT-4c 相关错误 (FIT4C)

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

## §9 数值求解器类错误 (SOLVE)

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

## §10 可识别性警告 (IDENT)

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
| ENV-E002 | ENV | E | pip install 失败: 依赖不在内部镜像索引中 | 2 | refuse | active |
| DATA-E001 | DATA | E | RPT CSV 列名或单位不符 SOP §3.2 | 20 | refuse | active |
| DATA-E002 | DATA | E | .dat 文件 x 列非单调或越界 | 21 | refuse | active |
| DATA-E003 | DATA | E | 电阻 .mat 形状不是 1001×2001 | 22 | refuse | active |
| FIT1-E001 | FIT1 | E | 材料 spec 中 dX 或 X0 字段未填 | 80 | refuse | active |
| FIT1-E002 | FIT1 | E | EXP-A OCV 拟合 RMSE 超过失败阈值 | 81 | refuse | active |
| FIT1-E003 | FIT1 | E | scipy.optimize.minimize 未收敛 | 82 | refuse | active |
| FIT1-W001 | FIT1 | W | EXP-A OCV 拟合 RMSE 在 marginal 区间 | 88 | warn | active |
| FIT2-E001 | FIT2 | E | RC 弛豫 CSV 列名或单位不符 SOP §三.2 | 90 | refuse | active |
| FIT2-E002 | FIT2 | E | scipy.optimize.curve_fit 未收敛或返回非有限协方差 | 91 | refuse | active |
| FIT2-E003 | FIT2 | E | RC 弛豫拟合 RMSE 超过失败阈值 | 92 | refuse | active |
| FIT2-W001 | FIT2 | W | RC 弛豫拟合 RMSE 在 marginal 区间或 tau→R 映射不确定 | 93 | warn | active |
| ICA-E001 | ICA | E | RPT C/40 CSV 列契约违规或样本不足 | 100 | refuse | active |
| ICA-E002 | ICA | E | scipy.optimize.least_squares 未收敛或协方差非有限 | 101 | refuse | active |
| ICA-E003 | ICA | E | IC 拟合 RMSE 或 R² 越过失败阈值 | 102 | refuse | active |
| ICA-W001 | ICA | W | IC 拟合质量在 marginal 区间 | 103 | warn | active |
| ICA-W002 | ICA | W | IC 分析参数命中 search bound | 104 | warn | active |
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
