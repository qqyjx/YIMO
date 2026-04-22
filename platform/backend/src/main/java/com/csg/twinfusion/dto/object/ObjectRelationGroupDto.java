package com.csg.twinfusion.dto.object;

import lombok.Data;

import java.util.List;

/**
 * 单个对象的三层关联分组: 前端关联面板直接消费.
 */
@Data
public class ObjectRelationGroupDto {

    private String objectCode;
    private String objectName;
    private List<RelationDto> concept;
    private List<RelationDto> logical;
    private List<RelationDto> physical;
}
