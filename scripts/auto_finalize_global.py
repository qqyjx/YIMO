#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动监控全局去重任务并在完成后生成汇总与技术报告。

逻辑：
- 周期性调用 resume_global_missing.py（不加 --exec）检测是否还有缺失组；
- 若缺失为 0，则：
  - 运行 summarize_dedupe_outputs.py 生成 global/summary/* 汇总；
  - 运行 check_db_semantic.py 生成 global/summary/db_check.txt；
  - 运行 generate_tech_report.py 生成 global/summary/TECH_REPORT.md；
  - 写入 global/summary/FINALIZED_OK 标记文件并退出。

用法示例：
  python scripts/auto_finalize_global.py \
    --out-dir /data1/xyf/smartgrid/outputs/semantic_dedupe_gpu_full/global \
    --dataset-ids 1,2,3 --interval 120
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def run_cmd(cmd, cwd=None, capture=False):
    if capture:
        return subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    else:
        return subprocess.run(cmd, cwd=cwd, check=False)


def detect_missing_groups(pybin: Path, scripts_dir: Path, out_dir: Path, dataset_ids: str):
    """返回 (missing_count, output_text)"""
    cmd = [str(pybin), str(scripts_dir / 'resume_global_missing.py'), '--dataset-ids', dataset_ids, '--out-dir', str(out_dir)]
    res = run_cmd(cmd, capture=True)
    text = res.stdout or ''
    # 判断无缺失
    if '[OK] No missing global groups detected. Nothing to resume.' in text:
        return 0, text
    # 估算缺失项数量（统计以 "- key=" 开头的行数）
    missing = 0
    for line in text.splitlines():
        if line.strip().startswith('- key='):
            missing += 1
    return missing, text


def write_file(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', default='/data1/xyf/smartgrid/outputs/semantic_dedupe_gpu_full/global')
    ap.add_argument('--dataset-ids', default='1,2,3')
    ap.add_argument('--interval', type=int, default=120, help='轮询间隔秒数')
    ap.add_argument('--py', default='/data1/xyf/smartgrid/grideav/bin/python')
    ap.add_argument('--scripts-dir', default='/data1/xyf/smartgrid/scripts')
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    scripts_dir = Path(args.scripts_dir)
    pybin = Path(args.py)

    log_path = out_dir / f'auto_finalize_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
    write_file(log_path, f"[START] {datetime.now()} auto_finalize started. out_dir={out_dir}, dataset_ids={args.dataset_ids}, interval={args.interval}\n")

    # 轮询检测缺失组
    while True:
        missing, text = detect_missing_groups(pybin, scripts_dir, out_dir, args.dataset_ids)
        with log_path.open('a', encoding='utf-8') as lf:
            lf.write(f"\n[HEARTBEAT] {datetime.now()} missing_groups={missing}\n")
            # 保留输出的前后若干行，避免日志过长
            preview = "\n".join(text.splitlines()[:50])
            lf.write(preview + "\n")

        if missing == 0:
            break
        time.sleep(args.interval)

    # 运行 summarize
    summ_out = out_dir / 'summary'
    with log_path.open('a', encoding='utf-8') as lf:
        lf.write(f"\n[INFO] {datetime.now()} running summarize_dedupe_outputs.py\n")
    run_cmd([str(pybin), str(scripts_dir / 'summarize_dedupe_outputs.py'), '--root', str(out_dir), '--out', str(summ_out)])

    # 运行 DB 检查（输出到 global/summary/db_check.txt）
    db_check_path = summ_out / 'db_check.txt'
    with log_path.open('a', encoding='utf-8') as lf:
        lf.write(f"[INFO] {datetime.now()} running check_db_semantic.py -> {db_check_path}\n")
    run_cmd([str(pybin), str(scripts_dir / 'check_db_semantic.py'), '--out', str(db_check_path)])

    # 运行 tech report 生成
    with log_path.open('a', encoding='utf-8') as lf:
        lf.write(f"[INFO] {datetime.now()} running generate_tech_report.py (global)\n")
    run_cmd([str(pybin), str(scripts_dir / 'generate_tech_report.py'), '--root', str(out_dir), '--title', 'EAV 语义去重运行报告（全局）', '--notes', f'自动收尾生成于 {datetime.now()}'])

    # 写完成标记
    final_flag = summ_out / 'FINALIZED_OK'
    write_file(final_flag, f"finished_at={datetime.now()}\n")

    with log_path.open('a', encoding='utf-8') as lf:
        lf.write(f"[DONE] {datetime.now()} finalized. summary written under {summ_out}\n")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        # 避免守护脚本静默失败
        sys.stderr.write(f"[FATAL] {e}\n")
        sys.exit(1)
