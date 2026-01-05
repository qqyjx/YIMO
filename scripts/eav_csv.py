#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 CSV 导入到标准 EAV 模型（可与 eav_full.py 互补）。
从根目录的 eav_singal_Database.py 提炼，路径与结构统一到 scripts/。
"""
import argparse
import hashlib
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional
import re

import pandas as pd
import mysql.connector as mysql
from dateutil import parser as dtparser

DEFAULT_CHARSET = "utf8mb4"

NA_TOKENS = {"nan","NaN","NAN","null","NULL","none","None","N/A","#N/A","na","NA","-","—",""}
NA_REGEX = re.compile(r"^\s*(?:nan|null|none|n/a|#n/a|na|)$", re.IGNORECASE)

def _normalize_na(x):
    if x is None:
        return None
    if isinstance(x, float) and str(x) == 'nan':
        return None
    s = str(x).strip()
    if s in NA_TOKENS or NA_REGEX.match(s) is not None:
        return None
    return x


def normalize_attr_name(name: str) -> str:
    if name is None:
        return ""
    s = str(name).strip()
    s = " ".join(s.split())
    return s


def infer_value_type(s: str) -> str:
    if s is None:
        return "text"
    v = str(s).strip()
    if v == "":
        return "text"
    if v.lower() in {"true", "false", "yes", "no", "y", "n", "是", "否"}:
        return "bool"
    try:
        Decimal(v.replace(",", ""))
        if any(ch in v for ch in "-/:T"):
            pass
        else:
            return "number"
    except InvalidOperation:
        pass
    try:
        dtparser.parse(v)
        return "datetime"
    except Exception:
        pass
    return "text"


def majority_type(samples: List[str]) -> str:
    counts = {"number":0, "datetime":0, "bool":0, "text":0}
    for s in samples:
        counts[infer_value_type(s)] += 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], ["number","datetime","bool","text"].index(kv[0])))[0][0]


def connect_mysql(host, port, user, password, database=None):
    kwargs = dict(host=host, port=port, user=user, password=password, charset=DEFAULT_CHARSET, use_unicode=True, autocommit=False)
    if database:
        kwargs["database"] = database
    return mysql.connect(**kwargs)


def pick_collation(cursor, preferred: Optional[str]=None) -> str:
    cursor.execute("SHOW COLLATION LIKE 'utf8mb4%';")
    rows = cursor.fetchall()
    available = {r[0] for r in rows}
    candidates = []
    if preferred:
        candidates.append(preferred)
    candidates.extend(["utf8mb4_0900_ai_ci", "utf8mb4_unicode_ci", "utf8mb4_general_ci"])
    for name in candidates:
        if name in available:
            return name
    cursor.execute("SHOW COLLATION LIKE 'utf8%';")
    rows = cursor.fetchall()
    for name, *_ in rows:
        if name.startswith("utf8"):
            return name
    return "utf8_general_ci"


def ensure_database(cursor, dbname: str, collation: str):
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{dbname}` DEFAULT CHARACTER SET {DEFAULT_CHARSET} COLLATE {collation};")


def ensure_schema(cursor, table_prefix="eav", collation="utf8mb4_unicode_ci"):
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS `{table_prefix}_datasets` (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        name VARCHAR(191) NOT NULL,
        source_file VARCHAR(1024),
        imported_at DATETIME(6) NOT NULL,
        UNIQUE KEY uniq_name (name)
    ) ENGINE=InnoDB ROW_FORMAT=DYNAMIC DEFAULT CHARSET={DEFAULT_CHARSET} COLLATE={collation};
    """)
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS `{table_prefix}_attributes` (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        dataset_id BIGINT NOT NULL,
        name VARCHAR(191) NOT NULL,
        display_name VARCHAR(512) NOT NULL,
        data_type ENUM('text','number','datetime','bool') NOT NULL DEFAULT 'text',
        ord_index INT NULL,
        UNIQUE KEY uniq_attr (dataset_id, name),
        KEY idx_dataset (dataset_id),
        CONSTRAINT fk_attr_dataset FOREIGN KEY (dataset_id) REFERENCES `{table_prefix}_datasets` (id) ON DELETE CASCADE
    ) ENGINE=InnoDB ROW_FORMAT=DYNAMIC DEFAULT CHARSET={DEFAULT_CHARSET} COLLATE={collation};
    """)
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS `{table_prefix}_entities` (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        dataset_id BIGINT NOT NULL,
        external_id VARCHAR(191) NULL,
        row_number BIGINT NOT NULL,
        row_hash CHAR(40) NOT NULL,
        created_at DATETIME(6) NOT NULL,
        UNIQUE KEY uniq_row (dataset_id, row_number),
        KEY idx_ext (dataset_id, external_id),
        KEY idx_hash (dataset_id, row_hash),
        CONSTRAINT fk_ent_dataset FOREIGN KEY (dataset_id) REFERENCES `{table_prefix}_datasets` (id) ON DELETE CASCADE
    ) ENGINE=InnoDB ROW_FORMAT=DYNAMIC DEFAULT CHARSET={DEFAULT_CHARSET} COLLATE={collation};
    """)
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS `{table_prefix}_values` (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        entity_id BIGINT NOT NULL,
        attribute_id BIGINT NOT NULL,
        value_text LONGTEXT NULL,
        value_number DECIMAL(38,10) NULL,
        value_datetime DATETIME(6) NULL,
        value_bool TINYINT(1) NULL,
        raw_text LONGTEXT NULL,
        KEY idx_ent (entity_id),
        KEY idx_attr (attribute_id),
        CONSTRAINT fk_val_entity FOREIGN KEY (entity_id) REFERENCES `{table_prefix}_entities` (id) ON DELETE CASCADE,
        CONSTRAINT fk_val_attribute FOREIGN KEY (attribute_id) REFERENCES `{table_prefix}_attributes` (id) ON DELETE CASCADE
    ) ENGINE=InnoDB ROW_FORMAT=DYNAMIC DEFAULT CHARSET={DEFAULT_CHARSET} COLLATE={collation};
    """)


def upsert_dataset(cursor, table_prefix, name, source_file)->int:
    cursor.execute(
        f"""
        INSERT INTO `{table_prefix}_datasets` (`name`, `source_file`, `imported_at`)
        VALUES (%s,%s,%s) AS new
        ON DUPLICATE KEY UPDATE `source_file`=new.`source_file`, `imported_at`=new.`imported_at`
        """,
        (name, source_file, datetime.utcnow())
    )
    cursor.execute(f"SELECT `id` FROM `{table_prefix}_datasets` WHERE `name`=%s", (name,))
    return cursor.fetchone()[0]


def upsert_attribute(cursor, table_prefix, dataset_id:int, name:str, display_name:str, data_type:str, ord_index:int)->int:
    cursor.execute(
        f"""
        INSERT INTO `{table_prefix}_attributes` (`dataset_id`, `name`, `display_name`, `data_type`, `ord_index`)
            VALUES (%s,%s,%s,%s,%s) AS new
            ON DUPLICATE KEY UPDATE `display_name`=new.`display_name`, `data_type`=new.`data_type`, `ord_index`=new.`ord_index`
        """,
        (dataset_id, name, display_name, data_type, ord_index)
    )
    cursor.execute(f"SELECT `id` FROM `{table_prefix}_attributes` WHERE `dataset_id`=%s AND `name`=%s", (dataset_id, name))
    return cursor.fetchone()[0]


def insert_value(cursor, table_prefix, entity_id:int, attribute_id:int, raw:Optional[str]):
    if raw is None:
        return
    raw = _normalize_na(raw)
    if raw is None or (isinstance(raw, str) and raw.strip()==""):
        return
    s = str(raw).strip()
    vtype = infer_value_type(s)
    value_text = value_number = value_datetime = value_bool = None
    if vtype == "number":
        try:
            value_number = Decimal(s.replace(",", ""))
        except InvalidOperation:
            value_text = s
    elif vtype == "datetime":
        try:
            value_datetime = dtparser.parse(s)
        except Exception:
            value_text = s
    elif vtype == "bool":
        value_bool = 1 if s.lower() in {"true","yes","y","1","是"} else 0
    else:
        value_text = s
    cursor.execute(
        f"""INSERT INTO `{table_prefix}_values` (entity_id, attribute_id, value_text, value_number, value_datetime, value_bool, raw_text)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (entity_id, attribute_id, value_text, value_number, value_datetime, value_bool, s)
    )


def main():
    ap = argparse.ArgumentParser(description="将 CSV 导入 MySQL 标准 EAV 模型")
    ap.add_argument("--csv", required=True, help="CSV 文件路径")
    ap.add_argument("--db", default="eav_db", help="MySQL 数据库名（默认 eav_db）")
    ap.add_argument("--host", default="127.0.0.1", help="MySQL 主机（默认 127.0.0.1）")
    ap.add_argument("--port", type=int, default=3306, help="MySQL 端口（默认 3306）")
    ap.add_argument("--user", default="root", help="MySQL 用户名（默认 root）")
    ap.add_argument("--password", default="root", help="MySQL 密码（默认 root）")
    ap.add_argument("--table-prefix", default="eav", help="表前缀（默认 eav）")
    ap.add_argument("--dataset-name", default=None, help="数据集名称（默认取文件名不含后缀）")
    ap.add_argument("--pk-column", default=None, help="CSV 中的主键列名（可选）")
    ap.add_argument("--sample-rows", type=int, default=200, help="类型推断采样数（默认200）")
    ap.add_argument("--table-name", default=None, help="可读别名（用于数据集名称显示）")
    ap.add_argument("--collation", default=None, help="强制使用某个排序规则（如 utf8mb4_unicode_ci）。若不指定将自动探测。")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"[ERROR] CSV 文件不存在: {csv_path}", file=sys.stderr)
        sys.exit(1)

    dataset_name = args.dataset_name or csv_path.stem
    if args.table_name:
        dataset_name = f"{dataset_name} ({args.table_name})"

    print(f"[INFO] 读取 CSV: {csv_path}")
    # 尝试多编码导入
    last_exc = None
    for enc in ("utf-8-sig","utf-8","gb18030"):
        try:
            df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, na_values=["", "NaN", "NULL", "None"], encoding=enc)
            df = df.apply(lambda s: s.map(_normalize_na))
            break
        except Exception as e:
            last_exc = e
            df = None
    if df is None:
        raise last_exc

    # 探测排序规则
    print(f"[INFO] 连接 MySQL: {args.user}@{args.host}:{args.port} / {args.db}")
    root_conn = connect_mysql(args.host, args.port, args.user, args.password)
    root_cur = root_conn.cursor()
    chosen_collation = args.collation or pick_collation(root_cur)
    print(f"[INFO] 使用排序规则: {chosen_collation}")

    try:
        ensure_database(root_cur, args.db, chosen_collation)
        root_conn.commit()
    except Exception as e:
        print(f"[WARN] 无权限创建数据库或已存在，尝试直接使用现有库 '{args.db}'：{e}")
    finally:
        root_cur.close()
        root_conn.close()

    # 连接到目标库
    conn = connect_mysql(args.host, args.port, args.user, args.password, args.db)
    cur = conn.cursor()

    ensure_schema(cur, table_prefix=args.table_prefix, collation=chosen_collation)
    conn.commit()

    dataset_id = upsert_dataset(cur, args.table_prefix, dataset_name, str(csv_path.resolve()))
    conn.commit()
    print(f"[INFO] 数据集 ID: {dataset_id}")

    original_cols = list(df.columns)
    cleaned_cols = [normalize_attr_name(c) for c in original_cols]
    attr_ids: Dict[str, int] = {}
    for i, (display_name, name) in enumerate(zip(original_cols, cleaned_cols)):
        samples = [v for v in df[display_name].dropna().tolist() if (isinstance(v,str) and v.strip()!="")]
        samples = samples[:args.sample_rows]
        dtype = majority_type(samples) if samples else "text"
        cur.execute(
            f"""INSERT INTO `{args.table_prefix}_attributes` (`dataset_id`, `name`, `display_name`, `data_type`, `ord_index`)
                VALUES (%s,%s,%s,%s,%s) AS new
                ON DUPLICATE KEY UPDATE `display_name`=new.`display_name`, `data_type`=new.`data_type`, `ord_index`=new.`ord_index`""",
            (dataset_id, name, display_name, dtype, i)
        )
        cur.execute(
            f"SELECT `id` FROM `{args.table_prefix}_attributes` WHERE `dataset_id`=%s AND `name`=%s",
            (dataset_id, name)
        )
        attr_ids[name] = cur.fetchone()[0]
    conn.commit()
    print(f"[INFO] 属性数量: {len(attr_ids)}")

    inserted = 0
    for idx, row in df.iterrows():
        row_number = idx + 1
        values = [row[col] for col in original_cols]
        rhash = hashlib.sha1("".join("" if v is None else str(v) for v in values).encode("utf-8")).hexdigest()
        external_id = None
        if args.pk_column and args.pk_column in df.columns:
            external_id = row[args.pk_column]
        cur.execute(
            f"""INSERT INTO `{args.table_prefix}_entities` (`dataset_id`, `row_number`, `external_id`, `row_hash`, `created_at`)
                VALUES (%s,%s,%s,%s,%s) AS new
                ON DUPLICATE KEY UPDATE `external_id`=new.`external_id`, `row_hash`=new.`row_hash`""",
            (dataset_id, row_number, external_id, rhash, datetime.utcnow())
        )
        cur.execute(
            f"SELECT `id` FROM `{args.table_prefix}_entities` WHERE `dataset_id`=%s AND `row_number`=%s",
            (dataset_id, row_number)
        )
        ent_id = cur.fetchone()[0]
        for display_name, name in zip(original_cols, cleaned_cols):
            val = row[display_name]
            if val is None or (isinstance(val,str) and val.strip()==""):
                continue
            s = str(val).strip()
            vtype = infer_value_type(s)
            value_text = value_number = value_datetime = value_bool = None
            if vtype == "number":
                try:
                    value_number = Decimal(s.replace(",", ""))
                except InvalidOperation:
                    value_text = s
            elif vtype == "datetime":
                try:
                    value_datetime = dtparser.parse(s)
                except Exception:
                    value_text = s
            elif vtype == "bool":
                value_bool = 1 if s.lower() in {"true","yes","y","1","是"} else 0
            else:
                value_text = s
            cur.execute(
                f"""INSERT INTO `{args.table_prefix}_values` (`entity_id`, `attribute_id`, `value_text`, `value_number`, `value_datetime`, `value_bool`, `raw_text`)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (ent_id, attr_ids[name], value_text, value_number, value_datetime, value_bool, s)
            )
        inserted += 1
        if inserted % 1000 == 0:
            conn.commit()
            print(f"[INFO] 已导入 {inserted} 行...")

    conn.commit()
    print(f"[DONE] 导入完成，共处理 {inserted} 行。")


if __name__ == "__main__":
    main()
