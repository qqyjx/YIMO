FROM python:3.10-slim

ENV TZ=Asia/Shanghai \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SBERT_MODEL_NAME=shibing624/text2vec-base-chinese \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 国内镜像加速 (南网内网若有私服改成那个)
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

COPY platform/algo/requirements.txt .
RUN pip install -r requirements.txt

# 算法源码 (主进程) + scripts/ (extract 子进程调用) + DATA/outputs (运行时挂载)
COPY platform/algo/app.py .
# 注: scripts/, DATA/, outputs/ 通过 volume 挂载, 不打进镜像
# 见 platform/deploy/docker-compose.yml 的 algo service

# 预加载 SBERT 模型到镜像 (避免容器启动时下载, ~400MB)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('shibing624/text2vec-base-chinese')"

EXPOSE 9000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:9000/health', timeout=3)"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000", "--workers", "1"]
