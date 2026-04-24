"""跨域对象融合 (A + B 综合).

- A 字面对齐: 按 (object_code, object_name) 精确匹配, 把 22 域里同名/同 code
  的本地对象归并到一个 "全局对象 GOBJ_*"; 同时保留每个本地对象源.
- B 语义聚类: 用 SBERT 对 (object_name + description + sample_entities[:5])
  嵌入后做层次聚类, 把语义相近的本地对象归到一个 "语义超级组";
  与 A 的精确组独立, 互为补充.

输入:   outputs/extraction_<域>.json  (22 份, 跨域独立抽取产物)
输出:   outputs/extraction_global.json

schema:
{
  "meta": {
    "built_at": "...",
    "total_domains": 22,
    "total_local_objects": 135,
    "total_relations": 125094,
    "literal_group_count": N1,     # A 字面组数
    "semantic_group_count": N2,    # B 语义组数
    "cross_domain_ratio": 0.62     # 跨域对象占比
  },
  "domains": ["产业金融", "人力资源", ...],
  "local_objects": [                # 22 域拍平
    {"domain": "计划财务", "object_code": "OBJ_PROJECT",
     "object_name": "项目", "object_type": "CORE",
     "cluster_size": 6, "sample_entities": [...],
     "concept_count": 6, "logical_count": 23, "physical_count": 23}
    ...
  ],
  "literal_groups": [               # A 结果: 精确同名跨域归并
    {"group_id": "GOBJ_PROJECT",
     "group_name": "项目",
     "members": [ {"domain": "...", "object_code": "..."}, ... ],
     "present_in_domains": ["计划财务", "输配电", ...],
     "total_concept": 80, "total_logical": 200, "total_physical": 180}
    ...
  ],
  "semantic_groups": [              # B 结果: SBERT 语义聚类
    {"group_id": "SEM_0", "repr_name": "项目/工程",
     "members": [ {"domain": "...", "object_code": "...", "object_name": "..."}, ... ],
     "present_in_domains": [...],
     "avg_similarity": 0.87}
    ...
  ]
}
"""

from __future__ import annotations

import datetime as _dt
import glob
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
OUTPUT_FILE = OUTPUTS_DIR / "extraction_global.json"

SBERT_MODEL = os.getenv("SBERT_MODEL_NAME", "shibing624/text2vec-base-chinese")
SEMANTIC_DISTANCE_THRESHOLD = float(os.getenv("CROSS_DOMAIN_DIST_THRESHOLD", "0.15"))


def load_domain_jsons() -> List[Dict[str, Any]]:
    files = sorted(glob.glob(str(OUTPUTS_DIR / "extraction_*.json")))
    # 排除 global/聚合产物本身与 legacy 拼音
    skip = {"extraction_global.json"}
    out = []
    for f in files:
        base = os.path.basename(f)
        if base in skip:
            continue
        try:
            d = json.load(open(f, encoding="utf-8"))
            # 为每个对象补上 domain
            dom = d.get("data_domain") or Path(f).stem.replace("extraction_", "")
            d["_domain"] = dom
            out.append(d)
        except Exception as e:
            print(f"[WARN] skip {f}: {e}", file=sys.stderr)
    return out


def flatten_local_objects(domain_blobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for blob in domain_blobs:
        dom = blob["_domain"]
        stats = blob.get("stats") or {}
        for o in blob.get("objects", []):
            code = o.get("object_code") or ""
            s = stats.get(code, {}) if isinstance(stats, dict) else {}
            rows.append({
                "domain": dom,
                "object_code": code,
                "object_name": o.get("object_name") or "",
                "object_type": o.get("object_type") or "CORE",
                "description": o.get("description") or "",
                "cluster_size": o.get("cluster_size") or s.get("cluster_size") or 0,
                "sample_entities": (o.get("sample_entities") or [])[:5],
                "concept_count": s.get("concept") or 0,
                "logical_count": s.get("logical") or 0,
                "physical_count": s.get("physical") or 0,
            })
    return rows


def build_literal_groups(local_objs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A: 按 (object_code | object_name) 精确同名组装."""
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for lo in local_objs:
        key = lo["object_code"] or lo["object_name"]
        if not key:
            continue
        buckets.setdefault(key, []).append(lo)

    groups = []
    for key, members in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        names = {m["object_name"] for m in members}
        group_name = "/".join(sorted(names)) if len(names) > 1 else next(iter(names), key)
        groups.append({
            "group_id": f"GOBJ_{key}" if key.startswith("OBJ_") else f"GOBJ_{key}",
            "group_name": group_name,
            "members": [
                {"domain": m["domain"], "object_code": m["object_code"],
                 "object_name": m["object_name"], "cluster_size": m["cluster_size"]}
                for m in members
            ],
            "present_in_domains": sorted({m["domain"] for m in members}),
            "member_count": len(members),
            "total_concept": sum(m["concept_count"] for m in members),
            "total_logical": sum(m["logical_count"] for m in members),
            "total_physical": sum(m["physical_count"] for m in members),
        })
    return groups


def build_semantic_groups(local_objs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """B: SBERT 嵌入 (name + desc + samples) → 层次聚类."""
    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.cluster import AgglomerativeClustering
        import numpy as np
    except ImportError as e:
        print(f"[WARN] 语义聚类跳过: {e}", file=sys.stderr)
        return []

    texts = []
    for lo in local_objs:
        t = lo["object_name"]
        if lo["description"]:
            t += " | " + lo["description"]
        if lo["sample_entities"]:
            t += " | " + "、".join(lo["sample_entities"])
        texts.append(t)

    print(f"[INFO] SBERT 嵌入 {len(texts)} 个本地对象...")
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME",
                          str(PROJECT_ROOT / "models"))
    model = SentenceTransformer(SBERT_MODEL)
    emb = model.encode(texts, convert_to_numpy=True, show_progress_bar=False,
                       normalize_embeddings=True)

    print(f"[INFO] 层次聚类 (distance_threshold={SEMANTIC_DISTANCE_THRESHOLD})...")
    # cosine = 1 - 内积 (向量已归一化); 使用 cosine 亲和力
    clustering = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=SEMANTIC_DISTANCE_THRESHOLD,
    )
    labels = clustering.fit_predict(emb)

    # 按 label 归组
    buckets: Dict[int, List[int]] = {}
    for i, lab in enumerate(labels):
        buckets.setdefault(int(lab), []).append(i)

    groups = []
    for lab, idxs in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        members = [local_objs[i] for i in idxs]
        # 代表名 = cluster_size 最大的那个
        repr_obj = max(members, key=lambda m: m["cluster_size"])
        names = {m["object_name"] for m in members}

        # 组内平均相似度: 对 idx 两两 cos 相似
        if len(idxs) > 1:
            sub = emb[idxs]
            sim_mat = sub @ sub.T
            n = len(idxs)
            avg_sim = (sim_mat.sum() - n) / (n * (n - 1))  # 减去对角
        else:
            avg_sim = 1.0

        groups.append({
            "group_id": f"SEM_{lab}",
            "repr_name": repr_obj["object_name"],
            "aliases": sorted(names),
            "members": [
                {"domain": m["domain"], "object_code": m["object_code"],
                 "object_name": m["object_name"], "cluster_size": m["cluster_size"]}
                for m in members
            ],
            "present_in_domains": sorted({m["domain"] for m in members}),
            "member_count": len(members),
            "avg_similarity": round(float(avg_sim), 4),
            "total_concept": sum(m["concept_count"] for m in members),
            "total_logical": sum(m["logical_count"] for m in members),
            "total_physical": sum(m["physical_count"] for m in members),
        })
    return groups


def main() -> int:
    domain_blobs = load_domain_jsons()
    print(f"[INFO] 载入 {len(domain_blobs)} 个域 JSON")
    local_objs = flatten_local_objects(domain_blobs)
    print(f"[INFO] 拍平后本地对象 {len(local_objs)}")

    literal_groups = build_literal_groups(local_objs)
    print(f"[INFO] A 字面对齐: {len(literal_groups)} 组")

    semantic_groups = build_semantic_groups(local_objs)
    print(f"[INFO] B 语义聚类: {len(semantic_groups)} 组")

    total_rels = 0
    for blob in domain_blobs:
        total_rels += len(blob.get("relations", []))

    cross_domain = [g for g in literal_groups if len(g["present_in_domains"]) > 1]

    result = {
        "meta": {
            "built_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sbert_model": SBERT_MODEL,
            "semantic_threshold": SEMANTIC_DISTANCE_THRESHOLD,
            "total_domains": len(domain_blobs),
            "total_local_objects": len(local_objs),
            "total_relations": total_rels,
            "literal_group_count": len(literal_groups),
            "semantic_group_count": len(semantic_groups),
            "cross_domain_literal_count": len(cross_domain),
            "cross_domain_ratio": round(len(cross_domain) / max(1, len(literal_groups)), 4),
        },
        "domains": sorted({b["_domain"] for b in domain_blobs}),
        "local_objects": local_objs,
        "literal_groups": literal_groups,
        "semantic_groups": semantic_groups,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    size_kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"[INFO] 写出 {OUTPUT_FILE.name} ({size_kb:.1f} KB)")
    print(f"  - 跨域字面组 {len(cross_domain)} / 共 {len(literal_groups)} 组")
    print(f"  - 语义组 {len(semantic_groups)} 组, 其中跨域 "
          f"{sum(1 for g in semantic_groups if len(g['present_in_domains']) > 1)} 组")
    return 0


if __name__ == "__main__":
    sys.exit(main())
