package com.csg.twinfusion.controller;

import com.csg.twinfusion.common.Result;
import com.csg.twinfusion.dto.object.ExtractedObjectDto;
import com.csg.twinfusion.dto.object.ObjectRelationGroupDto;
import com.csg.twinfusion.service.ObjectService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 对象 REST 入口.
 * 对齐 webapp /api/olm/extracted-objects + /api/olm/object-relations/{code}.
 */
@Tag(name = "对象", description = "抽取对象及其三层关联")
@RestController
@RequestMapping("/api/v1/objects")
public class ObjectController {

    @Resource
    private ObjectService objectService;

    @Operation(summary = "列出某域下抽取的全部对象")
    @GetMapping
    public Result<List<ExtractedObjectDto>> listObjects(
            @Parameter(description = "业务域编码, 如 '输配电'") @RequestParam String domain) {
        return Result.ok(objectService.listObjects(domain));
    }

    @Operation(summary = "取单个对象的三层关联")
    @GetMapping("/{code}/relations")
    public Result<ObjectRelationGroupDto> getRelations(
            @PathVariable("code") String code,
            @RequestParam String domain) {
        return Result.ok(objectService.getRelations(code, domain));
    }
}
