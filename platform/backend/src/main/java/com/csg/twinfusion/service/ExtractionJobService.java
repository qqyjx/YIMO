package com.csg.twinfusion.service;

import com.csg.twinfusion.dto.extraction.ExtractionJobDto;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 对象抽取任务管理.
 *
 * 实现策略 (algorithm-integration.md 方案 A):
 *   - 调 algo:9000/extract 提交异步任务, 算法侧 FastAPI 跑 object_extractor.py
 *   - 本地缓存 jobId → ExtractionJobDto, 提供查询入口
 *   - getStatus() 主动从 algo 同步状态 (algo 是真相源)
 *   - algo 不可达时降级为 in-memory 占位状态, 不让 backend 整体挂掉
 */
@Slf4j
@Service
public class ExtractionJobService {

    @Value("${algo.base-url:http://algo:9000}")
    private String algoBaseUrl;

    @Resource
    private RestTemplate restTemplate;

    private final ObjectMapper json = new ObjectMapper();
    private final Map<String, ExtractionJobDto> cache = new ConcurrentHashMap<>();

    public ExtractionJobDto submit(String dataDomain) {
        ExtractionJobDto job = new ExtractionJobDto();
        job.setDataDomain(dataDomain);
        job.setStatus("QUEUED");
        job.setProgress(0.0);
        job.setCreatedAt(LocalDateTime.now().toString());

        try {
            HttpHeaders h = new HttpHeaders();
            h.setContentType(MediaType.APPLICATION_JSON);
            Map<String, Object> body = Map.of(
                    "domain", dataDomain,
                    "use_llm", true
            );
            HttpEntity<Map<String, Object>> req = new HttpEntity<>(body, h);
            JsonNode resp = restTemplate.postForObject(algoBaseUrl + "/extract", req, JsonNode.class);
            if (resp != null && resp.hasNonNull("job_id")) {
                job.setJobId(resp.get("job_id").asText());
                job.setStatus(resp.path("status").asText("QUEUED"));
                cache.put(job.getJobId(), job);
                log.info("forwarded extract job to algo: jobId={}, domain={}", job.getJobId(), dataDomain);
                return job;
            }
            log.warn("algo /extract 返回异常: {}", resp);
        } catch (Exception e) {
            log.warn("algo:{} 不可达, 降级 in-memory: {}", algoBaseUrl, e.getMessage());
        }

        // 降级: 算法服务不可达时返回 stub jobId, 状态保持 QUEUED
        job.setJobId(UUID.randomUUID().toString().replace("-", "").substring(0, 12));
        job.setStatus("QUEUED_LOCAL");   // 业务侧据此判断是否真的提交到算法
        cache.put(job.getJobId(), job);
        return job;
    }

    public ExtractionJobDto get(String jobId) {
        ExtractionJobDto cached = cache.get(jobId);
        if (cached == null) return null;
        // 已是终态就不再去 algo 同步
        String s = cached.getStatus();
        if ("SUCCESS".equals(s) || "FAILED".equals(s)) {
            return cached;
        }
        // 主动拉一次最新状态
        try {
            JsonNode resp = restTemplate.getForObject(algoBaseUrl + "/jobs/" + jobId, JsonNode.class);
            if (resp != null && resp.hasNonNull("status")) {
                cached.setStatus(resp.path("status").asText());
                cached.setProgress(resp.path("progress").asDouble(0.0));
                if (resp.hasNonNull("object_count")) {
                    cached.setObjectCount(resp.get("object_count").asInt());
                }
                if (resp.hasNonNull("relation_count")) {
                    cached.setRelationCount(resp.get("relation_count").asInt());
                }
                if (resp.hasNonNull("error")) {
                    cached.setError(resp.get("error").asText());
                }
            }
        } catch (Exception e) {
            log.debug("拉取 algo 状态失败 (使用缓存): {}", e.getMessage());
        }
        return cached;
    }

    @Configuration
    static class RestTemplateConfig {
        @Bean
        RestTemplate restTemplate() {
            SimpleClientHttpRequestFactory f = new SimpleClientHttpRequestFactory();
            f.setConnectTimeout((int) Duration.ofSeconds(3).toMillis());
            f.setReadTimeout((int) Duration.ofSeconds(15).toMillis());
            return new RestTemplate(f);
        }
    }
}
