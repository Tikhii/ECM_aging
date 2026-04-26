# Fractional-order RC / DRT 升级文献入口

> **状态**: 占位 (literature starter pack)。本文件不锁定升级方案,
> 仅汇总 C7 (`docs/CRITICAL_REVIEW.md`) 升级路径上的候选模型与必读文献,
> 供后续 v0.6+ 任务包评估。
>
> 本目录 `docs/UPGRADE_LITERATURE/` 是按"升级方向"组织的资料索引,
> 不是规范文档, 不进入 R5 一致性扫描范围。
>
> 文献条目按 A/B/C/D/E 五类组织 (综述 / 方法 / 物理 / 实施 / 工具)。
> 所有条目默认标 `[verified: pending]`, 因未亲自核对 DOI / 卷期 / 页码;
> 完成实物核对后改为 `[verified: yes]`。

---

## §1 触发动机 (与 C7 对齐)

`docs/CRITICAL_REVIEW.md` C7 RC 拓扑对长弛豫的不足 指出: 二阶 RC 模型 (FIT-2
当前实现) 无法稳定描述长弛豫窗内的扩散控制 / 分布式界面响应。FIT2-E003
(`docs/07_offline_runbook.md §4`) 在 RMSE 越过失败阈值时把数据归档而拒绝写回,
即指向本文件描述的升级路径。

判别 "是否到了非升级不可" 的现场指标:
- 弛豫窗 ≥ 5τ2 后, 残差仍呈现单调对数尾 (扩散主导)
- 不同 SOC / 温度下 τ2 的 Arrhenius 斜率与文献界面化学不一致
- two_exponential 拟合的 σ_C2 / C2 量级 ≥ 1 但 RMSE 仍勉强通过

满足任一条即应启动 C7 升级评估。

---

## §2 候选模型方向

### 2.1 Fractional-order ECM (with Constant Phase Element)

把第二个 RC 用 R-CPE (constant phase element, 阻抗 $1/(Q (j\omega)^\alpha)$)
替换, 弛豫核从 exp(-t/τ) 变为 Mittag-Leffler 函数。

- 优点: 解析形式仍在, 参数仅多一个 α∈(0,1] 表征分布度
- 缺点: 时域拟合需要 Mittag-Leffler 函数实现 (`mpmath.mittag_leffler`
  或 numerical inverse Laplace)
- 适合判据: 残差形状是单调对数尾, 不是阶跃或周期

### 2.2 Distribution of Relaxation Times (DRT)

不假定有限离散 RC, 直接反演 G(τ) 分布。常见数值实现走 Tikhonov 正则化或
贝叶斯 (Hilbert / Gaussian process)。

- 优点: 模型选择自由度最大, 直接给出哪些 τ 尺度被激发
- 缺点: 反问题不适定, 正则化超参选择敏感; 写回 spec 时需把 G(τ) 离散化
  成有限 Ci 才能与现有参数 schema 兼容
- 适合判据: 残差形状显示多于 2 个时间常数, 或 SOC/温度扫描下 τ 谱形态
  显著漂移

### 2.3 Warburg + 2RC (有限扩散)

在第二阶 RC 之后串接有限长度 Warburg, 显式建模扩散层。

- 优点: 物理意义最直接, 时常数有明确扩散系数解释
- 缺点: 参数增多 (Warburg 三个独立参数), 与 FIT-3 电阻分配的耦合需重证
- 适合判据: 弛豫长尾随 SOC 单调变化, 且变化方向与扩散层厚度估计一致

---

## §3 文献 starter pack

### A 综述 (先读这一类建立总览)

**[A1]** Freeborn, Maundy, Elwakil 2015. "Fractional-order models of supercapacitors, batteries and fuel cells: a survey." Mater. Renew. Sustain. Energy 4:9. [verified: pending]
- 历史最早、引用率最高的综述, 从 super-capacitor 起步建立 fractional ECM 的统一视角, 直接给出 Mittag-Leffler 表达。建议首读。

**[A2]** Sabatier 2008. "Fractional system identification: an overview." Automatica 44:2274-2284. [verified: pending]
- 分数阶系统辨识的工程综述, 覆盖时域 / 频域 / 状态空间方法, 是 fractional ECM 在系统识别角度的入口。

**[A3]** Wang, Tian, Shu, Wei 2017. "A review of fractional-order modeling for lithium-ion batteries." J. Power Sources 363:30-44. [verified: pending]
- 锂电池场景下的 fractional ECM 综述, 把工程实施 (在线辨识、SOC 观测) 与理论根基对齐。

### B 方法学 (拟合算法 / 数值实现)

**[B1]** Garrappa 2015. "Numerical evaluation of two and three parameter Mittag-Leffler functions." Mathematics 3:368-389. [verified: pending]
- Mittag-Leffler 函数高精度数值算法, MATLAB 实现 `ml.m` 是事实标准, Python 端可用 `mpmath.mittag_leffler` 或 `numfracpy` 复现。

**[B2]** Wan, Saccoccio, Chen, Ciucci 2015. "Influence of the discretization methods on the distribution of relaxation times deconvolution: implementing radial basis functions with DRTtools." Electrochim. Acta 184:483-499. [verified: pending]
- DRT 反演的事实标准实现 (DRTtools), 详述 radial basis function 离散化, 给后续 Python 复现提供算法蓝本。

**[B3]** Saccoccio, Wan, Chen, Ciucci 2014. "Optimal regularization in distribution of relaxation times applied to electrochemical impedance spectroscopy: ridge and Lasso regression methods — a theoretical and experimental study." Electrochim. Acta 147:470-482. [verified: pending]
- 在 DRT 反问题里对比 ridge 与 Lasso 正则化, 给出超参选择的理论基础, 是 starter pack 中数值适定性的硬核入口。

**[B4]** Ciucci 2019. "Modeling electrochemical impedance spectroscopy." Curr. Opin. Electrochem. 13:132-139. [verified: pending]
- 贝叶斯 / Gaussian-process DRT 路径的最近综述, 列出何时用频域 EIS、何时用时域弛豫数据更优。

### C 物理基础 (CPE / 普适介电响应 / Warburg)

**[C1]** Warburg 1899. "Über das Verhalten sogenannter unpolarisierbarer Elektroden gegen Wechselstrom." Ann. Phys. Chem. 67:493-499. [verified: pending]
- Warburg 阻抗 ω^{-1/2} 形式的原始论文, 扩散控制阻抗的物理起点。锂电池长弛豫的 "对数尾" 残差形状根源在此。

**[C2]** Jonscher 1977. "The 'universal' dielectric response." Nature 267:673-679. [verified: pending]
- 提出 "普适介电响应" 概念, 把幂律频率响应作为材料普遍现象, 远超出锂电池范畴。这是把 CPE 行为从工程现象提升到物理普适性的源头。

**[C3]** Bisquert 2002. "Theory of the impedance of electron diffusion and recombination in a thin layer." Phys. Chem. Chem. Phys. 4:5360-5364. [verified: pending]
- 有限长度 Warburg 在时域响应的解析推导, 解释为什么扩散主导段在长 t 下退化为对数尾而非纯指数。

**[C4]** Huang, Zhang 2020. "Mathematical modeling of impedance spectroscopy and its application to battery research." J. Electrochem. Soc. 167:166517. [verified: pending]
- 把扩散阻抗的时频映射讲清楚, 锂电池场景的桥梁文献, 给 Warburg + 2RC 候选 (§2.3) 提供工程化推导。

### D 实施 (锂电池场景的工程 case studies)

**[D1]** Wang, Wei, Hu, Tian, Shu 2018. "A novel multistage online estimation algorithm of state of charge for fractional-order battery model." Microelectron. Reliab. 88-90:1187-1192. [verified: pending]
- 在线 SOC 估计场景的 fractional ECM 工程实施, 演示如何把分数阶模型嵌入实时观测器。

**[D2]** Hu, Yurkovich, Guezennec, Yurkovich 2011. "Electro-thermal battery model identification for automotive applications." J. Power Sources 196:449-457. [verified: pending]
- 经典 2RC 模型在车载场景的工程实施, 是 starter pack 中描述 "保留 two_exponential 作为兼容回退" 的工业先例。

**[D3]** Jossen 2006. "Fundamentals of battery dynamics." J. Power Sources 154:530-538. [verified: pending]
- 锂电池弛豫窗内多时间尺度叠加的物理诠释, 是 DRT 升级 (§2.2) 选型动机的最早硬证据之一。

### E 工具 (开源实现可直接复用)

**[E1]** Garrappa 2018. "Numerical solution of fractional differential equations: a survey and a software tutorial." Mathematics 6:16. [verified: pending]
- 分数阶 ODE 的数值积分综述 + Python `numfracpy` 教程, FIT-2 升级到 fractional 时的工具入口。

**[E2]** Plett 2015. Battery Management Systems Vol. II: Equivalent-Circuit Methods. Artech House. ISBN 978-1-63081-027-5. [verified: pending]
- BMS 工程经典教材, ECM 章节给出 RC ladder 的工程实施细节, 与 fractional / DRT 升级路径对照能看清各方案的工程化代价。

**[E3]** DRTtools (MATLAB), Ciucci group 维护. https://github.com/ciuccislab/DRTtools [verified: pending]
- DRT 反演的开源参考实现, Python 端有 `pyDRTtools` 副本; 任何 DRT 升级路径都应先在 DRTtools 上跑一次基准。

**[E4]** Mittag-Leffler 函数的 Python 实现: `mpmath.mittag_leffler` (高精度) / `numfracpy` (数值高效). [verified: pending]
- 评估 fractional / Mittag-Leffler 候选时的代码层依赖, 选型时需对比精度 / 速度 / `pcov` 可估性。

---

## §4 与 RELAXATION_MODELS dispatch 的接口约定

`libquiv_aging/relaxation_fitting.py::RELAXATION_MODELS` 是 dict[str, callable]
分发表。升级模型登记接口:

```python
RELAXATION_MODELS = {
    "two_exponential": fit_two_exponential_relaxation,   # 当前
    # "fractional_order": fit_fractional_order_relaxation,  # 候选 2.1
    # "drt": fit_drt_relaxation,                             # 候选 2.2
    # "warburg_2rc": fit_warburg_2rc_relaxation,             # 候选 2.3
}
```

升级模型的 fit 函数必须返回与 `fit_two_exponential_relaxation` 同 schema 的
dict, 至少含: `V_inf`, `rmse`, `r_squared`, `converged`, `pcov`,
以及该模型特定的物理参数; 物理参数到 (C1, C2) 的映射规则由各模型自行定义并
持久化到 `relaxation_metadata` 字段。

CLI 入口 `scripts/fit_rc_transient.py --relaxation-model <name>` 通过
`get_relaxation_model(name)` 查表获取拟合函数, 不需要修改 CLI 主流程。

---

## §5 升级评估清单 (供 v0.6+ 任务包初始化时复用)

- [ ] 收集 ≥3 个 SOC × ≥2 个温度的 EXP-B4 弛豫数据, 计算 two_exponential
      残差形态特征 (单调尾 / 多尺度 / 周期), 判定主导机制
- [ ] 选定首个升级目标 (2.1 / 2.2 / 2.3 之一), 写到 `PARAMETERS.json::
      deferred_extensions::C7_RC_topology` 的 `chosen_path` 字段
- [ ] 写新 fit 函数, 在 `tests/test_relaxation_fitting.py` 添加合成数据
      回归测试
- [ ] 在 `RELAXATION_MODELS` 注册新键, 验证 `--relaxation-model <new>` 在
      合成数据上能稳定收敛
- [ ] 把 C7 finding 状态从 `open` 改为 `addressed_v0.X`, 更新
      `docs/CRITICAL_REVIEW.md` C7 小节的"判断"段
- [ ] 按 R5/R6/R8 同步 SOP / runbook / README / QUICKSTART
- [ ] 把本文件中实际采用的文献条目从 `[verified: pending]` 升级为
      `[verified: yes]` (亲自核对 DOI / 卷期后再改)
