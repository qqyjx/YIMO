package com.csg.twinfusion.dto.extraction;

import lombok.Data;

/**
 * 抽取任务. 对应 webapp 的 /api/olm/run-extraction 异步任务.
 *
 * 当前实现策略 (Phase 1): 占位返回 jobId, 真实算法服务化 (FastAPI 容器)
 * 待 algorithm-integration.md 方案 A 落地后接入.
 */
@Data
public class ExtractionJobDto {
    private String jobId;
    private String dataDomain;
    private String status;     // QUEUED / RUNNING / SUCCESS / FAILED
    private Double progress;
    private Integer objectCount;
    private Integer relationCount;
    private String error;
    private String createdAt;
}
