#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_lifecycle_fusion.py - 智能本体融合代理
===============================================

基于LLM的实体融合代理，自动发现跨生命周期阶段的同一物理资产。
实现"白圆"(White Circle)概念：将不同阶段的数据关联到同一个全局资产标识。

核心功能:
1. 语义指纹生成：为实体生成语义向量，用于相似度计算
2. 候选匹配发现：基于向量相似度发现可能指向同一资产的实体对
3. LLM融合决策：使用LLM判断两个实体是否指向同一物理对象
4. 全局资产索引构建：创建/更新 global_asset_index 表

使用方法:
  python scripts/agent_lifecycle_fusion.py --mode discover   # 发现候选对
  python scripts/agent_lifecycle_fusion.py --mode fuse       # 执行融合
  python scripts/agent_lifecycle_fusion.py --mode full       # 完整流程
"""

import argparse
import json
import os
import struct
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
from tqdm.auto import tqdm

# 数据库连接
try:
    import pymysql
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False


# ============================================================================
# 配置
# ============================================================================

DEFAULT_MODEL_PATH = '/root/models/text2vec'
DEFAULT_SIMILARITY_THRESHOLD = 0.75  # 语义相似度阈值
DEFAULT_LLM_CONFIDENCE_THRESHOLD = 0.7  # LLM置信度阈值

# 生命周期阶段顺序（用于时序校验）
STAGE_ORDER = {
    'Planning': 1,
    'Design': 2,
    'Construction': 3,
    'Operation': 4,
    'Finance': 5,
}


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class EntitySummary:
    """实体摘要"""
    entity_id: int
    dataset_id: int
    dataset_name: str
    lifecycle_stage: str
    external_id: str
    attributes: Dict[str, str] = field(default_factory=dict)
    embedding: Optional[np.ndarray] = None
    text_summary: str = ""


@dataclass
class FusionCandidate:
    """融合候选对"""
    entity_a: EntitySummary
    entity_b: EntitySummary
    similarity: float
    llm_decision: Optional[str] = None
    llm_confidence: Optional[float] = None
    reasoning: Optional[str] = None


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


def ensure_lifecycle_tables(cur):
    """确保生命周期相关表存在"""
    # 这些表应该已经在 bootstrap.sql 中创建
    # 这里做一个检查
    cur.execute("SHOW TABLES LIKE 'global_asset_index'")
    if not cur.fetchone():
        raise RuntimeError("表 global_asset_index 不存在，请先执行 mysql-local/bootstrap.sql")


def fetch_all_entities_with_attributes(cur, prefix: str = 'eav') -> List[EntitySummary]:
    """获取所有实体及其属性"""
    # 获取所有数据集和阶段
    cur.execute(f"""
        SELECT d.id, d.name, d.lifecycle_stage, d.source_file
        FROM `{prefix}_datasets` d
    """)
    datasets = {row['id']: row for row in cur.fetchall()}
    
    if not datasets:
        return []
    
    # 获取所有实体
    cur.execute(f"""
        SELECT e.id, e.dataset_id, e.external_id, e.row_number
        FROM `{prefix}_entities` e
    """)
    entities_raw = cur.fetchall()
    
    # 获取所有属性值
    entities: List[EntitySummary] = []
    for ent in tqdm(entities_raw, desc="加载实体属性"):
        dataset = datasets.get(ent['dataset_id'])
        if not dataset:
            continue
        
        # 获取该实体的所有属性值
        cur.execute(f"""
            SELECT a.display_name, v.raw_text, v.value_text, v.value_number
            FROM `{prefix}_values` v
            JOIN `{prefix}_attributes` a ON a.id = v.attribute_id
            WHERE v.entity_id = %s
        """, (ent['id'],))
        
        attrs = {}
        for row in cur.fetchall():
            val = row['raw_text'] or row['value_text'] or str(row['value_number'] or '')
            if val:
                attrs[row['display_name']] = val
        
        # 构建文本摘要
        text_parts = []
        for k, v in attrs.items():
            if k != '__sheet__' and v:
                text_parts.append(f"{k}:{v}")
        text_summary = "; ".join(text_parts)
        
        entity = EntitySummary(
            entity_id=ent['id'],
            dataset_id=ent['dataset_id'],
            dataset_name=dataset['name'],
            lifecycle_stage=dataset.get('lifecycle_stage', 'Finance'),
            external_id=ent['external_id'] or '',
            attributes=attrs,
            text_summary=text_summary
        )
        entities.append(entity)
    
    return entities


def save_semantic_fingerprint(cur, entity_id: int, embedding: np.ndarray, 
                              text_summary: str, key_attrs: Dict, model_name: str):
    """保存语义指纹到数据库"""
    embedding_blob = embedding.tobytes()
    key_attrs_json = json.dumps(key_attrs, ensure_ascii=False)
    
    cur.execute("""
        INSERT INTO semantic_fingerprints 
        (entity_id, fingerprint_version, embedding_model, embedding_dim, embedding_blob, text_summary, key_attributes)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            embedding_model = VALUES(embedding_model),
            embedding_dim = VALUES(embedding_dim),
            embedding_blob = VALUES(embedding_blob),
            text_summary = VALUES(text_summary),
            key_attributes = VALUES(key_attributes),
            updated_at = NOW(6)
    """, ('v1', model_name, len(embedding), embedding_blob, text_summary, key_attrs_json, entity_id))


def create_global_asset(cur, asset_name: str, asset_type: str = None, 
                        first_stage: str = None) -> str:
    """创建全局资产记录，返回global_uid"""
    global_uid = f"ASSET-{uuid.uuid4().hex[:12].upper()}"
    
    cur.execute("""
        INSERT INTO global_asset_index 
        (global_uid, asset_name, asset_type, first_seen_stage, latest_stage, fusion_status, source_count)
        VALUES (%s, %s, %s, %s, %s, 'pending', 1)
    """, (global_uid, asset_name, asset_type, first_stage, first_stage))
    
    return global_uid


def link_entity_to_global(cur, entity_id: int, global_uid: str, 
                          stage: str, confidence: float, method: str, reason: str):
    """将实体关联到全局资产"""
    cur.execute("""
        INSERT INTO entity_global_mapping
        (entity_id, global_uid, lifecycle_stage, confidence, mapping_method, mapping_reason, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            confidence = VALUES(confidence),
            mapping_method = VALUES(mapping_method),
            mapping_reason = VALUES(mapping_reason)
    """, (entity_id, global_uid, stage, confidence, method, reason, 'fusion_agent'))
    
    # 更新全局资产的source_count和latest_stage
    cur.execute("""
        UPDATE global_asset_index 
        SET source_count = source_count + 1,
            latest_stage = CASE 
                WHEN %s > COALESCE(latest_stage, '') THEN %s 
                ELSE latest_stage 
            END
        WHERE global_uid = %s
    """, (stage, stage, global_uid))


def log_fusion_action(cur, global_uid: str, source_id: int, target_id: int,
                      action: str, agent_type: str, prompt: str, response: str,
                      confidence: float, reasoning: str, exec_time_ms: int):
    """记录融合操作日志"""
    cur.execute("""
        INSERT INTO fusion_logs
        (global_uid, source_entity_id, target_entity_id, action, agent_type,
         prompt_used, response_raw, confidence, reasoning, execution_time_ms)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (global_uid, source_id, target_id, action, agent_type, 
          prompt, response, confidence, reasoning, exec_time_ms))


# ============================================================================
# 语义向量生成
# ============================================================================

class SemanticEncoder:
    """语义编码器"""
    
    def __init__(self, model_path: str = DEFAULT_MODEL_PATH):
        self.model_path = model_path
        self.model = None
        self.model_name = 'text2vec-base-chinese'
    
    def load_model(self):
        """加载语义向量模型"""
        if self.model is not None:
            return
        
        try:
            from sentence_transformers import SentenceTransformer
            
            # 设置缓存目录
            os.environ.setdefault('SENTENCE_TRANSFORMERS_HOME', self.model_path)
            os.environ.setdefault('HF_HOME', self.model_path)
            
            # 尝试本地加载
            local_path = Path(self.model_path)
            if local_path.is_dir():
                # 查找模型目录
                model_dirs = list(local_path.glob('**/config.json'))
                if model_dirs:
                    model_dir = model_dirs[0].parent
                    self.model = SentenceTransformer(str(model_dir), local_files_only=True)
                    print(f"[INFO] 从本地加载模型: {model_dir}")
                    return
            
            # 回退到在线加载
            self.model = SentenceTransformer('shibing624/text2vec-base-chinese', 
                                             cache_folder=self.model_path)
            print(f"[INFO] 模型已加载")
            
        except Exception as e:
            print(f"[WARN] 无法加载句向量模型: {e}")
            print("[WARN] 将使用TF-IDF回退方案")
            self.model = None
    
    def encode(self, texts: List[str], batch_size: int = 64) -> np.ndarray:
        """编码文本为向量"""
        self.load_model()
        
        if self.model is not None:
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=True,
                normalize_embeddings=True
            )
            return embeddings.astype('float32')
        else:
            # TF-IDF回退
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.preprocessing import normalize
            
            vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 4), min_df=1)
            X = vec.fit_transform(texts)
            X = normalize(X, norm='l2')
            return X.toarray().astype('float32')


# ============================================================================
# LLM 融合决策
# ============================================================================

class LLMFusionJudge:
    """LLM融合判断器"""
    
    def __init__(self, api_key: str = None, api_base: str = None):
        self.api_key = api_key or os.environ.get('DEEPSEEK_API_KEY') or os.environ.get('OPENAI_API_KEY')
        self.api_base = api_base or os.environ.get('LLM_API_BASE', 'https://api.deepseek.com/v1')
        self.has_llm = bool(self.api_key)
    
    def build_fusion_prompt(self, entity_a: EntitySummary, entity_b: EntitySummary) -> str:
        """构建融合判断Prompt"""
        prompt = f"""你是一个电力资产数据融合专家。请判断以下两个来自不同生命周期阶段的数据记录是否指向同一个物理资产。

## 实体A（来自{entity_a.lifecycle_stage}阶段）
数据集: {entity_a.dataset_name}
外部ID: {entity_a.external_id}
属性:
{self._format_attributes(entity_a.attributes)}

## 实体B（来自{entity_b.lifecycle_stage}阶段）
数据集: {entity_b.dataset_name}
外部ID: {entity_b.external_id}
属性:
{self._format_attributes(entity_b.attributes)}

## 判断标准
1. 资产名称/编号是否一致或高度相似
2. 关键技术参数（如电压等级、容量、型号）是否匹配
3. 位置信息（如安装地点、所属单位）是否吻合
4. 时间逻辑是否合理（如设计早于建设，建设早于运维）

## 输出格式（严格JSON）
```json
{{
  "is_same_asset": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "判断理由",
  "matching_evidence": ["证据1", "证据2"],
  "conflicting_evidence": ["冲突点1"]
}}
```

请直接输出JSON，不要其他内容："""
        return prompt
    
    def _format_attributes(self, attrs: Dict[str, str], max_attrs: int = 15) -> str:
        """格式化属性显示"""
        lines = []
        for i, (k, v) in enumerate(attrs.items()):
            if i >= max_attrs:
                lines.append(f"  ... 还有 {len(attrs) - max_attrs} 个属性")
                break
            if k != '__sheet__':
                lines.append(f"  - {k}: {v[:100] if len(str(v)) > 100 else v}")
        return "\n".join(lines) if lines else "  (无属性)"
    
    def judge(self, entity_a: EntitySummary, entity_b: EntitySummary) -> Tuple[bool, float, str]:
        """
        判断两个实体是否指向同一资产
        返回: (is_same, confidence, reasoning)
        """
        if not self.has_llm:
            # 无LLM时使用规则引擎
            return self._rule_based_judge(entity_a, entity_b)
        
        prompt = self.build_fusion_prompt(entity_a, entity_b)
        
        try:
            import requests
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'model': 'deepseek-chat',
                'messages': [
                    {'role': 'system', 'content': '你是一个数据融合专家，专门判断不同来源的数据是否指向同一个实体。'},
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': 0.1,
                'max_tokens': 500
            }
            
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            # 解析JSON响应
            # 尝试提取JSON部分
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                data = json.loads(json_match.group())
                return (
                    data.get('is_same_asset', False),
                    data.get('confidence', 0.5),
                    data.get('reasoning', '')
                )
            
        except Exception as e:
            print(f"[WARN] LLM调用失败: {e}, 回退到规则引擎")
        
        return self._rule_based_judge(entity_a, entity_b)
    
    def _rule_based_judge(self, entity_a: EntitySummary, entity_b: EntitySummary) -> Tuple[bool, float, str]:
        """基于规则的融合判断（LLM回退方案）"""
        score = 0.0
        reasons = []
        
        # 规则1: 外部ID匹配
        if entity_a.external_id and entity_b.external_id:
            if entity_a.external_id == entity_b.external_id:
                score += 0.4
                reasons.append("外部ID完全匹配")
            elif entity_a.external_id in entity_b.external_id or entity_b.external_id in entity_a.external_id:
                score += 0.2
                reasons.append("外部ID部分匹配")
        
        # 规则2: 名称相似度
        name_keys = ['名称', '资产名称', 'name', 'asset_name', '设备名称']
        name_a = self._find_attr(entity_a.attributes, name_keys)
        name_b = self._find_attr(entity_b.attributes, name_keys)
        if name_a and name_b:
            from difflib import SequenceMatcher
            sim = SequenceMatcher(None, name_a, name_b).ratio()
            if sim > 0.8:
                score += 0.3
                reasons.append(f"名称高度相似({sim:.2f})")
            elif sim > 0.5:
                score += 0.15
                reasons.append(f"名称部分相似({sim:.2f})")
        
        # 规则3: 关键参数匹配
        key_params = ['电压等级', '额定电压', '容量', '型号', '规格']
        matched_params = 0
        for param in key_params:
            val_a = self._find_attr(entity_a.attributes, [param])
            val_b = self._find_attr(entity_b.attributes, [param])
            if val_a and val_b and val_a == val_b:
                matched_params += 1
        if matched_params > 0:
            score += min(0.2, matched_params * 0.05)
            reasons.append(f"{matched_params}个关键参数匹配")
        
        # 规则4: 位置信息
        loc_keys = ['位置', '安装地点', '所属单位', '变电站']
        loc_a = self._find_attr(entity_a.attributes, loc_keys)
        loc_b = self._find_attr(entity_b.attributes, loc_keys)
        if loc_a and loc_b:
            from difflib import SequenceMatcher
            sim = SequenceMatcher(None, loc_a, loc_b).ratio()
            if sim > 0.6:
                score += 0.1
                reasons.append("位置信息相似")
        
        is_same = score >= 0.5
        reasoning = "; ".join(reasons) if reasons else "无明显匹配证据"
        
        return is_same, min(score, 1.0), f"[规则引擎] {reasoning}"
    
    def _find_attr(self, attrs: Dict[str, str], keys: List[str]) -> Optional[str]:
        """查找属性值"""
        for k in keys:
            for attr_name, attr_val in attrs.items():
                if k.lower() in attr_name.lower():
                    return attr_val
        return None


# ============================================================================
# 融合代理主类
# ============================================================================

class LifecycleFusionAgent:
    """生命周期融合代理"""
    
    def __init__(self, db_config: Dict, model_path: str = DEFAULT_MODEL_PATH):
        self.db_config = db_config
        self.encoder = SemanticEncoder(model_path)
        self.judge = LLMFusionJudge()
        self.entities: List[EntitySummary] = []
        self.candidates: List[FusionCandidate] = []
    
    def run(self, mode: str = 'full', similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
            confidence_threshold: float = DEFAULT_LLM_CONFIDENCE_THRESHOLD):
        """运行融合代理"""
        conn = connect_mysql(**self.db_config)
        cur = conn.cursor()
        
        try:
            ensure_lifecycle_tables(cur)
            
            if mode in ('discover', 'full'):
                print("\n" + "="*60)
                print("📊 Phase 1: 加载实体数据")
                print("="*60)
                self.entities = fetch_all_entities_with_attributes(cur, 'eav')
                print(f"[INFO] 加载了 {len(self.entities)} 个实体")
                
                if not self.entities:
                    print("[WARN] 没有实体数据，退出")
                    return
                
                print("\n" + "="*60)
                print("🧠 Phase 2: 生成语义指纹")
                print("="*60)
                self._generate_fingerprints(cur)
                conn.commit()
                
                print("\n" + "="*60)
                print("🔍 Phase 3: 发现融合候选对")
                print("="*60)
                self._discover_candidates(similarity_threshold)
                print(f"[INFO] 发现 {len(self.candidates)} 个候选融合对")
            
            if mode in ('fuse', 'full'):
                print("\n" + "="*60)
                print("🔗 Phase 4: 执行本体融合")
                print("="*60)
                self._execute_fusion(cur, confidence_threshold)
                conn.commit()
                
            print("\n" + "="*60)
            print("✅ 融合代理运行完成")
            print("="*60)
            
        finally:
            cur.close()
            conn.close()
    
    def _generate_fingerprints(self, cur):
        """生成语义指纹"""
        texts = [e.text_summary for e in self.entities]
        
        if not texts:
            return
        
        print(f"[INFO] 编码 {len(texts)} 个实体...")
        embeddings = self.encoder.encode(texts)
        
        for i, (entity, emb) in enumerate(zip(self.entities, embeddings)):
            entity.embedding = emb
            
            # 保存到数据库
            key_attrs = {k: v for k, v in list(entity.attributes.items())[:10]}
            save_semantic_fingerprint(cur, entity.entity_id, emb, 
                                      entity.text_summary, key_attrs, 
                                      self.encoder.model_name)
        
        print(f"[INFO] 语义指纹生成完成")
    
    def _discover_candidates(self, threshold: float):
        """发现融合候选对"""
        # 按阶段分组
        stage_entities: Dict[str, List[EntitySummary]] = defaultdict(list)
        for e in self.entities:
            if e.embedding is not None:
                stage_entities[e.lifecycle_stage].append(e)
        
        print(f"[INFO] 各阶段实体数量: {', '.join(f'{k}:{len(v)}' for k,v in stage_entities.items())}")
        
        # 跨阶段比较
        stages = list(stage_entities.keys())
        self.candidates = []
        
        for i, stage_a in enumerate(stages):
            for stage_b in stages[i+1:]:
                print(f"[INFO] 比较 {stage_a} vs {stage_b}...")
                
                entities_a = stage_entities[stage_a]
                entities_b = stage_entities[stage_b]
                
                if not entities_a or not entities_b:
                    continue
                
                # 构建向量矩阵
                emb_a = np.array([e.embedding for e in entities_a])
                emb_b = np.array([e.embedding for e in entities_b])
                
                # 计算余弦相似度
                similarities = np.dot(emb_a, emb_b.T)
                
                # 找出高相似度对
                pairs = np.where(similarities > threshold)
                for idx_a, idx_b in zip(pairs[0], pairs[1]):
                    sim = similarities[idx_a, idx_b]
                    candidate = FusionCandidate(
                        entity_a=entities_a[idx_a],
                        entity_b=entities_b[idx_b],
                        similarity=float(sim)
                    )
                    self.candidates.append(candidate)
        
        # 按相似度排序
        self.candidates.sort(key=lambda x: x.similarity, reverse=True)
    
    def _execute_fusion(self, cur, confidence_threshold: float):
        """执行融合"""
        if not self.candidates:
            # 如果没有候选对，为所有实体创建独立的全局资产
            print("[INFO] 无候选融合对，为所有实体创建独立全局资产...")
            for entity in tqdm(self.entities, desc="创建全局资产"):
                name = self._get_entity_name(entity)
                global_uid = create_global_asset(cur, name, None, entity.lifecycle_stage)
                link_entity_to_global(cur, entity.entity_id, global_uid, 
                                      entity.lifecycle_stage, 1.0, 'rule', '无匹配，独立创建')
            return
        
        # 记录已处理的实体
        processed_entities = set()
        # 实体到全局资产的映射
        entity_to_global: Dict[int, str] = {}
        
        for candidate in tqdm(self.candidates, desc="融合决策"):
            ea, eb = candidate.entity_a, candidate.entity_b
            
            # 跳过已处理的实体对
            if ea.entity_id in processed_entities and eb.entity_id in processed_entities:
                continue
            
            # LLM/规则判断
            start_time = time.time()
            is_same, confidence, reasoning = self.judge.judge(ea, eb)
            exec_time = int((time.time() - start_time) * 1000)
            
            candidate.llm_decision = 'merge' if is_same else 'reject'
            candidate.llm_confidence = confidence
            candidate.reasoning = reasoning
            
            if is_same and confidence >= confidence_threshold:
                # 执行融合
                global_uid = entity_to_global.get(ea.entity_id) or entity_to_global.get(eb.entity_id)
                
                if not global_uid:
                    # 创建新的全局资产
                    name = self._get_entity_name(ea) or self._get_entity_name(eb)
                    global_uid = create_global_asset(cur, name, None, ea.lifecycle_stage)
                
                # 关联实体A
                if ea.entity_id not in processed_entities:
                    link_entity_to_global(cur, ea.entity_id, global_uid, 
                                          ea.lifecycle_stage, confidence, 
                                          'llm' if self.judge.has_llm else 'rule', reasoning)
                    entity_to_global[ea.entity_id] = global_uid
                    processed_entities.add(ea.entity_id)
                
                # 关联实体B
                if eb.entity_id not in processed_entities:
                    link_entity_to_global(cur, eb.entity_id, global_uid, 
                                          eb.lifecycle_stage, confidence,
                                          'llm' if self.judge.has_llm else 'rule', reasoning)
                    entity_to_global[eb.entity_id] = global_uid
                    processed_entities.add(eb.entity_id)
                
                # 记录日志
                log_fusion_action(cur, global_uid, ea.entity_id, eb.entity_id,
                                  'merge', 'llm' if self.judge.has_llm else 'rule',
                                  self.judge.build_fusion_prompt(ea, eb) if self.judge.has_llm else None,
                                  None, confidence, reasoning, exec_time)
        
        # 为未处理的实体创建独立全局资产
        for entity in self.entities:
            if entity.entity_id not in processed_entities:
                name = self._get_entity_name(entity)
                global_uid = create_global_asset(cur, name, None, entity.lifecycle_stage)
                link_entity_to_global(cur, entity.entity_id, global_uid, 
                                      entity.lifecycle_stage, 1.0, 'rule', '无匹配，独立创建')
        
        print(f"[INFO] 融合完成: {len(processed_entities)} 个实体被关联到全局资产")
    
    def _get_entity_name(self, entity: EntitySummary) -> str:
        """获取实体名称"""
        name_keys = ['名称', '资产名称', 'name', 'asset_name', '设备名称']
        for k in name_keys:
            for attr_name, attr_val in entity.attributes.items():
                if k.lower() in attr_name.lower() and attr_val:
                    return attr_val[:200]
        return f"Asset-{entity.entity_id}"


# ============================================================================
# 主入口
# ============================================================================

def main():
    ap = argparse.ArgumentParser(description='智能本体融合代理 - 一模到底')
    ap.add_argument('--mode', default='full', choices=['discover', 'fuse', 'full'],
                    help='运行模式: discover(发现候选)/fuse(执行融合)/full(完整流程)')
    ap.add_argument('--db', default='eav_db')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=3306)
    ap.add_argument('--user', default='eav_user')
    ap.add_argument('--password', default='Eav_pass_1234')
    ap.add_argument('--model-path', default=DEFAULT_MODEL_PATH, help='语义向量模型路径')
    ap.add_argument('--similarity-threshold', type=float, default=DEFAULT_SIMILARITY_THRESHOLD,
                    help='语义相似度阈值(0-1)')
    ap.add_argument('--confidence-threshold', type=float, default=DEFAULT_LLM_CONFIDENCE_THRESHOLD,
                    help='LLM置信度阈值(0-1)')
    args = ap.parse_args()
    
    db_config = {
        'host': args.host,
        'port': args.port,
        'user': args.user,
        'password': args.password,
        'database': args.db
    }
    
    print("="*60)
    print("🧬 YIMO 智能本体融合代理")
    print("   Universal Lifecycle Ontology Manager - Fusion Agent")
    print("="*60)
    print(f"模式: {args.mode}")
    print(f"相似度阈值: {args.similarity_threshold}")
    print(f"置信度阈值: {args.confidence_threshold}")
    print()
    
    agent = LifecycleFusionAgent(db_config, args.model_path)
    agent.run(args.mode, args.similarity_threshold, args.confidence_threshold)


if __name__ == '__main__':
    main()
