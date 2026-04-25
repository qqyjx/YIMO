package com.csg.twinfusion.dto.object;

import lombok.Data;

import java.util.List;

/**
 * 跨域重复对象: 同名 object 在多个 data_domain 出现.
 */
@Data
public class CrossDomainDuplicateDto {
    private String objectName;
    private Integer domainCount;
    private List<DomainOccurrence> occurrences;

    @Data
    public static class DomainOccurrence {
        private String dataDomain;
        private String objectCode;
        private Integer clusterSize;
        private List<String> sampleEntities;
    }
}
