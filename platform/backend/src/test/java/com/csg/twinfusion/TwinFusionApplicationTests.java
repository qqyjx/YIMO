package com.csg.twinfusion;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

/**
 * 冒烟测试: 确保 Spring 容器能启动.
 * 使用 local profile, 不连接真实数据库 (datasource 读 application-local.yml).
 */
@SpringBootTest
@ActiveProfiles("local")
class TwinFusionApplicationTests {

    @Test
    void contextLoads() {
        // Spring 上下文加载成功即视为通过
    }
}
