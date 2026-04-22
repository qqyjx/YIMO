package com.csg.twinfusion.service.extraction;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.MissingNode;
import jakarta.annotation.PostConstruct;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.File;
import java.io.IOException;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 读取 webapp 侧 outputs/extraction_<domain>.json.
 *
 * 说明:
 *  - JSON 本身是 webapp 算法 (object_extractor.py) 产物, platform Phase 1
 *    直接复用, 减少重复计算;
 *  - 同步到达梦后, 本类下线, 换成 MyBatis mapper.
 *
 * 域编码映射:
 *  - webapp 当前输出文件名用拼音 (shupeidian/jicai);
 *  - platform 对外用中文 (DATA/ 子目录名);
 *  - 两者用下表桥接, 新增域后在此登记即可;
 *  - 或等 object_extractor.py 改为直接按中文域名输出 JSON 后, 去掉本映射.
 */
@Slf4j
@Component
public class ExtractionJsonReader {

    private final ObjectMapper mapper = new ObjectMapper();
    private final Map<String, JsonNode> cache = new ConcurrentHashMap<>();

    @Value("${twinfusion.outputs-dir:../outputs}")
    private String outputsDir;

    private static final Map<String, String> DOMAIN_TO_LEGACY_CODE = Map.of(
            "输配电", "shupeidian",
            "计划财务", "jicai"
    );

    @PostConstruct
    void init() {
        File dir = new File(outputsDir);
        log.info("extraction outputs dir: {} (exists={})",
                dir.getAbsolutePath(), dir.isDirectory());
    }

    /**
     * 取指定域的抽取 JSON. 若文件不存在返回 Optional.empty().
     */
    public Optional<JsonNode> read(String domain) {
        if (domain == null || domain.isBlank()) {
            return Optional.empty();
        }
        return Optional.ofNullable(cache.computeIfAbsent(domain, this::loadFromDisk));
    }

    private JsonNode loadFromDisk(String domain) {
        File f = locateFile(domain);
        if (f == null) {
            return null;
        }
        try {
            log.info("load extraction json: {}", f.getAbsolutePath());
            return mapper.readTree(f);
        } catch (IOException e) {
            log.warn("failed to parse {}: {}", f.getAbsolutePath(), e.getMessage());
            return null;
        }
    }

    private File locateFile(String domain) {
        // 优先中文命名文件, 兜底拼音文件 (兼容 webapp 当前输出)
        File direct = new File(outputsDir, "extraction_" + domain + ".json");
        if (direct.isFile()) {
            return direct;
        }
        String legacy = DOMAIN_TO_LEGACY_CODE.get(domain);
        if (legacy != null) {
            File alt = new File(outputsDir, "extraction_" + legacy + ".json");
            if (alt.isFile()) {
                return alt;
            }
        }
        return null;
    }

    /** 便捷方法: 不关心是否存在, 直接拿节点, 缺失返回 MissingNode. */
    public JsonNode readOrMissing(String domain) {
        return read(domain).orElse(MissingNode.getInstance());
    }

    /** 清缓存 (算法重跑后前端立即看到新结果). */
    public void invalidate(String domain) {
        cache.remove(domain);
    }
}
