"""增强版跨域语义对齐 (P1 代表向量联合聚类).

不做全量 85k 实体真联合 (噪音多+成本高),
做 "每本地对象的 top-N sample 实体" 联合聚类 → 全局超对象.

为什么这样选:
 - 现有两阶段方案 (cross_domain_merge.py 的 B 语义聚类) 用每对象 1 个向量
   信息量薄弱, 难以识别 '项目∼工程' 这类一对象内部样例分散的情况
 - 用 top-20 sample 拍平 → 135 × 20 ≈ 2700 个向量, 信息量提 30×
 - 2700 实体 O(n²) 距离矩阵 28MB, 可以放心用 AgglomerativeClustering

输入:  outputs/extraction_<22 域>.json
输出:  outputs/extraction_join_sample.json

schema:
{
  "meta": {...},
  "join_groups": [
    {"group_id": "JOIN_0", "repr_name": "项目",
     "samples": [...top-20 实体名...],
     "local_objects": [(domain, object_code, object_name, sample_count_in_this_group), ...],
     "present_in_domains": [...],
     "intra_avg_similarity": 0.85}
  ]
}
"""

from __future__ import annotations

import datetime as _dt
import glob
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = PROJECT_ROOT / "outputs"
OUT_FILE = OUTPUTS / "extraction_join_sample.json"

SAMPLE_PER_OBJECT = int(os.getenv("SAMPLES_PER_OBJECT", "20"))
JOIN_DISTANCE = float(os.getenv("JOIN_DISTANCE", "0.20"))   # cosine distance threshold


def load_local_object_samples():
    """返回 [(domain, object_code, object_name, sample_text)] 拍平列表."""
    rows = []
    skip_global = "extraction_global", "extraction_join_sample"
    for f in sorted(glob.glob(str(OUTPUTS / "extraction_*.json"))):
        base = os.path.basename(f).replace(".json", "")
        if base in skip_global:
            continue
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception as e:
            print(f"[WARN] 跳过 {f}: {e}")
            continue
        domain = d.get("data_domain") or base.replace("extraction_", "")
        for o in d.get("objects", []):
            code = o.get("object_code", "")
            name = o.get("object_name", "")
            samples = (o.get("sample_entities") or [])[:SAMPLE_PER_OBJECT]
            if not samples:
                # 退而求其次: 只用 object_name 作为单一样本
                samples = [name] if name else []
            for s in samples:
                if isinstance(s, str) and s.strip():
                    rows.append((domain, code, name, s.strip()))
    return rows


def main() -> int:
    print(f"[INFO] 配置: samples_per_object={SAMPLE_PER_OBJECT}, "
          f"join_distance_threshold={JOIN_DISTANCE}")
    rows = load_local_object_samples()
    print(f"[INFO] 拍平 {len(rows)} 个 (域, 本地对象, 样例) 三元组")
    if not rows:
        print("[ERR] 没有数据"); return 1

    texts = [r[3] for r in rows]

    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.cluster import AgglomerativeClustering
        import numpy as np
    except ImportError as e:
        print(f"[ERR] 缺依赖: {e}"); return 2

    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(PROJECT_ROOT / "models"))
    print(f"[INFO] SBERT 嵌入 {len(texts)} 个样例文本...")
    model = SentenceTransformer("shibing624/text2vec-base-chinese")
    emb = model.encode(texts, convert_to_numpy=True, show_progress_bar=False,
                       normalize_embeddings=True)
    print(f"[INFO] 嵌入完成, shape={emb.shape}")

    print(f"[INFO] AgglomerativeClustering (cosine, average, "
          f"distance_threshold={JOIN_DISTANCE})...")
    cl = AgglomerativeClustering(
        n_clusters=None, metric="cosine", linkage="average",
        distance_threshold=JOIN_DISTANCE,
    )
    labels = cl.fit_predict(emb)
    n_clusters = len(set(labels))
    print(f"[INFO] 聚出 {n_clusters} 个簇")

    # 为每个簇汇总
    cluster_to_idxs = defaultdict(list)
    for i, lab in enumerate(labels):
        cluster_to_idxs[int(lab)].append(i)

    groups = []
    for lab, idxs in sorted(cluster_to_idxs.items(), key=lambda kv: -len(kv[1])):
        members_local = Counter()           # (domain, code, name) → sample 数
        sample_names = []
        for i in idxs:
            domain, code, name, sample = rows[i]
            members_local[(domain, code, name)] += 1
            sample_names.append(sample)

        # 每个本地对象贡献了多少 sample 进这个簇
        local_objects = [
            {"domain": d, "object_code": c, "object_name": n, "sample_count": cnt}
            for (d, c, n), cnt in sorted(members_local.items(),
                                         key=lambda kv: -kv[1])
        ]
        present_domains = sorted({d for (d, _, _) in members_local})

        # 选代表名: 簇里 sample_count 最大的本地对象的 object_name (出现最多)
        # 但若样例本身的众数和它不同, 用样例众数 (更具体)
        sample_counter = Counter(sample_names)
        most_common_sample, _ = sample_counter.most_common(1)[0]
        repr_name = most_common_sample
        if repr_name == "" and local_objects:
            repr_name = local_objects[0]["object_name"]

        # 簇内平均余弦相似度
        if len(idxs) > 1:
            sub = emb[idxs]
            sim_mat = sub @ sub.T
            n = len(idxs)
            avg_sim = (sim_mat.sum() - n) / (n * (n - 1))
        else:
            avg_sim = 1.0

        groups.append({
            "group_id": f"JOIN_{lab}",
            "repr_name": repr_name,
            "size": len(idxs),
            "local_objects": local_objects,
            "present_in_domains": present_domains,
            "domain_count": len(present_domains),
            "intra_avg_similarity": round(float(avg_sim), 4),
            "sample_examples": [s for s, _ in sample_counter.most_common(8)],
        })

    cross_groups = [g for g in groups if g["domain_count"] >= 2]

    result = {
        "meta": {
            "built_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "samples_per_object": SAMPLE_PER_OBJECT,
            "join_distance_threshold": JOIN_DISTANCE,
            "input_rows": len(rows),
            "n_clusters": n_clusters,
            "cross_domain_clusters": len(cross_groups),
            "cross_domain_ratio": round(len(cross_groups) / max(1, n_clusters), 4),
            "method": "P1 representative-vector joint clustering "
                      "(local objects' top-N sample entities, joint AgglomerativeClustering)"
        },
        "join_groups": groups,
    }
    OUT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    size_kb = OUT_FILE.stat().st_size / 1024
    print(f"\n[INFO] 写出 {OUT_FILE.name} ({size_kb:.1f} KB)")
    print(f"  - 共 {n_clusters} 簇, 跨域簇 {len(cross_groups)} ({100*len(cross_groups)/max(1,n_clusters):.1f}%)")

    print(f"\n[INFO] Top 10 跨域全局对象:")
    print(f"  {'repr':10s} {'size':>5s} {'doms':>5s} {'objs':>5s} {'avg_sim':>8s}  domains_preview")
    for g in sorted(cross_groups, key=lambda x: -x["domain_count"])[:10]:
        print(f"  {g['repr_name']:10s} {g['size']:>5d} {g['domain_count']:>5d} "
              f"{len(g['local_objects']):>5d} {g['intra_avg_similarity']:>8.4f}  "
              f"{','.join(g['present_in_domains'][:6])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
