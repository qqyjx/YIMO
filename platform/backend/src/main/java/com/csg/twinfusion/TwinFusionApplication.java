package com.csg.twinfusion;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * 支撑孪生体新范式多维数据融合分析框架原型系统 - 部署版后端入口
 *
 * 与本地演示版 (../../webapp) 独立运行, 面向南方电网正式部署.
 * 技术栈: Java 17 + Spring Boot 3 + MyBatis-Plus + 达梦 DM8.
 */
@SpringBootApplication
@MapperScan("com.csg.twinfusion.mapper")
public class TwinFusionApplication {

    public static void main(String[] args) {
        SpringApplication.run(TwinFusionApplication.class, args);
    }
}
