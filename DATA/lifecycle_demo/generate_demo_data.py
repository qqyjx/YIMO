#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成全生命周期样例数据 - 模拟电网资产从规划到运维的数据流

生成5个阶段的Excel文件：
1. planning/  - 可研阶段（规划设备清单）
2. design/    - 设计阶段（设计图纸设备表）
3. construction/ - 建设阶段（施工台账）
4. operation/ - 运维阶段（SCADA点表/巡检记录）
5. finance/   - 财务阶段（资产卡片）

每个阶段的数据会有：
- 相同资产的不同表达（用于测试融合）
- 部分字段的变化（用于测试一致性检测）
- 新增/缺失的资产（用于测试跨阶段追踪）
"""
import os
import random
from datetime import datetime, timedelta
import pandas as pd

# 设置随机种子保证可重复
random.seed(42)

# 基础资产数据 - 模拟一个220kV变电站的核心设备
BASE_ASSETS = [
    {
        "id": "TRF-001",
        "name": "220kV主变压器#1",
        "type": "主变压器",
        "voltage": "220kV",
        "capacity": "120MVA",
        "manufacturer": "特变电工",
        "model": "SFZ11-120000/220",
    },
    {
        "id": "TRF-002",
        "name": "220kV主变压器#2",
        "type": "主变压器",
        "voltage": "220kV",
        "capacity": "120MVA",
        "manufacturer": "特变电工",
        "model": "SFZ11-120000/220",
    },
    {
        "id": "CB-001",
        "name": "220kV断路器#1",
        "type": "断路器",
        "voltage": "220kV",
        "rated_current": "3150A",
        "manufacturer": "西门子",
        "model": "3AP1-FI",
    },
    {
        "id": "CB-002",
        "name": "220kV断路器#2",
        "type": "断路器",
        "voltage": "220kV",
        "rated_current": "3150A",
        "manufacturer": "ABB",
        "model": "LTB-245E1",
    },
    {
        "id": "PT-001",
        "name": "220kV电压互感器#1",
        "type": "电压互感器",
        "voltage": "220kV",
        "ratio": "220000/√3/100/√3",
        "manufacturer": "大连北方互感器",
        "accuracy": "0.2级",
    },
    {
        "id": "CT-001",
        "name": "220kV电流互感器#1",
        "type": "电流互感器",
        "voltage": "220kV",
        "ratio": "800/5A",
        "manufacturer": "大连北方互感器",
        "accuracy": "0.2S级",
    },
    {
        "id": "GIS-001",
        "name": "220kV GIS组合电器",
        "type": "GIS组合电器",
        "voltage": "220kV",
        "rated_current": "3150A",
        "manufacturer": "平高电气",
        "model": "ZF12-252",
    },
    {
        "id": "CAP-001",
        "name": "电容器组#1",
        "type": "电容器",
        "voltage": "35kV",
        "capacity": "30Mvar",
        "manufacturer": "荣信电力",
        "model": "BAM11/√3-300-1W",
    },
    {
        "id": "RECT-001",
        "name": "整流变压器",
        "type": "整流变压器",
        "voltage": "35kV/0.4kV",
        "capacity": "5000kVA",
        "manufacturer": "特变电工",
        "model": "ZSFP-5000/35",
    },
    {
        "id": "PROT-001",
        "name": "主变保护装置",
        "type": "保护装置",
        "protection_type": "差动保护",
        "manufacturer": "南瑞继保",
        "model": "RCS-9671CS",
    },
]

def generate_planning_data():
    """规划阶段 - 可研设备清单"""
    records = []
    base_date = datetime(2023, 3, 15)
    
    for asset in BASE_ASSETS:
        record = {
            "序号": len(records) + 1,
            "设备编号": f"KY-{asset['id']}",  # 可研阶段的编号前缀
            "设备名称": asset["name"],
            "设备类型": asset["type"],
            "电压等级": asset.get("voltage", ""),
            "额定容量/电流": asset.get("capacity", asset.get("rated_current", "")),
            "拟选厂家": asset.get("manufacturer", ""),
            "预估单价(万元)": random.randint(50, 500),
            "数量": 1,
            "技术参数要求": f"型号: {asset.get('model', '待定')}",
            "可研批复日期": base_date.strftime("%Y-%m-%d"),
            "项目阶段": "可行性研究",
            "备注": "初步规划",
        }
        records.append(record)
    
    # 添加一些规划阶段特有的、后来被取消的设备
    records.append({
        "序号": len(records) + 1,
        "设备编号": "KY-CANCEL-001",
        "设备名称": "35kV电抗器（后取消）",
        "设备类型": "电抗器",
        "电压等级": "35kV",
        "额定容量/电流": "10Mvar",
        "拟选厂家": "特变电工",
        "预估单价(万元)": 80,
        "数量": 1,
        "技术参数要求": "",
        "可研批复日期": base_date.strftime("%Y-%m-%d"),
        "项目阶段": "可行性研究",
        "备注": "经论证后取消",
    })
    
    df = pd.DataFrame(records)
    return df


def generate_design_data():
    """设计阶段 - 设计图纸设备表"""
    records = []
    base_date = datetime(2023, 8, 20)
    
    for asset in BASE_ASSETS:
        # 设计阶段有些字段会更详细，有些名称略有变化
        name_variations = {
            "220kV主变压器#1": "1#主变压器(220kV侧)",
            "220kV主变压器#2": "2#主变压器(220kV侧)",
            "220kV断路器#1": "220kV 1号线路断路器",
            "220kV断路器#2": "220kV 2号线路断路器",
        }
        
        record = {
            "图纸编号": f"DWG-{random.randint(1000,9999)}",
            "设备标识": f"SJ-{asset['id']}",  # 设计阶段的编号
            "设备名称": name_variations.get(asset["name"], asset["name"]),
            "设备分类": asset["type"],
            "额定电压": asset.get("voltage", ""),
            "技术规格": f"{asset.get('capacity', asset.get('rated_current', ''))} {asset.get('model', '')}",
            "生产厂商": asset.get("manufacturer", ""),
            "安装位置": f"主控楼-{random.choice(['A', 'B', 'C'])}区",
            "设计深度": random.choice(["初设", "施工图"]),
            "设计日期": base_date.strftime("%Y-%m-%d"),
            "设计人": random.choice(["张工", "李工", "王工"]),
            "校核人": random.choice(["陈总工", "刘总工"]),
        }
        records.append(record)
    
    # 设计阶段新增设备
    records.append({
        "图纸编号": f"DWG-{random.randint(1000,9999)}",
        "设备标识": "SJ-AUX-001",
        "设备名称": "站用变压器",
        "设备分类": "站用变",
        "额定电压": "35kV/0.4kV",
        "技术规格": "500kVA S11-500/35",
        "生产厂商": "江苏华鹏",
        "安装位置": "站用电室",
        "设计深度": "施工图",
        "设计日期": base_date.strftime("%Y-%m-%d"),
        "设计人": "张工",
        "校核人": "陈总工",
    })
    
    df = pd.DataFrame(records)
    return df


def generate_construction_data():
    """建设阶段 - 施工台账"""
    records = []
    base_date = datetime(2024, 2, 10)
    
    for i, asset in enumerate(BASE_ASSETS):
        arrival_date = base_date + timedelta(days=random.randint(0, 30))
        install_date = arrival_date + timedelta(days=random.randint(5, 20))
        
        record = {
            "台账编号": f"SG-2024-{str(i+1).zfill(4)}",
            "物资编码": f"WZ-{asset['id']}",
            "物资名称": asset["name"].replace("220kV", "").strip(),  # 施工方可能简化名称
            "规格型号": asset.get("model", ""),
            "制造商": asset.get("manufacturer", ""),
            "出厂编号": f"FAC-{random.randint(100000, 999999)}",
            "到货日期": arrival_date.strftime("%Y-%m-%d"),
            "安装日期": install_date.strftime("%Y-%m-%d"),
            "安装位置": f"间隔{random.randint(1,10)}",
            "施工单位": random.choice(["中电建", "国网工程", "特变电工安装"]),
            "质检结果": random.choice(["合格", "合格", "合格", "整改后合格"]),
            "验收状态": "已验收" if random.random() > 0.1 else "待验收",
        }
        records.append(record)
    
    # 施工阶段的站用变（设计阶段新增的）
    records.append({
        "台账编号": f"SG-2024-{str(len(records)+1).zfill(4)}",
        "物资编码": "WZ-AUX-001",
        "物资名称": "站用变压器",
        "规格型号": "S11-500/35",
        "制造商": "江苏华鹏",
        "出厂编号": f"FAC-{random.randint(100000, 999999)}",
        "到货日期": (base_date + timedelta(days=15)).strftime("%Y-%m-%d"),
        "安装日期": (base_date + timedelta(days=25)).strftime("%Y-%m-%d"),
        "安装位置": "站用电室",
        "施工单位": "国网工程",
        "质检结果": "合格",
        "验收状态": "已验收",
    })
    
    df = pd.DataFrame(records)
    return df


def generate_operation_data():
    """运维阶段 - SCADA点表 + 巡检记录"""
    # SCADA点表
    scada_records = []
    for asset in BASE_ASSETS[:7]:  # 主要设备有SCADA点
        points = []
        if "变压器" in asset["type"]:
            points = ["油温", "绕组温度", "油位", "有载开关档位", "有功功率", "无功功率"]
        elif "断路器" in asset["type"]:
            points = ["位置", "SF6压力", "弹簧储能", "动作次数"]
        elif "GIS" in asset["type"]:
            points = ["SF6压力", "局放监测", "温度"]
        else:
            points = ["运行状态", "温度"]
        
        for pt in points:
            scada_records.append({
                "点号": f"SCADA-{asset['id']}-{pt[:2]}",
                "设备KKS码": f"OP-{asset['id']}",
                "设备描述": asset["name"],
                "测点名称": pt,
                "测点类型": "模拟量" if pt not in ["位置", "运行状态", "弹簧储能"] else "状态量",
                "单位": {"油温": "℃", "绕组温度": "℃", "油位": "mm", "SF6压力": "MPa", 
                         "有功功率": "MW", "无功功率": "Mvar", "动作次数": "次"}.get(pt, ""),
                "当前值": round(random.uniform(20, 80), 2) if pt not in ["位置", "运行状态"] else random.choice(["合", "分", "正常"]),
                "采集时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
    
    scada_df = pd.DataFrame(scada_records)
    
    # 巡检记录
    inspection_records = []
    base_date = datetime(2024, 12, 1)
    
    for asset in BASE_ASSETS:
        for day_offset in [0, 7, 14, 21]:  # 每周巡检
            record = {
                "巡检单号": f"XJ-{(base_date + timedelta(days=day_offset)).strftime('%Y%m%d')}-{random.randint(100,999)}",
                "资产编号": f"OP-{asset['id']}",
                "资产名称": asset["name"],
                "巡检日期": (base_date + timedelta(days=day_offset)).strftime("%Y-%m-%d"),
                "巡检人员": random.choice(["张三", "李四", "王五", "赵六"]),
                "运行状态": random.choice(["正常", "正常", "正常", "正常", "异常"]),
                "外观检查": random.choice(["良好", "良好", "良好", "轻微锈蚀"]),
                "声音检查": random.choice(["正常", "正常", "正常", "轻微异响"]),
                "温度检测": f"{random.randint(25, 45)}℃",
                "缺陷描述": "" if random.random() > 0.1 else random.choice(["端子松动", "油位偏低", "表计模糊"]),
                "处理意见": "",
            }
            inspection_records.append(record)
    
    inspection_df = pd.DataFrame(inspection_records)
    
    return scada_df, inspection_df


def generate_finance_data():
    """财务阶段 - 资产卡片"""
    records = []
    base_date = datetime(2024, 6, 30)  # 转资日期
    
    for i, asset in enumerate(BASE_ASSETS):
        # 财务卡片的名称更规范
        record = {
            "资产卡片号": f"ZC-2024-{str(i+1).zfill(6)}",
            "资产编码": f"FIN-{asset['id']}",
            "资产名称": asset["name"],
            "资产分类": asset["type"],
            "规格型号": asset.get("model", ""),
            "计量单位": "台",
            "数量": 1,
            "原值(元)": random.randint(500000, 5000000),
            "累计折旧(元)": random.randint(10000, 100000),
            "净值(元)": 0,  # 将在下面计算
            "使用部门": "变电运检中心",
            "存放地点": "220kV某某变电站",
            "购置日期": datetime(2024, 1, 15).strftime("%Y-%m-%d"),
            "转资日期": base_date.strftime("%Y-%m-%d"),
            "预计使用年限": random.choice([15, 20, 25]),
            "资产状态": random.choice(["在用", "在用", "在用", "闲置"]),
            "责任人": random.choice(["站长A", "站长B"]),
        }
        record["净值(元)"] = record["原值(元)"] - record["累计折旧(元)"]
        records.append(record)
    
    # 站用变
    records.append({
        "资产卡片号": f"ZC-2024-{str(len(records)+1).zfill(6)}",
        "资产编码": "FIN-AUX-001",
        "资产名称": "站用变压器",
        "资产分类": "站用变",
        "规格型号": "S11-500/35",
        "计量单位": "台",
        "数量": 1,
        "原值(元)": 150000,
        "累计折旧(元)": 5000,
        "净值(元)": 145000,
        "使用部门": "变电运检中心",
        "存放地点": "220kV某某变电站",
        "购置日期": datetime(2024, 1, 15).strftime("%Y-%m-%d"),
        "转资日期": base_date.strftime("%Y-%m-%d"),
        "预计使用年限": 20,
        "资产状态": "在用",
        "责任人": "站长A",
    })
    
    df = pd.DataFrame(records)
    return df


def main():
    """生成所有阶段的样例数据"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    print("=" * 60)
    print("生成全生命周期样例数据")
    print("=" * 60)
    
    # 1. 规划阶段
    print("\n[1/5] 生成规划阶段数据...")
    planning_df = generate_planning_data()
    planning_path = os.path.join(base_dir, "planning", "可研设备清单.xlsx")
    planning_df.to_excel(planning_path, index=False, sheet_name="设备清单")
    print(f"  → {planning_path} ({len(planning_df)} 条记录)")
    
    # 2. 设计阶段
    print("\n[2/5] 生成设计阶段数据...")
    design_df = generate_design_data()
    design_path = os.path.join(base_dir, "design", "设计图纸设备表.xlsx")
    design_df.to_excel(design_path, index=False, sheet_name="设备表")
    print(f"  → {design_path} ({len(design_df)} 条记录)")
    
    # 3. 建设阶段
    print("\n[3/5] 生成建设阶段数据...")
    construction_df = generate_construction_data()
    construction_path = os.path.join(base_dir, "construction", "施工台账.xlsx")
    construction_df.to_excel(construction_path, index=False, sheet_name="台账")
    print(f"  → {construction_path} ({len(construction_df)} 条记录)")
    
    # 4. 运维阶段
    print("\n[4/5] 生成运维阶段数据...")
    scada_df, inspection_df = generate_operation_data()
    
    scada_path = os.path.join(base_dir, "operation", "SCADA点表.xlsx")
    scada_df.to_excel(scada_path, index=False, sheet_name="点表")
    print(f"  → {scada_path} ({len(scada_df)} 条记录)")
    
    inspection_path = os.path.join(base_dir, "operation", "巡检记录.xlsx")
    inspection_df.to_excel(inspection_path, index=False, sheet_name="巡检")
    print(f"  → {inspection_path} ({len(inspection_df)} 条记录)")
    
    # 5. 财务阶段
    print("\n[5/5] 生成财务阶段数据...")
    finance_df = generate_finance_data()
    finance_path = os.path.join(base_dir, "finance", "资产卡片.xlsx")
    finance_df.to_excel(finance_path, index=False, sheet_name="资产卡")
    print(f"  → {finance_path} ({len(finance_df)} 条记录)")
    
    print("\n" + "=" * 60)
    print("样例数据生成完成！")
    print("=" * 60)
    print("\n数据特点说明：")
    print("  • 同一资产在不同阶段的编号/名称略有差异（模拟真实情况）")
    print("  • 规划阶段有一个后来被取消的设备（35kV电抗器）")
    print("  • 设计阶段新增了站用变压器（规划阶段没有）")
    print("  • 建设/运维/财务阶段都有站用变压器的记录")
    print("\n导入命令示例：")
    print("  python scripts/import_all.py --stage planning DATA/lifecycle_demo/planning/")
    print("  python scripts/import_all.py --stage design DATA/lifecycle_demo/design/")
    print("  python scripts/import_all.py --stage construction DATA/lifecycle_demo/construction/")
    print("  python scripts/import_all.py --stage operation DATA/lifecycle_demo/operation/")
    print("  python scripts/import_all.py --stage finance DATA/lifecycle_demo/finance/")


if __name__ == "__main__":
    main()
