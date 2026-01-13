#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aiops_consistency_monitor.py - AIOps 一致性哨兵
================================================

监控"一模到底"本体数据的健康状态，自动检测数据异常。

核心规则:
1. 时序逻辑校验: 资产不能在"建设"之前就"运维"
2. 值漂移检测: 关键属性（如电压等级）跨阶段不一致
3. 孤立实体检测: 无法关联到全局资产的实体
4. 数据完整性: 检测缺失的生命周期阶段

使用方法:
  python scripts/aiops_consistency_monitor.py --scan        # 执行一次扫描
  python scripts/aiops_consistency_monitor.py --watch       # 持续监控
  python scripts/aiops_consistency_monitor.py --report      # 生成报告
"""

import argparse
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

try:
    import pymysql
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False


# ============================================================================
# 配置
# ============================================================================

# 生命周期阶段顺序（用于时序校验）
STAGE_ORDER = {
    'Planning': 1,
    'Design': 2,
    'Construction': 3,
    'Operation': 4,
    'Finance': 5,
}

# 时序规则：前置阶段
STAGE_PREREQUISITES = {
    'Design': ['Planning'],
    'Construction': ['Planning', 'Design'],
    'Operation': ['Construction'],
    'Finance': ['Construction'],
}

# 关键属性（跨阶段应保持一致）
CRITICAL_ATTRIBUTES = [
    '电压等级', '额定电压', 'voltage', 'voltage_level',
    '容量', '额定容量', 'capacity', 'rated_capacity',
    '型号', 'model', 'type',
    '资产编码', 'asset_code', 'asset_id',
]

# 异常严重程度映射
ANOMALY_SEVERITY = {
    'temporal_violation': 'error',
    'value_drift': 'warning',
    'missing_stage': 'info',
    'duplicate_conflict': 'warning',
    'schema_mismatch': 'warning',
    'orphan_entity': 'info',
}


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class Anomaly:
    """数据异常"""
    global_uid: str
    anomaly_type: str
    severity: str
    attribute_name: Optional[str]
    expected_value: Optional[str]
    actual_value: Optional[str]
    source_entities: List[int]
    description: str
    suggestion: str


@dataclass
class AssetHealthReport:
    """资产健康报告"""
    global_uid: str
    asset_name: str
    stages_present: List[str]
    stages_missing: List[str]
    trust_score: float
    anomalies: List[Anomaly] = field(default_factory=list)


@dataclass
class SystemHealthReport:
    """系统健康报告"""
    scan_time: datetime
    total_assets: int
    healthy_assets: int
    warning_assets: int
    critical_assets: int
    total_anomalies: int
    anomalies_by_type: Dict[str, int] = field(default_factory=dict)
    anomalies_by_severity: Dict[str, int] = field(default_factory=dict)
    asset_reports: List[AssetHealthReport] = field(default_factory=list)


# ============================================================================
# 数据库操作
# ============================================================================

def connect_mysql(host, port, user, password, database=None):
    """连接MySQL数据库"""
    if HAS_PYMYSQL:
        cfg = dict(host=host, port=port, user=user, password=password,
                   charset='utf8mb4', autocommit=False,
                   cursorclass=pymysql.cursors.DictCursor)
        if database:
            cfg['database'] = database
        return pymysql.connect(**cfg)
    else:
        import mysql.connector as mysql
        cfg = dict(host=host, port=port, user=user, password=password,
                   use_unicode=True, autocommit=False)
        if database:
            cfg['database'] = database
        return mysql.connect(**cfg)


def fetch_global_assets(cur) -> List[Dict]:
    """获取所有全局资产"""
    cur.execute("""
        SELECT global_uid, asset_name, asset_type, trust_score, 
               fusion_status, source_count, first_seen_stage, latest_stage
        FROM global_asset_index
    """)
    return cur.fetchall()


def fetch_asset_entities(cur, global_uid: str) -> List[Dict]:
    """获取资产关联的所有实体"""
    cur.execute("""
        SELECT m.entity_id, m.lifecycle_stage, m.confidence, m.mapping_method,
               d.name as dataset_name, e.external_id
        FROM entity_global_mapping m
        JOIN eav_entities e ON e.id = m.entity_id
        JOIN eav_datasets d ON d.id = e.dataset_id
        WHERE m.global_uid = %s
    """, (global_uid,))
    return cur.fetchall()


def fetch_entity_attribute(cur, entity_id: int, attr_names: List[str]) -> Optional[str]:
    """获取实体的指定属性值"""
    placeholders = ','.join(['%s'] * len(attr_names))
    cur.execute(f"""
        SELECT v.raw_text, v.value_text
        FROM eav_values v
        JOIN eav_attributes a ON a.id = v.attribute_id
        WHERE v.entity_id = %s 
        AND (a.name IN ({placeholders}) OR a.display_name IN ({placeholders}))
        LIMIT 1
    """, (entity_id, *attr_names, *attr_names))
    row = cur.fetchone()
    if row:
        return row['raw_text'] or row['value_text']
    return None


def fetch_orphan_entities(cur) -> List[Dict]:
    """获取孤立实体（未关联到全局资产）"""
    cur.execute("""
        SELECT e.id, e.external_id, d.name as dataset_name, d.lifecycle_stage
        FROM eav_entities e
        JOIN eav_datasets d ON d.id = e.dataset_id
        LEFT JOIN entity_global_mapping m ON m.entity_id = e.id
        WHERE m.id IS NULL
    """)
    return cur.fetchall()


def insert_anomaly(cur, anomaly: Anomaly):
    """插入异常记录"""
    cur.execute("""
        INSERT INTO data_anomalies
        (global_uid, anomaly_type, severity, attribute_name, expected_value, 
         actual_value, source_entities, description, suggestion, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'open')
    """, (
        anomaly.global_uid,
        anomaly.anomaly_type,
        anomaly.severity,
        anomaly.attribute_name,
        anomaly.expected_value,
        anomaly.actual_value,
        json.dumps(anomaly.source_entities),
        anomaly.description,
        anomaly.suggestion
    ))


def update_trust_score(cur, global_uid: str, score: float):
    """更新资产可信度"""
    cur.execute("""
        UPDATE global_asset_index SET trust_score = %s WHERE global_uid = %s
    """, (score, global_uid))


# ============================================================================
# 规则引擎
# ============================================================================

class ConsistencyRuleEngine:
    """一致性规则引擎"""
    
    def __init__(self, cur):
        self.cur = cur
        self.anomalies: List[Anomaly] = []
    
    def check_temporal_logic(self, global_uid: str, entities: List[Dict]) -> List[Anomaly]:
        """
        规则1: 时序逻辑校验
        例如: 资产不能在"建设"之前就有"运维"记录
        """
        anomalies = []
        stages_present = set(e['lifecycle_stage'] for e in entities if e['lifecycle_stage'])
        
        for stage in stages_present:
            prerequisites = STAGE_PREREQUISITES.get(stage, [])
            for prereq in prerequisites:
                if prereq not in stages_present:
                    # 但是如果当前阶段的顺序小于等于前置阶段，这是正常的
                    # 只有当存在后置阶段但不存在前置阶段时才报警
                    stage_order = STAGE_ORDER.get(stage, 0)
                    prereq_order = STAGE_ORDER.get(prereq, 0)
                    
                    if stage_order > prereq_order:
                        entity_ids = [e['entity_id'] for e in entities if e['lifecycle_stage'] == stage]
                        anomaly = Anomaly(
                            global_uid=global_uid,
                            anomaly_type='temporal_violation',
                            severity='error',
                            attribute_name=None,
                            expected_value=f"应先有 {prereq} 阶段",
                            actual_value=f"当前有 {stage} 但缺少 {prereq}",
                            source_entities=entity_ids,
                            description=f"时序违规: 存在'{stage}'阶段数据，但缺少前置阶段'{prereq}'",
                            suggestion=f"请检查是否遗漏了{prereq}阶段的数据，或确认数据导入时的阶段标记是否正确"
                        )
                        anomalies.append(anomaly)
        
        return anomalies
    
    def check_value_drift(self, global_uid: str, entities: List[Dict]) -> List[Anomaly]:
        """
        规则2: 值漂移检测
        关键属性（如电压等级）在不同阶段应保持一致
        """
        anomalies = []
        
        for attr_group in [CRITICAL_ATTRIBUTES[i:i+4] for i in range(0, len(CRITICAL_ATTRIBUTES), 4)]:
            values_by_stage = {}
            entity_by_stage = {}
            
            for entity in entities:
                val = fetch_entity_attribute(self.cur, entity['entity_id'], attr_group)
                if val:
                    stage = entity['lifecycle_stage']
                    values_by_stage[stage] = val
                    entity_by_stage[stage] = entity['entity_id']
            
            # 检查值是否一致
            unique_values = set(values_by_stage.values())
            if len(unique_values) > 1:
                # 找出最常见的值作为"期望值"
                value_counts = defaultdict(int)
                for v in values_by_stage.values():
                    value_counts[v] += 1
                expected = max(value_counts.items(), key=lambda x: x[1])[0]
                
                for stage, val in values_by_stage.items():
                    if val != expected:
                        anomaly = Anomaly(
                            global_uid=global_uid,
                            anomaly_type='value_drift',
                            severity='warning',
                            attribute_name=attr_group[0],
                            expected_value=expected,
                            actual_value=val,
                            source_entities=[entity_by_stage[stage]],
                            description=f"值漂移: '{attr_group[0]}'在{stage}阶段为'{val}'，与其他阶段'{expected}'不一致",
                            suggestion=f"请核实{stage}阶段的'{attr_group[0]}'数据是否正确，或更新其他阶段数据"
                        )
                        anomalies.append(anomaly)
        
        return anomalies
    
    def check_missing_stages(self, global_uid: str, entities: List[Dict]) -> List[Anomaly]:
        """
        规则3: 缺失阶段检测
        """
        anomalies = []
        stages_present = set(e['lifecycle_stage'] for e in entities if e['lifecycle_stage'])
        
        # 根据已有阶段推断应该有的阶段
        max_stage_order = max(STAGE_ORDER.get(s, 0) for s in stages_present) if stages_present else 0
        
        expected_stages = [s for s, o in STAGE_ORDER.items() if o <= max_stage_order]
        missing_stages = set(expected_stages) - stages_present
        
        if missing_stages:
            anomaly = Anomaly(
                global_uid=global_uid,
                anomaly_type='missing_stage',
                severity='info',
                attribute_name=None,
                expected_value=str(list(expected_stages)),
                actual_value=str(list(stages_present)),
                source_entities=[e['entity_id'] for e in entities],
                description=f"缺失阶段: 资产缺少 {', '.join(missing_stages)} 阶段的数据",
                suggestion=f"建议补充 {', '.join(missing_stages)} 阶段的数据以完善资产生命周期记录"
            )
            anomalies.append(anomaly)
        
        return anomalies
    
    def check_orphan_entities(self) -> List[Anomaly]:
        """
        规则4: 孤立实体检测
        """
        anomalies = []
        orphans = fetch_orphan_entities(self.cur)
        
        # 按数据集分组
        orphans_by_dataset = defaultdict(list)
        for o in orphans:
            orphans_by_dataset[o['dataset_name']].append(o)
        
        for dataset_name, entities in orphans_by_dataset.items():
            anomaly = Anomaly(
                global_uid=None,
                anomaly_type='orphan_entity',
                severity='info',
                attribute_name=None,
                expected_value="关联到全局资产",
                actual_value="未关联",
                source_entities=[e['id'] for e in entities[:50]],  # 最多记录50个
                description=f"孤立实体: 数据集'{dataset_name}'中有{len(entities)}个实体未关联到全局资产",
                suggestion="请运行融合代理(agent_lifecycle_fusion.py)来关联这些实体"
            )
            anomalies.append(anomaly)
        
        return anomalies


# ============================================================================
# 一致性监控器
# ============================================================================

class ConsistencyMonitor:
    """一致性监控器"""
    
    def __init__(self, db_config: Dict):
        self.db_config = db_config
    
    def scan(self) -> SystemHealthReport:
        """执行一次完整扫描"""
        conn = connect_mysql(**self.db_config)
        cur = conn.cursor()
        
        try:
            report = SystemHealthReport(
                scan_time=datetime.now(),
                total_assets=0,
                healthy_assets=0,
                warning_assets=0,
                critical_assets=0,
                total_anomalies=0
            )
            
            engine = ConsistencyRuleEngine(cur)
            
            # 获取所有全局资产
            assets = fetch_global_assets(cur)
            report.total_assets = len(assets)
            
            print(f"[INFO] 扫描 {len(assets)} 个全局资产...")
            
            for asset in assets:
                global_uid = asset['global_uid']
                entities = fetch_asset_entities(cur, global_uid)
                
                asset_anomalies = []
                
                # 应用所有规则
                asset_anomalies.extend(engine.check_temporal_logic(global_uid, entities))
                asset_anomalies.extend(engine.check_value_drift(global_uid, entities))
                asset_anomalies.extend(engine.check_missing_stages(global_uid, entities))
                
                # 计算信任分数
                trust_score = self._calculate_trust_score(asset_anomalies)
                update_trust_score(cur, global_uid, trust_score)
                
                # 生成资产报告
                stages_present = list(set(e['lifecycle_stage'] for e in entities if e['lifecycle_stage']))
                all_stages = list(STAGE_ORDER.keys())
                stages_missing = [s for s in all_stages if s not in stages_present]
                
                asset_report = AssetHealthReport(
                    global_uid=global_uid,
                    asset_name=asset['asset_name'] or global_uid,
                    stages_present=stages_present,
                    stages_missing=stages_missing,
                    trust_score=trust_score,
                    anomalies=asset_anomalies
                )
                report.asset_reports.append(asset_report)
                
                # 统计
                if not asset_anomalies:
                    report.healthy_assets += 1
                elif any(a.severity in ('error', 'critical') for a in asset_anomalies):
                    report.critical_assets += 1
                else:
                    report.warning_assets += 1
                
                # 保存异常
                for anomaly in asset_anomalies:
                    insert_anomaly(cur, anomaly)
                    report.total_anomalies += 1
                    report.anomalies_by_type[anomaly.anomaly_type] = \
                        report.anomalies_by_type.get(anomaly.anomaly_type, 0) + 1
                    report.anomalies_by_severity[anomaly.severity] = \
                        report.anomalies_by_severity.get(anomaly.severity, 0) + 1
            
            # 检查孤立实体
            orphan_anomalies = engine.check_orphan_entities()
            for anomaly in orphan_anomalies:
                insert_anomaly(cur, anomaly)
                report.total_anomalies += 1
                report.anomalies_by_type['orphan_entity'] = \
                    report.anomalies_by_type.get('orphan_entity', 0) + 1
                report.anomalies_by_severity['info'] = \
                    report.anomalies_by_severity.get('info', 0) + 1
            
            conn.commit()
            return report
            
        finally:
            cur.close()
            conn.close()
    
    def _calculate_trust_score(self, anomalies: List[Anomaly]) -> float:
        """计算信任分数"""
        if not anomalies:
            return 1.0
        
        penalty = 0.0
        for a in anomalies:
            if a.severity == 'critical':
                penalty += 0.3
            elif a.severity == 'error':
                penalty += 0.2
            elif a.severity == 'warning':
                penalty += 0.1
            else:
                penalty += 0.05
        
        return max(0.0, min(1.0, 1.0 - penalty))
    
    def watch(self, interval: int = 300):
        """持续监控"""
        print(f"[INFO] 启动持续监控，间隔 {interval} 秒...")
        
        while True:
            try:
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始扫描...")
                report = self.scan()
                self._print_summary(report)
                print(f"[INFO] 下次扫描: {interval} 秒后")
                time.sleep(interval)
            except KeyboardInterrupt:
                print("\n[INFO] 监控已停止")
                break
            except Exception as e:
                print(f"[ERROR] 扫描失败: {e}")
                time.sleep(60)  # 出错后等待1分钟
    
    def generate_report(self, output_path: str = None) -> str:
        """生成健康报告"""
        report = self.scan()
        
        lines = []
        lines.append("=" * 70)
        lines.append("📊 YIMO 数据一致性健康报告")
        lines.append("   AIOps Consistency Monitor Report")
        lines.append("=" * 70)
        lines.append(f"扫描时间: {report.scan_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        # 总览
        lines.append("## 📈 总体概况")
        lines.append(f"  总资产数: {report.total_assets}")
        lines.append(f"  健康资产: {report.healthy_assets} ✅")
        lines.append(f"  警告资产: {report.warning_assets} ⚠️")
        lines.append(f"  严重问题: {report.critical_assets} ❌")
        lines.append(f"  总异常数: {report.total_anomalies}")
        lines.append("")
        
        # 异常统计
        if report.anomalies_by_type:
            lines.append("## 🔍 异常类型分布")
            type_names = {
                'temporal_violation': '时序违规',
                'value_drift': '值漂移',
                'missing_stage': '缺失阶段',
                'duplicate_conflict': '重复冲突',
                'orphan_entity': '孤立实体',
            }
            for atype, count in sorted(report.anomalies_by_type.items(), key=lambda x: -x[1]):
                name = type_names.get(atype, atype)
                lines.append(f"  {name}: {count}")
            lines.append("")
        
        # 严重程度分布
        if report.anomalies_by_severity:
            lines.append("## ⚡ 严重程度分布")
            severity_icons = {'critical': '🔴', 'error': '🟠', 'warning': '🟡', 'info': '🔵'}
            for sev, count in sorted(report.anomalies_by_severity.items(), 
                                     key=lambda x: ['critical', 'error', 'warning', 'info'].index(x[0])):
                icon = severity_icons.get(sev, '⚪')
                lines.append(f"  {icon} {sev}: {count}")
            lines.append("")
        
        # 详细问题列表（最多显示20个）
        problem_assets = [a for a in report.asset_reports if a.anomalies]
        if problem_assets:
            lines.append("## 📋 问题资产详情 (前20个)")
            for asset in problem_assets[:20]:
                lines.append(f"\n### {asset.asset_name}")
                lines.append(f"  Global UID: {asset.global_uid}")
                lines.append(f"  Trust Score: {asset.trust_score:.2f}")
                lines.append(f"  已有阶段: {', '.join(asset.stages_present) or '无'}")
                lines.append(f"  缺失阶段: {', '.join(asset.stages_missing) or '无'}")
                lines.append("  异常列表:")
                for anomaly in asset.anomalies:
                    icon = {'critical': '🔴', 'error': '🟠', 'warning': '🟡', 'info': '🔵'}.get(anomaly.severity, '⚪')
                    lines.append(f"    {icon} [{anomaly.anomaly_type}] {anomaly.description}")
                    if anomaly.suggestion:
                        lines.append(f"       💡 {anomaly.suggestion}")
        
        lines.append("")
        lines.append("=" * 70)
        lines.append("报告生成完毕")
        
        report_text = "\n".join(lines)
        
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_text)
            print(f"[INFO] 报告已保存到: {output_path}")
        
        return report_text
    
    def _print_summary(self, report: SystemHealthReport):
        """打印简要摘要"""
        print(f"[SUMMARY] 资产: {report.total_assets} | "
              f"健康: {report.healthy_assets} | "
              f"警告: {report.warning_assets} | "
              f"严重: {report.critical_assets} | "
              f"异常: {report.total_anomalies}")


# ============================================================================
# 主入口
# ============================================================================

def main():
    ap = argparse.ArgumentParser(description='AIOps 一致性哨兵 - 数据健康监控')
    ap.add_argument('--scan', action='store_true', help='执行一次扫描')
    ap.add_argument('--watch', action='store_true', help='持续监控')
    ap.add_argument('--report', action='store_true', help='生成详细报告')
    ap.add_argument('--interval', type=int, default=300, help='监控间隔(秒)')
    ap.add_argument('--output', default=None, help='报告输出路径')
    ap.add_argument('--db', default='eav_db')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=3306)
    ap.add_argument('--user', default='eav_user')
    ap.add_argument('--password', default='eavpass123')
    args = ap.parse_args()
    
    db_config = {
        'host': args.host,
        'port': args.port,
        'user': args.user,
        'password': args.password,
        'database': args.db
    }
    
    print("="*60)
    print("🛡️ YIMO AIOps 一致性哨兵")
    print("   Data Consistency Monitor")
    print("="*60)
    
    monitor = ConsistencyMonitor(db_config)
    
    if args.watch:
        monitor.watch(args.interval)
    elif args.report:
        report_text = monitor.generate_report(args.output)
        print(report_text)
    else:
        # 默认执行一次扫描
        report = monitor.scan()
        monitor._print_summary(report)
        print("\n[TIP] 使用 --report 生成详细报告，使用 --watch 持续监控")


if __name__ == '__main__':
    main()
