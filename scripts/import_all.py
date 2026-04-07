#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量导入目录下的所有 .xlsx 到 MySQL 的 EAV 模型。
支持生命周期阶段标记（YIMO 对象抽取与三层架构关联系统）。

用法:
  python scripts/import_all.py --dir ./data --stage Operation
  python scripts/import_all.py --dir ./design_docs --stage Design
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR_DEFAULT = ROOT / 'data'
EAV_SCRIPT = ROOT / 'scripts' / 'eav_full.py'

# 有效的生命周期阶段
VALID_STAGES = ['Planning', 'Design', 'Construction', 'Operation']


def main():
    ap = argparse.ArgumentParser(description='批量导入Excel到EAV模型（支持生命周期阶段）')
    ap.add_argument('--dir', default=str(DATA_DIR_DEFAULT), help='包含 .xlsx 的目录')
    ap.add_argument('--db', default='eav_db')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=3306)
    ap.add_argument('--user', default='eav_user')
    ap.add_argument('--password', default='eavpass123')
    ap.add_argument('--table-prefix', default='eav')
    # 生命周期阶段参数
    ap.add_argument('--stage', default='Operation', choices=VALID_STAGES,
                    help='生命周期阶段: Planning/Design/Construction/Operation')
    ap.add_argument('--stage-date', default=None, help='阶段日期（如 2026-01-09）')
    ap.add_argument('--stage-source', default=None, help='数据来源系统')
    ap.add_argument('--data-domain', default=None, help='数据域编码（如 jicai/shupeidian）')
    ap.add_argument('--incremental', action='store_true', help='启用增量导入')
    args = ap.parse_args()

    data_dir = Path(args.dir)
    files = sorted([p for p in data_dir.glob('*.xlsx')])
    if not files:
        print(f'[WARN] 目录中未找到 .xlsx: {data_dir}')
        return

    print(f'[INFO] 🏷️  批量导入阶段: {args.stage}')
    print(f'[INFO] 📁 目录: {data_dir}')
    print(f'[INFO] 📊 发现 {len(files)} 个文件')
    print()

    for f in files:
        print(f'\n[RUN] 导入 {f.name} (阶段: {args.stage}) ...')
        cmd = [
            sys.executable, str(EAV_SCRIPT),
            '--excel', str(f),
            '--db', args.db,
            '--host', args.host,
            '--port', str(args.port),
            '--user', args.user,
            '--password', args.password,
            '--table-prefix', args.table_prefix,
            '--stage', args.stage,
        ]
        if args.stage_date:
            cmd.extend(['--stage-date', args.stage_date])
        if args.stage_source:
            cmd.extend(['--stage-source', args.stage_source])
        if args.data_domain:
            cmd.extend(['--data-domain', args.data_domain])
        if args.incremental:
            cmd.append('--incremental')
        subprocess.check_call(cmd)
    
    print(f'\n[DONE] ✅ 批量导入完成，共处理 {len(files)} 个文件')


if __name__ == '__main__':
    main()
