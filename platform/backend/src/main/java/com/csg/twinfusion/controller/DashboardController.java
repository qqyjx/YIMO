package com.csg.twinfusion.controller;

import com.csg.twinfusion.common.Result;
import com.csg.twinfusion.dto.stats.OverallStatsDto;
import com.csg.twinfusion.service.StatsService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Dashboard 汇总接口.
 * 对齐 webapp /api/olm/summary (把多个单点统计拼成一页).
 */
@Tag(name = "Dashboard", description = "首页汇总")
@RestController
@RequestMapping("/api/v1/summary")
public class DashboardController {

    @Resource
    private StatsService statsService;

    @Operation(summary = "首页汇总卡片数据")
    @GetMapping
    public Result<Map<String, Object>> getSummary() {
        OverallStatsDto overall = statsService.getOverall();
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("totalDomains", overall.getTotalDomains());
        payload.put("extractedDomains", overall.getExtractedDomains());
        payload.put("totalObjects", overall.getTotalObjects());
        payload.put("totalRelations", overall.getTotalRelations());
        payload.put("domains", overall.getDomains());
        return Result.ok(payload);
    }
}
