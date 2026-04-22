package com.csg.twinfusion.dto.stats;

import lombok.Data;

/**
 * 单域统计.
 */
@Data
public class DomainStatDto {

    private String domain;
    private Integer objectCount;
    private Integer relationCount;
    private Integer conceptCount;
    private Integer logicalCount;
    private Integer physicalCount;
    private Double avgStrength;
    private Boolean extracted;   // 是否已有 extraction_<domain>.json
}
