# 计算机学报论文撰写大纲

## 论文元信息

- **标题：** 大语言模型增强的自下而上数据对象归纳抽取方法
- **英文标题：** LLM-Enhanced Bottom-Up Inductive Extraction of Data Objects from Enterprise Data Architectures
- **目标期刊：** 计算机学报（CCF-A中文期刊）
- **预计正文：** 10000-12000字（不含参考文献）
- **应用背景：** 南方电网数据架构治理

---

## 0. 摘要（约300字）

**结构：背景 → 问题 → 方法 → 实验 → 结论**

### 要点
- **背景**：企业数据架构文档包含概念实体、逻辑实体、物理实体三层结构，统一的数据对象模型是数据治理的基础
- **问题**：传统方法依赖领域专家自顶向下手工建模，成本高、一致性差、难以规模化
- **方法**：提出"语义聚类 + 大语言模型归纳命名"的自下而上混合抽取方法
  - (1) 利用中文预训练语义模型（SBERT）将实体名称映射到语义空间
  - (2) 提出基于轮廓系数与领域语义一致性的双目标优化算法自适应确定聚类数量
  - (3) 设计正向归纳-反向验证-一致性评分的LLM质量控制框架
- **实验**：在南方电网X个数据域、共Y个实体上验证，结果表明...（待补充具体数值）
- **关键词**：数据对象抽取；语义聚类；大语言模型；数据架构；本体归纳

---

## 1. 引言（约1500字）

### 1.1 研究背景（约500字）
- 企业数字化转型背景下，数据治理成为核心需求
- 数据架构文档的三层结构是国内大型企业（央企、国企）的标准规范
  - 概念实体（Concept Entity）：业务场景层，对应DA-01表
  - 逻辑实体（Logical Entity）：交互形式层，对应DA-02表
  - 物理实体（Physical Entity）：数据库层，对应DA-03表
- "数据对象"是比实体更高一层的抽象概念，如"项目"、"设备"、"资产"
- 建立对象与三层实体的关联关系是构建统一数据模型、实现数据资产目录的关键

### 1.2 问题与挑战（约500字）
- **挑战1：抽象粒度难以把握** — 对象需要足够抽象（如"设备"而非"变压器"），但又不能过于宽泛
- **挑战2：人工建模成本高** — 一个数据域可能有数百个实体，人工归纳耗时且主观性强
- **挑战3：跨域一致性差** — 不同领域专家对同一概念的抽象粒度不一致
- **挑战4：命名规范性** — 抽取的对象需要命名准确、语义清晰、符合行业惯例

### 1.3 本文贡献（约500字）
- **(1)** 提出自下而上的数据对象归纳抽取范式，区别于传统自顶向下的预定义匹配方法。形式化定义了对象抽取的三个优化目标：完备性（Coverage）、粒度最优性（Granularity）、语义一致性（Coherence）
- **(2)** 设计了基于轮廓系数与领域语义一致性的双目标优化算法，自适应确定最优聚类数量，解决了固定聚类数的局限性
- **(3)** 构建了"正向归纳→反向验证→一致性评分"的LLM命名质量控制框架，有效提升了对象命名的准确性和可靠性
- **(4)** 在南方电网真实数据架构上进行了系统实验验证

---

## 2. 相关工作（约2000字）

### 2.1 本体学习与概念抽取（约600字）
- 从非结构化文本中学习本体的经典方法（Maedche & Staab 2001等）
- 基于模式匹配、统计方法、深度学习的概念抽取
- **差异点**：现有方法面向自由文本或Web数据，本文面向结构化的三层架构文档

### 2.2 文本聚类与语义表示（约400字）
- 传统文本聚类：TF-IDF + K-Means
- 预训练语义模型：BERT、SBERT（Reimers & Gurevych 2019）
- 中文语义模型：text2vec（shibing624）
- 短文本聚类的挑战与解决方案

### 2.3 大语言模型在数据管理中的应用（约600字）
- Text-to-SQL / NL2SQL（DAIL-SQL, DIN-SQL等）
- Schema Matching with LLM（Narayan et al. 2022等）
- LLM for Data Integration（Arora et al. 2023等）
- LLM for Data Cleaning（Narayan et al. 2022等）
- **差异点**：现有LLM+数据管理的工作集中在查询生成和数据集成，本文首次探索LLM在数据对象发现/本体归纳中的应用

### 2.4 数据治理与数据对象建模（约400字）
- DAMA-DMBOK数据管理知识体系
- 数据中台方法论中的数据对象层
- 国内央企数据架构标准（三层架构规范）
- 现有工具（如ERWin、PowerDesigner）的局限性——仅支持自顶向下建模

---

## 3. 问题定义（约1500字）

### 3.1 三层数据架构模型

**定义1（三层实体集合）：**
给定一个数据域 D，其三层数据架构表示为 A(D) = (E_c, E_l, E_p, M_cl, M_lp)，其中：
- E_c = {e_c^1, ..., e_c^m} 为概念实体集合
- E_l = {e_l^1, ..., e_l^n} 为逻辑实体集合
- E_p = {e_p^1, ..., e_p^q} 为物理实体集合
- M_cl: E_c → P(E_l) 为概念-逻辑层间映射
- M_lp: E_l → P(E_p) 为逻辑-物理层间映射

> 在代码中，这三层分别对应 DA-01/DA-02/DA-03 三个sheet，层间映射通过 `_build_concept_logical_mapping`（object_extractor.py:488-552）和 `_build_logical_physical_mapping`（object_extractor.py:554-589）构建

### 3.2 数据对象

**定义2（数据对象）：**
数据对象 o = (name, type, R) 是对一组语义相关实体的高度抽象概括，其中：
- name 为对象名称（如"项目"、"设备"）
- type ∈ {CORE, DERIVED, AUXILIARY} 为对象类型
- R(o) ⊆ E_c 为该对象关联的概念实体子集

> 代码中对应 `ExtractedObject` 数据类（object_extractor.py:86-102），type对应object_type字段

### 3.3 优化目标

**定义3（对象抽取问题）：**
给定三层架构 A(D)，目标是找到对象集合 O* = {o_1, ..., o_k} 使得：

**(a) 完备性 Coverage(O, E_c)**：
Coverage(O, E_c) = |∪_{o∈O} R(o)| / |E_c|
要求 Coverage → 1，即每个概念实体至少被一个对象覆盖

**(b) 粒度最优性 Granularity(O)**：
Granularity(O) = -∑_{o∈O} (|R(o)|/|E_c|) · log(|R(o)|/|E_c|)
信息熵度量，过粗（一个对象包含所有实体）和过细（每个实体一个对象）的粒度都会降低该值

**(c) 语义一致性 Coherence(o)**：
Coherence(o) = (1/|R(o)|^2) · ∑_{e_i, e_j ∈ R(o)} cos(v(e_i), v(e_j))
其中 v(e) 为实体 e 的SBERT向量表示

> 当前代码中仅隐式优化了Coherence（通过聚类实现），未显式优化Coverage和Granularity

---

## 4. 方法（约5000字）

### 4.1 总体框架（约500字）

**图1：方法总体框架图**

```
┌─────────────────────────────────────────────────────────────────┐
│                     输入：三层架构文档                              │
│              DA-01(概念) / DA-02(逻辑) / DA-03(物理)              │
└────────────┬────────────────────────────────────────────────────┘
             ▼
┌─────────────────────────┐
│  Phase 1: 实体收集与预处理  │  → 概念实体名称集合 E_c
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│  Phase 2: SBERT语义向量化  │  → 768维向量矩阵 V ∈ R^{m×768}
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│  Phase 3: 自适应语义聚类   │  → 聚类标签 L = {l_1,...,l_m}，最优聚类数 k*
│  (双目标优化确定k*)       │
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│  Phase 4: LLM归纳命名     │  → 初始对象集合 O_init
│  (结构化Prompt)           │
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│  Phase 5: 质量控制        │  → 验证后对象集合 O_verified
│  (正向归纳→反向验证→评分)  │
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│  Phase 6: 约束后处理+输出  │  → 最终对象集合 O* + 三层关联
│  (必须对象、去重、层级关联) │
└─────────────────────────┘
```

- 6个阶段的概述和设计动机
- 代码对应关系：`SemanticObjectExtractionPipeline`（object_extractor.py:1380-1482）编排整个流程

### 4.2 实体收集与SBERT语义向量化（约600字）

- 从DA-01 sheet中提取概念实体名称作为聚类输入
  - 代码：`DataArchitectureReader._read_concept_entities`（object_extractor.py:246-248）
  - 实体信息保留：name, layer, code, data_domain, source_file等元数据
- SBERT向量化
  - 模型：shibing624/text2vec-base-chinese，输出768维向量
  - 代码：`SemanticClusterExtractor._vectorize_entities`（object_extractor.py:684-702）
  - 批处理：batch_size=64
- 讨论中文短文本（2-8字实体名）的语义表示挑战

### 4.3 自适应聚类数确定算法（约1500字）—— 创新点2

#### 4.3.1 现有方法的局限
- 当前启发式：`n_clusters = min(target, max(5, n_samples // 10))`（object_extractor.py:714）
- 问题：(a)依赖人工设定target参数；(b)不同数据域的最优k差异大；(c)缺乏理论依据

#### 4.3.2 双目标优化框架

**目标1 — 聚类结构质量 S(k)：**
S(k) = SilhouetteScore(V, L_k)
其中 L_k 是k个聚类下的标签分配

**目标2 — 领域语义一致性 DSC(k)：**
DSC(k) = (1/k) · ∑_{j=1}^{k} Coherence(C_j)
其中 Coherence(C_j) 按照定义3(c)计算

**双目标优化：**
k* = argmax_{k∈[k_min, k_max]} α·S(k) + (1-α)·DSC(k)
其中 α 为平衡参数，可通过交叉验证确定

**算法1：自适应聚类数确定**
```
输入：向量矩阵 V，搜索范围 [k_min, k_max]，平衡参数 α
输出：最优聚类数 k*

1. FOR k = k_min TO k_max:
2.   L_k ← AgglomerativeClustering(V, k, metric='cosine', linkage='average')
3.   S(k) ← SilhouetteScore(V, L_k)
4.   DSC(k) ← (1/k)·∑_j Coherence(C_j^k)
5.   Score(k) ← α·Normalize(S(k)) + (1-α)·Normalize(DSC(k))
6. END FOR
7. k* ← argmax_k Score(k)
8. RETURN k*
```

#### 4.3.3 复杂度分析
- 时间复杂度：O((k_max - k_min) · m^2 · d)，其中m为实体数，d为向量维度
- 实际搜索范围较小（如5-30），开销可接受

**图2：** k值变化时S(k)和DSC(k)的曲线图（实验中补充）

### 4.4 LLM归纳命名（约1000字）

#### 4.4.1 结构化Prompt设计
- 基于现有prompt（object_extractor.py:813-846）的改进
- Prompt组成：角色设定 + 任务描述 + 约束条件 + 聚类数据 + 输出格式
- 输出要求：JSON格式包含 object_code, object_name, object_name_en, object_type, description, synonyms, key_attributes, confidence, reasoning
- temperature=0.3（低随机性）

#### 4.4.2 规则备选机制
- 关键词映射表（object_extractor.py:950-978）：22个关键词 → 11个标准对象
- Counter投票机制（object_extractor.py:984-989）：统计聚类内各关键词频率，选最高频对应对象
- 触发条件：LLM API不可用 或 LLM输出解析失败

### 4.5 LLM质量控制框架（约1500字）—— 创新点3

#### 4.5.1 正向归纳（Forward Induction）
- 即4.4节的LLM命名过程
- 输出：每个聚类的对象名称 name_j 和置信度 conf_j

#### 4.5.2 反向验证（Reverse Verification）
**核心思想**：如果一个对象名是正确的，那么LLM应该能够判断聚类中的实体确实属于该对象

**Prompt设计（反向验证）：**
```
给定数据对象"{object_name}"（{description}），
请判断以下实体是否属于该对象，输出每个实体的归属概率(0-1)：
[实体列表]
```

- 输出：每个实体的归属概率 p(e_i ∈ o_j)

#### 4.5.3 一致性评分（Consistency Score）

**定义4（命名一致性分数）：**
CS(o_j) = (1/|S_j|) · ∑_{e_i ∈ S_j} p(e_i ∈ o_j)
其中 S_j 为聚类 j 的样本实体集合

**决策规则：**
- CS >= θ_high（如0.8）：接受命名
- θ_low <= CS < θ_high（如0.5-0.8）：触发重命名（调整prompt重新调用LLM）
- CS < θ_low（如0.5）：触发聚类拆分（该聚类可能包含了不相关的实体）

**算法2：LLM质量控制流程**
```
输入：聚类集合 {C_1,...,C_k}，阈值 θ_high, θ_low, 最大重试次数 T
输出：验证后的对象集合 O_verified

1. O_init ← ForwardInduction({C_1,...,C_k})  // 正向归纳
2. FOR EACH o_j IN O_init:
3.   CS_j ← ReverseVerify(o_j, C_j)  // 反向验证
4.   IF CS_j >= θ_high:
5.     O_verified ← O_verified ∪ {o_j}  // 接受
6.   ELSE IF CS_j >= θ_low:
7.     retry ← 0
8.     WHILE retry < T AND CS_j < θ_high:
9.       o_j' ← ReInduction(C_j, feedback=low_score_entities)  // 带反馈的重命名
10.      CS_j ← ReverseVerify(o_j', C_j)
11.      retry ← retry + 1
12.    O_verified ← O_verified ∪ {o_j'}
13.  ELSE:
14.    {C_j1, C_j2} ← SplitCluster(C_j)  // 聚类拆分
15.    递归处理 C_j1, C_j2
16. RETURN O_verified
```

**图3：** 质量控制流程图

### 4.6 约束后处理与层级关联构建（约900字）

#### 4.6.1 必须对象约束
- 某些对象是业务必须的（如"项目"为甲方硬性要求）
- 泛化为约束集合 Ω = {name_1, ..., name_r}
- 当必须对象未被抽出时，在聚类中搜索最相关的聚类强制添加
- 代码对应：`_ensure_required_objects`（object_extractor.py:915-943）

#### 4.6.2 对象去重与合并
- 基于对象名称和同义词的去重
- 编辑距离 + 语义相似度的混合去重策略

#### 4.6.3 层级关联构建
- Object → 概念实体：DIRECT关联（聚类归属），strength=0.9/0.8
- Object → 逻辑实体：INDIRECT关联（通过概念-逻辑映射M_cl），strength=0.7
- Object → 物理实体：INDIRECT关联（通过逻辑-物理映射M_lp），strength=0.6
- 代码对应：`HierarchicalRelationBuilder`（object_extractor.py:1102-1210）

**图4：** 层级关联关系示意图（Object→Concept→Logical→Physical）

---

## 5. 实验（约3000字）

### 5.1 实验设置（约600字）

#### 5.1.1 数据集

**表1：实验数据集统计**
| 数据域 | 文件数 | 概念实体数 | 逻辑实体数 | 物理实体数 | 总实体数 |
|--------|--------|-----------|-----------|-----------|---------|
| 输配电 | 3 | (统计) | (统计) | (统计) | (统计) |
| (扩展域)| ... | ... | ... | ... | ... |

- 数据来源：南方电网数据架构文档（DA-01/02/03表）
- 数据文件：DATA/1.xlsx, DATA/2.xlsx, DATA/3.xlsx

#### 5.1.2 实验环境
- Python 3.10+, SBERT (text2vec-base-chinese), scikit-learn
- LLM: DeepSeek-Chat (API调用)
- 硬件环境：(补充)

#### 5.1.3 参数设置
| 参数 | 值 | 说明 |
|------|-----|------|
| SBERT模型 | text2vec-base-chinese | 768维中文语义向量 |
| 聚类方法 | AgglomerativeClustering | cosine距离，average链接 |
| k搜索范围 | [5, 30] | 聚类数搜索区间 |
| α（平衡参数）| 0.5 | S(k)和DSC(k)的权重 |
| θ_high | 0.8 | 质量控制高阈值 |
| θ_low | 0.5 | 质量控制低阈值 |
| LLM temperature | 0.3 | 低随机性 |
| 最大重试次数T | 3 | 质量控制最大重命名次数 |

### 5.2 评价指标（约400字）

**对象质量指标：**
- **Expert-Match Rate (EMR)**：抽取的对象与领域专家标注对象的匹配率
- **Coverage**：定义3(a)的完备性
- **Avg-Coherence**：所有对象的平均语义一致性
- **Granularity Score**：定义3(b)的粒度最优性

**命名质量指标：**
- **Naming Accuracy (NA)**：LLM命名与专家命名的完全匹配率
- **Semantic Naming Similarity (SNS)**：LLM命名与专家命名的语义相似度

**聚类质量指标：**
- **Silhouette Score**
- **Calinski-Harabasz Index**

### 5.3 对比方法（约400字）

**表2：对比方法**
| 方法 | 描述 | 对应代码 |
|------|------|---------|
| **Rule-Only** | 仅使用关键词映射表 | `_rule_based_naming` (line 945) |
| **Cluster-Only** | SBERT聚类 + 中心实体作为对象名（无LLM） | 修改pipeline跳过LLM |
| **LLM-Direct** | 将所有实体直接交给LLM分组命名（无聚类） | 新增baseline |
| **Fixed-K** | SBERT聚类(固定k=15) + LLM命名（无自适应k、无质量控制） | 当前代码默认行为 |
| **Ours-NoQC** | 自适应k + LLM命名（无质量控制） | 去除Phase 5 |
| **Ours** | 完整方法（自适应k + LLM + 质量控制） | 完整pipeline |

### 5.4 主要实验结果（约800字）

**表3：各方法在对象抽取任务上的性能对比**
| 方法 | EMR | Coverage | Avg-Coherence | Granularity | NA |
|------|-----|----------|---------------|-------------|-----|
| Rule-Only | | | | | |
| Cluster-Only | | | | | |
| LLM-Direct | | | | | |
| Fixed-K | | | | | |
| Ours-NoQC | | | | | |
| **Ours** | | | | | |

（实验数据待运行后填充）

**分析要点：**
- Ours vs Rule-Only：验证自下而上范式优于关键词匹配
- Ours vs Cluster-Only：验证LLM命名的必要性
- Ours vs LLM-Direct：验证聚类预处理对LLM的帮助（降低LLM负担、提升一致性）
- Ours vs Fixed-K：验证自适应k的贡献
- Ours vs Ours-NoQC：验证质量控制框架的贡献

### 5.5 消融实验（约400字）

**表4：消融实验**
| 变体 | EMR | Coverage | Avg-Coherence |
|------|-----|----------|---------------|
| Ours (完整) | | | |
| -自适应k（用固定k=15） | | | |
| -反向验证 | | | |
| -领域约束 | | | |
| -规则备选 | | | |

### 5.6 参数敏感性分析（约400字）

**图5：** α值对性能的影响曲线
**图6：** θ_high和θ_low对命名准确率的影响
**图7：** 不同SBERT模型的对比（text2vec-base-chinese vs paraphrase-multilingual-MiniLM-L12-v2 vs 其他）
**图8：** 不同LLM的对比（DeepSeek vs GPT-4 vs Qwen vs GLM-4）

### 5.7 案例分析（约400字）

**表5：抽取对象示例**
| 对象名 | 类型 | 代表性实体 | 聚类大小 | 置信度 | 一致性分数 |
|--------|------|-----------|---------|--------|-----------|
| 项目 | CORE | 项目信息、工程进度信息 | | | |
| 设备 | CORE | 变压器参数、断路器台账 | | | |
| ... | ... | ... | | | |

- 选2-3个典型对象详细分析抽取过程
- 展示质量控制框架的纠正案例（原本命名不佳 → 反向验证发现问题 → 重命名后改善）

---

## 6. 结论与展望（约500字）

### 结论
- 总结本文提出的三个贡献
- 强调自下而上范式的实用价值
- 实验验证了方法的有效性

### 展望
- 跨域对象融合：多个数据域的对象如何统一（引出后续工作）
- 增量式对象更新：新数据导入时如何增量更新对象模型
- 对象层级结构：当前抽取的对象是扁平的，未来可探索对象间的层次关系

---

## 7. 图表清单

| 编号 | 类型 | 内容 |
|------|------|------|
| 图1 | 框架图 | 方法总体框架（6个Phase） |
| 图2 | 折线图 | k值 vs S(k)/DSC(k)曲线 |
| 图3 | 流程图 | 质量控制框架流程 |
| 图4 | 示意图 | 层级关联关系（Object→三层实体） |
| 图5 | 折线图 | α参数敏感性 |
| 图6 | 热力图 | θ_high/θ_low对命名准确率的影响 |
| 图7 | 柱状图 | 不同SBERT模型对比 |
| 图8 | 柱状图 | 不同LLM对比 |
| 表1 | 数据表 | 数据集统计 |
| 表2 | 方法表 | 对比方法描述 |
| 表3 | 结果表 | 主要实验结果 |
| 表4 | 结果表 | 消融实验 |
| 表5 | 案例表 | 抽取对象示例 |

---

## 8. 参考文献方向（约30篇）

### 本体学习
- Maedche & Staab, 2001 (Ontology Learning)
- Wong et al., 2012 (Ontology Learning from Text)

### 语义表示与聚类
- Reimers & Gurevych, 2019 (Sentence-BERT)
- text2vec-base-chinese (shibing624)
- Aggarwal & Zhai, 2012 (Survey on Text Clustering)

### LLM在数据管理
- Narayan et al., 2022 (Can Foundation Models Wrangle Your Data?)
- Li et al., 2023 (Large Language Models for Data Management)
- Arora et al., 2023 (Language Models Enable Simple Systems for Generating Structured Views of Heterogeneous Data Lakes)
- DAIL-SQL, DIN-SQL (Text-to-SQL)

### 数据治理
- DAMA-DMBOK (Data Management Body of Knowledge)
- 国家电网/南方电网数据架构标准文档

### 聚类数确定
- Rousseeuw, 1987 (Silhouettes)
- Calinski & Harabasz, 1974
- Tibshirani et al., 2001 (Gap Statistic)

---

## 9. 需要实现的代码模块

### 新增代码（在 `scripts/object_extractor.py` 中）

| 模块 | 方法名 | 功能 |
|------|--------|------|
| 自适应k | `_adaptive_cluster_count()` | 替换 `_hierarchical_clustering` 中的启发式k确定 |
| 反向验证 | `LLMObjectNamer._reverse_verify()` | 反向验证prompt调用 |
| 一致性评分 | `LLMObjectNamer._compute_consistency_score()` | 计算CS分数 |
| 质量控制 | `LLMObjectNamer._quality_control()` | 编排正向归纳→反向验证→决策 |
| 聚类拆分 | `SemanticClusterExtractor._split_cluster()` | 低一致性聚类的拆分 |

### 新增实验脚本（在 `scripts/experiments/` 目录）

| 脚本 | 功能 |
|------|------|
| `run_baselines.py` | 运行所有对比方法 |
| `run_ablation.py` | 消融实验 |
| `evaluate_adaptive_k.py` | 自适应k评估（生成图2） |
| `parameter_sensitivity.py` | 参数敏感性（生成图5-8） |
| `export_results.py` | 导出实验结果表格 |
