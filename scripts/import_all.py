#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量导入 /data1/xyf/smartgrid/data 目录下的所有 .xlsx 到 MySQL 的 EAV 模型。
会为每个文件运行一次 eav_full.py。
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR_DEFAULT = ROOT / 'data'
EAV_SCRIPT = ROOT / 'scripts' / 'eav_full.py'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=str(DATA_DIR_DEFAULT), help='包含 .xlsx 的目录，默认 /data1/xyf/smartgrid/data')
    ap.add_argument('--db', default='eav_db')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=3306)
    ap.add_argument('--user', default='eav_user')
    ap.add_argument('--password', default='Eav_pass_1234')
    ap.add_argument('--table-prefix', default='eav')
    args = ap.parse_args()

    data_dir = Path(args.dir)
    files = sorted([p for p in data_dir.glob('*.xlsx')])
    if not files:
        print(f'[WARN] 目录中未找到 .xlsx: {data_dir}')
        return

    for f in files:
        print(f'\n[RUN] 导入 {f.name} ...')
        cmd = [
            sys.executable, str(EAV_SCRIPT),
            '--excel', str(f),
            '--db', args.db,
            '--host', args.host,
            '--port', str(args.port),
            '--user', args.user,
            '--password', args.password,
            '--table-prefix', args.table_prefix
        ]
        subprocess.check_call(cmd)


if __name__ == '__main__':
    main()
