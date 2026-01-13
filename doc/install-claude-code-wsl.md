# WSL 中安装 Claude Code 指南

本文档介绍如何在 Windows Subsystem for Linux (WSL) 中安装和配置 Claude Code CLI 工具。

## 系统要求

### Windows 要求
- Windows 10 (版本 2004 或更高) 或 Windows 11
- 在 BIOS/UEFI 中启用虚拟化支持

### 软件要求
- WSL 2 (推荐) 或 WSL 1
- Node.js 18.0 或更高版本
- npm (随 Node.js 附带)

---

## 安装步骤

### 第一步：安装 WSL 2

在 Windows PowerShell (以管理员身份运行) 中执行：

```bash
wsl --install
```

此命令会自动：
- 启用虚拟机平台和 WSL 功能
- 下载并安装 WSL2 内核
- 安装 Ubuntu 作为默认发行版

完成后**重启计算机**。

### 第二步：准备 WSL 环境

启动 WSL Ubuntu 终端，执行：

```bash
# 更新包管理器
sudo apt update && sudo apt upgrade -y

# 移除旧版本 Node.js（如果有）
sudo apt remove nodejs npm -y
```

### 第三步：安装 Node.js 20.x

```bash
# 使用 NodeSource 仓库安装
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install nodejs -y

# 验证安装
node --version   # 应显示 v20.x.x
npm --version    # 应显示 10.x.x
```

### 第四步：配置 npm 全局目录

**重要**：此步骤避免权限问题！

```bash
# 创建全局目录
mkdir -p ~/.npm-global

# 配置 npm
npm config set prefix ~/.npm-global

# 添加到 PATH
echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
```

### 第五步：安装 Claude Code

```bash
# 安装（不要使用 sudo！）
npm install -g @anthropic-ai/claude-code

# 验证安装
claude --version
```

### 第六步：身份验证

```bash
# 启动 Claude Code
claude
```

首次运行时：
1. 选择 "Anthropic Console account"
2. 在浏览器中打开显示的链接并登录
3. 复制身份验证代码
4. 粘贴回终端

---

## 验证安装

```bash
# 检查配置状态
claude doctor

# 查看身份验证状态
claude auth status

# 在项目目录中启动
cd /path/to/your/project
claude
```

---

## 常见问题

### Q: 遇到 npm 权限错误？

```bash
# 检查 npm 配置
npm config get prefix

# 确保权限正确
chmod -R u+w ~/.npm-global
```

### Q: 需要重置身份验证？

在 Claude Code 中运行：
```
/auth reset
/auth login
```

### Q: 项目性能较慢？

将项目文件放在 WSL 文件系统中（如 `/home/username/projects/`），而不是 Windows 路径（`/mnt/c/...`）。

---

## 参考链接

- [Claude Code 官方文档](https://code.claude.com/docs/en/setup)
- [WSL 官方文档](https://docs.microsoft.com/zh-cn/windows/wsl/)
