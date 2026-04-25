# 算法微服务 (FastAPI)

按 [docs/algorithm-integration.md](../docs/algorithm-integration.md) 方案 A 落地：把 webapp 的对象抽取算法包成独立 HTTP 服务，给 Java 后端（platform/backend）调用。

## 端点

| 端点 | 用途 |
|------|------|
| `GET  /health` | 健康检查 + SBERT 状态 |
| `POST /extract` | 异步触发对象抽取，body: `{domain, use_llm, target_clusters}` → 返回 jobId |
| `GET  /jobs/{id}` | 查询任务状态 |
| `POST /embed` | 给文本算 SBERT 768D 向量 |
| `POST /match` | 在 FAISS 索引里找 top-K 最相似 |

## 本地跑（不进容器）

```bash
cd /home/qq/YIMO
pip install -r platform/algo/requirements.txt
PORT=9000 python platform/algo/app.py
curl http://localhost:9000/health
```

## Docker 部署

```bash
cd /home/qq/YIMO
docker build -f platform/algo/Dockerfile -t twin-fusion-algo:0.1 .
docker run -p 9000:9000 \
  -v $(pwd)/scripts:/app/scripts:ro \
  -v $(pwd)/DATA:/data:ro \
  -v $(pwd)/outputs:/outputs \
  twin-fusion-algo:0.1
```

## 与 Java 后端的对接

`platform/backend/src/main/java/com/csg/twinfusion/service/ExtractionJobService.java` 的 TODO 注释处做 HTTP forward：

```java
// 当前 in-memory stub:
// jobs.put(job.getJobId(), job);

// 真实实现 (待启用):
// String algoBase = env.getProperty("algo.base.url", "http://algo:9000");
// HttpClient.send(POST(algoBase + "/extract")
//     .body({domain, use_llm, callback_url: "http://backend:8080/api/v1/internal/jobs/{jobId}/done"}))
```

南网内网 LLM 网关替换：

```bash
# 启动算法服务时
DEEPSEEK_API_BASE=https://内网网关地址/v1 \
DEEPSEEK_API_KEY=内网token \
DEEPSEEK_MODEL=deepseek-chat \
python app.py
```

## 部署清单

加进 `platform/deploy/docker-compose.yml`：

```yaml
algo:
  build:
    context: ../..
    dockerfile: platform/algo/Dockerfile
  container_name: twin-fusion-algo
  environment:
    SBERT_MODEL_NAME: shibing624/text2vec-base-chinese
    DEEPSEEK_API_BASE: ${DEEPSEEK_API_BASE:-https://api.deepseek.com/v1}
    DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY}
    DEEPSEEK_MODEL: ${DEEPSEEK_MODEL:-deepseek-v4-pro}
    TZ: Asia/Shanghai
  volumes:
    - ../../scripts:/app/scripts:ro
    - ../../DATA:/data:ro
    - ../../outputs:/outputs
  deploy:
    resources:
      limits: { cpus: "8", memory: 4G }
      reservations: { cpus: "2", memory: 2G }
  restart: unless-stopped
  networks: [twin-net]
```

## 限制 / 待办

- [ ] FAISS 索引 `/match` 端点尚未实现 `/index/rebuild`，初版返回 404
- [ ] 完成回调 `callback_url` 通知 backend 待写
- [ ] 大批量 `/embed` 没分批 (一次 1000+ 文本可能 OOM)
- [ ] 镜像内置 SBERT 模型 (~400MB)，构建慢但运行时快；若南网内网无 huggingface 直连，需在构建机预下载后 `COPY` 进去
