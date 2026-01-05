#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于 BERT 语义相似度的 EAV 文本值去重工具

功能
- 从 EAV 数据库中读取指定数据集(dataset_id)与属性(attribute)的去重候选（按 raw_text 去重并统计频次）
- 使用句向量模型计算文本嵌入，基于余弦相似度进行聚类合并（阈值可调）
- 生成规范值(canonical)与映射表，并写入数据库的语义辅助表；同时导出 CSV 报告

依赖
  pip install sentence-transformers scikit-learn torch --extra-index-url https://download.pytorch.org/whl/cpu

示例
  python scripts/eav_semantic_dedupe.py \
    --dataset-id 1 \
    --attributes 名称,地址 \
    --threshold 0.85 \
    --model shibing624/text2vec-base-chinese \
    --model-cache /data1/xyf/models \
    --out-dir /data1/xyf/smartgrid/outputs/semantic_dedupe
"""
import argparse
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
from tqdm.auto import tqdm

try:
    import pymysql
    HAS_PYMYSQL = True
except Exception:
    HAS_PYMYSQL = False


# ---------- DB 连接 ----------

def connect_mysql(host, port, user, password, database=None):
    if HAS_PYMYSQL:
        cfg = dict(host=host, port=port, user=user, password=password,
                   charset='utf8mb4', autocommit=False,
                   cursorclass=pymysql.cursors.DictCursor)
        if database:
            cfg['database'] = database
        return pymysql.connect(**cfg)
    else:
        import mysql.connector as mysql
        cfg = dict(host=host, port=port, user=user, password=password,
                   use_unicode=True, autocommit=False)
        if database:
            cfg['database'] = database
        return mysql.connect(**cfg)


def ensure_semantic_tables(cur, prefix: str, charset: str = 'utf8mb4', collation: str = 'utf8mb4_unicode_ci'):
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS `{prefix}_semantic_canon` (
        `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
        `dataset_id` BIGINT NOT NULL,
        `attribute_id` BIGINT NOT NULL,
        `canonical_text` TEXT NOT NULL,
        `cluster_size` INT NOT NULL,
        `created_at` DATETIME(6) NOT NULL,
        KEY `idx_ds_attr` (`dataset_id`,`attribute_id`)
    ) ENGINE=InnoDB ROW_FORMAT=DYNAMIC DEFAULT CHARSET={charset} COLLATE={collation};
    """)
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS `{prefix}_semantic_mapping` (
        `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
        `dataset_id` BIGINT NOT NULL,
        `attribute_id` BIGINT NOT NULL,
        `from_text` TEXT NOT NULL,
        `canonical_id` BIGINT NOT NULL,
        `similarity` DECIMAL(6,5) NULL,
        `freq` INT NOT NULL DEFAULT 1,
        `created_at` DATETIME(6) NOT NULL,
        KEY `idx_ds_attr` (`dataset_id`,`attribute_id`),
        KEY `idx_canon` (`canonical_id`),
        CONSTRAINT `fk_sem_map_canon` FOREIGN KEY (`canonical_id`) REFERENCES `{prefix}_semantic_canon` (`id`) ON DELETE CASCADE
    ) ENGINE=InnoDB ROW_FORMAT=DYNAMIC DEFAULT CHARSET={charset} COLLATE={collation};
    """)


# ---------- 业务逻辑 ----------

@dataclass
class AttrInfo:
    id: int
    name: str
    display_name: str
    data_type: str
    dataset_id: Optional[int] = None


def fetch_attributes(cur, prefix: str, dataset_id: int, target_names: Optional[List[str]]) -> List[AttrInfo]:
    if target_names:
        # 名称同时匹配规范名(name)或显示名(display_name)
        placeholders = ",".join(["%s"] * len(target_names))
        cur.execute(
            f"""
            SELECT id, name, display_name, data_type
            FROM `{prefix}_attributes`
            WHERE dataset_id=%s AND (name IN ({placeholders}) OR display_name IN ({placeholders}))
            ORDER BY ord_index, id
            """,
            (dataset_id, *target_names, *target_names)
        )
    else:
        cur.execute(
            f"""
            SELECT id, name, display_name, data_type
            FROM `{prefix}_attributes`
            WHERE dataset_id=%s AND data_type IN ('text','number','datetime','bool')
            ORDER BY ord_index, id
            """,
            (dataset_id,)
        )
    rows = cur.fetchall()
    attrs = [AttrInfo(**r) for r in rows]
    # 排除系统属性
    attrs = [a for a in attrs if a.name != "__sheet__"]
    return attrs


def fetch_attributes_multi(cur, prefix: str, dataset_ids: List[int], target_names: Optional[List[str]]) -> List[AttrInfo]:
    attrs: List[AttrInfo] = []
    for dsid in dataset_ids:
        part = fetch_attributes(cur, prefix, dsid, target_names)
        for a in part:
            a.dataset_id = dsid
        attrs.extend(part)
    return attrs


def fetch_distinct_texts(cur, prefix: str
                         , dataset_id: int, attribute_id: int, limit: int) -> List[Tuple[str, int]]:
    # 优先使用 raw_text；若该属性是 number/datetime/bool，raw_text 仍保留原始输入，可用于相似聚类
    cur.execute(
        f"""
        SELECT v.raw_text AS txt, COUNT(*) AS freq
        FROM `{prefix}_values` v
        JOIN `{prefix}_entities` e ON e.id=v.entity_id
        WHERE e.dataset_id=%s AND v.attribute_id=%s AND v.raw_text IS NOT NULL AND v.raw_text<>''
        GROUP BY v.raw_text
        ORDER BY freq DESC
        LIMIT %s
        """,
        (dataset_id, attribute_id, limit)
    )
    rows = cur.fetchall()
    return [(r['txt'], int(r['freq'])) for r in rows]


def fetch_distinct_texts_multi(
    cur,
    prefix: str,
    pairs: List[Tuple[int, int]],
    limit: int,
) -> List[Tuple[str, int, Dict[Tuple[int, int], int]]]:
    """跨多个 (dataset_id, attribute_id) 聚合不同 raw_text 的全局频次。
    返回列表项：(text, total_freq, per_attr_freq_dict)
    """
    freq_global: Dict[str, int] = defaultdict(int)
    per_attr: Dict[str, Dict[Tuple[int, int], int]] = defaultdict(lambda: defaultdict(int))
    for dsid, aid in pairs:
        cur.execute(
            f"""
            SELECT v.raw_text AS txt, COUNT(*) AS freq
            FROM `{prefix}_values` v
            JOIN `{prefix}_entities` e ON e.id=v.entity_id
            WHERE e.dataset_id=%s AND v.attribute_id=%s AND v.raw_text IS NOT NULL AND v.raw_text<>''
            GROUP BY v.raw_text
            ORDER BY freq DESC
            LIMIT %s
            """,
            (dsid, aid, limit)
        )
        for r in cur.fetchall():
            t = r['txt']
            f = int(r['freq'])
            freq_global[t] += f
            per_attr[t][(dsid, aid)] += f
    items = [(t, freq_global[t], per_attr[t]) for t in freq_global]
    items.sort(key=lambda x: x[1], reverse=True)
    if limit and len(items) > limit:
        items = items[:limit]
    return items


def _l2_normalize(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True) + 1e-12
    return (x / n).astype('float32')


def _resolve_local_model_path(model_name: str) -> str:
    """支持以下情况：
    - 直接是存放模型文件的目录（包含 config.json / modules.json 等）
    - HuggingFace 缓存目录结构 models--ORG--NAME，需自动定位 snapshots/* 子目录
    - 其余字符串按远程模型名处理
    返回可被 SentenceTransformer 接受的路径或原始模型名。
    """
    p = Path(model_name)
    if p.is_dir():
        # 如是 HF 缓存目录命名：models--*
        if p.name.startswith('models--'):
            snaps = sorted((p / 'snapshots').glob('*'), key=lambda x: x.stat().st_mtime, reverse=True)
            if snaps:
                return str(snaps[0])
        # 已是模型目录
        return str(p)
    return model_name


def embed_texts(
    texts: List[str],
    model_name: str,
    cache_dir: str,
    batch_size: int = 128,
    offline: bool = False,
    device: str = 'auto',
    fp16: bool = False,
    multi_gpu: int = 0,
) -> np.ndarray:
    """优先使用 SentenceTransformer；如离线加载失败，则退化到 TF-IDF ngram 表示。
    返回 L2 归一化后的 dense 向量。
    """
    # 设置缓存目录
    os.environ.setdefault('SENTENCE_TRANSFORMERS_HOME', cache_dir)
    os.environ.setdefault('HF_HOME', cache_dir)
    try:
        from sentence_transformers import SentenceTransformer
        import torch
        kwargs = dict(cache_folder=cache_dir)
        if offline:
            kwargs.update(dict(local_files_only=True))
        # 解析本地模型路径（如为 HF 缓存目录）
        resolved = _resolve_local_model_path(model_name)
        is_local_dir = Path(resolved).is_dir()
        if is_local_dir:
            # 本地目录时强制本地加载，避免意外联网
            kwargs.update(dict(local_files_only=True))
        model = SentenceTransformer(resolved, **kwargs)

        # 设备选择
        torch.backends.cudnn.benchmark = True
        if device == 'auto':
            device_sel = 'cuda' if torch.cuda.is_available() else 'cpu'
        else:
            device_sel = device

        # 多卡：优先尝试新版 encode 并行参数，不支持时回退旧的 multi-process 方案
        if device_sel.startswith('cuda') and torch.cuda.is_available() and (multi_gpu != 0):
            gpu_count = torch.cuda.device_count()
            use_n = gpu_count if (multi_gpu < 0 or multi_gpu > gpu_count) else multi_gpu
            use_n = max(1, min(use_n, gpu_count))
            target_devices = [f'cuda:{i}' for i in range(use_n)]
            print(f"[INFO] 多卡编码: {target_devices} / 可见GPU={gpu_count}, batch_size={batch_size}, fp16={fp16}")

            # 动态探测 encode 是否支持并行参数
            import inspect
            enc_sig = None
            try:
                enc_sig = inspect.signature(model.encode)
            except Exception:
                enc_sig = None

            def _encode_new_api():
                kwargs_enc = dict(
                    batch_size=batch_size,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=True,
                )
                # 1) 优先使用 devices 参数（若存在）
                if enc_sig and 'devices' in enc_sig.parameters:
                    kwargs_enc['devices'] = target_devices
                    return model.encode(texts, **kwargs_enc)
                # 2) 其次使用 num_processes（若存在）
                if enc_sig and 'num_processes' in enc_sig.parameters:
                    kwargs_enc['num_processes'] = len(target_devices)
                    # device 留空让库自行分配
                    return model.encode(texts, **kwargs_enc)
                # 3) 某些版本支持 device=list 的形式（保守探测）
                try:
                    return model.encode(texts, device=target_devices, **kwargs_enc)  # type: ignore[arg-type]
                except TypeError:
                    # 不支持则交由回退路径
                    raise

            try:
                emb = _encode_new_api()
                emb = np.asarray(emb, dtype='float32')
                # normalize_embeddings=True 时已归一化，但为稳妥再做一次轻量归一
                emb = _l2_normalize(emb)
                return emb
            except Exception as _:
                # 回退到旧的 multi-process 池接口（兼容老版本）
                try:
                    pool = model.start_multi_process_pool(target_devices=target_devices)
                    try:
                        emb = model.encode_multi_process(texts, pool, batch_size=batch_size, chunk_size=None)
                    finally:
                        try:
                            model.stop_multi_process_pool(pool)
                        except Exception:
                            pass
                    emb = np.asarray(emb, dtype='float32')
                    emb = _l2_normalize(emb)
                    return emb
                except Exception as e2:
                    # 若老接口也失败，抛出以触发 TF-IDF 回退
                    raise RuntimeError(f"multi-gpu encode failed (new&old API): {e2}")

        # 单卡/CPU
        print(f"[INFO] 设备: {device_sel}, batch_size={batch_size}, fp16={fp16}")
        if device_sel.startswith('cuda') and fp16:
            # encode 不直接暴露 amp；但模型内部使用 torch.cuda.amp 无需我们改；这里仅放大 batch 可加速
            pass
        emb = model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=True,
            device=device_sel,
        )
        return emb.astype('float32')
    except Exception as e:
        print(f"[WARN] 加载/使用句向量模型失败，退化到 TF-IDF：{e}")
        # 退化方案：TF-IDF 字符 ngram（适合中英文混合，免分词）
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.preprocessing import normalize
        vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(2,4), min_df=1)
        X = vec.fit_transform(texts)
        X = normalize(X, norm='l2', copy=False)
        return X.astype('float32').toarray()


def cluster_by_threshold(emb: np.ndarray, threshold: float) -> List[List[int]]:
    """使用基于半径的近邻图进行聚类（余弦相似度>threshold 归为一簇）。
    对于 n<=5000 的规模适用。
    """
    from sklearn.neighbors import NearestNeighbors
    if len(emb) == 0:
        return []
    # 余弦距离 = 1 - 余弦相似度
    radius = max(1.0 - float(threshold), 1e-6)
    nn = NearestNeighbors(metric='cosine', radius=radius, n_jobs=-1)
    nn.fit(emb)
    # 半径邻居
    neigh_ind = nn.radius_neighbors(return_distance=False)

    # 并查集
    parent = list(range(len(emb)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, neigh in enumerate(neigh_ind):
        for j in neigh:
            if i == j:
                continue
            union(i, j)

    groups: Dict[int, List[int]] = defaultdict(list)
    for i in range(len(emb)):
        groups[find(i)].append(i)
    return list(groups.values())


def choose_canonical(indices: List[int], texts: List[str], freqs: List[int]) -> int:
    """选择簇内规范值：优先频次最高；频次相同选更短文本。返回簇内索引的相对位置。"""
    best = None
    for k, idx in enumerate(indices):
        key = (freqs[idx], -len(texts[idx]))
        if best is None or key > best[0]:
            best = (key, k)
    return best[1]


def main():
    ap = argparse.ArgumentParser(description="EAV 语义相似度去重")
    ap.add_argument('--db', default='eav_db')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=3306)
    ap.add_argument('--user', default='eav_user')
    ap.add_argument('--password', default='Eav_pass_1234')
    ap.add_argument('--table-prefix', dest='prefix', default='eav')
    ap.add_argument('--dataset-id', type=int, required=False, help='单个数据集 ID（与 --dataset-ids 二选一）')
    ap.add_argument('--dataset-ids', default=None, help='逗号分隔的多个数据集 ID，会依次处理（与 --dataset-id 二选一）')
    ap.add_argument('--attributes', default=None, help='逗号分隔的属性名列表（可填规范名或显示名）；不填表示处理该数据集的所有属性')
    ap.add_argument('--threshold', type=float, default=0.85, help='聚类相似度阈值（0-1），默认 0.85')
    ap.add_argument('--max-values', type=int, default=5000, help='每个属性最多取多少个不同文本（按频次排序），默认 5000')
    ap.add_argument('--batch-size', type=int, default=128)
    ap.add_argument('--model', default='shibing624/text2vec-base-chinese', help='句向量模型名或本地路径')
    ap.add_argument('--model-cache', default='/data1/xyf/models', help='模型缓存目录（会自动创建）')
    ap.add_argument('--out-dir', default='/data1/xyf/smartgrid/outputs/semantic_dedupe')
    ap.add_argument('--dry-run', action='store_true', default=False, help='仅输出报告，不写入数据库语义表')
    ap.add_argument('--offline', action='store_true', default=False, help='仅离线加载模型（不访问网络）；失败则退化到 TF-IDF')
    ap.add_argument('--device', default='auto', help="设备选择：auto/cpu/cuda/cuda:0 等，默认 auto")
    ap.add_argument('--fp16', action='store_true', default=False, help='GPU 半精度推理（部分模型会自动使用）')
    ap.add_argument('--multi-gpu', type=int, default=0, help='多卡并行编码（0 关闭；>0 指定卡数；-1 使用全部 GPU）')
    ap.add_argument('--global-dedupe', action='store_true', default=False, help='跨数据集全局去重：对多个数据集中“同名属性”的文本合并聚类，然后分别写回各数据集/属性')
    args = ap.parse_args()

    Path(args.model_cache).mkdir(parents=True, exist_ok=True)
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)

    conn = connect_mysql(args.host, args.port, args.user, args.password, args.db)
    cur = conn.cursor()

    # 语义辅助表
    ensure_semantic_tables(cur, args.prefix)
    conn.commit()

    # 确定数据集列表
    ds_list: List[int] = []
    if args.dataset_ids:
        ds_list = [int(s.strip()) for s in args.dataset_ids.split(',') if s.strip()]
    elif args.dataset_id is not None:
        ds_list = [args.dataset_id]
    else:
        raise SystemExit('[ERR] 必须提供 --dataset-id 或 --dataset-ids')

    # 全局去重模式：对多个数据集里“同名属性”合并聚类
    if args.global_dedupe and len(ds_list) > 1:
        print("\n[GLOBAL] 跨数据集全局去重已启用（按同名属性合并）")
        # 解析属性过滤
        targets = None
        if args.attributes:
            targets = [s.strip() for s in args.attributes.split(',') if s.strip()]

        # 获取所有属性并按属性名归组
        attrs_all = fetch_attributes_multi(cur, args.prefix, ds_list, targets)
        groups_by_name: Dict[str, List[AttrInfo]] = defaultdict(list)
        for a in attrs_all:
            key = (a.name or a.display_name or '').strip().lower()
            if not key:
                continue
            groups_by_name[key].append(a)

        if not groups_by_name:
            print('[WARN] 未找到可处理的同名属性组。')
        else:
            for name_key, group_attrs in groups_by_name.items():
                pairs = [(a.dataset_id, a.id) for a in group_attrs if a.dataset_id is not None]
                if not pairs:
                    continue
                print(f"\n[GLOBAL] 处理属性组: '{name_key}'，涉及 {len(pairs)} 个 (dataset,attr) 对")

                # 聚合不同文本（带每个 pair 的频次）
                items = fetch_distinct_texts_multi(cur, args.prefix, pairs, args.max_values)
                if not items:
                    print("[GLOBAL] 无候选文本，跳过。")
                    continue
                texts = [t for (t, _, _) in items]
                freqs_global = [int(f) for (_, f, _) in items]
                per_attr_maps = [m for (_, _, m) in items]  # 与 texts 对齐

                print(f"[GLOBAL] 属性组 '{name_key}' 候选不同文本: {len(texts)}")
                emb = embed_texts(
                    texts,
                    args.model,
                    args.model_cache,
                    batch_size=args.batch_size,
                    offline=args.offline,
                    device=args.device,
                    fp16=args.fp16,
                    multi_gpu=args.multi_gpu,
                )

                clusters = cluster_by_threshold(emb, args.threshold)
                print(f"[GLOBAL] 聚类得到 {len(clusters)} 个簇")

                # 为每个 pair 单独收集 CSV 行
                pair_rows: Dict[Tuple[int, int], List[str]] = defaultdict(lambda: [
                    "from_text,freq,canonical_text,similarity,cluster_size"
                ])

                now = datetime.utcnow()

                # 遍历簇，先统计各 pair 的簇内总频次，再插入 canon，再写映射
                for cid, group in enumerate(clusters):
                    if not group:
                        continue
                    # 选择全局规范项（按全局频次/长度）
                    rel_best = choose_canonical(group, texts, freqs_global)
                    best_idx = group[rel_best]
                    canon_text = texts[best_idx]
                    # 计算全局簇心
                    centroid = emb[group].mean(axis=0)
                    centroid /= (np.linalg.norm(centroid) + 1e-12)

                    # 统计该簇在各 pair 上的总频次
                    pair_cluster_size: Dict[Tuple[int, int], int] = defaultdict(int)
                    for idx in group:
                        per_map = per_attr_maps[idx]
                        for pair, f in per_map.items():
                            pair_cluster_size[pair] += int(f)

                    # 对每个 pair 插入 canon，记录 canon_id
                    cluster_pair_to_canon_id: Dict[Tuple[int, int], int] = {}
                    for pair, csize in pair_cluster_size.items():
                        if csize <= 0:
                            continue
                        dsid, aid = pair
                        if not args.dry_run:
                            cur.execute(
                                f"""INSERT INTO `{args.prefix}_semantic_canon`
                                    (`dataset_id`,`attribute_id`,`canonical_text`,`cluster_size`,`created_at`)
                                    VALUES (%s,%s,%s,%s,%s)
                                """,
                                (dsid, aid, canon_text, int(csize), now)
                            )
                            canon_id = cur.lastrowid
                        else:
                            canon_id = 1  # 占位
                        cluster_pair_to_canon_id[pair] = canon_id

                    # 写入映射（对该簇内每个文本，分发到对应 pair）
                    vecs = emb[group]
                    sims = (vecs @ centroid)
                    for local_idx, idx in enumerate(group):
                        sim = float(sims[local_idx])
                        txt = texts[idx]
                        # 分发到每个出现过的 pair
                        per_map = per_attr_maps[idx]
                        for pair, f in per_map.items():
                            if pair not in cluster_pair_to_canon_id:
                                continue
                            dsid, aid = pair
                            canon_id = cluster_pair_to_canon_id[pair]
                            pair_rows[pair].append(
                                f"{txt.replace(',', '，')},{int(f)},{canon_text.replace(',', '，')},{sim:.5f},{pair_cluster_size[pair]}"
                            )
                            if not args.dry_run:
                                cur.execute(
                                    f"""INSERT INTO `{args.prefix}_semantic_mapping`
                                        (`dataset_id`,`attribute_id`,`from_text`,`canonical_id`,`similarity`,`freq`,`created_at`)
                                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                                    """,
                                    (dsid, aid, txt, canon_id, sim, int(f), now)
                                )

                if not args.dry_run:
                    conn.commit()

                # 写报告：为每个 pair 生成各自的 mapping.csv
                for dsid, aid in pairs:
                    out_dir = Path(args.out_dir) / f"dataset_{dsid}" / f"attr_{aid}_{name_key}"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    report_path = out_dir / 'mapping.csv'
                    rows = pair_rows.get((dsid, aid))
                    if rows and len(rows) > 1:
                        with open(report_path, 'w', encoding='utf-8') as f:
                            f.write("\n".join(rows))
                        print(f"[DONE][GLOBAL] 报告已写入: {report_path}")
                    else:
                        print(f"[INFO][GLOBAL] pair (ds={dsid},attr={aid}) 无映射数据，跳过写入。")
        print("[ALL DONE] 全局语义去重完成。")
        return

    # 普通模式：逐数据集、逐属性处理
    for dsid in ds_list:
        print(f"\n[DATASET] 处理 dataset_id={dsid}")
        # 属性解析
        targets = None
        if args.attributes:
            targets = [s.strip() for s in args.attributes.split(',') if s.strip()]
        attrs = fetch_attributes(cur, args.prefix, dsid, targets)
        if not attrs:
            print('[WARN] 未找到可处理的属性。')
            continue

        # 遍历属性处理
        for attr in attrs:
            values = fetch_distinct_texts(cur, args.prefix, dsid, attr.id, args.max_values)
            if not values:
                continue
            texts, freqs = zip(*values)
            texts = list(texts)
            freqs = list(map(int, freqs))

            print(f"[INFO] 属性 {attr.display_name} (name={attr.name}, id={attr.id}) 候选不同文本: {len(texts)}")
            emb = embed_texts(
                texts,
                args.model,
                args.model_cache,
                batch_size=args.batch_size,
                offline=args.offline,
                device=args.device,
                fp16=args.fp16,
                multi_gpu=args.multi_gpu,
            )

            clusters = cluster_by_threshold(emb, args.threshold)
            print(f"[INFO] 聚类得到 {len(clusters)} 个簇")

            # 输出目录
            out_dir = Path(args.out_dir) / f"dataset_{dsid}" / f"attr_{attr.id}_{attr.name}"
            out_dir.mkdir(parents=True, exist_ok=True)
            report_path = out_dir / 'mapping.csv'

            # 计算并写入
            now = datetime.utcnow()
            rows_csv: List[str] = ["from_text,freq,canonical_text,similarity,cluster_size"]

            # 计算每个簇的规范值与映射
            for group in clusters:
                if not group:
                    continue
                # 选择规范项
                rel_best = choose_canonical(group, texts, freqs)
                best_idx = group[rel_best]
                canon_text = texts[best_idx]
                cluster_size = sum(freqs[i] for i in group)

                # 计算簇心（均值向量）
                centroid = emb[group].mean(axis=0)
                centroid /= (np.linalg.norm(centroid) + 1e-12)

                # 写入 canon 表
                if not args.dry_run:
                    cur.execute(
                        f"""INSERT INTO `{args.prefix}_semantic_canon`
                            (`dataset_id`,`attribute_id`,`canonical_text`,`cluster_size`,`created_at`)
                            VALUES (%s,%s,%s,%s,%s)
                        """,
                        (dsid, attr.id, canon_text, int(cluster_size), now)
                    )
                    canon_id = cur.lastrowid
                else:
                    canon_id = 1  # 占位

                # 遍历簇内样本，写入映射
                vecs = emb[group]
                sims = (vecs @ centroid)
                for idx, sim in zip(group, sims):
                    rows_csv.append(
                        f"{texts[idx].replace(',', '，')},{freqs[idx]},{canon_text.replace(',', '，')},{float(sim):.5f},{cluster_size}"
                    )
                    if not args.dry_run:
                        cur.execute(
                            f"""INSERT INTO `{args.prefix}_semantic_mapping`
                                (`dataset_id`,`attribute_id`,`from_text`,`canonical_id`,`similarity`,`freq`,`created_at`)
                                VALUES (%s,%s,%s,%s,%s,%s,%s)
                            """,
                            (dsid, attr.id, texts[idx], canon_id, float(sim), int(freqs[idx]), now)
                        )

            if not args.dry_run:
                conn.commit()

            # 写报告
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(rows_csv))
            print(f"[DONE] 报告已写入: {report_path}")

    print("[ALL DONE] 语义去重完成。")


if __name__ == '__main__':
    main()
