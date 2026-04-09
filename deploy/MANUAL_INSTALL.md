# GDB MCP Server 安装部署指南

本文档提供 GDB MCP Server 的完整安装步骤。

> **v0.2.0 架构变更**：MCP Server 现在运行在**本地**，通过 SSH 连接远端 GDB。远端服务器只需要安装 GDB，不再需要部署 Python 环境或 MCP Server。

---

## 架构概览

```
┌─────────────────────┐                    ┌──────────────────────────────┐
│  MCP Client          │                    │    远程 Linux 服务器           │
│  (Claude Desktop /   │                    │                              │
│   CodeBuddy IDE)     │     stdio          │  只需要：                     │
│                      │ ◄──────────►       │  ✓ GDB 已安装                │
│                      │                    │  ✓ SSH 可访问                 │
│  ┌────────────────┐  │     SSH            │  ✗ 不需要 Python             │
│  │ MCP Server     │──│─────────────────►  │  ✗ 不需要 MCP Server         │
│  │ (本地 Python)   │  │                    │                              │
│  │ ├─ MI Parser   │  │                    │  ┌────────────────────────┐  │
│  │ └─ SSH Ctrl    │  │                    │  │  GDB --interpreter=mi  │  │
│  └────────────────┘  │                    │  │  ├── executable         │  │
│                      │                    │  │  ├── coredump          │  │
│                      │                    │  │  └── sysroot           │  │
└─────────────────────┘                    │  └────────────────────────┘  │
                                           └──────────────────────────────┘
```

---

## 第 1 步：本地安装 MCP Server

### 前置条件

- **本地机器**：Python 3.10+、SSH 客户端
- **远程服务器**：GDB 已安装、SSH 可访问

### 安装

```bash
# 克隆项目
git clone <repository-url> ~/gdb-mcp
cd ~/gdb-mcp

# 方式 A：使用 pipx（推荐）
pipx install .

# 方式 B：使用虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
pip install -e .
```

验证安装：
```bash
# pipx 方式
gdb-mcp-server  # Ctrl+C 退出

# venv 方式
python -m gdb_mcp  # Ctrl+C 退出
# 应输出: INFO:gdb_mcp.server:GDB MCP Server starting...
```

---

## 第 2 步：确保远程服务器有 GDB

```bash
# 在远程服务器上
ssh user@remote-server

# 检查 GDB
gdb --version

# 如果没有安装
sudo apt install -y gdb           # Ubuntu/Debian
sudo yum install -y gdb           # CentOS/RHEL
sudo dnf install -y gdb           # Fedora

# 跨架构调试（ARM coredump 等）
sudo apt install -y gdb-multiarch
```

**就这些！** 远端不需要安装 Python、不需要部署 MCP Server。

---

## 第 3 步：配置 SSH 免密登录

```bash
# 在本地机器上
ssh-keygen -t ed25519 -C "gdb-mcp"
ssh-copy-id user@remote-server

# 验证
ssh user@remote-server "echo OK && gdb --version"
```

（可选）配置 SSH 别名 `~/.ssh/config`：
```
Host gdb-remote
    HostName 远程服务器IP
    User 你的用户名
    Port 22
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 60
```

---

## 第 4 步：配置 MCP 客户端

### Claude Desktop

编辑配置文件：
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

**基础配置**（每次调用时传 SSH 参数）：
```json
{
  "mcpServers": {
    "gdb": {
      "command": "gdb-mcp-server"
    }
  }
}
```

**推荐配置**（预设 SSH 默认参数，调用时无需重复传递）：
```json
{
  "mcpServers": {
    "gdb": {
      "command": "gdb-mcp-server",
      "env": {
        "GDB_SSH_HOST": "远程服务器IP",
        "GDB_SSH_USER": "你的用户名",
        "GDB_SSH_PORT": "22",
        "GDB_SSH_KEY": "SSH私钥路径"
      }
    }
  }
}
```

配置 SSH 环境变量后，AI 只需提供 `program`/`core` 路径即可自动走 SSH 远程调试，无需每次传递 SSH 参数。

### CodeBuddy IDE

在 MCP 设置中添加相同配置。

---

## 第 5 步：开始远程调试

在 MCP 客户端中向 AI 发送：

```
请调试远程服务器 devbox 上的 /home/dev/myapp，在 main 处设断点并运行。
```

AI 将自动使用 SSH 参数调用 `gdb_start_session`：
```json
{
  "program": "/home/dev/myapp",
  "ssh_host": "devbox",
  "ssh_user": "dev"
}
```

### 远程 Coredump 分析

```
分析远程服务器 10.0.0.5 上的 coredump：
- 可执行文件：/data/debug/my_server
- Core 文件：/data/debug/core.12345
- Sysroot：/data/debug/sysroot
```

AI 将使用：
```json
{
  "program": "/data/debug/my_server",
  "core": "/data/debug/core.12345",
  "ssh_host": "10.0.0.5",
  "ssh_user": "root",
  "init_commands": [
    "set sysroot /data/debug/sysroot"
  ]
}
```

---

## 本地模式（无 SSH）

不提供 SSH 参数时，MCP Server 直接启动本地 GDB，行为与之前完全一致：

```json
{
  "program": "/path/to/local/app"
}
```

---

## SSH 连接参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `ssh_host` | SSH 主机（IP 或 SSH config 别名） | 无（不传则走本地模式） |
| `ssh_user` | SSH 用户名 | 使用 SSH config 默认值 |
| `ssh_port` | SSH 端口 | 22 |
| `ssh_key` | SSH 私钥文件路径 | 使用 SSH agent 或默认密钥 |
| `ssh_options` | 额外 SSH 选项列表 | 无 |

`ssh_options` 示例：
```json
{
  "ssh_options": ["-o", "ProxyJump=bastion", "-o", "ConnectTimeout=10"]
}
```

---

## 常见问题

### Q: SSH 连接超时
```bash
ssh -vvv user@remote-server  # 详细调试
ssh-add -l                    # 确认 key 已加载
```

### Q: 远端 GDB 版本太旧
使用 `gdb_path` 参数指定远端的 GDB 路径：
```json
{
  "ssh_host": "server",
  "gdb_path": "/opt/gdb-13/bin/gdb"
}
```

### Q: 跨架构调试 ARM coredump
在远端安装 `gdb-multiarch`，然后：
```json
{
  "ssh_host": "server",
  "gdb_path": "/usr/bin/gdb-multiarch"
}
```

### Q: 需要通过跳板机连接
使用 `ssh_options` 或配置 SSH config 中的 `ProxyJump`：
```json
{
  "ssh_host": "target-server",
  "ssh_options": ["-o", "ProxyJump=bastion-host"]
}
```
