package com.csg.twinfusion.controller;

import com.csg.twinfusion.common.Result;
import com.csg.twinfusion.dto.stats.DomainStatDto;
import com.csg.twinfusion.dto.stats.OverallStatsDto;
import com.csg.twinfusion.service.StatsService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 统计 REST 入口.
 * 对齐 webapp /api/olm/stats + /api/olm/domain-stats.
 */
@Tag(name = "统计", description = "全局与分域统计")
@RestController
@RequestMapping("/api/v1/stats")
public class StatsController {

    @Resource
    private StatsService statsService;

    @Operation(summary = "全局统计 (含每域明细)")
    @GetMapping
    public Result<OverallStatsDto> getOverall() {
        return Result.ok(statsService.getOverall());
    }

    @Operation(summary = "分域统计 (22 个业务域)")
    @GetMapping("/domains")
    public Result<List<DomainStatDto>> listDomains() {
        return Result.ok(statsService.listDomainStats());
    }
}
