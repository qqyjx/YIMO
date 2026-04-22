"""
Unpack three architecture ZIP archives (BA/DA/AA) into DATA/{domain}/{1,2,3}.xlsx.

- 1.xlsx = 业务架构 (BA-*)
- 2.xlsx = 数据架构 (DA-*)
- 3.xlsx = 应用架构 (AA-*)

For every sheet in every file, if the rightmost header cell contains "校验"
(e.g. "校验结果"/"校验成功"/"20250327校验结果"), that column is deleted.

Pre-existing files under DATA/{domain}/ are backed up to DATA/_archive/backup_YYYYMMDD/
before being overwritten. Each xlsx is processed in an isolated subprocess so
that openpyxl's peak memory footprint does not accumulate across files (large
workbooks of 10+MB previously triggered the OOM killer when run in-process).
"""

from __future__ import annotations

import datetime as _dt
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

YIMO_ROOT = Path("/home/qq/YIMO")
DATA_DIR = YIMO_ROOT / "DATA"
ARCHIVE_DIR = DATA_DIR / "_archive"
WORKER = YIMO_ROOT / "scripts" / "_ingest_one.py"

ZIPS = {
    "1": ARCHIVE_DIR / "业务架构覆盖导入日志(1).zip",
    "2": ARCHIVE_DIR / "数据架构覆盖导入日志(1).zip",
    "3": ARCHIVE_DIR / "网公司应用架构-蓝图-导入日志20250520(1).zip",
}

# Order matters: more-specific keywords must come before more-generic ones
# (e.g. "企业架构" must precede "数字化" because filenames like
# "企业架构域...修改架构发布数字化情况..." would otherwise be misrouted).
DOMAIN_KEYWORDS = [
    ("纪检监察", "纪检监察"),
    ("国际业务", "国际业务"),
    ("产业金融", "产业金融"),
    ("供应链", "供应链"),
    ("安全监管", "安全监管"),
    ("审计", "审计"),
    ("法规", "法规"),
    ("党建", "党建"),
    ("办公", "办公"),
    ("巡视", "巡视"),
    ("工会", "工会"),
    ("系统运行", "系统运行"),
    ("人力资源", "人力资源"),
    ("计划与财务", "计划财务"),
    ("计财", "计划财务"),
    ("企业架构", "企业架构"),
    ("科技创新", "科技创新"),
    ("政策研究", "政策研究"),
    ("输配电", "输配电"),
    ("战略规划", "战略规划"),
    ("新兴业务", "新兴业务"),
    ("市场营销", "市场营销"),
    ("数字化", "数字化"),
]


def identify_domain(filename: str) -> str | None:
    for kw, domain in DOMAIN_KEYWORDS:
        if kw in filename:
            return domain
    return None


def process_file_subprocess(dest: Path) -> int:
    """Run _ingest_one.py in a child process; return number of columns dropped."""
    result = subprocess.run(
        [sys.executable, str(WORKER), str(dest)],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        print(f"    [ERR] worker rc={result.returncode} stderr={result.stderr.strip()[:200]}",
              flush=True)
        return -1
    for line in result.stdout.splitlines():
        if line.startswith("removed="):
            return int(line.split("=", 1)[1])
    return 0


def main() -> int:
    backup_root = ARCHIVE_DIR / f"backup_{_dt.date.today().strftime('%Y%m%d')}"
    backup_root.mkdir(parents=True, exist_ok=True)

    unmatched: list[str] = []
    per_domain: dict[str, dict[str, int]] = {}

    for idx, zip_path in ZIPS.items():
        if not zip_path.exists():
            print(f"[SKIP] not found: {zip_path}", flush=True)
            continue
        print(f"[ZIP] {zip_path.name} -> slot {idx}", flush=True)
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".xlsx"):
                    continue
                name = info.filename
                if not (info.flag_bits & 0x800):
                    try:
                        name = name.encode("cp437").decode("gbk")
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        pass
                domain = identify_domain(name)
                if domain is None:
                    unmatched.append(name)
                    continue

                dest_dir = DATA_DIR / domain
                dest_dir.mkdir(parents=True, exist_ok=True)

                # back up existing slot before overwriting
                src_existing = dest_dir / f"{idx}.xlsx"
                if src_existing.exists():
                    bdir = backup_root / domain
                    bdir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_existing, bdir / f"{idx}.xlsx")

                dest = dest_dir / f"{idx}.xlsx"
                with zf.open(info) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)

                n_removed = process_file_subprocess(dest)
                per_domain.setdefault(domain, {})[idx] = n_removed
                tag = (f"dropped {n_removed}" if n_removed > 0
                       else "no 校验 col" if n_removed == 0 else "ERR")
                print(f"  [{domain}] slot {idx}: {tag} (source={name[:60]}...)",
                      flush=True)

    print("\n=== SUMMARY ===", flush=True)
    expected = {d for _, d in DOMAIN_KEYWORDS}
    for domain in sorted(expected):
        slots = per_domain.get(domain, {})
        have = "".join(s if s in slots else "-" for s in ("1", "2", "3"))
        total_removed = sum(v for v in slots.values() if v > 0)
        print(f"  {domain}: slots={have} verification-cols-removed={total_removed}",
              flush=True)
    if unmatched:
        print("\n[WARN] unmatched files:", flush=True)
        for n in unmatched:
            print(f"  - {n}", flush=True)
    print(f"\nBackup of prior files at: {backup_root}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
