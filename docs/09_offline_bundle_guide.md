# 离线工作站安装指南 (内部 pip 镜像单轨制)

本文档描述如何将 libquiv-aging 从联网 macOS 开发机部署到离线 Linux 工作站。

---

## 一、方案定位

离线工作站通过内部 pip 镜像重建 Python 环境。联网 macOS 上维护代码仓库与依赖声明，通过 git bundle 或源码快照搬运到离线工作站，离线工作站使用内部 pip 镜像完成依赖安装。整个流程不依赖公网，但依赖内部镜像站的可用性。

本方案不提供离线 wheel 归档路径。物理传输带宽限制使大文件（几百 MB）交付不现实，且内部 pip 镜像作为企业基础设施由 IT 部门保障可用性，在本工程范围内不做冗余备份。若内部 pip 镜像发生不可恢复失效，属于基础设施级事件，应通过 IT 协作而非工程内部归档处理。

---

## 二、离线工作站的前置条件

Python 3.11 必须已安装。Ubuntu 20.04 默认 Python 为 3.8，需通过 deadsnakes PPA 或内部 apt 镜像安装 3.11。

离线机的 pip 配置由 IT 部门统一分发，确保 `index-url` 指向内部镜像站。使用者无需手动配置。如需验证配置是否就位，可执行以下命令查看当前生效的 index-url，具体值属内部基础设施信息，不在本文档记录：

```bash
python3.11 -m pip config list -v
```

若验证时发现 pip 未配置内部镜像，先与 IT 协调修复配置，再执行后续安装流程。不要尝试手工修改 `/etc/pip.conf` 或用户级配置，这类改动可能与内部策略冲突。

---

## 三、操作流程

### 3.1 联网 macOS：打包源码

在联网 macOS 上，将项目打包为 git bundle 或压缩归档。git bundle 是推荐方式，因为它保留完整的 git 历史：

```bash
# 方式一: git bundle (推荐)
cd libquiv_aging_py
git bundle create libquiv-aging.bundle --all
# 将 libquiv-aging.bundle 拷贝到 U 盘或上传到内部 Git 服务器

# 方式二: 源码压缩包 (不保留 git 历史)
tar czf libquiv-aging-src.tar.gz \
    --exclude='.venv' --exclude='dist' --exclude='__pycache__' \
    --exclude='.mypy_cache' --exclude='.pytest_cache' \
    --exclude='*.egg-info' --exclude='.claude' \
    libquiv_aging_py/
```

### 3.2 离线 Linux：解包

```bash
# 方式一: 从 git bundle 恢复
git clone libquiv-aging.bundle libquiv_aging_py
cd libquiv_aging_py

# 方式二: 从压缩包解包
tar xzf libquiv-aging-src.tar.gz
cd libquiv_aging_py
```

### 3.3 离线 Linux：安装

```bash
# 一键安装 (创建 venv, 安装依赖, 安装项目)
bash scripts/install_offline.sh
```

该脚本依次执行：创建 `.venv` 虚拟环境、升级 pip/setuptools/wheel、按 `requirements.txt` 的精确版本安装所有依赖、以 editable 模式安装 libquiv-aging 本身。

### 3.4 离线 Linux：验证

```bash
source .venv/bin/activate
bash scripts/verify_install.sh
```

验证脚本检查 Python 版本（必须为 3.11.x）、`import libquiv_aging` 是否成功、pytest 测试套件是否全通过、smoke test 是否正常运行。全部通过后即可进入正常工作流。

---

## 四、版本锁定的职责转变

`environment-frozen.yml` 的职责由原来的"提供二进制包本身"转变为"声明精确版本号"。即使内部镜像站提供了更新版本，也应严格按 frozen.yml 的版本安装，否则开发机与实验机的环境发生漂移，ENV-E001 的检测语义也失去意义。

`requirements.txt` 从 `environment-frozen.yml` 机器派生，两份文件的一致性由 `scripts/build_requirements.sh` 脚本保证。当 conda 环境发生任何变更（新增包、升级版本）时，应重新导出 `environment-frozen.yml`，然后运行 `build_requirements.sh` 重新生成 `requirements.txt`，确保两侧同步。

依赖更新的标准流程是：

```
conda 环境变更 → conda env export → environment-frozen.yml
                                    → bash scripts/build_requirements.sh
                                    → requirements.txt
                                    → git commit 两者
```

---

## 五、已知失败模式与应对

依赖安装时报 `No matching distribution found`，通常表示 `requirements.txt` 中的某个包或版本未进入内部镜像索引。应对顺序是：首先确认内部镜像能访问（直接浏览镜像站首页或尝试 `pip index versions <package-name>`），其次确认该包名与版本在 PyPI 上真实存在（可能是 conda→PyPI 的包名映射有误），最后与 IT 协调将缺失包加入白名单。不应通过放松版本约束绕过此错误，会破坏环境一致性。此失败模式将在后续单独追加为 ENV-E002 错误码。

`pip install -e .` 报错通常表示 `setuptools` 版本不够新。`install_offline.sh` 在安装依赖前已执行 `pip install --upgrade pip setuptools wheel`，正常情况下不会出现此问题。若仍报错，检查内部镜像上 setuptools 的最新可用版本。

在 Ubuntu 20.04 上，如果系统 glibc 版本低于某些 wheel 的编译要求（glibc >= 2.28 对应 Ubuntu 18.04+，Ubuntu 20.04 的 glibc 2.31 满足此要求），pip 会回退到源码编译，可能因缺少编译工具链（gcc、python3.11-dev）而失败。此时应通过内部 apt 镜像安装 `build-essential` 和 `python3.11-dev`。

---

## §六 作用范围说明

本文档针对当前实验室离线机配置 (Ubuntu 20.04+, x86_64, Python 3.11,
内部 pip 镜像可达) 撰写。如未来目标平台或网络配置发生变化, 本文档
需重新评估, 不保证对其他配置有效。
