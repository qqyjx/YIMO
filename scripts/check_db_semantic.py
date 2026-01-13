#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import pymysql


def q(cur, sql, args=None):
    cur.execute(sql, args or ())
    return cur.fetchall()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default='eav_db')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=3306)
    ap.add_argument('--user', default='eav_user')
    ap.add_argument('--password', default='eavpass123')
    ap.add_argument('--prefix', default='eav')
    ap.add_argument('--out', default='/data1/xyf/smartgrid/outputs/semantic_dedupe_gpu_full/summary/db_check.txt')
    args = ap.parse_args()

    conn = pymysql.connect(host=args.host, port=args.port, user=args.user, password=args.password, database=args.db, charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
    cur = conn.cursor()

    with open(args.out, 'w', encoding='utf-8') as f:
        def write(line):
            f.write(str(line) + '\n')
        # 1) 统计表行数
        for t in (f"{args.prefix}_semantic_canon", f"{args.prefix}_semantic_mapping"):
            rows = q(cur, f"SELECT COUNT(*) AS c FROM `{t}`")
            write(f"{t}.count = {rows[0]['c']}")
        # 2) 映射与规范的关联健康度（抽样 TOP10 规范）
        rows = q(cur, f"""
            SELECT c.id AS canon_id, c.dataset_id, c.attribute_id, c.canonical_text, c.cluster_size,
                   COUNT(m.id) AS mapping_rows
            FROM `{args.prefix}_semantic_canon` c
            LEFT JOIN `{args.prefix}_semantic_mapping` m ON m.canonical_id = c.id
            GROUP BY c.id
            ORDER BY c.cluster_size DESC
            LIMIT 10
        """)
        write("\nTOP10 canon by cluster_size:")
        for r in rows:
            write(r)
        # 3) 映射孤儿检查（理论上为0）
        rows = q(cur, f"""
            SELECT COUNT(*) AS orphans
            FROM `{args.prefix}_semantic_mapping` m
            LEFT JOIN `{args.prefix}_semantic_canon` c ON c.id = m.canonical_id
            WHERE c.id IS NULL
        """)
        write(f"\norphan_mappings = {rows[0]['orphans']}")

    cur.close(); conn.close()
    print(f"[OK] DB check written to {args.out}")


if __name__ == '__main__':
    main()
