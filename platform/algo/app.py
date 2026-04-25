"""算法微服务 FastAPI 入口 (platform/docs/algorithm-integration.md 方案 A).

提供给 Java 后端 (platform/backend) 调用的算法能力:
  POST /extract       触发对象抽取 (异步, 返回 jobId)
  GET  /jobs/{id}     查询任务状态
  POST /embed         给文本计算 SBERT 768 dim 向量
  POST /match         给定文本找最相似实体 (FAISS 加速)
  GET  /health        健康检查

模型与算法源码复用 webapp 侧 scripts/object_extractor.py / sample_join_extract.py.
容器化部署见 Dockerfile.
"""

from __future__ import annotations

import os
import sys
import uuid
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

# 把 webapp 的 scripts 目录加入 path 以便 import 已实现的算法
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

logger = logging.getLogger("algo")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# 全局状态
_jobs: Dict[str, dict] = {}    # jobId → job dict
_sbert_model = None
_faiss_index = None
_faiss_texts: List[str] = []


@asynccontextmanager
async def lifespan(_: FastAPI):
    """启动时预加载 SBERT, 关闭时清理."""
    global _sbert_model
    try:
        from sentence_transformers import SentenceTransformer
        model_name = os.getenv("SBERT_MODEL_NAME", "shibing624/text2vec-base-chinese")
        logger.info(f"loading SBERT {model_name}...")
        _sbert_model = SentenceTransformer(model_name)
        logger.info("SBERT ready")
    except Exception as e:
        logger.error(f"SBERT 加载失败: {e}, /embed /match 不可用")
    yield
    logger.info("shutdown")


app = FastAPI(
    title="支撑孪生体新范式多维数据融合分析框架原型系统 - 算法微服务",
    version="0.1.0",
    description="对象抽取 / SBERT 嵌入 / 相似度匹配",
    lifespan=lifespan,
)


# ============== Schemas ==============

class ExtractRequest(BaseModel):
    domain: str
    target_clusters: Optional[int] = None
    use_llm: bool = True
    callback_url: Optional[str] = None    # 完成后回调 platform/backend


class ExtractResponse(BaseModel):
    job_id: str
    domain: str
    status: str


class JobStatus(BaseModel):
    job_id: str
    domain: Optional[str]
    status: str          # QUEUED | RUNNING | SUCCESS | FAILED
    progress: float = 0.0
    object_count: Optional[int] = None
    relation_count: Optional[int] = None
    error: Optional[str] = None
    created_at: str
    finished_at: Optional[str] = None


class EmbedRequest(BaseModel):
    texts: List[str]
    normalize: bool = True


class EmbedResponse(BaseModel):
    dim: int
    count: int
    embeddings: List[List[float]]


class MatchRequest(BaseModel):
    query: str
    top_k: int = 5


class MatchResponse(BaseModel):
    query: str
    matches: List[dict]


# ============== Routes ==============

@app.get("/health")
async def health():
    return {
        "status": "UP" if _sbert_model is not None else "DEGRADED",
        "sbert_loaded": _sbert_model is not None,
        "active_jobs": sum(1 for j in _jobs.values() if j["status"] == "RUNNING"),
    }


@app.post("/extract", response_model=ExtractResponse, status_code=202)
async def submit_extract(req: ExtractRequest, bg: BackgroundTasks):
    """异步提交对象抽取任务."""
    job_id = uuid.uuid4().hex[:12]
    job = {
        "job_id": job_id,
        "domain": req.domain,
        "status": "QUEUED",
        "progress": 0.0,
        "object_count": None,
        "relation_count": None,
        "error": None,
        "created_at": datetime.utcnow().isoformat(),
        "finished_at": None,
    }
    _jobs[job_id] = job
    bg.add_task(_run_extract, job_id, req.dict())
    return {"job_id": job_id, "domain": req.domain, "status": "QUEUED"}


@app.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job(job_id: str):
    j = _jobs.get(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return j


@app.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest):
    if _sbert_model is None:
        raise HTTPException(503, "SBERT model 未就绪")
    if not req.texts:
        return {"dim": 0, "count": 0, "embeddings": []}
    arr = _sbert_model.encode(req.texts, convert_to_numpy=True,
                              normalize_embeddings=req.normalize,
                              show_progress_bar=False)
    return {"dim": arr.shape[1], "count": arr.shape[0], "embeddings": arr.tolist()}


@app.post("/match", response_model=MatchResponse)
async def match(req: MatchRequest):
    """给定 query 在已索引实体里找 top-K 最相似. 索引由内置实体集构建."""
    if _sbert_model is None:
        raise HTTPException(503, "SBERT 未就绪")
    if _faiss_index is None or not _faiss_texts:
        raise HTTPException(404, "FAISS 索引未构建; 先调 /index/rebuild")
    import numpy as np
    q_emb = _sbert_model.encode([req.query], convert_to_numpy=True,
                                normalize_embeddings=True)
    distances, indices = _faiss_index.search(q_emb.astype("float32"), req.top_k)
    matches = [
        {"text": _faiss_texts[idx], "similarity": float(distances[0][i])}
        for i, idx in enumerate(indices[0]) if 0 <= idx < len(_faiss_texts)
    ]
    return {"query": req.query, "matches": matches}


# ============== Internals ==============

async def _run_extract(job_id: str, req: dict):
    """后台跑 object_extractor.py (subprocess 方式, 隔离内存)."""
    job = _jobs[job_id]
    job["status"] = "RUNNING"
    job["progress"] = 0.05
    try:
        import subprocess, json
        domain = req["domain"]
        out_file = PROJECT_ROOT / "outputs" / f"extraction_{domain}.json"
        cmd = [
            sys.executable, str(PROJECT_ROOT / "scripts" / "object_extractor.py"),
            "--data-dir", str(PROJECT_ROOT / "DATA"),
            "--data-domain", domain,
            "--no-db",
            "-o", str(out_file),
        ]
        if not req.get("use_llm"):
            cmd.append("--no-llm")
        if req.get("target_clusters"):
            cmd.extend(["--target-clusters", str(req["target_clusters"])])

        logger.info(f"job {job_id}: {' '.join(cmd)}")
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        out, _ = await proc.communicate()
        job["progress"] = 0.95
        if proc.returncode != 0:
            job["status"] = "FAILED"
            job["error"] = (out.decode("utf-8", "replace") or "")[-500:]
        else:
            try:
                d = json.loads(out_file.read_text(encoding="utf-8"))
                job["object_count"] = len(d.get("objects", []))
                job["relation_count"] = len(d.get("relations", []))
            except Exception:
                pass
            job["status"] = "SUCCESS"
            job["progress"] = 1.0
    except Exception as e:
        job["status"] = "FAILED"
        job["error"] = str(e)
    finally:
        job["finished_at"] = datetime.utcnow().isoformat()
        # TODO: 若 callback_url 给了, HTTP POST 通知 platform/backend


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "9000")))
