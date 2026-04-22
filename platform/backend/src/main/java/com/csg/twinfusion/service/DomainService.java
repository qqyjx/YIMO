package com.csg.twinfusion.service;

import com.csg.twinfusion.dto.DomainDto;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.File;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

/**
 * 业务域查询服务.
 *
 * 当前实现从文件系统扫描; 待数据入库后改为走 TF_EAV_DATASET + 聚合.
 */
@Slf4j
@Service
public class DomainService {

    @Value("${twinfusion.data-dir:../DATA}")
    private String dataDir;

    public List<DomainDto> listDomains() {
        File root = new File(dataDir);
        if (!root.isDirectory()) {
            log.warn("data dir not found: {}", root.getAbsolutePath());
            return List.of();
        }
        File[] children = Objects.requireNonNullElse(root.listFiles(File::isDirectory), new File[0]);
        List<DomainDto> result = new ArrayList<>(children.length);
        for (File child : children) {
            String code = child.getName();
            if (code.startsWith("_")) {
                continue;
            }
            DomainDto dto = new DomainDto();
            dto.setCode(code);
            dto.setName(code);
            dto.setHasBusinessArchitecture(new File(child, "1.xlsx").isFile());
            dto.setHasDataArchitecture(new File(child, "2.xlsx").isFile());
            dto.setHasApplicationArchitecture(new File(child, "3.xlsx").isFile());
            result.add(dto);
        }
        result.sort(Comparator.comparing(DomainDto::getCode));
        return result;
    }
}
