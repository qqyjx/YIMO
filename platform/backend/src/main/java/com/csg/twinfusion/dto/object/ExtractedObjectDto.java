package com.csg.twinfusion.dto.object;

import lombok.Data;

import java.util.List;

/**
 * 抽取对象 DTO (对齐 outputs/extraction_<domain>.json 中 objects[] 元素).
 */
@Data
public class ExtractedObjectDto {

    private String objectCode;
    private String objectName;
    private String objectType;
    private String description;
    private String dataDomain;
    private Double extractionConfidence;
    private Integer clusterSize;
    private Integer totalRelations;
    private Integer conceptCount;
    private Integer logicalCount;
    private Integer physicalCount;
    private List<String> synonyms;
    private List<String> sampleEntities;
}
