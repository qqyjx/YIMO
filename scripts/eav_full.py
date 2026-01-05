#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
excel_to_eav.py
----------------
将「任意 Excel 文件（含多个表单/工作表）」导入到 MySQL 的标准 EAV（Entity-Attribute-Value）模型中。

特性
- 一次读取 Excel 的所有表单（sheet），每一行视为一个实体（entity）。
- 同名字段（列名）在同一数据集内**自动合并**为同一个属性（attribute）。
- 自动建库/建表；自动选择可用的 utf8/utf8mb4 排序规则；兼容 MySQL 5.7 / 8.0 / MariaDB。
- 处理中文与缺项（NaN/NULL/N/A/空白等），缺项不写入值表。
- 自动推断列类型：text / number / datetime / bool（各列采样，多数投票）。
- 进度条：对表单与行导入使用 tqdm 展示进度。
- 索引兼容旧版 InnoDB：将参与索引的 VARCHAR 统一为 191 字符，且启用 ROW_FORMAT=DYNAMIC。
- 可将工作表名写入一个系统属性（默认开启，列名为“__sheet__”）。

依赖
  pip install pandas openpyxl mysql-connector-python python-dateutil tqdm

用法示例
  python eav_full.py --excel ./data.xlsx
  python eav_full.py --excel ./data.xlsx --db eav_db --host 127.0.0.1 --user root --password root
  python eav_full.py --excel ./data.xlsx --table-name 项目权限清单 --pk-column 主键列
"""

import argparse
import hashlib
import sys
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
import mysql.connector as mysql
try:
    import pymysql
    HAS_PYMYSQL = True
except Exception:
    HAS_PYMYSQL = False
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from pandas import ExcelFile
from dateutil import parser as dtparser
from tqdm.auto import tqdm

# ---------- 常量与 NA 规范 ----------

DEFAULT_CHARSET = "utf8mb4"  # 尝试使用 utf8mb4；若服务器不支持再降级到 utf8
NA_TOKENS = {"nan", "NaN", "NAN", "null", "NULL", "none", "None", "N/A", "#N/A", "na", "NA", "-", "—", ""}
NA_REGEX = re.compile(r"^\s*(?:nan|null|none|n/a|#n/a|na|)$", re.IGNORECASE)

def _normalize_na(x):
    if x is None:
        return None
    if isinstance(x, float) and str(x) == "nan":
        return None
    s = str(x).strip()
    if s in NA_TOKENS or NA_REGEX.match(s) is not None:
        return None
    return x

# ---------- 工具函数 ----------

def normalize_attr_name(name: str) -> str:
    """将属性名标准化为便于唯一索引的 key（不改变展示名）。"""
    if name is None:
        return ""
    s = str(name).strip()
    s = " ".join(s.split())
    return s

def infer_value_type(s: str) -> str:
    """推断单个值的数据类型。返回: number/datetime/bool/text"""
    if s is None:
        return "text"
    v = str(s).strip()
    if v == "":
        return "text"
    # bool
    if v.lower() in {"true", "false", "yes", "no", "y", "n", "是", "否"}:
        return "bool"
    # number
    try:
        Decimal(v.replace(",", ""))
        # 若包含日期字符，则不直接判为 number
        if any(ch in v for ch in "-/:T"):
            pass
        else:
            return "number"
    except InvalidOperation:
        pass
    # datetime
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
    # 优先级：number > datetime > bool > text（相同计数时按此顺序）
    return sorted(counts.items(), key=lambda kv: (-kv[1], ["number","datetime","bool","text"].index(kv[0])))[0][0]

def connect_mysql(host, port, user, password, database=None):
    """优先使用 PyMySQL；若不可用再回退 mysql-connector。"""
    if HAS_PYMYSQL:
        py_kwargs = dict(
            host=host,
            port=port,
            user=user,
            password=password,
            charset=DEFAULT_CHARSET,
            autocommit=False,
        )
        if database:
            py_kwargs["database"] = database
        return pymysql.connect(**py_kwargs)
    # 回退 mysql-connector
    kwargs = dict(
        host=host,
        port=port,
        user=user,
        password=password,
        use_unicode=True,
        charset=DEFAULT_CHARSET,
        autocommit=False,
        get_server_public_key=True,
    )
    if database:
        kwargs["database"] = database
    return mysql.connect(**kwargs)

def pick_collation(cursor, preferred: Optional[str]=None) -> Tuple[str, str]:
    """
    基于服务器支持情况选择字符集 + 排序规则。
    优先 utf8mb4；若服务器没有任何 utf8mb4 排序规则，则退回 utf8。
    返回 (charset, collation)
    """
    # 优先 utf8mb4
    cursor.execute("SHOW COLLATION LIKE 'utf8mb4%';")
    rows = cursor.fetchall()
    if rows:
        available = {r[0] for r in rows}
        candidates = []
        if preferred:
            candidates.append(preferred)
        candidates.extend(["utf8mb4_0900_ai_ci", "utf8mb4_unicode_ci", "utf8mb4_general_ci"])
        for name in candidates:
            if name in available:
                return "utf8mb4", name
        # 任取一个 utf8mb4 的排序规则
        for name in available:
            if str(name).startswith("utf8mb4"):
                return "utf8mb4", name

    # 退回 utf8
    cursor.execute("SHOW COLLATION LIKE 'utf8%';")
    rows = cursor.fetchall()
    if rows:
        # 优先常见
        available = {r[0] for r in rows}
        for cand in ["utf8_unicode_ci", "utf8_general_ci"]:
            if cand in available:
                return "utf8", cand
        # 任取一个 utf8
        for name in available:
            if str(name).startswith("utf8"):
                return "utf8", name

    # 最后兜底
    return "utf8", "utf8_general_ci"

def ensure_database(cursor, dbname: str, charset: str, collation: str):
    cursor.execute(
        f"CREATE DATABASE IF NOT EXISTS `{dbname}` "
        f"DEFAULT CHARACTER SET {charset} COLLATE {collation};"
    )

def ensure_schema(cursor, table_prefix="eav", charset="utf8mb4", collation="utf8mb4_unicode_ci"):
    """
    注意：为兼容旧 InnoDB 767 字节限制，所有参与索引的可变长字符列统一使用 VARCHAR(191)，
    并指定 ROW_FORMAT=DYNAMIC。
    """
    # datasets
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS `{table_prefix}_datasets` (
        `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
        `name` VARCHAR(191) NOT NULL,
        `source_file` VARCHAR(1024),
        `imported_at` DATETIME(6) NOT NULL,
        UNIQUE KEY `uniq_name` (`name`)
    ) ENGINE=InnoDB ROW_FORMAT=DYNAMIC DEFAULT CHARSET={charset} COLLATE={collation};
    """)
    # attributes
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS `{table_prefix}_attributes` (
        `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
        `dataset_id` BIGINT NOT NULL,
        `name` VARCHAR(191) NOT NULL,
        `display_name` VARCHAR(512) NOT NULL,
        `data_type` ENUM('text','number','datetime','bool') NOT NULL DEFAULT 'text',
        `ord_index` INT NULL,
        UNIQUE KEY `uniq_attr` (`dataset_id`, `name`),
        KEY `idx_dataset` (`dataset_id`),
        CONSTRAINT `fk_attr_dataset` FOREIGN KEY (`dataset_id`)
            REFERENCES `{table_prefix}_datasets` (`id`) ON DELETE CASCADE
    ) ENGINE=InnoDB ROW_FORMAT=DYNAMIC DEFAULT CHARSET={charset} COLLATE={collation};
    """)
    # entities
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS `{table_prefix}_entities` (
        `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
        `dataset_id` BIGINT NOT NULL,
        `external_id` VARCHAR(191) NULL,
        `row_number` BIGINT NOT NULL,
        `row_hash` CHAR(40) NOT NULL,
        `created_at` DATETIME(6) NOT NULL,
        UNIQUE KEY `uniq_row` (`dataset_id`, `row_number`),
        KEY `idx_ext` (`dataset_id`, `external_id`),
        KEY `idx_hash` (`dataset_id`, `row_hash`),
        CONSTRAINT `fk_ent_dataset` FOREIGN KEY (`dataset_id`)
            REFERENCES `{table_prefix}_datasets` (`id`) ON DELETE CASCADE
    ) ENGINE=InnoDB ROW_FORMAT=DYNAMIC DEFAULT CHARSET={charset} COLLATE={collation};
    """)
    # values
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS `{table_prefix}_values` (
        `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
        `entity_id` BIGINT NOT NULL,
        `attribute_id` BIGINT NOT NULL,
        `value_text` LONGTEXT NULL,
        `value_number` DECIMAL(38,10) NULL,
        `value_datetime` DATETIME(6) NULL,
        `value_bool` TINYINT(1) NULL,
        `raw_text` LONGTEXT NULL,
        KEY `idx_ent` (`entity_id`),
        KEY `idx_attr` (`attribute_id`),
        CONSTRAINT `fk_val_entity` FOREIGN KEY (`entity_id`)
            REFERENCES `{table_prefix}_entities` (`id`) ON DELETE CASCADE,
        CONSTRAINT `fk_val_attribute` FOREIGN KEY (`attribute_id`)
            REFERENCES `{table_prefix}_attributes` (`id`) ON DELETE CASCADE
    ) ENGINE=InnoDB ROW_FORMAT=DYNAMIC DEFAULT CHARSET={charset} COLLATE={collation};
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
        INSERT INTO `{table_prefix}_attributes`
            (`dataset_id`, `name`, `display_name`, `data_type`, `ord_index`)
            VALUES (%s,%s,%s,%s,%s) AS new
            ON DUPLICATE KEY UPDATE
                `display_name`=new.`display_name`,
                `data_type`=new.`data_type`,
                `ord_index`=new.`ord_index`
        """,
        (dataset_id, name, display_name, data_type, ord_index)
    )
    cursor.execute(
        f"SELECT `id` FROM `{table_prefix}_attributes` WHERE `dataset_id`=%s AND `name`=%s",
        (dataset_id, name)
    )
    return cursor.fetchone()[0]

def sha1_row(values: List[Optional[str]]) -> str:
    m = hashlib.sha1()
    for v in values:
        if v is None:
            m.update(b"\xff")
        else:
            m.update(str(v).encode("utf-8"))
        m.update(b"\x1f")
    return m.hexdigest()

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
            d = Decimal(s.replace(",", ""))
            if d.is_nan() or d.is_infinite():
                value_text = s
            else:
                value_number = d
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
        f"""INSERT INTO `{table_prefix}_values`
            (entity_id, attribute_id, value_text, value_number, value_datetime, value_bool, raw_text)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (entity_id, attribute_id, value_text, value_number, value_datetime, value_bool, s)
    )

# ---------- Excel 加载 ----------

def load_excel_all_sheets(path: Path) -> Dict[str, pd.DataFrame]:
    """
    读取 Excel 所有表单为 {sheet_name: DataFrame[str]}，统一做 NA 规范化与去空白。
    使用更高效的数据处理方式。
    """
    try:
        xls = ExcelFile(path)
        sheets = {}
        na_values = list(NA_TOKENS)
        for sheet in xls.sheet_names:
            df = xls.parse(
                sheet_name=sheet,
                dtype=str,
                keep_default_na=False,
                na_values=na_values
            )
            for col in df.columns:
                mask = df[col].isna()
                if mask.any():
                    df.loc[mask, col] = None
                mask = df[col].isin(NA_TOKENS)
                if mask.any():
                    df.loc[mask, col] = None
                mask = df[col].str.strip().eq('')
                if mask.any():
                    df.loc[mask, col] = None
            sheets[sheet] = df
        if not sheets:
            raise ValueError("Excel文件中没有找到任何工作表")
        return sheets
    except Exception as e:
        print(f"[ERROR] 读取Excel文件时出错: {str(e)}", file=sys.stderr)
        raise

# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser(description="将 Excel(含多表单) 导入 MySQL 的标准 EAV 模型")
    ap.add_argument("--excel", required=True, help="Excel 文件路径（.xlsx/.xls）")
    ap.add_argument("--db", default="eav_db", help="MySQL 数据库名（默认 eav_db）")
    ap.add_argument("--host", default="127.0.0.1", help="MySQL 主机（默认 127.0.0.1）")
    ap.add_argument("--port", type=int, default=3306, help="MySQL 端口（默认 3306）")
    ap.add_argument("--user", default="root", help="MySQL 用户名（默认 root）")
    ap.add_argument("--password", default="root", help="MySQL 密码（默认 root）")
    ap.add_argument("--table-prefix", default="eav", help="表前缀（默认 eav）")
    ap.add_argument("--dataset-name", default=None, help="数据集名称（默认取文件名不含后缀）")
    ap.add_argument("--pk-column", default=None, help="主键列名（可选，用于 external_id）")
    ap.add_argument("--sample-rows", type=int, default=200, help="列类型推断采样数（默认200）")
    ap.add_argument("--table-name", default=None, help="数据集可读别名（仅展示）")
    ap.add_argument("--collation", default=None, help="强制排序规则（如 utf8mb4_unicode_ci）。若不指定将自动探测。")
    ap.add_argument("--add-sheet-attr", action="store_true", default=True, help="为每个实体添加系统属性 __sheet__（默认开启）")
    args = ap.parse_args()

    excel_path = Path(args.excel)
    if not excel_path.exists():
        print(f"[ERROR] Excel 文件不存在: {excel_path}", file=sys.stderr)
        sys.exit(1)

    dataset_name = args.dataset_name or excel_path.stem
    if args.table_name:
        dataset_name = f"{dataset_name} ({args.table_name})"

    print(f"[INFO] 读取 Excel: {excel_path}")
    sheet_dfs = load_excel_all_sheets(excel_path)
    if not sheet_dfs:
        print("[ERROR] Excel 文件没有任何表单。", file=sys.stderr)
        sys.exit(1)

    # 建立初始连接，探测 charset/collation
    print(f"[INFO] 连接 MySQL: {args.user}@{args.host}:{args.port} / {args.db}")
    root_conn = connect_mysql(args.host, args.port, args.user, args.password)
    root_cur = root_conn.cursor()
    chosen_charset = DEFAULT_CHARSET
    chosen_charset, chosen_collation = (chosen_charset, args.collation) if args.collation else pick_collation(root_cur)
    print(f"[INFO] 使用字符集/排序规则: {chosen_charset} / {chosen_collation}")

    # 创建数据库：若当前账号无权限，优雅跳过（要求库已由管理员预先创建）
    try:
        ensure_database(root_cur, args.db, chosen_charset, chosen_collation)
        root_conn.commit()
    except Exception as e:
        print(f"[WARN] 无权限创建数据库或已存在，将尝试直接使用现有库 '{args.db}' ：{e}")
    root_cur.close()
    root_conn.close()

    # 连接到目标库
    conn = connect_mysql(args.host, args.port, args.user, args.password, args.db)
    cur = conn.cursor()

    # 建表
    ensure_schema(cur, table_prefix=args.table_prefix, charset=chosen_charset, collation=chosen_collation)
    conn.commit()

    # 数据集记录
    dataset_id = upsert_dataset(cur, args.table_prefix, dataset_name, str(excel_path.resolve()))
    conn.commit()
    print(f"[INFO] 数据集 ID: {dataset_id}")

    # --- 收集所有列名，建立属性（合并同名） ---
    from collections import OrderedDict
    all_columns_ordered: "OrderedDict[str, Tuple[str,int]]" = OrderedDict()

    if args.add_sheet_attr and "__sheet__" not in all_columns_ordered:
        all_columns_ordered["__sheet__"] = ("__sheet__", -1)

    for sheet_name, df in sheet_dfs.items():
        for col in list(df.columns):
            norm = normalize_attr_name(col)
            if norm not in all_columns_ordered:
                all_columns_ordered[norm] = (str(col), len(all_columns_ordered))

    # 推断类型并 upsert 属性
    attr_ids: Dict[str, int] = {}
    print("[INFO] 开始属性类型推断与建表（合并同名字段）...")
    for i, (norm_name, (display_name, _)) in enumerate(all_columns_ordered.items()):
        if norm_name == "__sheet__" and args.add_sheet_attr:
            dtype = "text"
        else:
            samples: List[str] = []
            for sheet_name, df in sheet_dfs.items():
                if display_name in df.columns:
                    vals = [v for v in df[display_name].dropna().tolist() if (isinstance(v, str) and v.strip() != "")]
                    samples.extend(vals[:args.sample_rows])
                else:
                    for c in df.columns:
                        if normalize_attr_name(c) == norm_name:
                            vals = [v for v in df[c].dropna().tolist() if (isinstance(v, str) and v.strip() != "")]
                            samples.extend(vals[:args.sample_rows])
                            break
        dtype = "text" if (norm_name == "__sheet__" and args.add_sheet_attr) else (majority_type(samples) if samples else "text")
        attr_id = upsert_attribute(cur, args.table_prefix, dataset_id, norm_name, display_name, dtype, i if norm_name != "__sheet__" else -1)
        attr_ids[norm_name] = attr_id
    conn.commit()
    print(f"[INFO] 属性数量: {len(attr_ids)}")

    # 导入实体与值
    print("[INFO] 开始导入实体与值 ...")
    global_row_no = 0
    sheet_names = list(sheet_dfs.keys())

    for sheet_name in tqdm(sheet_names, desc="表单(Sheets)", unit="sheet"):
        df = sheet_dfs[sheet_name]
        for idx in tqdm(range(len(df)), desc=f"行(Row)@{sheet_name}", unit="row", leave=False):
            row = df.iloc[idx]
            global_row_no += 1
            row_values_for_hash = []
            for norm_name, (display_name, _) in all_columns_ordered.items():
                if norm_name == "__sheet__" and args.add_sheet_attr:
                    row_values_for_hash.append(sheet_name)
                    continue
                value = None
                if display_name in df.columns:
                    value = row.get(display_name, None)
                else:
                    for c in df.columns:
                        if normalize_attr_name(c) == norm_name:
                            value = row.get(c, None)
                            break
                row_values_for_hash.append(value)

            rhash = sha1_row(row_values_for_hash)

            external_id = None
            if args.pk_column:
                if args.pk_column in df.columns:
                    external_id = row.get(args.pk_column, None)
                else:
                    for c in df.columns:
                        if normalize_attr_name(c) == normalize_attr_name(args.pk_column):
                            external_id = row.get(c, None)
                            break
            if external_id is None:
                external_id = f"{sheet_name}!{idx+1}"

            cur.execute(
                f"""
                INSERT INTO `{args.table_prefix}_entities`
                    (`dataset_id`, `row_number`, `external_id`, `row_hash`, `created_at`)
                    VALUES (%s,%s,%s,%s,%s) AS new
                    ON DUPLICATE KEY UPDATE `external_id`=new.`external_id`, `row_hash`=new.`row_hash`
                """,
                (dataset_id, global_row_no, external_id, rhash, datetime.utcnow())
            )
            cur.execute(
                f"SELECT `id` FROM `{args.table_prefix}_entities` WHERE `dataset_id`=%s AND `row_number`=%s",
                (dataset_id, global_row_no)
            )
            ent_id = cur.fetchone()[0]

            if args.add_sheet_attr:
                insert_value(cur, args.table_prefix, ent_id, attr_ids["__sheet__"], sheet_name)

            for c in df.columns:
                norm = normalize_attr_name(c)
                if norm not in attr_ids:
                    continue
                val = row.get(c, None)
                insert_value(cur, args.table_prefix, ent_id, attr_ids[norm], val)

            if (global_row_no % 1000) == 0:
                conn.commit()

    conn.commit()
    print(f"[DONE] 导入完成：共导入 {len(sheet_names)} 个表单、{global_row_no} 行实体。")
    print("[HINT] 典型查询：")
    print(f"  -- 列出数据集属性：")
    print(f"  SELECT a.display_name, a.data_type FROM {args.table_prefix}_attributes a WHERE a.dataset_id = {dataset_id} ORDER BY a.ord_index;")
    print(f"  -- 查询第1个实体的所有属性值：")
    print(f"  SELECT a.display_name, v.value_text, v.value_number, v.value_datetime, v.value_bool")
    print(f"  FROM {args.table_prefix}_entities e")
    print(f"  JOIN {args.table_prefix}_values v ON v.entity_id=e.id")
    print(f"  JOIN {args.table_prefix}_attributes a ON a.id=v.attribute_id")
    print(f"  WHERE e.dataset_id={dataset_id} AND e.row_number=1;")

if __name__ == "__main__":
    main()
