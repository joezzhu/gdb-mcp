# Remote Debugging Guide

MCP Server 运行在**本地**，通过 SSH 连接远端 GDB。远端只需安装 GDB。

## 架构

```
本地 MCP Client (IDE)           远程 Linux 服务器
┌──────────────────┐            ┌─────────────────────┐
│ Claude Desktop / │   stdio    │ 只需要:              │
│ CodeBuddy IDE    │◄─────────► │  ✓ GDB              │
│                  │            │  ✓ SSH               │
│ ┌──────────────┐ │    SSH     │  ✗ 不需要 Python     │
│ │ gdb-mcp-svr  │─│───────────►│  ✗ 不需要 MCP Server │
│ │ (本地 Python) │ │            │                     │
│ └──────────────┘ │            │ GDB --interpreter=mi │
└──────────────────┘            └─────────────────────┘
```

## 快速开始

### 1. 本地安装

```bash
cd /path/to/gdb-mcp
pip install -e .
```

### 2. 远端确认 GDB 可用

```bash
ssh -p PORT -i /path/to/key user@host "gdb --version"
```

### 3. 配置 MCP 客户端

```json
{
  "mcpServers": {
    "gdb": {
      "command": "gdb-mcp-server",
      "env": {
        "GDB_SSH_HOST": "your-server-ip",
        "GDB_SSH_USER": "your-username",
        "GDB_SSH_PORT": "22",
        "GDB_SSH_KEY": "/path/to/ssh/key"
      }
    }
  }
}
```

### 4. 开始调试

AI 调用时只需提供路径，SSH 连接自动从环境变量获取：

```
分析 coredump：
- 可执行文件：/data/debug/my_server
- Core 文件：/data/debug/core.12345
```

---

## Coredump 调试场景

### 基本分析

```
请加载 coredump 分析崩溃原因：
- 可执行文件：/data/debug/executables/my_program
- Core 文件：/data/debug/coredumps/core.12345

请告诉我崩溃线程的调用栈和所有线程状态。
```

### 带 Sysroot（容器/跨环境）

```
分析 coredump，使用自定义 sysroot：
- 可执行文件：/data/debug/executables/my_server
- Core 文件：/data/debug/coredumps/core.99999
- Sysroot：/data/debug/sysroot
- 库路径：/data/debug/sysroot/usr/lib
```

### 批量分析

```
依次分析以下 coredump，对比崩溃原因：
1. /data/debug/coredumps/core.001
2. /data/debug/coredumps/core.002
3. /data/debug/coredumps/core.003
可执行文件：/data/debug/executables/my_server
```

---

## SSH 配置

### 环境变量（在 MCP 客户端 env 中设置）

| 变量 | 说明 | 示例 |
|------|------|------|
| `GDB_SSH_HOST` | SSH 主机 | `9.134.194.81` |
| `GDB_SSH_USER` | SSH 用户 | `joezzhu` |
| `GDB_SSH_PORT` | SSH 端口 | `36000` |
| `GDB_SSH_KEY` | SSH 私钥路径 | `D:\joezzhu\pc7.key` |
| `GDB_SSH_OPTIONS` | 额外选项（逗号分隔） | `-o,ProxyJump=bastion` |

### 工具参数覆盖

工具参数始终优先于环境变量。如需连接不同服务器：

```json
{
  "program": "/path/to/app",
  "ssh_host": "other-server",
  "ssh_user": "root",
  "ssh_port": 2222
}
```

### SSH 免密登录

```bash
ssh-keygen -t ed25519 -C "gdb-mcp"
ssh-copy-id -p PORT user@host

# 验证
ssh -p PORT -i /path/to/key user@host "echo OK && gdb --version"
```

### （可选）SSH Config 优化

在 `~/.ssh/config` 中添加：

```
Host gdb-remote
    HostName your-server-ip
    User your-username
    Port 22
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 60
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ControlPersist 600
```

---

## 故障排除

### SSH 连接失败
```bash
ssh -vvv -p PORT -i /path/to/key user@host
ssh-add -l   # 确认 key 已加载
```

### 跳板机连接
```json
{
  "env": {
    "GDB_SSH_OPTIONS": "-o,ProxyJump=bastion-host"
  }
}
```

### 跨架构调试（ARM 等）
远端安装 `gdb-multiarch`，然后设置 `gdb_path`：
```json
{"gdb_path": "/usr/bin/gdb-multiarch"}
```

### No debugging symbols found
可执行文件需用 `-g` 编译。检查：`file /path/to/executable`

### 会话超时
空闲 30 分钟后自动关闭。调整：`GDB_SESSION_TIMEOUT=3600`（秒）

---

## Docker/K8s Coredump

```bash
# 从容器提取调试文件
docker cp container_id:/usr/bin/my_server /data/debug/executables/
docker cp container_id:/lib/ /data/debug/sysroot/lib/
docker cp container_id:/usr/lib/ /data/debug/sysroot/usr/lib/

# K8s
kubectl cp pod-name:/usr/bin/my_server /tmp/my_server
```

然后使用 sysroot 模式分析。
