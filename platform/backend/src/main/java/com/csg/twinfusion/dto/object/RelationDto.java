package com.csg.twinfusion.dto.object;

import lombok.Data;

/**
 * 对象 <-> 三层实体关联 DTO.
 */
@Data
public class RelationDto {

    private String objectCode;
    private String entityLayer;        // CONCEPT | LOGICAL | PHYSICAL
    private String entityName;
    private String entityCode;
    private String relationType;       // DIRECT | INDIRECT | DERIVED | CLUSTER
    private Double relationStrength;
    private String matchMethod;
    private String dataDomain;
    private String sourceFile;
    private String sourceSheet;
    private String viaConceptEntity;
}
