package com.csg.twinfusion.service;

import com.csg.twinfusion.dto.object.CrossDomainDuplicateDto;
import com.csg.twinfusion.service.extraction.ExtractionJsonReader;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 跨域重复对象检测.
 * 与 webapp /api/olm/cross-domain-duplicates 语义对齐.
 */
@Service
public class CrossDomainService {

    @Resource
    private ExtractionJsonReader extractionJsonReader;

    @Resource
    private DomainService domainService;

    public List<CrossDomainDuplicateDto> listDuplicates() {
        Map<String, List<CrossDomainDuplicateDto.DomainOccurrence>> nameMap = new HashMap<>();

        for (var d : domainService.listDomains()) {
            extractionJsonReader.read(d.getCode()).ifPresent(root -> {
                for (JsonNode obj : root.path("objects")) {
                    String name = obj.path("object_name").asText("");
                    if (name.isEmpty()) continue;
                    var occ = new CrossDomainDuplicateDto.DomainOccurrence();
                    occ.setDataDomain(d.getCode());
                    occ.setObjectCode(obj.path("object_code").asText());
                    occ.setClusterSize(obj.path("cluster_size").asInt(0));
                    List<String> samples = new ArrayList<>();
                    obj.path("sample_entities").forEach(s -> samples.add(s.asText()));
                    occ.setSampleEntities(samples.subList(0, Math.min(5, samples.size())));
                    nameMap.computeIfAbsent(name, k -> new ArrayList<>()).add(occ);
                }
            });
        }

        List<CrossDomainDuplicateDto> dups = new ArrayList<>();
        for (var entry : nameMap.entrySet()) {
            var occList = entry.getValue();
            if (occList.size() < 2) continue;
            long distinctDomains = occList.stream()
                    .map(CrossDomainDuplicateDto.DomainOccurrence::getDataDomain)
                    .distinct().count();
            if (distinctDomains < 2) continue;
            CrossDomainDuplicateDto dto = new CrossDomainDuplicateDto();
            dto.setObjectName(entry.getKey());
            dto.setDomainCount((int) distinctDomains);
            dto.setOccurrences(occList);
            dups.add(dto);
        }
        dups.sort((a, b) -> Integer.compare(b.getDomainCount(), a.getDomainCount()));
        return dups;
    }
}
