package com.csg.twinfusion.service;

import com.csg.twinfusion.dto.object.ExtractedObjectDto;
import com.csg.twinfusion.dto.object.ObjectRelationGroupDto;
import com.csg.twinfusion.dto.object.RelationDto;
import com.csg.twinfusion.service.extraction.ExtractionJsonReader;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Optional;

/**
 * 对象查询服务.
 *
 * Phase 1 从 outputs/extraction_*.json 读取 (与 webapp 共享);
 * Phase 2 迁至 DM 数据库 (TF_OM_EXTRACTED_OBJECT + TF_OM_ENTITY_RELATION).
 */
@Slf4j
@Service
public class ObjectService {

    @Resource
    private ExtractionJsonReader extractionJsonReader;

    private final ObjectMapper mapper = new ObjectMapper();

    public List<ExtractedObjectDto> listObjects(String domain) {
        Optional<JsonNode> root = extractionJsonReader.read(domain);
        if (root.isEmpty()) {
            return List.of();
        }
        JsonNode objects = root.get().path("objects");
        JsonNode stats = root.get().path("stats");
        List<ExtractedObjectDto> result = new ArrayList<>();
        for (JsonNode n : objects) {
            ExtractedObjectDto dto = toObjectDto(n, domain);
            fillRelationCounts(dto, stats);
            result.add(dto);
        }
        return result;
    }

    public ObjectRelationGroupDto getRelations(String objectCode, String domain) {
        ObjectRelationGroupDto group = new ObjectRelationGroupDto();
        group.setObjectCode(objectCode);
        group.setConcept(new ArrayList<>());
        group.setLogical(new ArrayList<>());
        group.setPhysical(new ArrayList<>());

        Optional<JsonNode> root = extractionJsonReader.read(domain);
        if (root.isEmpty()) {
            return group;
        }

        for (JsonNode n : root.get().path("objects")) {
            if (objectCode.equals(n.path("object_code").asText())) {
                group.setObjectName(n.path("object_name").asText());
                break;
            }
        }

        Iterator<JsonNode> it = root.get().path("relations").elements();
        while (it.hasNext()) {
            JsonNode r = it.next();
            if (!objectCode.equals(r.path("object_code").asText())) {
                continue;
            }
            RelationDto rel = toRelationDto(r);
            switch (rel.getEntityLayer()) {
                case "CONCEPT"  -> group.getConcept().add(rel);
                case "LOGICAL"  -> group.getLogical().add(rel);
                case "PHYSICAL" -> group.getPhysical().add(rel);
                default -> log.debug("unknown layer {}", rel.getEntityLayer());
            }
        }
        return group;
    }

    private ExtractedObjectDto toObjectDto(JsonNode n, String domain) {
        ExtractedObjectDto dto = new ExtractedObjectDto();
        dto.setObjectCode(n.path("object_code").asText());
        dto.setObjectName(n.path("object_name").asText());
        dto.setObjectType(n.path("object_type").asText("CORE"));
        dto.setDescription(n.path("description").asText(null));
        dto.setDataDomain(domain);
        if (n.hasNonNull("extraction_confidence")) {
            dto.setExtractionConfidence(n.get("extraction_confidence").asDouble());
        }
        dto.setClusterSize(n.path("cluster_size").asInt(0));
        dto.setSynonyms(jsonArrayToStringList(n.path("synonyms")));
        dto.setSampleEntities(jsonArrayToStringList(n.path("sample_entities")));
        return dto;
    }

    private void fillRelationCounts(ExtractedObjectDto dto, JsonNode stats) {
        JsonNode statsForObject = stats.path(dto.getObjectCode());
        if (statsForObject.isMissingNode()) {
            return;
        }
        dto.setTotalRelations(statsForObject.path("total").asInt(0));
        dto.setConceptCount(statsForObject.path("concept").asInt(0));
        dto.setLogicalCount(statsForObject.path("logical").asInt(0));
        dto.setPhysicalCount(statsForObject.path("physical").asInt(0));
    }

    private RelationDto toRelationDto(JsonNode r) {
        RelationDto dto = new RelationDto();
        dto.setObjectCode(r.path("object_code").asText());
        dto.setEntityLayer(r.path("entity_layer").asText());
        dto.setEntityName(r.path("entity_name").asText());
        dto.setEntityCode(r.path("entity_code").asText(null));
        dto.setRelationType(r.path("relation_type").asText("DIRECT"));
        if (r.hasNonNull("relation_strength")) {
            dto.setRelationStrength(r.get("relation_strength").asDouble());
        }
        dto.setMatchMethod(r.path("match_method").asText(null));
        dto.setDataDomain(r.path("data_domain").asText(null));
        dto.setSourceFile(r.path("source_file").asText(null));
        dto.setSourceSheet(r.path("source_sheet").asText(null));
        dto.setViaConceptEntity(r.path("via_concept_entity").asText(null));
        return dto;
    }

    private List<String> jsonArrayToStringList(JsonNode arr) {
        if (arr == null || !arr.isArray()) {
            return List.of();
        }
        List<String> out = new ArrayList<>(arr.size());
        for (JsonNode n : arr) {
            out.add(n.asText());
        }
        return out;
    }
}
