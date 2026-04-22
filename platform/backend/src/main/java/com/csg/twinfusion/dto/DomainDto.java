package com.csg.twinfusion.dto;

import lombok.Data;

/**
 * 业务域 DTO.
 *
 *  - code: 目录名 (中文,与 DATA/{域}/ 对齐)
 *  - name: 展示名称 (目前同 code)
 *  - hasBusinessArchitecture / Data / Application: 三份架构文件是否齐全
 */
@Data
public class DomainDto {

    private String code;
    private String name;
    private boolean hasBusinessArchitecture;
    private boolean hasDataArchitecture;
    private boolean hasApplicationArchitecture;
}
