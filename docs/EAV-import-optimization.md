# EAV 导入性能优化设计

## 问题定位

现有 `scripts/eav_full.py` 实测 **~100 entities/s**，大域处理不可接受：

| 域 | 2.xlsx 行数 | 估算耗时（原版） | 实测 |
|----|-------------|-----------------|------|
| 供应链 DA-02 | 88,893 | ~15 分钟 | 超时 |
| 输配电 DA-02 | ~60,000 | ~10 分钟 | 超时 |
| 人力资源 DA-02 | ~60,000 | ~10 分钟 | 超时 |

## 瓶颈分析

逐行 INSERT 每行开销（基于 pymysql + MySQL 8 @ localhost）：
```
1 次 INSERT INTO entities    ≈ 1.0 ms  (网络+protocol parse+disk fsync)
1 次 SELECT id 回查          ≈ 0.5 ms
N 次 INSERT INTO values      ≈ N × 1.0 ms  (每列一次)

单行总耗时 ≈ (2 + N) ms, N≈60 列 → ~62 ms/row
→ 100 rows/sec (与实测吻合)
```

总 INSERT 次数：88,893 × 61 ≈ **5.4M 次往返**。每次 1ms → 90 分钟（如果不是还有每 1000 行 commit 的话）。

## 方案矩阵

| 级别 | 手段 | 预期提速 | 实施风险 | 开发时间 |
|------|------|---------|----------|---------|
| L0 | 每 5000 行 commit（原已有 1000 行 commit） | 2× | 零 | 5 分钟 |
| **L1** | **executemany + 多行 VALUES bulk INSERT + 去除 SELECT id 回查** | **15×** | **低** | **45-60 分钟** |
| L2 | MySQL 侧 `unique_checks=0 / foreign_key_checks=0 / DISABLE KEYS` | +1.8× | 低（导完恢复即可） | 10 分钟 |
| L3 | `LOAD DATA LOCAL INFILE` + CSV 中转 | 50× | 中（需开 `local_infile=1`） | 2-3 小时 |
| L4 | multiprocessing 每域并发 4 进程 | 线性加速 | 中（连接池 + 写冲突） | 2 小时 |

## 推荐方案：L1 + L2 新写 eav_fast_import.py

**理由**：
- L1+L2 综合可达 **25-30×**，供应链 88,893 行预计 **40-60 秒**跑完
- 不改 `eav_full.py`（老脚本继续作为稳定回退）
- 不依赖 MySQL 配置改动（local_infile 在南网环境可能不开）
- 可以在本地演示前跑完剩下 11 大域

**牺牲**：
- 跳过增量模式 `--incremental`（每次全量覆盖）
- 跳过 row_hash 计算（去重由 UNIQUE 约束兜底）
- 简化类型推断（全部按 TEXT 存 value_text；全量 DA-02 字段本身就是文本）

## 实施步骤

### Step 1: 编写 scripts/eav_fast_import.py
- CLI 与 eav_full.py 兼容：`--excel --data-domain --dataset-name --host --port --user --password --db`
- 核心改动：
  1. `cursor.executemany("INSERT INTO {tbl} (...) VALUES (%s,...)", [tuple, tuple, ...])` 每批 5000 行
  2. 去除"INSERT + SELECT id"：用 `cur.executemany` 返回的 `lastrowid` + `rowcount` 推导连续 id 段（MySQL 8 对 executemany 保证 lastrowid 是第一条的 id）
  3. INSERT INTO values 用同样的 bulk pattern，一批 10,000 行
  4. 关键 pragma：`SET UNIQUE_CHECKS=0; SET FOREIGN_KEY_CHECKS=0` 进入 / 退出时切换
  5. 每 sheet 结束一次 `commit()`；异常回滚后向上抛

### Step 2: 正确性验证
- 用"纪检监察" 小域跑 eav_fast，和 eav_full 产物做 `SELECT COUNT(*)` 对比
- 实体数、values 数、每个 attribute 的覆盖数必须一致

### Step 3: 批量跑剩余 11 大域
- 清理旧的半入数据（如有）
- 用 batch 脚本跑 timeout 600s（单域预留 10 分钟）
- 预计 15-20 分钟完成全部

## 降级预案

若 eav_fast_import.py 出现数据一致性问题：
- 直接回退到 `eav_full.py` 跑单域（已验证正确性）
- 批量过夜跑，接受长耗时

## 附：推导 lastrowid 段的正确性

MySQL 的 `executemany` bulk INSERT，产生
```
INSERT INTO t (c1,c2) VALUES (1,2),(3,4),(5,6);
```
`LAST_INSERT_ID()` 返回**第一条**的 id，后续自增连续。因此：
```python
cur.executemany(sql, rows)
first_id = cur.lastrowid          # 批首 id
for i, _ in enumerate(rows):
    ids.append(first_id + i)
```
需要约束：
- `innodb_autoinc_lock_mode = 1`（默认 consecutive）；本地 MySQL 8 已默认
- 并发导入禁用（单线程），否则 id 可能非连续
- 确认表无 `AUTO_INCREMENT` gap 风险（我们每次 TRUNCATE / DROP-RECREATE 不用这方案）

## 回收承诺

跑完全部域后：
- 清理旧 legacy `shupeidian` / `jicai` 数据（保留 FK 依赖的 16 个对象不动，只清 eav_datasets 中的拼音域重复切片，避免数字混淆）
- 更新 CLAUDE.md "Requirements Fulfillment Status" 反映最新 EAV 数字
- 更新演示 brief 的 EAV 卖点数字
