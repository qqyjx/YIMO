package com.csg.twinfusion.dto.object;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/**
 * 对象合并请求体.
 */
@Data
public class MergeRequestDto {
    @NotBlank
    private String sourceCode;
    @NotBlank
    private String targetCode;
    @NotBlank
    private String dataDomain;
    private String reason;
}
