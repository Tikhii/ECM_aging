# libquiv-aging — 物理信息化老化敏感等效电路电池模型（Python 移植）

本工程是文章

> Mmeka P O, Dubarry M, Bessler W G. **Physics-Informed Aging-Sensitive Equivalent Circuit Model for Predicting the Knee in Lithium-Ion Batteries**. *J. Electrochem. Soc.* 172 080538 (2025). [DOI: 10.1149/1945-7111/adf9cb](https://iopscience.iop.org/article/10.1149/1945-7111/adf9cb/meta)

所附 MATLAB 代码的 Python 完整移植版本。原始代码由论文作者发布于 Zenodo（CC BY-NC 4.0 许可）。

## 工程特点

- **模块化设计**：将原 758 行单文件 `LIBquivAging.m` 拆分为 5 个单一职责的模块（热力学 LUT、电阻 LUT、老化动力学、主模型类、电池参数工厂），便于 Claude Code 按需检索和修改。
- **面向研究**：所有数值参数都集中到可配置 `dataclass` 中（`SEIParameters`、`PlatingParameters` 等），方便替换化学体系或运行敏感性研究。
- **高性能**：通过标量快速插值 + Newton warm-start 求解器，单次完整 DST 放电耗时 30 秒左右（原 MATLAB 代码 ~40 秒）。
- **完整测试集**：15 个 pytest 用例覆盖初始化、CC/CV/CP 三种模式、CCCV 循环和老化。

## 目录结构

```
libquiv_aging_py/
├── README.md                     # 本文件
├── QUICKSTART.md                 # 10 分钟 Mac 上手清单
├── environment.yml               # ★ conda 环境定义 (推荐入口)
├── pyproject.toml                # 现代 Python 项目配置
├── requirements.txt              # pip 依赖 (若不用 conda)
├── .vscode/                      # VS Code 调试 & 设置
│
├── libquiv_aging/                # ★ 核心代码包
│   ├── __init__.py               # 公共 API
│   ├── constants.py              # 物理常数
│   ├── lookup_tables.py          # 半电池 OCV / 电阻 LUT 与插值
│   ├── aging_kinetics.py         # 所有老化速率律 (SEI/Plating/LAM)
│   ├── cell_model.py             # EquivCircuitCell 主类 (ODE 求解)
│   ├── panasonic_ncr18650b.py    # NCR18650B 参数工厂
│   └── data/                     # 配套数据 (.dat / .mat / .csv)
│
├── examples/                     # 可运行示例
│   ├── smoke_test.py             # 快速功能验证
│   ├── figure7_simulation.py     # 复现论文图 7 的 DST 循环老化
│   └── analysis_template.py      # 自己做分析用的起点模板
│
├── tests/                        # pytest 单元测试
│   └── test_basic.py
│
└── docs/                         # ★ 详细文档 (中文)
    ├── 01_setup_guide.md         # macOS + conda + VS Code + Claude Code 安装
    ├── 02_model_overview.md      # 模型数学结构与 DAE 系统说明
    ├── 03_inputs_guide.md        # 如何获取/格式化模型输入数据
    ├── 04_outputs_guide.md       # 如何解读输出、进行评估
    ├── 05_workflow_examples.md   # 常见工作流 (参数研究、新电池等)
    ├── 06_parameter_sourcing.md  # 深度参数来源分析 (LFP/Gr 案例)
    ├── CLAUDE.md                 # 给 AI 助手的路由手册
    ├── PARAMETERS.json           # ★ 参数元数据 (单一事实来源)
    ├── PARAMETER_SOP.md          # 参数获取标准作业流程 (SOP)
    └── CRITICAL_REVIEW.md        # 批判性审查结果 + 作用域卡片
```

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
```

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
| 参数敏感性研究 / 参数辨识 | `docs/05_workflow_examples.md` |
| 系统化参数获取（实验 DOE 到拟合 SOP） | `docs/PARAMETER_SOP.md` |
| 查参数元数据 / 论文错误 / 批判性审查 | `docs/PARAMETERS.json` + `docs/CRITICAL_REVIEW.md` |
| 给 AI 助手（Claude Code）的路由手册 | `docs/CLAUDE.md` |

## 引用

若在学术工作中使用，请引用原论文（见顶部），并可注明本 Python 移植。

## 许可

代码遵循原作者的 **CC BY-NC 4.0** 许可（非商业使用）。
