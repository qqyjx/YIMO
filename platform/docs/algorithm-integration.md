# 算法接入设计

## 要接入什么

[webapp/scripts/object_extractor.py](../../scripts/object_extractor.py)（2369 行）做的事：

```
Excel 读取 → SBERT 向量化 (text2vec-base-chinese 768维)
  → AgglomerativeClustering 聚类
  → DeepSeek LLM 给聚类命名（或规则回退）
  → 垃圾名过滤 + 小对象合并
  → 对象 + 三层关联 JSON 输出
```

关键依赖：
- **sentence-transformers**（SBERT）：Python 生态，JVM 直接跑需要 DJL/ONNX 转换
- **scikit-learn**：AgglomerativeClustering
- **DeepSeek API**：HTTP，任何语言都能调
- **simple_extractor.py**（回退）：纯 Python 关键词规则，无重依赖

## 三种接入路线

### 方案 A — Python 算法微服务 + Java 网关（**推荐**）

```
前端 → Java 后端 (:8080)
              └── HTTP → Python 算法服务 (:9000) ── SBERT/scikit-learn/DeepSeek
```

**做法**：把 `scripts/object_extractor.py` 包成 FastAPI 容器，暴露：
- `POST /extract` — 触发单域抽取，body: `{domain, target_clusters, use_llm}`
- `GET /jobs/{id}` — 查抽取任务状态
- `POST /embed` — 给任意文本生成 768 维向量（RAG / 补算）
- `POST /match` — 给定对象名找最相似概念实体

**部署**：
```yaml
services:
  algo:
    build: deploy/Dockerfile.algo   # python:3.10-slim + sentence-transformers
    ports: ["9000:9000"]
    volumes: ["../../DATA:/data:ro", "../../outputs:/outputs"]
  backend:
    environment:
      ALGO_BASE_URL: http://algo:9000
```

**优势**：
- 算法原封不动搬过来，不用重写
- Python 生态更新快（SBERT 出新模型直接升级）
- Java 后端只做编排，代码薄

**劣势**：
- 多了一个容器 = 一个运维点
- 南网内网可能限制自建 Python 服务（待甲方确认）
- 跨进程调用延迟 10-50ms

### 方案 B — JVM 原生 (DJL + ONNX)

把 `text2vec-base-chinese` 转成 ONNX，在 Java 里用 DJL（Deep Java Library）跑：

```java
try (Predictor<String, float[]> predictor = ZooModel.loadModel(...).newPredictor()) {
    float[] embedding = predictor.predict("项目");  // 768-dim
}
```

**优势**：单语言栈，符合南网"全 Java"运维偏好；无额外容器。

**劣势**：
- SBERT 模型 ONNX 转换需要调参，社区范例少
- DJL 内存占用比 Python 原生高 2-3×
- 算法改动（换模型、换聚类算法）要改 Java，慢
- **聚类算法需要自行实现**（sklearn AgglomerativeClustering 在 JVM 无成熟等价品）

适合：后期有时间把 Python 算法固化 + 南网坚决不让跑 Python 服务时。

### 方案 C — 离线预计算 + Java 只读

webapp 提取完 JSON 后作为数据集入库，platform 只做查询不做重新抽取：

```
   webapp 本地跑 object_extractor.py → outputs/extraction_<domain>.json
                → 人工 review / 合并 → dm-schema import 脚本 → DM 数据库
                                                                    ↑
                                                        platform Java 只读这张
```

**优势**：zero 算法耦合，platform 极简。

**劣势**：甲方 1.md 4 点"支持新增域"，每次加域都要回 webapp 跑一遍；抽取不能实时触发。

## 推荐路线与理由

**Phase 1（现在 → 3 周）走方案 C**：

- 现有 `outputs/extraction_shupeidian.json` + `outputs/extraction_jicai.json` 已能撑起演示
- 新加的 20 个域需要重跑抽取，webapp 本地跑一次即可
- platform 先把展示与管理端口上线，不管算法

**Phase 2（甲方上线演示后）切方案 A**：

- Python 算法服务打包独立容器
- Java 后端加 `/api/v1/extraction/run` 转发到 `algo:9000/extract`
- 保留方案 C 的抽取结果作为冷备

**方案 B 只在南网不让跑 Python 时启用**。触发条件：运维明确回复"测试机禁装 Python 3.10+/禁开第二个容器"。

## 契约：Java ↔ Python 算法服务（方案 A/B 都适用）

### 触发抽取

```
POST /api/v1/extraction/run
Body: { "domain": "输配电", "targetClusters": null, "useLlm": true }
→ 202 Accepted
Result: { "code": 0, "data": { "jobId": "e7f3c2a1", "status": "QUEUED" } }
```

Java 后端侧实现：
1. 校验 domain 在 `DATA/` 下存在
2. 生成 jobId (UUID)，入 `TF_OM_EXTRACTION_JOB` 表，status=QUEUED
3. 异步 HTTP POST 到 algo:9000/extract，带 jobId + callback URL
4. algo 跑完回调 Java `/internal/jobs/{jobId}/done` 更新状态

### 查询状态

```
GET /api/v1/extraction/jobs/{jobId}
Result: { "status": "RUNNING|SUCCESS|FAILED", "progress": 0.0-1.0,
          "objectCount": 12, "relationCount": 1456, "error": null }
```

### 结果入库

algo 完成后，结果 JSON 落到 `/outputs/extraction_<domain>.json`；
Java 读该 JSON（或算法直接写 DM 表），前端 Phase 1 的 7 个端点即可展示。

## 本次不做

- 不把 SBERT 搬 JVM（方案 B 的工作量与收益不成正比，除非南网强制）
- 不动 simple_extractor.py 回退链路（webapp 侧继续保留）
- 不改 DeepSeek 调用方（南网内网 LLM 网关一旦确定，只改 `DEEPSEEK_API_BASE` 这一项）
