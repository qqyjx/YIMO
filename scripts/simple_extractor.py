#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版对象抽取器 - 基于关键词规则
不依赖 SBERT，适合快速演示
"""

import os
import json
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

# ============================================================
# 数据类定义
# ============================================================

@dataclass
class ExtractedObject:
    """抽取的对象"""
    object_code: str
    object_name: str
    object_name_en: str = ""
    object_type: str = "CORE"
    description: str = ""
    extraction_source: str = "KEYWORD_RULE"
    extraction_confidence: float = 0.7
    synonyms: List[str] = field(default_factory=list)
    sample_entities: List[str] = field(default_factory=list)
    stats: Dict = field(default_factory=dict)


@dataclass
class EntityInfo:
    """实体信息"""
    name: str
    layer: str  # CONCEPT, LOGICAL, PHYSICAL
    code: str = ""
    data_domain: str = ""
    source_file: str = ""


@dataclass
class EntityRelation:
    """对象与实体的关联"""
    object_code: str
    entity_layer: str
    entity_name: str
    entity_code: str = ""
    relation_strength: float = 0.8
    data_domain: str = ""


# ============================================================
# 关键词到对象的映射规则
# ============================================================

KEYWORD_OBJECT_MAP = {
    # 项目相关
    "项目": ("OBJ_PROJECT", "项目", "Project", "CORE", "电网建设项目", ["工程", "建设项目"]),
    "工程": ("OBJ_PROJECT", "项目", "Project", "CORE", "电网建设项目", ["项目", "建设工程"]),
    # 设备相关
    "设备": ("OBJ_DEVICE", "设备", "Device", "CORE", "电网设备资产", ["装置", "器材"]),
    "变压器": ("OBJ_DEVICE", "设备", "Device", "CORE", "电网设备资产", ["变电设备"]),
    "断路器": ("OBJ_DEVICE", "设备", "Device", "CORE", "电网设备资产", ["开关设备"]),
    "线路": ("OBJ_LINE", "线路", "Line", "CORE", "输配电线路", ["电缆", "导线"]),
    # 资产相关
    "资产": ("OBJ_ASSET", "资产", "Asset", "CORE", "固定资产", ["固定资产", "设施"]),
    # 合同相关
    "合同": ("OBJ_CONTRACT", "合同", "Contract", "CORE", "业务合同", ["协议", "契约"]),
    # 人员相关
    "人员": ("OBJ_PERSONNEL", "人员", "Personnel", "CORE", "相关人员", ["员工", "工作人员"]),
    "员工": ("OBJ_PERSONNEL", "人员", "Personnel", "CORE", "相关人员", ["人员", "工作人员"]),
    # 组织相关
    "组织": ("OBJ_ORGANIZATION", "组织", "Organization", "CORE", "组织机构", ["部门", "单位"]),
    "部门": ("OBJ_ORGANIZATION", "组织", "Organization", "CORE", "组织机构", ["单位", "组织"]),
    # 文档相关
    "文档": ("OBJ_DOCUMENT", "文档", "Document", "AUXILIARY", "业务文档", ["报告", "文件"]),
    "报告": ("OBJ_DOCUMENT", "文档", "Document", "AUXILIARY", "业务文档", ["文档", "记录"]),
    # 任务相关
    "任务": ("OBJ_TASK", "任务", "Task", "DERIVED", "工作任务", ["工单", "作业"]),
    "工单": ("OBJ_TASK", "任务", "Task", "DERIVED", "工作任务", ["任务", "作业"]),
    # 物资相关
    "物资": ("OBJ_MATERIAL", "物资", "Material", "CORE", "工程物资", ["材料", "备品"]),
    "材料": ("OBJ_MATERIAL", "物资", "Material", "CORE", "工程物资", ["物资", "备件"]),
    # 费用相关
    "费用": ("OBJ_COST", "费用", "Cost", "DERIVED", "费用成本", ["成本", "预算"]),
    "预算": ("OBJ_COST", "费用", "Cost", "DERIVED", "费用成本", ["费用", "成本"]),
    # 流程相关
    "流程": ("OBJ_PROCESS", "流程", "Process", "AUXILIARY", "业务流程", ["审批", "程序"]),
    "审批": ("OBJ_PROCESS", "流程", "Process", "AUXILIARY", "业务流程", ["流程", "审核"]),
    # 指标相关
    "指标": ("OBJ_METRIC", "指标", "Metric", "AUXILIARY", "业务指标", ["统计", "数据"]),
    # 计划相关
    "计划": ("OBJ_PLAN", "计划", "Plan", "DERIVED", "业务计划", ["规划", "方案"]),
    # 故障相关
    "故障": ("OBJ_FAULT", "故障", "Fault", "DERIVED", "故障事件", ["缺陷", "异常"]),
    "缺陷": ("OBJ_FAULT", "故障", "Fault", "DERIVED", "故障事件", ["故障", "问题"]),
    # 检修相关
    "检修": ("OBJ_MAINTENANCE", "检修", "Maintenance", "DERIVED", "检修维护", ["维护", "保养"]),
    "维护": ("OBJ_MAINTENANCE", "检修", "Maintenance", "DERIVED", "检修维护", ["检修", "保养"]),
    # 运行相关
    "运行": ("OBJ_OPERATION", "运行", "Operation", "DERIVED", "设备运行", ["运维", "监控"]),
}


# ============================================================
# 数据读取
# ============================================================

def read_entities(data_dir: str, data_domain: str = "default") -> List[EntityInfo]:
    """读取三层架构实体数据"""
    entities = []
    data_path = Path(data_dir)

    if not data_path.exists():
        print(f"[WARN] 数据目录不存在: {data_path}")
        return entities

    # 查找所有 xlsx 文件
    xlsx_files = list(data_path.glob("*.xlsx"))
    if not xlsx_files:
        print(f"[WARN] 未找到 xlsx 文件: {data_path}")
        return entities

    sheet_configs = [
        ("DA-01 数据实体清单-概念实体清单", "概念实体", "CONCEPT"),
        ("DA-02 数据实体清单-逻辑实体清单", "逻辑实体名称", "LOGICAL"),
        ("DA-03数据实体清单-物理实体清单", "物理实体名称", "PHYSICAL"),
    ]

    for xlsx_file in xlsx_files:
        print(f"  读取 {xlsx_file.name}...")
        for sheet_name, name_col, layer in sheet_configs:
            try:
                df = pd.read_excel(xlsx_file, sheet_name=sheet_name)
                seen = set()
                for idx, row in df.iterrows():
                    name = str(row.get(name_col, "")).strip()
                    if name and name != "nan" and name not in seen:
                        seen.add(name)
                        entities.append(EntityInfo(
                            name=name,
                            layer=layer,
                            code=str(row.get(f"{layer.lower()}实体编码", "")).strip(),
                            data_domain=data_domain,
                            source_file=xlsx_file.name
                        ))
            except Exception as e:
                # 忽略工作表不存在的错误
                if "not found" not in str(e).lower():
                    print(f"    [WARN] 读取 {sheet_name} 失败: {e}")

    return entities


# ============================================================
# 基于关键词的对象抽取
# ============================================================

def extract_objects(entities: List[EntityInfo]) -> tuple:
    """基于关键词规则抽取对象"""
    print(f"[INFO] 开始基于关键词的对象抽取...")
    print(f"  实体总数: {len(entities)}")

    # 统计每个关键词的出现次数
    keyword_entities: Dict[str, List[EntityInfo]] = defaultdict(list)

    for entity in entities:
        for keyword in KEYWORD_OBJECT_MAP:
            if keyword in entity.name:
                keyword_entities[keyword].append(entity)

    # 按对象代码聚合
    object_entities: Dict[str, List[EntityInfo]] = defaultdict(list)
    object_info: Dict[str, tuple] = {}

    for keyword, ents in keyword_entities.items():
        obj_code = KEYWORD_OBJECT_MAP[keyword][0]
        object_entities[obj_code].extend(ents)
        if obj_code not in object_info:
            object_info[obj_code] = KEYWORD_OBJECT_MAP[keyword]

    # 创建对象列表
    objects = []
    relations = []

    for obj_code, ents in object_entities.items():
        if not ents:
            continue

        info = object_info[obj_code]
        _, name, name_en, obj_type, desc, synonyms = info

        # 去重实体
        unique_entities = list({e.name: e for e in ents}.values())

        # 按层级统计
        concept_ents = [e for e in unique_entities if e.layer == "CONCEPT"]
        logical_ents = [e for e in unique_entities if e.layer == "LOGICAL"]
        physical_ents = [e for e in unique_entities if e.layer == "PHYSICAL"]

        # 只保留有关联实体的对象
        if len(unique_entities) == 0:
            continue

        obj = ExtractedObject(
            object_code=obj_code,
            object_name=name,
            object_name_en=name_en,
            object_type=obj_type,
            description=desc,
            synonyms=synonyms,
            sample_entities=[e.name for e in unique_entities[:20]],
            stats={
                "concept": len(concept_ents),
                "logical": len(logical_ents),
                "physical": len(physical_ents),
                "total": len(unique_entities)
            }
        )
        objects.append(obj)

        # 创建关联关系
        for entity in unique_entities:
            relations.append(EntityRelation(
                object_code=obj_code,
                entity_layer=entity.layer,
                entity_name=entity.name,
                entity_code=entity.code,
                relation_strength=0.8,
                data_domain=entity.data_domain
            ))

    # 按实体数量排序
    objects.sort(key=lambda x: x.stats.get("total", 0), reverse=True)

    print(f"[INFO] 抽取完成: {len(objects)} 个对象, {len(relations)} 条关联")

    return objects, relations


# ============================================================
# 主函数
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="简化版对象抽取器")
    parser.add_argument("--data-dir", default="DATA/shupeidian", help="数据目录")
    parser.add_argument("--data-domain", default="shupeidian", help="数据域")
    parser.add_argument("--output", "-o", default="outputs/extraction_result.json", help="输出文件")
    args = parser.parse_args()

    print("=" * 60)
    print("简化版对象抽取器 (基于关键词规则)")
    print("=" * 60)
    print(f"数据目录: {args.data_dir}")
    print(f"数据域: {args.data_domain}")
    print()

    # 1. 读取实体
    entities = read_entities(args.data_dir, args.data_domain)

    if not entities:
        print("[ERROR] 没有读取到实体数据")
        return

    # 统计
    concept_count = len([e for e in entities if e.layer == "CONCEPT"])
    logical_count = len([e for e in entities if e.layer == "LOGICAL"])
    physical_count = len([e for e in entities if e.layer == "PHYSICAL"])

    print(f"[INFO] 实体读取完成:")
    print(f"  概念实体: {concept_count}")
    print(f"  逻辑实体: {logical_count}")
    print(f"  物理实体: {physical_count}")
    print()

    # 2. 抽取对象
    objects, relations = extract_objects(entities)

    # 3. 打印结果
    print("\n[INFO] 抽取的对象:")
    for obj in objects:
        print(f"  {obj.object_code}: {obj.object_name}")
        print(f"    概念:{obj.stats['concept']} 逻辑:{obj.stats['logical']} 物理:{obj.stats['physical']}")

    # 4. 构建输出结构
    result = {
        "data_domain": args.data_domain,
        "data_domain_name": {"shupeidian": "输配电", "jicai": "集采"}.get(args.data_domain, args.data_domain),
        "extraction_time": datetime.now().isoformat(),
        "entity_stats": {
            "concept": concept_count,
            "logical": logical_count,
            "physical": physical_count,
            "total": len(entities)
        },
        "objects": [asdict(obj) for obj in objects],
        "relations": [asdict(rel) for rel in relations],
        "relations_count": len(relations)
    }

    # 5. 保存结果
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n[INFO] 结果已保存到: {output_path}")


if __name__ == "__main__":
    main()
