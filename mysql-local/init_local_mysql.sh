#!/usr/bin/env bash
set -euo pipefail
CONF_DIR="/data1/xyf/smartgrid/mysql-local"
DATA_DIR="$CONF_DIR/dbdata"
SOCK="$CONF_DIR/mysql.sock"
PORT=3307

# 初始化数据目录（仅首次）
if [ ! -d "$DATA_DIR/mysql" ]; then
  echo "[INIT] 初始化数据目录到 $DATA_DIR"
  mysqld --no-defaults --initialize-insecure --datadir="$DATA_DIR"
fi

# 启动mysqld（前台）
exec mysqld --defaults-file="$CONF_DIR/my.cnf" --user=$(whoami)
