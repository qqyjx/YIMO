package com.csg.twinfusion.controller;

import com.csg.twinfusion.common.Result;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 健康检查 & 系统信息接口.
 *
 * 用途:
 *  - K8s / 南网监控对接 liveness/readiness
 *  - 前端启动时拉取系统名称显示在页面标题
 */
@Tag(name = "系统", description = "健康检查与系统信息")
@RestController
@RequestMapping("/api/v1")
public class HealthController {

    private static final String SYSTEM_NAME = "支撑孪生体新范式多维数据融合分析框架原型系统";

    @Operation(summary = "获取健康状态")
    @GetMapping("/health")
    public Result<Map<String, Object>> getHealth() {
        Map<String, Object> info = new LinkedHashMap<>();
        info.put("systemName", SYSTEM_NAME);
        info.put("status", "UP");
        info.put("time", LocalDateTime.now());
        return Result.ok(info);
    }
}
