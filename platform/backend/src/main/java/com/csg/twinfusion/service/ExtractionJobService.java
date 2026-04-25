package com.csg.twinfusion.service;

import com.csg.twinfusion.dto.extraction.ExtractionJobDto;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 对象抽取任务管理 (Phase 1 占位实现).
 *
 * 真实算法服务化方案见 platform/docs/algorithm-integration.md (方案 A):
 *   - object_extractor.py 包成 FastAPI 容器 (algo:9000)
 *   - 本服务转发: POST algo:9000/extract → 算法侧执行
 *   - 算法完成后回调 /api/v1/internal/jobs/{id}/done 更新状态
 *
 * 当前 in-memory map 是 stub, 重启后丢失.
 */
@Slf4j
@Service
public class ExtractionJobService {

    private final Map<String, ExtractionJobDto> jobs = new ConcurrentHashMap<>();

    public ExtractionJobDto submit(String dataDomain) {
        ExtractionJobDto job = new ExtractionJobDto();
        job.setJobId(UUID.randomUUID().toString().replace("-", "").substring(0, 12));
        job.setDataDomain(dataDomain);
        job.setStatus("QUEUED");
        job.setProgress(0.0);
        job.setCreatedAt(LocalDateTime.now().toString());
        jobs.put(job.getJobId(), job);
        log.info("submit extraction job {} for domain {} (TODO: forward to algo:9000)",
                job.getJobId(), dataDomain);
        // TODO: HTTP POST 到算法服务 algo:9000/extract
        return job;
    }

    public ExtractionJobDto get(String jobId) {
        return jobs.get(jobId);
    }
}
