# GDB MCP 远程 Coredump 调试部署方案

## 概述

本方案提供一套完整的远程 coredump 调试环境部署方案。通过在远程 Linux 服务器上部署 GDB MCP Server，本地 MCP 客户端经 SSH 直连远程服务器启动 MCP 进程，AI 助手可以直接远程分析 coredump 文件，无需将 coredump 和符号文件传输到本地。

### 架构图

```
┌─────────────────────┐           SSH            ┌──────────────────────────────┐
│  本地 MCP Client     │  ◄──── stdio over SSH ──► │    远程 Linux 服务器           │
│  (Claude Desktop /   │                          │                              │
│   CodeBuddy IDE)     │     ssh user@host        │  ┌────────────────────────┐  │
│                      │     python -m gdb_mcp    │  │  Python venv           │  │
│                      │                          │  │  ├── gdb-mcp-server    │  │
│                      │                          │  │  └── dependencies      │  │
│                      │                          │  └──────────┬─────────────┘  │
│                      │                          │             │                │
│                      │                          │  ┌──────────▼─────────────┐  │
│                      │                          │  │  GDB                   │  │
│                      │                          │  │  ├── executable         │  │
│                      │                          │  │  ├── coredump          │  │
│                      │                          │  │  ├── sysroot           │  │
│                      │                          │  │  └── shared libs       │  │
│                      │                          │  └────────────────────────┘  │
└─────────────────────┘                          └──────────────────────────────┘
```

### 工作原理

MCP 客户端通过 SSH 在远程服务器上直接启动 `gdb-mcp-server` 进程，stdin/stdout 通过 SSH 隧道透传，实现与本地启动完全一致的 stdio 通信。无需额外开放端口、无需守护进程。

---

## 前置条件

### 远程服务器要求

- Linux 操作系统（推荐 Ubuntu 20.04+ / CentOS 7+）
- Python 3.10+
- GDB（需与目标程序架构匹配）
- SSH 服务（sshd）运行中

### 本地客户端要求

- SSH 客户端（OpenSSH）
- 已配置 SSH 免密登录到远程服务器
- MCP 客户端（Claude Desktop / CodeBuddy IDE / Cline 等）

---

## 快速开始

### 一键部署（推荐）

将本项目代码传输到远程服务器后执行：

```bash
# 在远程服务器上
cd /path/to/gdb-mcp
chmod +x deploy/setup_remote.sh
./deploy/setup_remote.sh
```

脚本会自动完成：
1. 检查系统依赖（Python、GDB）
2. 创建 Python 虚拟环境
3. 安装 gdb-mcp-server 及其依赖
4. 创建调试工作目录
5. 生成 MCP 客户端配置模板
6. 验证安装

---

## 详细部署步骤

### 第 1 步：准备远程服务器

```bash
# 安装系统依赖
# Ubuntu/Debian
sudo apt update && sudo apt install -y python3 python3-venv python3-pip gdb

# CentOS/RHEL
sudo yum install -y python3 python3-pip gdb
# 或
sudo dnf install -y python3 python3-pip gdb

# 验证版本
python3 --version   # 需要 >= 3.10
gdb --version
```

### 第 2 步：部署 GDB MCP Server

```bash
# 克隆项目到远程服务器
git clone <repository-url> /opt/gdb-mcp
cd /opt/gdb-mcp

# 创建 Python 虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装 gdb-mcp-server
pip install -e .

# 验证安装
python -m gdb_mcp  # 应输出 "GDB MCP Server starting..."，Ctrl+C 退出
```

### 第 3 步：准备调试文件

在远程服务器上，组织好调试所需文件：

```bash
# 创建工作目录
mkdir -p /data/debug/{coredumps,executables,sysroot}

# 示例目录结构
/data/debug/
├── coredumps/
│   ├── core.12345           # coredump 文件
│   └── core.67890
├── executables/
│   ├── my_program           # 带调试符号的可执行文件
│   └── my_program.debug     # 单独的调试符号文件
└── sysroot/
    ├── lib/                 # 匹配的系统库
    ├── lib64/
    └── usr/lib/
```

### 第 4 步：配置 SSH 免密登录

```bash
# 在本地机器上生成 SSH 密钥（如果没有）
ssh-keygen -t ed25519 -C "gdb-mcp-remote"

# 将公钥复制到远程服务器
ssh-copy-id user@remote-server

# 验证免密登录
ssh user@remote-server "echo OK"
```

### 第 5 步：优化 SSH 连接

在本地 `~/.ssh/config` 中添加（可选但推荐）：

```
Host gdb-remote
    HostName remote-server-ip
    User your-username
    Port 22
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 60
    ServerAliveCountMax 3
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ControlPersist 600
```

> `ControlMaster` / `ControlPersist` 可复用 SSH 连接，避免每次启动 MCP 都重新握手，大幅降低延迟。

### 第 6 步：配置 MCP 客户端

#### Claude Desktop

编辑配置文件：
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

**基础配置**（直接指定 SSH 参数）：

```json
{
  "mcpServers": {
    "gdb-remote": {
      "command": "ssh",
      "args": [
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "user@remote-server",
        "/opt/gdb-mcp/venv/bin/python", "-m", "gdb_mcp"
      ]
    }
  }
}
```

**简化配置**（使用 SSH config 别名）：

```json
{
  "mcpServers": {
    "gdb-remote": {
      "command": "ssh",
      "args": [
        "gdb-remote",
        "/opt/gdb-mcp/venv/bin/python", "-m", "gdb_mcp"
      ]
    }
  }
}
```

**带环境变量**（指定 GDB 路径或日志级别）：

```json
{
  "mcpServers": {
    "gdb-remote": {
      "command": "ssh",
      "args": [
        "gdb-remote",
        "GDB_PATH=/usr/bin/gdb-multiarch",
        "GDB_MCP_LOG_LEVEL=DEBUG",
        "/opt/gdb-mcp/venv/bin/python", "-m", "gdb_mcp"
      ]
    }
  }
}
```

#### CodeBuddy IDE

在 CodeBuddy 的 MCP 设置中添加相同配置即可。

#### 多远程服务器

如果有多台调试服务器，可分别配置：

```json
{
  "mcpServers": {
    "gdb-server-a": {
      "command": "ssh",
      "args": ["gdb-server-a", "/opt/gdb-mcp/venv/bin/python", "-m", "gdb_mcp"]
    },
    "gdb-server-b": {
      "command": "ssh",
      "args": ["gdb-server-b", "/opt/gdb-mcp/venv/bin/python", "-m", "gdb_mcp"]
    }
  }
}
```

### 第 7 步：验证连接

```bash
# 手动测试：SSH 直接运行 MCP server（应看到 "GDB MCP Server starting..."）
ssh user@remote-server "/opt/gdb-mcp/venv/bin/python -m gdb_mcp"
# Ctrl+C 退出

# 在 MCP 客户端中测试：发送消息
# "你有访问 GDB 调试工具吗？"
# AI 应确认有 gdb_* 系列工具可用
```

---

## Coredump 调试使用指南

### 场景 1：基本 Coredump 分析

向 AI 发送如下提示：

```
请加载远程服务器上的 coredump 进行分析：
- 可执行文件：/data/debug/executables/my_program
- Core 文件：/data/debug/coredumps/core.12345

请告诉我：
1. 程序崩溃时有多少个线程？
2. 每个线程在做什么？
3. 崩溃的根本原因是什么？
```

AI 将自动调用 `gdb_start_session`：
```json
{
  "program": "/data/debug/executables/my_program",
  "core": "/data/debug/coredumps/core.12345"
}
```

### 场景 2：带 Sysroot 的 Coredump 分析

当 coredump 来自不同环境（如容器、嵌入式设备）时：

```
分析 coredump，使用自定义的 sysroot：
- 可执行文件：/data/debug/executables/my_server
- Core 文件：/data/debug/coredumps/core.99999
- Sysroot：/data/debug/sysroot
- 库路径：/data/debug/sysroot/usr/lib:/data/debug/sysroot/lib
```

AI 将使用：
```json
{
  "program": "/data/debug/executables/my_server",
  "core": "/data/debug/coredumps/core.99999",
  "init_commands": [
    "set sysroot /data/debug/sysroot",
    "set solib-search-path /data/debug/sysroot/usr/lib:/data/debug/sysroot/lib"
  ]
}
```

### 场景 3：批量 Coredump 分析

```
请依次分析以下 coredump，对比它们的崩溃原因：
1. /data/debug/coredumps/core.001
2. /data/debug/coredumps/core.002
3. /data/debug/coredumps/core.003
可执行文件都是 /data/debug/executables/my_server

对于每个 coredump，请告诉我崩溃的线程和调用栈，最后总结共同点。
```

### 场景 4：使用 GDB 初始化脚本

创建调试初始化脚本 `/data/debug/init_coredump.gdb`：

```gdb
# 加载程序和 coredump
file /data/debug/executables/my_server
core-file /data/debug/coredumps/core.12345

# 设置符号路径
set sysroot /data/debug/sysroot
set solib-search-path /data/debug/sysroot/usr/lib

# 调试友好设置
set print pretty on
set print array on
set print object on
set pagination off

# 显示初始信息
info threads
bt
```

然后：
```
使用初始化脚本 /data/debug/init_coredump.gdb 启动调试会话，分析崩溃原因。
```

---

## 配置文件说明

### deploy/config.env

环境变量配置文件，用于定制部署行为：

```bash
# GDB MCP Server 配置
GDB_MCP_INSTALL_DIR=/opt/gdb-mcp          # 安装目录
GDB_MCP_VENV_DIR=/opt/gdb-mcp/venv        # 虚拟环境目录
GDB_MCP_LOG_LEVEL=INFO                     # 日志级别
GDB_PATH=/usr/bin/gdb                      # GDB 路径

# 调试文件目录
DEBUG_WORK_DIR=/data/debug                 # 调试工作目录
COREDUMP_DIR=/data/debug/coredumps         # Coredump 目录
EXECUTABLE_DIR=/data/debug/executables     # 可执行文件目录
SYSROOT_DIR=/data/debug/sysroot            # Sysroot 目录
```

---

## 故障排除

### SSH 连接问题

**1. SSH 连接超时**
```bash
# 详细调试 SSH 连接
ssh -vvv user@remote-server

# 确保 SSH key 已加载
ssh-add -l
```

**2. "Permission denied (publickey)"**
```bash
# 确认公钥已复制
ssh-copy-id user@remote-server

# 检查远程 authorized_keys 权限
ssh user@remote-server "chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
```

**3. Python 路径错误**
```bash
# 在远程确认路径
ssh user@remote-server "ls -la /opt/gdb-mcp/venv/bin/python"

# 确认模块可导入
ssh user@remote-server "/opt/gdb-mcp/venv/bin/python -c 'import gdb_mcp; print(\"OK\")'"
```

**4. SSH 连接断开导致会话丢失**
- 在本地 `~/.ssh/config` 中配置 `ServerAliveInterval 60`
- 使用 `ControlMaster` 复用连接

### GDB 调试问题

**1. "No debugging symbols found"**
- 确保可执行文件编译时带 `-g` 选项
- 或提供单独的 `.debug` 符号文件
- 检查：`file /path/to/executable`（应看到 "with debug_info" 或 "not stripped"）

**2. 共享库符号缺失**
- 确保 sysroot 中的库版本与 coredump 完全匹配
- 检查 `info sharedlibrary` 输出
- 添加 `set solib-search-path` 指向所有库目录

**3. Coredump 与可执行文件不匹配**
```bash
# 确保 build-id 一致
file /path/to/executable
eu-readelf -n /path/to/coredump | grep Build
```

**4. GDB 架构不匹配**
- 如果目标程序是 ARM 架构，需要安装 `gdb-multiarch`：
  ```bash
  sudo apt install gdb-multiarch
  ```
  然后在 MCP 配置的 SSH args 中传入环境变量：
  ```json
  {
    "command": "ssh",
    "args": [
      "gdb-remote",
      "GDB_PATH=/usr/bin/gdb-multiarch",
      "/opt/gdb-mcp/venv/bin/python", "-m", "gdb_mcp"
    ]
  }
  ```
  或在 AI 对话中指定 `gdb_path` 参数。

---

## 高级配置

### 多 GDB 版本共存

```bash
# 安装多架构 GDB
sudo apt install gdb-multiarch

# 通过 SSH 传入环境变量指定
ssh user@remote-server "GDB_PATH=/usr/bin/gdb-multiarch /opt/gdb-mcp/venv/bin/python -m gdb_mcp"
```

或在 `gdb_start_session` 的 `gdb_path` 参数中指定。

### Docker 容器环境中的 Coredump

从 Docker 容器中收集调试文件：

```bash
# 1. 从容器中提取可执行文件和库
docker cp container_id:/usr/bin/my_server /data/debug/executables/
docker cp container_id:/lib/ /data/debug/sysroot/lib/
docker cp container_id:/usr/lib/ /data/debug/sysroot/usr/lib/

# 2. Coredump 通常在宿主机上
cat /proc/sys/kernel/core_pattern

# 3. 使用 sysroot 进行分析
```

### Kubernetes Pod 中的 Coredump

```bash
# 1. 从 pod 中提取文件
kubectl cp pod-name:/usr/bin/my_server /tmp/my_server
kubectl cp pod-name:/lib/ /tmp/sysroot/lib/

# 2. 传输到调试服务器
scp -r /tmp/my_server /tmp/sysroot user@debug-server:/data/debug/

# 3. Coredump 位置取决于集群配置
```

---

## 文件清单

```
deploy/
├── REMOTE_COREDUMP_DEPLOY.md    # 本文档 - 部署方案说明
├── setup_remote.sh              # 一键部署脚本
├── config.env                   # 环境变量配置
└── test_deployment.sh           # 部署验证脚本
```
