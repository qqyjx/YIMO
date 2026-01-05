-- 以 root 身份在系统 MySQL 或用户态 mysqld 中执行本脚本以创建数据库与账号
-- 数据库
CREATE DATABASE IF NOT EXISTS `eav_db` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 创建应用用户（仅本地）
CREATE USER IF NOT EXISTS 'eav_user'@'localhost' IDENTIFIED BY 'eav_pass_123!';
GRANT ALL PRIVILEGES ON `eav_db`.* TO 'eav_user'@'localhost';

-- 为 TCP 访问(127.0.0.1) 同步创建与授权（Navicat/脚本默认用 127.0.0.1 走 TCP）
CREATE USER IF NOT EXISTS 'eav_user'@'127.0.0.1' IDENTIFIED BY 'eav_pass_123!';
GRANT ALL PRIVILEGES ON `eav_db`.* TO 'eav_user'@'127.0.0.1';
FLUSH PRIVILEGES;
