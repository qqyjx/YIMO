# 在远程 SSH 服务器上使用 Claude Code

本文档介绍如何通过 SSH 在远程服务器上安装和使用 Claude Code CLI 工具。

## 目录

- [方案概览](#方案概览)
- [方案一：直接在远程服务器运行](#方案一直接在远程服务器运行)
- [方案二：VS Code Remote SSH](#方案二vs-code-remote-ssh)
- [方案三：终端复用器持久会话](#方案三终端复用器持久会话)
- [身份验证技巧](#身份验证技巧)
- [常见问题](#常见问题)

---

## 方案概览

| 方案 | 适用场景 | 优点 | 缺点 |
|------|----------|------|------|
| 直接 SSH | 纯命令行操作 | 简单直接 | 断开连接会中断 |
| VS Code Remote | 需要 IDE 功能 | 图形化界面、插件支持 | 需要安装 VS Code |
| tmux/screen | 长时间任务 | 会话持久化 | 需要学习复用器命令 |

---

## 方案一：直接在远程服务器运行

### 1.1 连接到远程服务器

```bash
# 基本 SSH 连接
ssh username@your-server.com

# 使用密钥认证
ssh -i ~/.ssh/your_key username@your-server.com

# 通过跳板机连接
ssh -J jump_user@jump_host username@target_host
```

### 1.2 在服务器上安装 Node.js

**Ubuntu/Debian:**

```bash
# 使用 NodeSource 仓库
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install nodejs -y

# 验证
node --version  # v20.x.x
npm --version   # 10.x.x
```

**CentOS/RHEL:**

```bash
curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
sudo yum install nodejs -y
```

**使用 nvm（推荐，无需 sudo）:**

```bash
# 安装 nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc

# 安装 Node.js
nvm install 20
nvm use 20
```

### 1.3 配置 npm 全局目录（避免权限问题）

```bash
# 创建用户级全局目录
mkdir -p ~/.npm-global

# 配置 npm
npm config set prefix ~/.npm-global

# 添加到 PATH
echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
```

### 1.4 安装 Claude Code

```bash
# 安装（不要使用 sudo）
npm install -g @anthropic-ai/claude-code

# 验证
claude --version
```

### 1.5 身份验证

由于远程服务器通常没有浏览器，需要使用以下方法进行身份验证：

**方法 A：本地端口转发（推荐）**

```bash
# 在本地终端执行（新开一个终端窗口）
ssh -L 8080:localhost:8080 username@your-server.com

# 在远程服务器上启动 claude
claude

# 当出现认证 URL 时，将 URL 中的主机名替换为 localhost
# 例如：http://127.0.0.1:8080/... 可以在本地浏览器打开
```

**方法 B：复制 URL 到本地浏览器**

```bash
# 在远程服务器启动 claude
claude

# 复制显示的认证 URL
# 在本地浏览器打开
# 完成认证后，复制认证代码粘贴回终端
```

**方法 C：使用 API Key（最简单）**

```bash
# 设置环境变量
export ANTHROPIC_API_KEY="your-api-key-here"

# 或添加到 .bashrc 持久化
echo 'export ANTHROPIC_API_KEY="your-api-key"' >> ~/.bashrc
source ~/.bashrc

# 启动 claude（会自动使用 API Key）
claude
```

---

## 方案二：VS Code Remote SSH

此方案使用 VS Code 的 Remote - SSH 扩展，提供完整的 IDE 体验。

### 2.1 本地配置

1. 安装 [VS Code](https://code.visualstudio.com/)
2. 安装扩展：**Remote - SSH**（`ms-vscode-remote.remote-ssh`）
3. 安装扩展：**Claude Code**（如果有官方扩展）

### 2.2 配置 SSH 连接

在本地 `~/.ssh/config` 添加：

```
Host my-remote-server
    HostName your-server.com
    User username
    IdentityFile ~/.ssh/your_key
    ForwardAgent yes
    # 可选：通过跳板机
    # ProxyJump jump_user@jump_host
```

### 2.3 连接远程服务器

1. 按 `F1` 或 `Ctrl+Shift+P`
2. 输入 `Remote-SSH: Connect to Host`
3. 选择 `my-remote-server`
4. 等待 VS Code Server 安装完成

### 2.4 在远程安装 Claude Code

在 VS Code 集成终端中：

```bash
# 确保 Node.js 已安装
node --version

# 配置 npm（如果未配置）
mkdir -p ~/.npm-global
npm config set prefix ~/.npm-global
echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc
source ~/.bashrc

# 安装 Claude Code
npm install -g @anthropic-ai/claude-code
```

### 2.5 使用 Claude Code

在 VS Code 集成终端中直接运行：

```bash
cd /path/to/your/project
claude
```

VS Code Remote 会自动处理端口转发，身份验证链接可直接在本地浏览器打开。

---

## 方案三：终端复用器持久会话

使用 tmux 或 screen 可以保持 Claude Code 会话，即使 SSH 断开也不会丢失。

### 3.1 安装 tmux

```bash
# Ubuntu/Debian
sudo apt install tmux -y

# CentOS/RHEL
sudo yum install tmux -y
```

### 3.2 基本使用

```bash
# 创建新会话
tmux new -s claude-session

# 在 tmux 中启动 claude
claude

# 分离会话（保持后台运行）
# 按 Ctrl+b 然后按 d

# 重新连接会话
tmux attach -t claude-session

# 列出所有会话
tmux ls

# 关闭会话
tmux kill-session -t claude-session
```

### 3.3 推荐的 tmux 配置

创建 `~/.tmux.conf`：

```bash
# 使用更友好的前缀键
set -g prefix C-a
unbind C-b
bind C-a send-prefix

# 启用鼠标支持
set -g mouse on

# 增加历史记录
set -g history-limit 50000

# 更好的颜色支持
set -g default-terminal "screen-256color"
```

---

## 身份验证技巧

### 使用 API Key 认证

最简单的方式是使用 Anthropic API Key：

1. 访问 [Anthropic Console](https://console.anthropic.com/)
2. 创建 API Key
3. 在服务器上设置环境变量：

```bash
# 临时设置
export ANTHROPIC_API_KEY="sk-ant-api..."

# 永久设置（添加到 shell 配置）
echo 'export ANTHROPIC_API_KEY="sk-ant-api..."' >> ~/.bashrc
source ~/.bashrc
```

### 使用 OAuth 认证（需要浏览器）

如果必须使用 OAuth：

```bash
# 在本地开启端口转发
ssh -L 9999:localhost:9999 username@remote-server

# 在远程运行 claude，当提示 URL 时
# 将 URL 复制到本地浏览器完成认证
```

### 检查认证状态

```bash
# 查看当前认证状态
claude auth status

# 重新登录
claude auth login

# 重置认证
claude auth reset
```

---

## 常见问题

### Q: SSH 连接断开后 Claude Code 会话丢失？

使用 tmux 或 screen：

```bash
# 启动 tmux 会话
tmux new -s claude

# 在其中运行 claude
claude

# 断开时按 Ctrl+b, d
# 重连时：tmux attach -t claude
```

### Q: 无法在服务器上打开浏览器进行认证？

使用 API Key 方式：

```bash
export ANTHROPIC_API_KEY="your-key"
claude
```

或使用端口转发：

```bash
# 本地执行
ssh -L 8080:localhost:8080 user@server
```

### Q: npm 安装权限错误？

配置用户级全局目录：

```bash
mkdir -p ~/.npm-global
npm config set prefix ~/.npm-global
echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc
source ~/.bashrc

# 然后重新安装
npm install -g @anthropic-ai/claude-code
```

### Q: Node.js 版本过低？

使用 nvm 管理 Node.js 版本：

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
nvm install 20
nvm use 20
```

### Q: 连接速度慢或超时？

1. 检查网络连接
2. 使用 SSH 连接保活：

在 `~/.ssh/config` 添加：

```
Host *
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

### Q: 如何在多个项目间切换？

```bash
# 使用 tmux 窗口
tmux new-window -n project2
cd /path/to/project2
claude

# 切换窗口：Ctrl+b, n（下一个）或 Ctrl+b, p（上一个）
```

---

## 快速参考

### SSH 常用命令

```bash
# 基本连接
ssh user@host

# 带端口转发
ssh -L local_port:localhost:remote_port user@host

# 后台运行端口转发
ssh -fNL 8080:localhost:8080 user@host

# 通过跳板机
ssh -J jump_host user@target
```

### tmux 常用快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+b d` | 分离会话 |
| `Ctrl+b c` | 新建窗口 |
| `Ctrl+b n` | 下一窗口 |
| `Ctrl+b p` | 上一窗口 |
| `Ctrl+b %` | 垂直分屏 |
| `Ctrl+b "` | 水平分屏 |

### Claude Code 常用命令

```bash
# 启动
claude

# 查看版本
claude --version

# 检查状态
claude doctor

# 认证相关
claude auth status
claude auth login
claude auth reset
```

---

## 参考链接

- [Claude Code 官方文档](https://docs.anthropic.com/en/docs/claude-code)
- [VS Code Remote SSH](https://code.visualstudio.com/docs/remote/ssh)
- [tmux 官方文档](https://github.com/tmux/tmux/wiki)
- [Anthropic Console](https://console.anthropic.com/)
