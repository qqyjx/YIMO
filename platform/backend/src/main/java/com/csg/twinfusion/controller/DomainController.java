package com.csg.twinfusion.controller;

import com.csg.twinfusion.common.Result;
import com.csg.twinfusion.dto.DomainDto;
import com.csg.twinfusion.service.DomainService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 业务域查询接口.
 *
 * 从共享的 ../../../DATA/ 目录扫描 22 个域,供前端在切换域时使用.
 */
@Tag(name = "业务域", description = "22 个业务域元数据")
@RestController
@RequestMapping("/api/v1/domains")
public class DomainController {

    @Resource
    private DomainService domainService;

    @Operation(summary = "列出全部业务域")
    @GetMapping
    public Result<List<DomainDto>> listDomains() {
        return Result.ok(domainService.listDomains());
    }
}
