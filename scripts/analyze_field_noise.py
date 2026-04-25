"""sample_entities 字段噪音分析.

DA-02 数据架构表里大量"实体名"实际是 schema 字段名 (如 "项目编号 / 项目名称 / 项目状态"),
而非真正的语义实体. 这些噪音对后续语义分析有干扰.

本脚本只做统计 + 报告, 不修改数据. 输出:
 - 每个本地对象的 sample_entities 中, 字段噪音占比
 - 全局噪音模式 top-N (X编号 / X名称 / X状态...)
 - 建议: 噪音占比 > 60% 的对象, 考虑重抽取时启用过滤
"""

from __future__ import annotations

import glob
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = PROJECT_ROOT / "outputs"

# 字段噪音判别: 以这些后缀结尾的多半是 schema 字段
NOISE_SUFFIXES = (
    "编号", "代码", "代号", "ID", "id",
    "名称", "标题", "简称", "全称",
    "状态", "类型", "类别", "分类",
    "时间", "日期",
    "金额", "数量", "价格", "单价", "总价",
    "地址", "电话", "邮箱",
    "标识", "标志", "标记",
)
# 衍生类: "X 信息 / X 详情" 也可能是噪音, 但保留 (语义比较实)
SOFT_SUFFIXES = ("信息", "详情", "记录", "明细")

GLOBAL_PATTERN = re.compile(r"(.+?)(?:" + "|".join(NOISE_SUFFIXES) + ")$")


def is_field_noise(text: str) -> bool:
    if not text:
        return False
    for suf in NOISE_SUFFIXES:
        if text.endswith(suf) and len(text) > len(suf) + 1:
            return True
    return False


def main() -> None:
    suffix_count = Counter()
    domain_stats = []   # (domain, total_samples, noise_count, noise_ratio)

    for f in sorted(glob.glob(str(OUTPUTS / "extraction_*.json"))):
        if "global" in f or "join_sample" in f:
            continue
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        domain = d.get("data_domain") or Path(f).stem.replace("extraction_", "")
        total = 0
        noise = 0
        per_obj = []
        for o in d.get("objects", []):
            samples = o.get("sample_entities") or []
            t = len(samples)
            n = sum(1 for s in samples if is_field_noise(str(s)))
            total += t
            noise += n
            for s in samples:
                m = GLOBAL_PATTERN.match(str(s))
                if m:
                    # 拿后缀模式
                    for suf in NOISE_SUFFIXES:
                        if str(s).endswith(suf):
                            suffix_count[suf] += 1
                            break
            if t:
                per_obj.append({
                    "object_code": o.get("object_code"),
                    "object_name": o.get("object_name"),
                    "noise_ratio": round(n / t, 2),
                    "total": t,
                })
        ratio = round(noise / total, 4) if total else 0.0
        domain_stats.append((domain, total, noise, ratio, per_obj))

    print("=== 全局噪音后缀 Top 10 ===")
    for suf, c in suffix_count.most_common(10):
        print(f"  {suf:8s} 出现 {c:5d} 次")

    print("\n=== 22 域 sample_entities 噪音占比 ===")
    print(f"  {'domain':10s} {'total':>6s} {'noise':>6s} {'ratio':>8s}")
    for dom, total, noise, ratio, _ in sorted(domain_stats, key=lambda x: -x[3]):
        flag = " ⚠" if ratio > 0.6 else ""
        print(f"  {dom:10s} {total:>6d} {noise:>6d} {ratio*100:>7.1f}%{flag}")

    grand_total = sum(s[1] for s in domain_stats)
    grand_noise = sum(s[2] for s in domain_stats)
    print(f"\n  合计       {grand_total:>6d} {grand_noise:>6d} {grand_noise*100/max(1,grand_total):>7.1f}%")

    # 高噪音对象 Top 10
    flat = []
    for _, _, _, _, per_obj in domain_stats:
        flat.extend(per_obj)
    flat.sort(key=lambda r: (-r["noise_ratio"], -r["total"]))
    print("\n=== 高噪音对象 (前 10) ===")
    print(f"  {'object_code':22s} {'object_name':10s} {'noise_ratio':>11s} {'total':>5s}")
    for r in flat[:10]:
        print(f"  {(r['object_code'] or ''):22s} {(r['object_name'] or ''):10s} "
              f"{r['noise_ratio']*100:>10.0f}% {r['total']:>5d}")

    print("\n=== 建议 ===")
    print("- 噪音占比 > 60% 的域 / 对象, 重抽取时启用噪音过滤可显著改善聚类质量")
    print("- 实施: 修改 scripts/object_extractor.py 在收集 entities 阶段过滤掉")
    print("  以 编号/代码/名称/状态/类型/时间 等结尾的字段名 (即 NOISE_SUFFIXES)")
    print("- 替代方案: 走 DA-04 业务对象清单 (而不是 DA-01/02/03 字段清单) 作为抽取源")


if __name__ == "__main__":
    main()
