package com.csg.twinfusion.controller;

import com.csg.twinfusion.common.Result;
import com.csg.twinfusion.dto.extraction.ExtractionJobDto;
import com.csg.twinfusion.service.ExtractionJobService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * 对象抽取任务 REST 入口.
 *
 * Phase 1: 算法服务尚未容器化, 接口先占位返回 jobId.
 * 真实接入见 platform/docs/algorithm-integration.md 方案 A.
 */
@Tag(name = "抽取任务", description = "异步对象抽取任务")
@RestController
@RequestMapping("/api/v1/extraction")
public class ExtractionController {

    @Resource
    private ExtractionJobService extractionJobService;

    @Operation(summary = "提交抽取任务 (异步, 返回 jobId)")
    @PostMapping("/run")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public Result<ExtractionJobDto> run(@RequestParam String domain) {
        return Result.ok(extractionJobService.submit(domain));
    }

    @Operation(summary = "查询抽取任务状态")
    @GetMapping("/jobs/{jobId}")
    public Result<ExtractionJobDto> getJob(@PathVariable String jobId) {
        ExtractionJobDto job = extractionJobService.get(jobId);
        if (job == null) {
            return Result.fail(404, "任务不存在: " + jobId);
        }
        return Result.ok(job);
    }
}
