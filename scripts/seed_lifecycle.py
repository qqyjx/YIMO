#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一生命周期数据种子脚本

为全部 16 个对象生成标准化的 4 阶段生命周期记录：
    Planning → Design → Construction → Operation

每个对象生成 4 条记录，时间间隔约 30-90 天，attributes_snapshot
体现该对象在该阶段应有的核心字段。

用法:
    python scripts/seed_lifecycle.py
"""
import json
import os
import sys
from datetime import datetime, timedelta

import pymysql

DB_CONFIG = {
    'host': os.environ.get('MYSQL_HOST', '127.0.0.1'),
    'port': int(os.environ.get('MYSQL_PORT', 3307)),
    'user': os.environ.get('MYSQL_USER', 'eav_user'),
    'password': os.environ.get('MYSQL_PASSWORD', 'eavpass123'),
    'database': os.environ.get('MYSQL_DB', 'eav_db'),
    'charset': 'utf8mb4',
}

# 4 阶段统一定义
STAGES = ['Planning', 'Design', 'Construction', 'Operation']

# 16 个对象的统一生命周期模板
LIFECYCLE_TEMPLATE = {
    'OBJ_PROJECT': {
        'domain': 'shupeidian', 'source': 'PMS',
        'Planning':     {'立项编号': 'PRJ-2024-001', '可研预算': 12000000, '负责人': '张工', '建设规模': '2×180MVA主变'},
        'Design':       {'设计单位': '南方电网设计院', '图纸数量': 342, '审查轮次': 3, '设计变更': 5},
        'Construction': {'施工单位': '南方电网工程公司', '施工进度': '100%', '质量合格率': '98.5%', '里程碑': '8/8'},
        'Operation':    {'投运日期': '2024-12-01', '运行状态': '正常', '负荷率': '65.3%', '巡检次数': 48},
    },
    'OBJ_DEVICE': {
        'domain': 'shupeidian', 'source': 'EAM',
        'Planning':     {'设备类型': '180MVA主变压器', '技术规格': '220/110/10kV', '采购预算': 3200000, '需求数量': 2},
        'Design':       {'制造厂家': '特变电工', '出厂编号': 'TBE-2024-0156', '型式试验': '合格', '监造次数': 4},
        'Construction': {'安装位置': '渝中变电站', '调试状态': '完成', '保护定值': '已整定', '耐压试验': '合格'},
        'Operation':    {'运行状态': '正常', '累计运行小时': 4380, '油色谱': '正常', '局放监测': '< 5pC'},
    },
    'OBJ_CONTRACT': {
        'domain': 'shupeidian', 'source': 'SAP-MM',
        'Planning':     {'合同类型': '工程施工合同', '招标方式': '公开招标', '预算控制价': 85000000, '标段数': 3},
        'Design':       {'条款版本': 'v1.3', '法务审核': '通过', '评审状态': '已评审', '审批日期': '2023-11-30'},
        'Construction': {'签订日期': '2023-12-01', '合同金额': 78600000, '甲方代表': '张总', '生效日期': '2023-12-15'},
        'Operation':    {'履约状态': '执行中', '已付金额': 62880000, '付款比例': '80%', '变更金额': 3200000},
    },
    'OBJ_ASSET': {
        'domain': 'jicai', 'source': 'SAP-AM',
        'Planning':     {'资产类别': '输变电设备', '计划采购数量': 156, '预算总额': 45000000, '需求部门': '设备管理部'},
        'Design':       {'采购方式': '公开招标', '供应商评估': '完成', '技术规格': 'GB/T 1094', '审批状态': '已批准'},
        'Construction': {'已到货数量': 142, '验收合格数': 138, '安装进度': '88.5%', '质量合格率': '97.2%'},
        'Operation':    {'在运资产数': 138, '资产完好率': '99.1%', '累计折旧': 6750000, '故障率': '0.7%'},
    },
    'OBJ_PERSONNEL': {
        'domain': 'jicai', 'source': 'HR-System',
        'Planning':     {'编制人数': 320, '岗位规划': '已完成', '招聘计划': 20, '培训预算': 850000},
        'Design':       {'岗位说明书': '已制定', '能力模型': 'v2024', '考核方案': '已审批', '招聘渠道': '5个'},
        'Construction': {'招聘到岗': 18, '培训完成': '100%', '考核通过率': '94%', '上岗确认': '已完成'},
        'Operation':    {'在岗人数': 318, '持证上岗率': '96.2%', '培训完成率': '88.7%', '人均工时': 1920},
    },
    'OBJ_COST': {
        'domain': 'jicai', 'source': 'SAP-FI',
        'Planning':     {'预算类别': '运维费用', '年度预算': 28000000, '费用科目数': 45, '审批状态': '编制中'},
        'Design':       {'科目分配': '已分配', '归口部门': '财务部', '预算下达': '完成', '管控规则': '已配置'},
        'Construction': {'已执行预算': 19560000, '执行率': '69.9%', '超支科目': 3, '节余科目': 12},
        'Operation':    {'年度决算': 26500000, '决算偏差': '5.4%', '审计状态': '已审计', '归集完整率': '94.2%'},
    },
    'OBJ_VOUCHER': {
        'domain': 'jicai', 'source': 'SAP-FI',
        'Planning':     {'票据类型': '增值税专用发票', '管理制度版本': 'v2024', '电子化覆盖率': '75%', '合规规则数': 28},
        'Design':       {'分类规则': '已配置', '验真接口': '已对接', '工作流': '4级审批', '归档策略': '已确定'},
        'Construction': {'本年收票数': 8560, '验真通过率': '99.7%', '退票数': 26, '电子票据比例': '82.3%'},
        'Operation':    {'已核销金额': 182000000, '待核销金额': 3000000, '归档完成率': '97.5%', '审计异常': 8},
    },
    'OBJ_METRIC': {
        'domain': 'jicai', 'source': 'KPI-System',
        'Planning':     {'指标体系版本': 'v2024.1', 'KPI数量': 28, '考核维度': 4, '审批状态': '已批准'},
        'Design':       {'目标值设定': '已完成', '权重分配': '已确定', '采集方式': '系统对接', '考核周期': '月度'},
        'Construction': {'数据采集': '运行', '数据质量': '高', '看板上线': '已完成', '试运行': '通过'},
        'Operation':    {'达标指标': 22, '预警指标': 4, '未达标': 2, '综合达标率': '78.6%'},
    },
    'OBJ_TASK': {
        'domain': 'shupeidian', 'source': 'PMS',
        'Planning':     {'任务类型': '年度检修计划', '计划任务数': 560, '涉及设备': 1230, '预算额': 18000000},
        'Design':       {'方案评审': '通过', '资源调配': '完成', '风险评估': '已审核', '安排发布': '已下达'},
        'Construction': {'人员到位': '4500人·天', '材料就绪': '100%', '工器具齐备': '100%', '安全交底': '完成'},
        'Operation':    {'已完成': 485, '完成率': '86.6%', '超期任务': 12, '安全事故': 0},
    },
    'OBJ_AUDIT': {
        'domain': 'shupeidian', 'source': 'QMS',
        'Planning':     {'监督类型': '工程质量监督', '年度计划': 120, '重点领域': '安全/质量/进度/投资', '人员': 15},
        'Design':       {'监督方案': '已批准', '检查清单': '已制定', '评分标准': '4级', '工具准备': '完成'},
        'Construction': {'已检查项目': 95, '发现问题': 23, '整改完成': 21, '通报次数': 4},
        'Operation':    {'年度完成率': '79.2%', '严重问题': 0, '一般问题': 23, '整改率': '91.3%'},
    },
    'OBJ_SYSTEM': {
        'domain': 'shupeidian', 'source': 'IT',
        'Planning':     {'系统名称': 'PMS3.0', '建设目标': '生产管理一体化', '预算': 8500000, '建设周期': '18个月'},
        'Design':       {'架构设计': '微服务', '技术栈': 'Java+Vue', '接口数': 127, '设计评审': '通过'},
        'Construction': {'开发进度': '100%', '测试用例': 1850, '缺陷修复率': '99.8%', '上线就绪': '是'},
        'Operation':    {'上线日期': '2024-09-01', '在线用户': 3200, '可用性': '99.95%', '工单数': 156},
    },
    'OBJ_STANDARD': {
        'domain': 'shupeidian', 'source': 'QMS',
        'Planning':     {'标准类型': '企业标准', '编制依据': 'GB/T+行标', '主管部门': '技术管理部', '编制单位': '技术中心'},
        'Design':       {'草案版本': 'v0.8', '征求意见稿': '已发布', '反馈数': 47, '修订次数': 3},
        'Construction': {'报批稿': 'v1.0', '审批通过': '是', '发布编号': 'Q/CSG-001-2024', '实施日期': '2024-07-01'},
        'Operation':    {'宣贯次数': 12, '执行情况': '良好', '修订计划': '2026年', '引用次数': 89},
    },
    'OBJ_DOCUMENT': {
        'domain': 'shupeidian', 'source': 'OA',
        'Planning':     {'文档类型': '技术规范', '编制单位': '设计院', '提纲版本': 'v1.0', '页数估计': 80},
        'Design':       {'初稿版本': 'v0.5', '内容审核': '完成', '专家评审': '通过', '修订建议': 18},
        'Construction': {'终稿版本': 'v1.0', '正式发布': '是', '发布渠道': 'OA+纸质', '存档份数': 50},
        'Operation':    {'下载次数': 234, '查阅次数': 1820, '应用反馈': '良好', '修订状态': '稳定'},
    },
    'OBJ_TEAM': {
        'domain': 'shupeidian', 'source': 'HR-System',
        'Planning':     {'班站名称': '渝中变电运维班', '编制人数': 18, '管辖范围': '5座变电站', '负责人': '李工'},
        'Design':       {'岗位设置': '完成', '工作流程': '已制定', '应急预案': '已审批', '培训计划': '已下达'},
        'Construction': {'人员配齐': 18, '设备到位': '100%', '资质审核': '通过', '挂牌成立': '2024-04-01'},
        'Operation':    {'在岗人数': 17, '巡检次数': 156, '检修次数': 24, '安全运行天数': 288},
    },
    'OBJ_PLAN': {
        'domain': 'shupeidian', 'source': 'PMS',
        'Planning':     {'计划类型': '年度生产计划', '编制周期': 'Q4', '涉及部门': 8, '审批状态': '编制中'},
        'Design':       {'计划版本': 'v1.0', '部门会签': '完成', '资源平衡': '已审核', '审批通过': '是'},
        'Construction': {'下达日期': '2024-01-05', '执行部门': 8, '配套文件': 12, '宣贯完成': '是'},
        'Operation':    {'执行进度': '78%', '调整次数': 3, '关键指标达成': '85%', '风险事项': 4},
    },
    'OBJ_移交信': {
        'domain': 'shupeidian', 'source': 'PMS',
        'Planning':     {'移交类型': '工程竣工移交', '移交对象': '运维部门', '资料清单': 42, '移交计划': '已制定'},
        'Design':       {'移交方案': '已审批', '验收标准': '4类', '问题整改': '完成', '签章准备': '完成'},
        'Construction': {'移交设备': 86, '资料完整度': '92%', '验收签章': '已完成', '遗留问题': 3},
        'Operation':    {'已移交': 86, '运维接管': '已确认', '问题处理': '2/3已解决', '运行月报': '正常'},
    },
}


def gen_time_series(start_date: datetime, intervals_days: list) -> list:
    """生成 4 阶段的进入/退出时间，最后一阶段 stage_exited_at=NULL"""
    times = []
    cur = start_date
    for i, days in enumerate(intervals_days):
        entered = cur
        if i == len(intervals_days) - 1:
            exited = None
        else:
            exited = cur + timedelta(days=days)
            cur = exited
        times.append((entered, exited))
    return times


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        return

    print("=" * 60)
    print("YIMO 统一生命周期数据种子脚本")
    print("=" * 60)

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            # 查询所有对象
            cur.execute("SELECT object_id, object_code FROM extracted_objects ORDER BY object_id")
            objects = cur.fetchall()
            print(f"\n[1/4] 发现 {len(objects)} 个对象")

            # 清空生命周期表
            cur.execute("DELETE FROM object_lifecycle_history")
            print(f"[2/4] 已清空 object_lifecycle_history")

            # 生成数据
            inserted = 0
            skipped = 0
            stage_intervals = [60, 90, 180]  # Planning→Design 60d, Design→Construction 90d, Construction→Operation 180d
            base_date = datetime(2024, 1, 15, 9, 0, 0)

            for object_id, object_code in objects:
                if object_code not in LIFECYCLE_TEMPLATE:
                    print(f"  ⚠ 跳过未模板化对象: {object_code}")
                    skipped += 1
                    continue

                tpl = LIFECYCLE_TEMPLATE[object_code]
                domain = tpl['domain']
                source = tpl['source']

                # 每个对象起始时间略错开（按 object_id 偏移 7 天）
                start = base_date + timedelta(days=(object_id % 30) * 7)
                times = gen_time_series(start, stage_intervals + [0])

                for stage, (entered, exited) in zip(STAGES, times):
                    snapshot = tpl[stage]
                    cur.execute("""
                        INSERT INTO object_lifecycle_history
                            (object_id, lifecycle_stage, stage_entered_at, stage_exited_at,
                             attributes_snapshot, data_domain, source_system, notes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        object_id, stage, entered, exited,
                        json.dumps(snapshot, ensure_ascii=False),
                        domain, source,
                        f"{stage} 阶段（统一模板生成）"
                    ))
                    inserted += 1

            conn.commit()
            print(f"[3/4] 已插入 {inserted} 条记录（跳过 {skipped} 个对象）")

            # 验证
            cur.execute("SELECT lifecycle_stage, COUNT(*) FROM object_lifecycle_history GROUP BY lifecycle_stage ORDER BY FIELD(lifecycle_stage,'Planning','Design','Construction','Operation')")
            print(f"\n[4/4] 阶段分布:")
            for stage, count in cur.fetchall():
                print(f"  {stage:14s} {count} 条")

            cur.execute("SELECT COUNT(DISTINCT object_id) FROM object_lifecycle_history")
            distinct_objs = cur.fetchone()[0]
            print(f"\n  覆盖对象数: {distinct_objs} / {len(objects)}")
            print(f"  总记录数:   {inserted}")

    finally:
        conn.close()

    print("\n✅ 完成")


if __name__ == '__main__':
    main()
