package com.csg.twinfusion.dto.stats;

import lombok.Data;

import java.util.List;

/**
 * 全局统计.
 */
@Data
public class OverallStatsDto {

    private Integer totalDomains;
    private Integer extractedDomains;
    private Integer totalObjects;
    private Integer totalRelations;
    private List<DomainStatDto> domains;
}
