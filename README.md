# libquiv-aging — 物理信息化老化敏感等效电路电池模型（Python 移植）

本工程是文章

> Mmeka P O, Dubarry M, Bessler W G. **Physics-Informed Aging-Sensitive Equivalent Circuit Model for Predicting the Knee in Lithium-Ion Batteries**. *J. Electrochem. Soc.* 172 080538 (2025). [DOI: 10.1149/1945-7111/adf9cb](https://iopscience.iop.org/article/10.1149/1945-7111/adf9cb/meta)

所附 MATLAB 代码的 Python 完整移植版本。原始代码由论文作者发布于 Zenodo（CC BY-NC 4.0 许可）。

## 工程特点

- **模块化设计**：将原 758 行单文件 `LIBquivAging.m` 拆分为多个单一职责的模块, 含核心模型、查找表、老化动力学、cell type 抽象层、FIT 脚本基础设施等, 便于 Claude Code 按需检索和修改。
- **面向研究**：所有数值参数都集中到可配置 `dataclass` 中（`SEIParameters`、`PlatingParameters` 等），方便替换化学体系或运行敏感性研究。
- **高性能**：通过标量快速插值 + Newton warm-start 求解器，单次完整 DST 放电耗时 30 秒左右（原 MATLAB 代码 ~40 秒）。
- **完整测试集**：109 个 pytest 用例覆盖核心模型、cell type 加载、FIT 脚本基础设施 (含 FIT-1, FIT-2) 和 IC 分析。

## 目录结构

```
libquiv_aging_py/
├── README.md                     # 本文件
├── QUICKSTART.md                 # 10 分钟 Mac 上手清单
├── environment.yml               # ★ conda 环境定义 (推荐入口)
├── environment-frozen.yml        # 冻结版 (air-gapped 部署用)
├── requirements.txt              # 从 frozen.yml 派生的 pip 清单
├── pyproject.toml                # 现代 Python 项目配置
├── .gitignore                    # 含 runs/ 排除
├── .vscode/                      # VS Code 调试 & 设置
│
├── libquiv_aging/                # ★ 核心代码包
│   ├── __init__.py               # 公共 API
│   ├── constants.py              # 物理常数
│   ├── lookup_tables.py          # 半电池 OCV / 电阻 LUT
│   ├── aging_kinetics.py         # 老化速率律 (SEI/Plating/LAM)
│   ├── cell_model.py             # EquivCircuitCell 主类 (ODE 求解)
│   ├── cell_factory.py           # 通用 cell 加载器 (双 spec)
│   ├── fitting.py                # FIT 脚本系列共享基础设施
│   ├── relaxation_fitting.py     # FIT-2 RC 弛豫内核 (RELAXATION_MODELS dispatch)
│   ├── ic_analysis.py            # IC 分析:RPT C/40 → (LLI, LAM_PE, LAM_NE) (SOP-4.5)
│   ├── model_versions/           # 机制模型版本路由
│   │   ├── __init__.py           # 版本注册表
│   │   └── mmeka2025.py          # 当前机制的组装逻辑
│   ├── panasonic_ncr18650b.py    # NCR18650B 兼容层入口
│   └── data/                     # 配套数据 (.dat / .mat / .csv)
│
├── schemas/                      # ★ JSON Schema 定义
│   ├── material.schema.v1.json
│   └── params_mmeka2025.schema.v1.json
│
├── material_specs/               # ★ 材料 spec (本征参数)
│   └── panasonic_ncr18650b.material.json
│
├── param_specs/                  # ★ 参数 spec (唯象参数)
│   └── panasonic_ncr18650b__mmeka2025.params.json
│
├── scripts/                      # 拟合脚本与工具
│   ├── fit_electrode_balance.py  # FIT-1: LR/OFS 拟合
│   ├── fit_rc_transient.py       # FIT-2: C1/C2 RC 弛豫双指数拟合 (dispatch 模式)
│   ├── fit_ic_to_dms.py          # IC 分析 CLI (SOP-4.5): RPT C/40 → DMs + JSON/PNG
│   ├── check_parameter_consistency.py
│   ├── install_offline.sh        # air-gapped 安装入口
│   ├── verify_install.sh
│   └── build_requirements.sh
│
├── examples/                     # 可运行示例
│   ├── smoke_test.py             # 快速功能验证
│   ├── figure7_simulation.py     # 复现论文图 7
│   └── analysis_template.py      # 自定义分析模板
│
├── tests/                        # pytest 测试 (109 用例)
│   ├── test_basic.py             # 原始 22 个核心模型测试
│   ├── test_schemas.py           # schema 与 spec 验证
│   ├── test_cell_factory.py      # cell_factory 加载器
│   ├── test_panasonic_equivalence.py  # 兼容层等价性
│   ├── test_fitting.py           # FIT 基础设施
│   ├── test_fit_electrode_balance.py  # FIT-1 端到端
│   ├── test_relaxation_fitting.py     # FIT-2 内核单测 (RELAXATION_MODELS)
│   ├── test_fit_rc_transient.py       # FIT-2 端到端
│   ├── test_ic_analysis.py            # IC 分析 + CLI 端到端 (T1-T5 + 错误码集成)
│   ├── test_error_codes_registry.py   # 错误码 registry 验证
│   └── golden_panasonic_snapshot.json # 回归测试金标准
│
├── runs/                         # FIT 脚本运行产物 (.gitignore 排除)
│
└── docs/                         # ★ 详细文档
    ├── 01_setup_guide.md         # macOS + conda 环境搭建
    ├── 02_model_overview.md      # 模型数学结构与 DAE 系统
    ├── 03_inputs_guide.md        # 输入数据获取/格式化
    ├── 04_outputs_guide.md       # 输出解读与评估
    ├── 05_workflow_examples.md   # 工作流示例
    ├── 06_parameter_sourcing.md  # 参数来源深度分析
    ├── 07_offline_runbook.md     # 离线现场错误码手册
    ├── 08_consultation_protocol.md # 跨 air-gap 咨询协议
    ├── 09_offline_bundle_guide.md  # 离线工作站部署指南
    ├── CLAUDE.md                 # AI 代理路由手册 (R1-R8)
    ├── PARAMETERS.json           # ★ 参数元数据 (单一事实来源)
    ├── PARAMETER_SOP.md          # 参数获取 SOP
    ├── CRITICAL_REVIEW.md        # 批判性审查 (S/C/N 系列)
    ├── legacy/MIGRATION_NOTES.md # 跨会话演化笔记 (frozen 2026-04-30)
    ├── error_codes_registry.json # 错误码事实层
    ├── error_codes.schema.json   # 错误码 schema
    └── UPGRADE_LITERATURE/       # 模型升级方向的文献 starter pack
```

## 工作流概览

本工程已演化为多层架构。一个完整的 cell type 由两份 spec 文件
定义: 材料 spec (本征参数, 跨机制稳定) 加上参数 spec (唯象参数,
随机制版本变化)。加载入口是 `create_cell_from_specs(material_path,
params_path)`, 内部根据参数 spec 的 `model_version` 字段路由到对应
机制的组装函数。当前机制版本是 mmeka2025, 未来 `CRITICAL_REVIEW.md`
中的升级路径 (R_s 退化、动态镀锂等) 会引入新机制版本, 旧 spec
保留为历史。

参数化工作流: 新 cell type 通过复制 panasonic 示例 spec 起步, 填入
Tier I 直测参数, 准备 EXP-A 到 EXP-G 实验数据 (详见 `PARAMETER_SOP.md`
§一二), 运行 `scripts/` 下的 FIT-X 拟合脚本依次产出参数。已实现:
`fit_electrode_balance.py` (FIT-1, LR/OFS)、`fit_rc_transient.py`
(FIT-2, C1/C2 RC 弛豫双指数, dispatch 模式预留 fractional-order /
DRT 升级) 和 `fit_ic_to_dms.py` (SOP-4.5, IC 分析:RPT C/40 →
LLI/LAM_PE/LAM_NE,JSON + 2×2 诊断 PNG,5 条 ICA-Exxx/Wxxx 错误码)。
FIT-1/FIT-2 自动回写到对应 spec 含完整 fit provenance (`fit_step`,
`fit_source`, `fit_r_squared`, `relaxation_metadata` 等);IC 分析按
SPEC 不回写 spec,产出独立 JSON 供下游 FIT-4 等消费。FIT-3/4 待
v0.6.0 实施。

版本演化通过 git tag 标记: `docs/vX.Y.Z` 是文档基建或错误码 patch,
`release/vX.Y.0` 是代码能力 minor release。截至 v0.5.0 已有九层 tag
阶梯, 完整演化历史见 `CHANGELOG.md`, 深度档案见
`docs/legacy/MIGRATION_NOTES.md`, 架构决策记录见 `docs/decisions/`。

air-gapped 实验室部署通过内部 pip 镜像单轨制, 详见
`docs/09_offline_bundle_guide.md`。错误码体系 (ENV / DATA / FIT1 /
FIT2 / FIT4A / FIT4B / FIT4C / SOLVE / IDENT 九个作用域) 见
`docs/07_offline_runbook.md` 和 `docs/error_codes_registry.json`。

## 快速开始

```bash
# 1. 克隆或解压工程 (详见 docs/01_setup_guide.md)
cd libquiv_aging_py

# 2. 创建 conda 环境 (一条命令装好所有依赖 + 可编辑安装本工程)
conda env create -f environment.yml
conda activate libquiv-aging

# 3. 运行烟雾测试 (几十秒)
python examples/smoke_test.py

# 4. 运行论文图 7 的快速版 (约 5 分钟)
python examples/figure7_simulation.py

# 5. 试运行 FIT-1 拟合脚本 (dry-run 模式, 用合成数据反演验证)
python scripts/fit_electrode_balance.py \
    --material-spec material_specs/panasonic_ncr18650b.material.json \
    --dry-run
```

应输出 LR≈1.04, OFS≈2.0 (反演相对误差 < 0.5% 和 < 20%)。

运行结果保存在 `examples/outputs/`（PNG 图片）。

> **已装 mamba 可替换**：`mamba env create -f environment.yml` (快 5–10 倍)
>
> **不想用 conda 也可以**：`pip install -e ".[dev]"` —— 但 conda 在 macOS (尤其 Apple Silicon) 处理 scipy/numpy 更可靠。

## 下一步

| 想做什么 | 去哪里读文档 |
| --- | --- |
| 在 Mac 上从零搭环境 | `docs/01_setup_guide.md` |
| 理解方程结构和数学约定 | `docs/02_model_overview.md` |
| 用自己的电池数据替换参数 | `docs/03_inputs_guide.md` |
| 评估模型预测好坏 | `docs/04_outputs_guide.md` |
| 参数敏感性研究 | `docs/05_workflow_examples.md` |
| 系统化参数获取 (实验 DOE 到拟合 SOP) | `docs/PARAMETER_SOP.md` |
| 创建新 cell type (双 spec 架构) | `docs/PARAMETER_SOP.md` §二.0 |
| 拟合电极平衡 LR/OFS | `scripts/fit_electrode_balance.py` + `docs/PARAMETER_SOP.md` §三.1 |
| 拟合 RC 弛豫电容 C1/C2 | `scripts/fit_rc_transient.py` + `docs/PARAMETER_SOP.md` §三.2 |
| 模型升级方向 (RC 不够用 / 长弛豫 / IC 分析方法学等) | 文献入口在 `docs/UPGRADE_LITERATURE/` (`fractional_order_RC.md` 对应 `CRITICAL_REVIEW.md` C7; `ic_analysis_methodology_review.md` 对应 N2/N3) |
| 离线实验室部署 | `docs/09_offline_bundle_guide.md` |
| 现场错误码手册 | `docs/07_offline_runbook.md` |
| 跨 air-gap 向在线 Claude 咨询 | `docs/08_consultation_protocol.md` |
| 查参数元数据 / 论文错误 / 批判性审查 | `docs/PARAMETERS.json` + `docs/CRITICAL_REVIEW.md` |
| 查项目演化历史 | `CHANGELOG.md` (release-level) + `docs/decisions/` (ADR 决策记录) + `docs/legacy/MIGRATION_NOTES.md` (深度档案) |
| 给 AI 代理 (Claude Code) 的路由手册 | `docs/CLAUDE.md` |

## 许可证 (License)

本工程采用 **Creative Commons Attribution-NonCommercial 4.0 International
(CC BY-NC 4.0)** 许可证发布，与上游 Zenodo MATLAB 代码保持一致。完整法律条款
见仓库根目录 `LICENSE`，归属与派生关系见 `NOTICE`。

### 派生关系澄清

本 Python 实现是 Mmeka, Dubarry & Bessler (2025) 论文**配套 MATLAB 代码**
（Zenodo: [10.5281/zenodo.15833031](https://doi.org/10.5281/zenodo.15833031),
CC BY-NC 4.0）的派生作品。

注意：原论文正文本身使用更严格的 CC BY-NC-**ND** 4.0（禁止衍生），但**不是**
本代码的法律来源。本代码的法律来源是 Zenodo 上的 MATLAB 源码，其许可证不含
ND 条款，因此允许产生派生作品。

### Non-Commercial 范围的解释性声明

CC BY-NC 4.0 中 "non-commercial" 的官方定义是 *"not primarily intended for
or directed towards commercial advantage or monetary compensation"*。作为
版权持有人，对常见模糊场景作如下声明。**本声明不修改 CC 许可条款本身**，
仅用于降低使用者的咨询成本。

**明确允许（无需联系作者）**:

- 学术研究使用，包括博士论文、会议与期刊投稿、研究项目原型代码
- 高校与研究机构的教学使用
- 个人学习与非营利开源贡献

**需事先联系作者**:

- 工业界（包括初创公司）的内部研究、产品开发、咨询项目
- 嵌入到商业产品中的使用，包括 SaaS、BMS 固件、电池诊断或寿命预测服务
- 任何收费的培训或咨询服务中作为示例代码使用

联系方式：通过本仓库 GitHub Issues 提出。

### 引用 (Citation)

如在学术工作中使用本代码，请同时引用：

1. **原论文**: Mmeka P. O., Dubarry M., Bessler W. G. *J. Electrochem. Soc.*
   **172** 080538 (2025). DOI: [10.1149/1945-7111/adf9cb](https://doi.org/10.1149/1945-7111/adf9cb)
2. **本 Python 移植**: 仓库 URL，或未来发布的 Zenodo DOI（建议在版本稳定
   后注册）。
