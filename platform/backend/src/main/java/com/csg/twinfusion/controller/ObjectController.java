package com.csg.twinfusion.controller;

import com.csg.twinfusion.common.Result;
import com.csg.twinfusion.dto.object.CrossDomainDuplicateDto;
import com.csg.twinfusion.dto.object.ExtractedObjectDto;
import com.csg.twinfusion.dto.object.GranularityRowDto;
import com.csg.twinfusion.dto.object.MergeRequestDto;
import com.csg.twinfusion.dto.object.ObjectRelationGroupDto;
import com.csg.twinfusion.service.CrossDomainService;
import com.csg.twinfusion.service.GranularityService;
import com.csg.twinfusion.service.ObjectService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

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

    @Resource
    private GranularityService granularityService;

    @Resource
    private CrossDomainService crossDomainService;

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

    @Operation(summary = "颗粒度报表 (所有域所有对象的 cluster_size 与等级)")
    @GetMapping("/granularity")
    public Result<List<GranularityRowDto>> getGranularity() {
        return Result.ok(granularityService.listAllDomainsGranularity());
    }

    @Operation(summary = "小对象列表 (cluster_size ≤ threshold)")
    @GetMapping("/small")
    public Result<List<GranularityRowDto>> listSmallObjects(
            @RequestParam(defaultValue = "3") int threshold) {
        return Result.ok(granularityService.listSmallObjects(threshold));
    }

    @Operation(summary = "跨域重复对象 (同名 object 出现在多个域)")
    @GetMapping("/cross-domain-duplicates")
    public Result<List<CrossDomainDuplicateDto>> getCrossDomainDuplicates() {
        return Result.ok(crossDomainService.listDuplicates());
    }

    // -------- 写操作: 当前 Phase 2 占位, 待 DM 接入 --------

    @Operation(summary = "创建对象 (待 DM 接入)")
    @PostMapping
    @ResponseStatus(HttpStatus.NOT_IMPLEMENTED)
    public Result<Void> createObject(@Valid @RequestBody ExtractedObjectDto body) {
        throw new ResponseStatusException(HttpStatus.NOT_IMPLEMENTED,
                "创建对象需要达梦库写权限, 待南网现场配置后启用");
    }

    @Operation(summary = "更新对象 (待 DM 接入)")
    @PutMapping("/{code}")
    @ResponseStatus(HttpStatus.NOT_IMPLEMENTED)
    public Result<Void> updateObject(@PathVariable("code") String code,
                                     @Valid @RequestBody ExtractedObjectDto body) {
        throw new ResponseStatusException(HttpStatus.NOT_IMPLEMENTED,
                "更新对象需要达梦库写权限, 待南网现场配置后启用");
    }

    @Operation(summary = "删除对象 (待 DM 接入)")
    @DeleteMapping("/{code}")
    @ResponseStatus(HttpStatus.NOT_IMPLEMENTED)
    public Result<Void> deleteObject(@PathVariable("code") String code,
                                     @RequestParam String domain) {
        throw new ResponseStatusException(HttpStatus.NOT_IMPLEMENTED,
                "删除对象需要达梦库写权限, 待南网现场配置后启用");
    }

    @Operation(summary = "合并对象 (sourceCode → targetCode, 待 DM 接入)")
    @PostMapping("/merge")
    @ResponseStatus(HttpStatus.NOT_IMPLEMENTED)
    public Result<Void> merge(@Valid @RequestBody MergeRequestDto body) {
        throw new ResponseStatusException(HttpStatus.NOT_IMPLEMENTED,
                "合并对象需要达梦库写权限, 待南网现场配置后启用");
    }
}
