package com.csg.twinfusion.common;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.Data;

/**
 * 统一响应体.
 *
 * 字段:
 *  - code: 业务码 (0=成功,其他=失败,与 HTTP 状态解耦)
 *  - message: 提示信息
 *  - data: 业务数据 (失败时通常为 null,为减少 payload 体积使用 NON_NULL 序列化)
 */
@Data
@JsonInclude(JsonInclude.Include.NON_NULL)
public class Result<T> {

    private Integer code;
    private String message;
    private T data;

    public static <T> Result<T> ok(T data) {
        Result<T> r = new Result<>();
        r.setCode(0);
        r.setMessage("OK");
        r.setData(data);
        return r;
    }

    public static <T> Result<T> ok() {
        return ok(null);
    }

    public static <T> Result<T> fail(Integer code, String message) {
        Result<T> r = new Result<>();
        r.setCode(code);
        r.setMessage(message);
        return r;
    }
}
