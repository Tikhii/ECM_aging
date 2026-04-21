# 01 · macOS + conda 本地工作环境搭建（完整版）

本文档给出在 **Apple Silicon 或 Intel Mac** 上从零搭建完整开发环境的逐步说明。以下命令均在 Terminal 中执行；估算时间 20–30 分钟。

若你已经熟悉 conda，直接看 `QUICKSTART.md` 即可。

---

## 1. 前置工具

### 1.1 Homebrew (macOS 的包管理器)

```bash
# 若未安装 Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

安装完后按提示将 `brew` 加入 `PATH` (Apple Silicon 通常需要执行提示给你的 `echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile`)。

### 1.2 conda (核心，Python 环境管理器)

我们用 conda 管理 Python 和所有科学计算依赖。macOS 下的最佳选择是 **Miniforge**：

```bash
brew install --cask miniforge
conda init zsh                       # 或 conda init bash
# 关闭并重开 Terminal
conda --version                      # 应输出 conda 23.x+
```

**为什么 Miniforge 而不是 Anaconda？**
- 体积小（约 100 MB vs 3 GB）
- 默认通道为 `conda-forge`，社区维护、包更新及时
- 原生支持 Apple Silicon (arm64)
- 无商用授权顾虑

**若你已经装过 Anaconda / Miniconda**：直接用即可，跳过 Miniforge 安装。

### 1.3 mamba (可选，强烈推荐)

`mamba` 是用 C++ 重写的 conda 求解器，在创建环境时速度快 5–10 倍，尤其是处理大型依赖图：

```bash
conda install -n base -c conda-forge mamba
```

之后所有 `conda env create / update / install` 都可替换成 `mamba`，用法完全一致。

### 1.4 Git

```bash
brew install git
git --version
```

### 1.5 VS Code

```bash
brew install --cask visual-studio-code
```

打开 VS Code，按 `⇧⌘P` 打开命令面板，输入 `Shell Command: Install 'code' command in PATH` 以便之后能用 `code .` 命令从终端打开工程。

### 1.6 Claude Code (可选但强烈推荐)

Claude Code 是 Anthropic 发布的命令行 AI 编程助手，非常适合在这种物理建模项目里做"改速率律重跑"、"写一段参数扫描脚本"、"帮我解读报错"等任务。

```bash
# Claude Code 的安装方式可能随版本更新，以下为 2026 年 4 月写法
brew install anthropic/claude/claude-code
# 或使用 npm:
npm install -g @anthropic/claude-code

# 首次运行 —— 会引导你完成 API Key 配置
claude
```

详细安装和登录说明请见 [docs.claude.com/claude-code](https://docs.claude.com/en/docs/claude-code/overview)（以官方文档为准）。

---

## 2. 获取本工程代码

### 方案 A：从 Claude.ai 下载的 ZIP

1. 将我提供的 `libquiv_aging_py.zip` 解压到你习惯的工程目录，例如：
    ```bash
    mkdir -p ~/code && cd ~/code
    unzip ~/Downloads/libquiv_aging_py.zip
    cd libquiv_aging_py
    ```

### 方案 B：放进自己的 Git 仓库

一旦代码在本地，立即建立版本控制：

```bash
cd ~/code/libquiv_aging_py
git init
git add .
git commit -m "Initial import of libquiv-aging Python port"
```

也建议推到自己的 GitHub / Gitee 私库，方便跨机器同步。

---

## 3. 创建 conda 环境

这是整个工程最关键的一步。**任何 Python 项目都不应污染 conda base 环境**——每个项目独立环境。

### 3.1 一键创建

```bash
cd ~/code/libquiv_aging_py

# 从 environment.yml 创建环境
conda env create -f environment.yml
# 若已装 mamba:
# mamba env create -f environment.yml

# 激活 (之后每次开新终端都要这一步)
conda activate libquiv-aging

# 确认现在用的是环境里的 python
which python           # 应显示 .../envs/libquiv-aging/bin/python
python --version       # 应显示 Python 3.11.x
```

### 3.2 environment.yml 里装了什么？

打开 `environment.yml` 可以看到：

```yaml
name: libquiv-aging
channels:
  - conda-forge
  - defaults
dependencies:
  - python=3.11
  - numpy>=1.24,<3
  - scipy>=1.11
  - matplotlib>=3.7
  - pandas>=2.0
  # 开发工具
  - pytest, black, ruff, mypy
  # Jupyter
  - ipykernel, jupyter, ipywidgets
  - pip
  - pip:
      - -e .                        # 把本工程可编辑安装
```

末尾的 `pip: - -e .` 会在 conda 装完所有原生依赖后，自动调用 pip 以 **可编辑模式（editable）** 安装本工程本身。"可编辑"的意思是：你改 `libquiv_aging/` 下的源码，import 时立即生效，不用重新安装。

### 3.3 验证

```bash
# 确认包能导入
python -c "import libquiv_aging; print(libquiv_aging.__file__)"
# 应输出类似 .../libquiv_aging_py/libquiv_aging/__init__.py

# 确认 numpy/scipy 用的是 conda 版 (BLAS 优化)
python -c "import numpy; numpy.show_config()"
# Apple Silicon 下应看到 Accelerate 或 OpenBLAS
```

---

## 4. 用 VS Code 打开工程

```bash
cd ~/code/libquiv_aging_py
code .
```

首次打开时 VS Code 会弹窗：

1. **推荐插件安装提示** → 点 "Install All"。这会装上 Python、Pylance、Black、Ruff、Jupyter、Claude Code 等本工程配置好的扩展。

2. **"Select Interpreter" 提示** → 选择 conda 环境下的 Python。如果没弹出，按 `⇧⌘P` → `Python: Select Interpreter` → 选 `Python 3.11 ('libquiv-aging')` 或对应的 `.../envs/libquiv-aging/bin/python` 路径。

3. **可选：启用 "Format on Save"**。`.vscode/settings.json` 已经配置好，代码保存时自动用 Black 格式化。

### 验证环境 OK

在 VS Code 里：

- 打开 `examples/smoke_test.py`
- 按 `F5`（或左侧"运行和调试"面板选 `Smoke Test`）
- 若输出 "**全部烟雾测试通过 ✓**"，环境就绪。

---

## 5. 运行测试套件

```bash
# 在终端中（仍在 conda 环境激活状态）
pytest tests/ -v
```

应看到：

```
============================= 15 passed in ~20s =============================
```

或者在 VS Code 左侧"测试"面板里直接点单个用例调试。

---

## 6. 在 VS Code 里使用 Claude Code

### 6.1 CLI 方式 (任何终端均可)

在本工程目录打开终端，**先激活 conda 环境，再启动 claude**：

```bash
cd ~/code/libquiv_aging_py
conda activate libquiv-aging
claude
```

首次会要求登录；登录后直接进入交互会话。可以这样提问：

> `请解释一下 aging_kinetics.py 里 I_SEI_NE 函数各项的物理意义，对应论文哪一个方程？`

> `我想把 SEI 激活能从 55500 改成 60000，然后重跑 figure7_simulation.py 看结果变化。`

Claude Code 能直接读你的代码文件、执行命令、改写源代码。**这样启动的 Claude Code 能直接使用 conda 环境的 Python 和所有依赖**。

### 6.2 VS Code 插件方式

安装了 Claude Code 扩展后，在右侧边栏会有 🟠 图标。点击即可在编辑器内直接对话，支持 "highlight 一段代码 → 让 Claude 解释/改写"。

### 6.3 推荐的对话模式

- **导览**：初次接触代码时，先让 Claude Code 通读 `docs/02_model_overview.md` 并解释关键方程。
- **修改**：提出具体需求，如"把 acceleration_factor 改为 10 并重跑 3 个 cycle"，让它直接改文件并执行。
- **排障**：遇到报错时把 Traceback 全文贴给它，配合读源码能快速定位。

> **注意**：Claude Code 会执行实际命令（包括写文件）。处理重要代码前 `git commit` 一次是好习惯。

---

## 7. 日常工作流

### 每次开新终端干活

```bash
cd ~/code/libquiv_aging_py
conda activate libquiv-aging
# ... 开始工作 ...
```

### 结束时

```bash
conda deactivate
```

（不退出也没关系，关闭终端即可。）

---

## 8. 常用环境维护命令

| 任务 | 命令 |
| --- | --- |
| 列出所有 conda 环境 | `conda env list` |
| 列出当前环境的所有包 | `conda list` |
| 临时装一个新包 | `conda install -c conda-forge <package>` |
| 更新单个包 | `conda update -c conda-forge <package>` |
| 更新环境到匹配 yml (你改过 yml 后) | `conda env update -f environment.yml --prune` |
| 导出当前环境（跨机器复现） | `conda env export --from-history > my_env.yml` |
| 删除环境（准备重装） | `conda env remove -n libquiv-aging` |

### conda vs pip 混用原则

很多教程会警告 conda + pip 混用会破坏环境。核心规则：

> **永远先装完所有 conda 依赖，再用 pip 装那些只有 pip 才有的包。**

本工程的 `environment.yml` 已经把这个顺序内建好了：先装 conda 里的 numpy/scipy/matplotlib 等，最后用 `pip: - -e .` 装本工程本身（因为 editable install 是 pip 的特性）。

你自己加新依赖时也遵循这条：能走 conda-forge 的优先走 conda，只有 conda-forge 上没有的才用 pip。

---

## 9. 常见问题

| 症状 | 解决 |
| --- | --- |
| `conda env create` 卡在 Solving environment 很久 | 先 `conda install -n base mamba`，再用 `mamba env create -f environment.yml` |
| `ResolvePackageNotFound: python=3.11` | `environment.yml` 缺 `channels:` 段，或只有 `defaults`；确保包含 `conda-forge` |
| Apple Silicon 下某些包报 "not available for osx-arm64" | 确认用的是 Miniforge 或 Miniconda arm64 版；若用 Intel 版的 Anaconda，某些包在 arm64 下没预编译 |
| VS Code 找不到 `libquiv_aging` | 左下角 interpreter 必须是 `libquiv-aging` 环境下的 Python；重启 VS Code |
| `claude` 命令不存在 | 重开终端让 PATH 刷新；检查 `which claude` |
| `matplotlib` 窗口不弹出 | macOS 需要 `backend = MacOSX` 或 `TkAgg`；或用 `matplotlib.use('Agg')` + 保存 PNG |
| 仿真报 `NaN in RHS` | 参数敏感性问题；先降 `acceleration_factor` 到 1，检查初值合理性 |
| 想完全重装环境 | `conda env remove -n libquiv-aging` → `conda env create -f environment.yml` |

---

## 10. 下一步

环境搭好之后，强烈建议按顺序读：

1. **`docs/02_model_overview.md`** —— 理解模型数学结构（是什么、怎么算）。
2. **`docs/03_inputs_guide.md`** —— 理解需要哪些输入、如何自己测量。
3. **`docs/04_outputs_guide.md`** —— 理解输出含义、如何评估。
4. **`docs/05_workflow_examples.md`** —— 看具体工作流。

或者直接用 Claude Code："`帮我按 docs/02_model_overview.md 的顺序讲一遍，遇到核心公式就打开对应代码指给我看`"。
