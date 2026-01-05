#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import pymysql


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default='eav_db')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=3306)
    ap.add_argument('--user', default='eav_user')
    ap.add_argument('--password', default='Eav_pass_1234')
    ap.add_argument('--sql-file', required=True, help='要执行的 SQL 文件路径')
    args = ap.parse_args()

    sql_text = open(args.sql_file, 'r', encoding='utf-8').read()

    conn = pymysql.connect(host=args.host, port=args.port, user=args.user, password=args.password, database=args.db, charset='utf8mb4', autocommit=True)
    cur = conn.cursor()
    try:
        for stmt in [s.strip() for s in sql_text.split(';') if s.strip()]:
            cur.execute(stmt)
        print(f"[OK] Executed SQL from {args.sql_file}")
    finally:
        cur.close(); conn.close()


if __name__ == '__main__':
    main()
