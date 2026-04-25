package com.csg.twinfusion.service;

import com.csg.twinfusion.dto.object.GranularityRowDto;
import com.csg.twinfusion.service.extraction.ExtractionJsonReader;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

/**
 * 颗粒度 / 小对象分析.
 *
 * 复用 outputs/extraction_*.json (JSON fallback);
 * Phase 2 迁库后改读 TF_OM_EXTRACTED_OBJECT.cluster_size.
 */
@Service
public class GranularityService {

    private static final int SMALL_THRESHOLD_DEFAULT = 3;
    private static final int LARGE_THRESHOLD = 20;

    @Resource
    private ExtractionJsonReader extractionJsonReader;

    @Resource
    private DomainService domainService;

    public List<GranularityRowDto> listAllDomainsGranularity() {
        List<GranularityRowDto> result = new ArrayList<>();
        for (var d : domainService.listDomains()) {
            result.addAll(buildForDomain(d.getCode()));
        }
        return result;
    }

    public List<GranularityRowDto> listSmallObjects(int threshold) {
        if (threshold <= 0) {
            threshold = SMALL_THRESHOLD_DEFAULT;
        }
        final int t = threshold;
        return listAllDomainsGranularity().stream()
                .filter(r -> r.getClusterSize() != null && r.getClusterSize() <= t)
                .toList();
    }

    private List<GranularityRowDto> buildForDomain(String domain) {
        var rootOpt = extractionJsonReader.read(domain);
        if (rootOpt.isEmpty()) {
            return List.of();
        }
        JsonNode root = rootOpt.get();
        JsonNode stats = root.path("stats");
        List<GranularityRowDto> rows = new ArrayList<>();
        for (JsonNode n : root.path("objects")) {
            GranularityRowDto r = new GranularityRowDto();
            r.setObjectCode(n.path("object_code").asText());
            r.setObjectName(n.path("object_name").asText());
            r.setObjectType(n.path("object_type").asText("CORE"));
            r.setDataDomain(domain);
            int size = n.path("cluster_size").asInt(0);
            r.setClusterSize(size);
            JsonNode statForObj = stats.path(r.getObjectCode());
            int total = statForObj.path("total").asInt(0);
            r.setTotalRelations(total);
            r.setSeverity(size <= SMALL_THRESHOLD_DEFAULT ? "SMALL"
                    : size >= LARGE_THRESHOLD ? "LARGE" : "NORMAL");
            rows.add(r);
        }
        return rows;
    }
}
