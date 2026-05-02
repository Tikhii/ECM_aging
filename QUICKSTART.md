# 🚀 QUICKSTART — macOS + conda 10 分钟上手清单

这是 `docs/01_setup_guide.md` 的**精简版**。按顺序在 Terminal 里执行即可。

---

## ☑ Step 1 · 把 zip 解压到你的工作目录

```bash
mkdir -p ~/code
cd ~/code
unzip ~/Downloads/libquiv_aging_py.zip
cd libquiv_aging_py
ls                                   # 应看到 libquiv_aging/, examples/, docs/, tests/
```

## ☑ Step 2 · 装前置工具（若已有就跳过）

### 装 conda（二选一）

**方案 A：Miniforge（推荐，社区维护、轻量、默认走 conda-forge）**

```bash
brew install --cask miniforge
conda init zsh                       # 或 conda init bash, 看你的默认 shell
# 关闭并重开 Terminal 让初始化生效
```

**方案 B：Miniconda / Anaconda**

如果你已经装过 Anaconda 或 Miniconda，直接跳过；这两者任意一个都可以。

验证：

```bash
conda --version                      # 应输出 conda 23.x 或更高
```

### 可选但推荐：装 mamba（更快的 conda 求解器）

```bash
conda install -n base -c conda-forge mamba
```

之后所有 `conda install / env create / env update` 都可换成 `mamba`，快 5–10 倍。

### 装 Git、VS Code、Claude Code

```bash
brew install git
brew install --cask visual-studio-code

# Claude Code CLI (可选, 强烈推荐)
brew install anthropic/claude/claude-code   # 或 npm install -g @anthropic/claude-code
```

## ☑ Step 3 · 创建 conda 环境

```bash
cd ~/code/libquiv_aging_py

# 一条命令创建环境并装好所有依赖
conda env create -f environment.yml

# 或用 mamba (若已装)
# mamba env create -f environment.yml

# 激活环境 (重要: 每开新终端都要激活一次)
conda activate libquiv-aging
```

`environment.yml` 末尾有 `pip: - -e .`，所以创建过程会自动把本工程以**可编辑模式**装进环境——你改源码不用重新安装。

验证：

```bash
which python                         # 应在 ~/miniforge3/envs/libquiv-aging/bin/python
python -c "import libquiv_aging; print(libquiv_aging.__file__)"
```

## ☑ Step 4 · 验证环境

```bash
# 跑 109 个单元测试 (~45 秒)
pytest tests/ -v

# 烟雾测试 (~10 秒)
python examples/smoke_test.py

# 复现论文图 7 的快速版本 (~5 分钟)
python examples/figure7_simulation.py
```

全部通过即表示**环境 OK**。图片输出在 `examples/outputs/`。

## ☑ Step 5 · 打开 VS Code

```bash
cd ~/code/libquiv_aging_py
code .
```

- 首次打开 VS Code 会弹"是否安装推荐插件"，点 **Install All**。
- 按 `⇧⌘P` → `Python: Select Interpreter` → 选 `libquiv-aging` 环境下的 Python（路径通常是 `~/miniforge3/envs/libquiv-aging/bin/python`）。
- 打开 `examples/smoke_test.py`，按 `F5` 可直接调试。

> `.vscode/settings.json` 里我把 interpreter 默认路径保留为占位；第一次选过 conda 环境后 VS Code 会记住。

## ☑ Step 6 · 启动 Claude Code

```bash
cd ~/code/libquiv_aging_py
conda activate libquiv-aging          # 确保在 conda 环境里启动
claude
```

推荐的第一个提问：

> `通读 docs/02_model_overview.md，然后用 3 句话总结这个模型在做什么。再指给我看 cell_model.py 里哪里对应论文的 (36) 式。`

---

## 🔁 日常工作流

每次开新终端来干活：

```bash
cd ~/code/libquiv_aging_py
conda activate libquiv-aging
# ... 开始工作 ...
```

退出环境：

```bash
conda deactivate
```

## 🧹 环境维护

| 任务 | 命令 |
| --- | --- |
| 更新依赖（你改了 environment.yml 后） | `conda env update -f environment.yml --prune` |
| 列出当前环境的包 | `conda list` |
| 装新包（临时） | `conda install -c conda-forge PACKAGE_NAME` |
| 导出当前环境为 yml（分享给同事） | `conda env export --from-history > my_env.yml` |
| 删除整个环境（重装） | `conda env remove -n libquiv-aging` |

---

## 🗂 文档路线图

| 我想... | 读这个 |
| --- | --- |
| 理解模型在做什么 | `docs/02_model_overview.md` |
| 用到我自己的电池上 | `docs/03_inputs_guide.md` |
| 创建新 cell type (双 spec) | `docs/PARAMETER_SOP.md` §二.0 |
| 解读仿真输出 | `docs/04_outputs_guide.md` |
| 看完整工作流示例 | `docs/05_workflow_examples.md` |
| 用 FIT-1 拟合电极平衡 | `scripts/fit_electrode_balance.py` + `docs/PARAMETER_SOP.md` §三.1 |
| 用 FIT-4 拟合老化参数 (calendar/cycle/knee) | `scripts/fit_dm_aging.py` + `docs/SPEC_dm_aging.md` + `docs/07_offline_runbook.md` |
| 在离线实验室部署 | `docs/09_offline_bundle_guide.md` |
| 现场报错速查 | `docs/07_offline_runbook.md` |
| 从模板开始写自己的分析 | `examples/analysis_template.py` |
| 查项目演化历史 | `CHANGELOG.md` (release-level) + `docs/decisions/` (ADR 决策记录) + `docs/legacy/MIGRATION_NOTES.md` (深度档案) |

## 🆘 常见问题速查

| 症状 | 怎么办 |
| --- | --- |
| `conda env create` 卡住很久 | 换成 `mamba env create -f environment.yml`（先 `conda install -n base mamba`） |
| `ResolvePackageNotFound` | 确认 `environment.yml` 里有 `channels: [conda-forge, defaults]`；Apple Silicon 下某些包只在 conda-forge |
| VS Code 报 `import libquiv_aging` 找不到 | 左下角 interpreter 必须是 conda 环境下的 Python，不是系统 Python |
| `claude` 命令不存在 | 重开终端；或先 `conda deactivate && source ~/.zprofile` |
| 图窗不弹 | 脚本开头加 `import matplotlib; matplotlib.use('MacOSX')`；或保存成 PNG |
| 仿真报 NaN | 把 `acceleration_factor` 降到 1，定位是哪个老化率炸了 |
| conda 和 pip 混用起冲突 | 永远**先 conda 装、后 pip 装**；本工程 `environment.yml` 已经按此编排 |

---

## 🧬 v0.3 后新功能速览

本工程的 cell type 现在通过两份 spec 文件定义 (材料 spec + 参数 spec),
加载入口是 `create_cell_from_specs`:

```python
from libquiv_aging import create_cell_from_specs
cell = create_cell_from_specs(
    "material_specs/panasonic_ncr18650b.material.json",
    "param_specs/panasonic_ncr18650b__mmeka2025.params.json",
)
cell.init(SOC=0.5)
```

旧的 `create_panasonic_ncr18650b()` 仍然可用作便捷入口, 行为完全等价。

拟合 LR 和 OFS 用 FIT-1 脚本:

```bash
# dry-run 模式 (合成数据验证脚本)
python scripts/fit_electrode_balance.py \
    --material-spec material_specs/panasonic_ncr18650b.material.json \
    --dry-run
```

详见 `docs/PARAMETER_SOP.md` §三.1 和 `docs/05_workflow_examples.md`。

拟合老化参数 (FIT-4a/4b/4c, v0.7.0-fit4) 用 FIT-4 统一入口:

```bash
python scripts/fit_dm_aging.py \
    --cell-dir <RPT 数据目录> \
    --out <输出目录> \
    --stage all   # 或 a / b / c 单 stage
```

`--stage all` 串行跑 a → b → c, 早期 E-码中止后续 stage; W-码累积到
最终 exit code。16 条错误码语义见 `docs/07_offline_runbook.md`,
SPEC 见 `docs/SPEC_dm_aging.md`。

---

**准备好了就开始干活吧。一切问题优先问 Claude Code + 贴报错。**
