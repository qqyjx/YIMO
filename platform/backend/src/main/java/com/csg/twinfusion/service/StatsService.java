package com.csg.twinfusion.service;

import com.csg.twinfusion.dto.DomainDto;
import com.csg.twinfusion.dto.stats.DomainStatDto;
import com.csg.twinfusion.dto.stats.OverallStatsDto;
import com.csg.twinfusion.service.extraction.ExtractionJsonReader;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * 统计服务.
 */
@Service
public class StatsService {

    @Resource
    private DomainService domainService;

    @Resource
    private ExtractionJsonReader extractionJsonReader;

    public OverallStatsDto getOverall() {
        List<DomainDto> domains = domainService.listDomains();
        List<DomainStatDto> stats = new ArrayList<>(domains.size());
        int totalObjects = 0;
        int totalRelations = 0;
        int extractedDomains = 0;
        for (DomainDto dom : domains) {
            DomainStatDto s = statForDomain(dom.getCode());
            stats.add(s);
            if (Boolean.TRUE.equals(s.getExtracted())) {
                extractedDomains++;
                totalObjects += nz(s.getObjectCount());
                totalRelations += nz(s.getRelationCount());
            }
        }
        OverallStatsDto result = new OverallStatsDto();
        result.setTotalDomains(domains.size());
        result.setExtractedDomains(extractedDomains);
        result.setTotalObjects(totalObjects);
        result.setTotalRelations(totalRelations);
        result.setDomains(stats);
        return result;
    }

    public List<DomainStatDto> listDomainStats() {
        return domainService.listDomains().stream()
                .map(d -> statForDomain(d.getCode()))
                .toList();
    }

    private DomainStatDto statForDomain(String domain) {
        DomainStatDto s = new DomainStatDto();
        s.setDomain(domain);
        Optional<JsonNode> root = extractionJsonReader.read(domain);
        if (root.isEmpty()) {
            s.setExtracted(false);
            s.setObjectCount(0);
            s.setRelationCount(0);
            s.setConceptCount(0);
            s.setLogicalCount(0);
            s.setPhysicalCount(0);
            s.setAvgStrength(0d);
            return s;
        }
        s.setExtracted(true);
        JsonNode stats = root.get().path("stats");
        s.setObjectCount(stats.path("total_objects").asInt(0));
        s.setRelationCount(stats.path("total_relations").asInt(0));
        int concept = 0;
        int logical = 0;
        int physical = 0;
        for (JsonNode n : stats) {
            if (n.isObject() && n.has("concept")) {
                concept  += n.path("concept").asInt(0);
                logical  += n.path("logical").asInt(0);
                physical += n.path("physical").asInt(0);
            }
        }
        s.setConceptCount(concept);
        s.setLogicalCount(logical);
        s.setPhysicalCount(physical);
        s.setAvgStrength(avgStrength(root.get()));
        return s;
    }

    private double avgStrength(JsonNode root) {
        double sum = 0;
        int n = 0;
        for (JsonNode r : root.path("relations")) {
            if (r.hasNonNull("relation_strength")) {
                sum += r.get("relation_strength").asDouble();
                n++;
            }
        }
        return n == 0 ? 0 : Math.round(sum / n * 10000d) / 10000d;
    }

    private int nz(Integer v) {
        return v == null ? 0 : v;
    }
}
