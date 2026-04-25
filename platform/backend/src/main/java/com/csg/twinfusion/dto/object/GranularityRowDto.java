package com.csg.twinfusion.dto.object;

import lombok.Data;

/**
 * 颗粒度报表单行 (一个对象一条).
 */
@Data
public class GranularityRowDto {
    private String objectCode;
    private String objectName;
    private String objectType;
    private String dataDomain;
    private Integer clusterSize;
    private Integer totalRelations;
    private String severity;     // SMALL (<=3) / NORMAL / LARGE (>=20)
}
