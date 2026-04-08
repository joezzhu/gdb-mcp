# GDB MCP Server 手动安装指南

本文档提供从零开始在 Linux 服务器上手动部署 GDB MCP Server 的完整步骤，适用于远程 coredump 调试场景。

---

## 第 1 步：安装 GDB

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install -y gdb

# CentOS/RHEL/TencentOS
sudo yum install -y gdb
# 或
sudo dnf install -y gdb

# 验证
gdb --version
```

如果需要调试 ARM 等非本机架构的 coredump：
```bash
# Ubuntu/Debian
sudo apt install -y gdb-multiarch

# CentOS/RHEL（可能需要 EPEL 源）
sudo yum install -y gdb-multiarch
```

---

## 第 2 步：安装 Python 3.10+

> **GDB MCP Server 要求 Python >= 3.10。** 许多 Linux 发行版（如 CentOS 7/8、TencentOS）自带的 Python 是 3.6/3.8，版本不够，需要额外安装。

先检查当前版本：
```bash
python3 --version
```

如果已经 >= 3.10，跳到第 3 步。否则按以下方式安装。

### 方式 A：从系统包管理器安装（推荐）

```bash
# ---- Ubuntu 22.04+ ----
# 自带 Python 3.10+，无需额外安装
sudo apt install -y python3 python3-venv python3-pip

# ---- Ubuntu 20.04 ----
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt install -y python3.11 python3.11-venv python3.11-dev

# ---- CentOS 8 / CentOS Stream / TencentOS 3.1+ ----
sudo dnf install -y python3.11
# 或
sudo dnf install -y python3.10

# ---- CentOS 7 ----
# 需要启用 SCL 或 EPEL
sudo yum install -y centos-release-scl
sudo yum install -y rh-python38  # CentOS 7 最高到 3.8，建议升级系统或用源码编译
```

安装后验证：
```bash
python3.11 --version   # 或 python3.10 --version
```

### 方式 B：从源码编译安装

适用于系统包管理器中没有 Python 3.10+ 的情况。

```bash
# 1. 安装编译依赖
# Ubuntu/Debian
sudo apt install -y build-essential zlib1g-dev libncurses5-dev \
    libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev \
    libsqlite3-dev wget libbz2-dev

# CentOS/RHEL/TencentOS
sudo yum groupinstall -y "Development Tools"
sudo yum install -y gcc openssl-devel bzip2-devel libffi-devel \
    zlib-devel readline-devel sqlite-devel wget

# 2. 下载 Python 源码
cd /tmp
wget https://www.python.org/ftp/python/3.11.9/Python-3.11.9.tgz
tar xzf Python-3.11.9.tgz
cd Python-3.11.9

# 3. 编译安装
./configure --enable-optimizations --prefix=/usr/local
make -j$(nproc)
sudo make altinstall    # 重要：用 altinstall，不会覆盖系统自带的 python3

# 4. 验证
/usr/local/bin/python3.11 --version
# 输出: Python 3.11.9
```

> **⚠️ 注意**：务必使用 `make altinstall` 而不是 `make install`，否则会覆盖系统的 `python3` 命令，可能导致 `dnf`/`yum` 等系统工具异常。

---

## 第 3 步：获取 GDB MCP Server 源码

```bash
# 方式 1：git clone
git clone <repository-url> ~/gdb-mcp
cd ~/gdb-mcp

# 方式 2：scp 从本地传输
# （在本地执行）
scp -r /path/to/gdb-mcp user@remote-server:~/gdb-mcp
```

---

## 第 4 步：创建 Python 虚拟环境并安装

根据你安装的 Python 版本，选择对应的命令（以下以 `python3.11` 为例）：

```bash
cd ~/gdb-mcp

# 创建虚拟环境（使用你安装的高版本 Python）
python3.11 -m venv venv
# 如果是源码编译的：
# /usr/local/bin/python3.11 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 确认 Python 版本
python --version
# 输出: Python 3.11.x

# 升级 pip
pip install --upgrade pip

# 安装 gdb-mcp-server
pip install -e .
```

安装完成后验证：
```bash
# 确认模块可导入
python -c "import gdb_mcp; print(f'gdb-mcp-server v{gdb_mcp.__version__} OK')"

# 确认依赖完整
python -c "import mcp; import pygdbmi; print('dependencies OK')"

# 启动测试（Ctrl+C 退出）
python -m gdb_mcp
# 应输出: INFO:gdb_mcp.server:GDB MCP Server starting...
```

退出虚拟环境：
```bash
deactivate
```

---

## 第 5 步：配置本地 SSH 免密登录

在你的**本地机器**上操作：

```bash
# 生成 SSH 密钥（如果没有）
ssh-keygen -t ed25519 -C "gdb-mcp"

# 复制公钥到远程服务器
ssh-copy-id user@remote-server

# 验证免密登录
ssh user@remote-server "echo OK"
```

（可选）在本地 `~/.ssh/config` 中添加别名，简化后续配置：

```
Host gdb-remote
    HostName 远程服务器IP
    User 你的用户名
    Port 22
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

---

## 第 6 步：验证远程 SSH 启动

在**本地**终端执行：

```bash
# 用绝对路径通过 SSH 启动 MCP server
ssh user@remote-server "~/gdb-mcp/venv/bin/python -m gdb_mcp"
# 应看到: INFO:gdb_mcp.server:GDB MCP Server starting...
# Ctrl+C 退出
```

如果看到正常输出，说明远程环境已就绪。

---

## 第 7 步：配置 MCP 客户端

在你的 MCP 客户端（Claude Desktop / CodeBuddy IDE）中添加配置。

### Claude Desktop

编辑配置文件（位置见下方），添加 `gdb-remote`：
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "gdb-remote": {
      "command": "ssh",
      "args": [
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "user@remote-server",
        "/home/user/gdb-mcp/venv/bin/python", "-m", "gdb_mcp"
      ]
    }
  }
}
```

如果配置了 SSH 别名，可简化为：

```json
{
  "mcpServers": {
    "gdb-remote": {
      "command": "ssh",
      "args": [
        "gdb-remote",
        "/home/user/gdb-mcp/venv/bin/python", "-m", "gdb_mcp"
      ]
    }
  }
}
```

### CodeBuddy IDE

在 MCP 设置中添加相同配置。

---

## 第 8 步：开始调试 Coredump

在 MCP 客户端中向 AI 发送：

```
请加载远程服务器上的 coredump 进行分析：
- 可执行文件：/path/to/my_program
- Core 文件：/path/to/core.12345

请告诉我崩溃原因和所有线程的状态。
```

带 sysroot 的场景：

```
分析 coredump：
- 可执行文件：/data/debug/executables/my_server
- Core 文件：/data/debug/coredumps/core.99999
- Sysroot：/data/debug/sysroot
- 库路径：/data/debug/sysroot/usr/lib:/data/debug/sysroot/lib
```

---

## 常见问题

### Q: `pip install -e .` 报 `No matching distribution found for mcp>=0.9.0`
**原因**：Python 版本低于 3.10，`mcp` 包不支持。
**解决**：确认 venv 使用的是 Python 3.10+：
```bash
~/gdb-mcp/venv/bin/python --version
```
如果不是，删除旧 venv 重新创建：
```bash
rm -rf ~/gdb-mcp/venv
python3.11 -m venv ~/gdb-mcp/venv
source ~/gdb-mcp/venv/bin/activate
pip install -e .
```

### Q: `python3.11 -m venv venv` 报 `No module named venv`
**解决**：
```bash
# Ubuntu/Debian
sudo apt install -y python3.11-venv

# CentOS/RHEL（源码编译的通常自带 venv，无需额外安装）
```

### Q: 源码编译时 `./configure` 报缺少 openssl
**解决**：
```bash
# Ubuntu/Debian
sudo apt install -y libssl-dev

# CentOS/RHEL
sudo yum install -y openssl-devel
```

### Q: SSH 启动后无输出或报错 `ModuleNotFoundError`
**解决**：确认 SSH 命令中使用的是 venv 的**绝对路径**：
```bash
# 正确 ✓
ssh user@server "/home/user/gdb-mcp/venv/bin/python -m gdb_mcp"

# 错误 ✗（系统 python 没有装 gdb_mcp）
ssh user@server "python3 -m gdb_mcp"
```

### Q: 不想覆盖系统 Python，安装了 python3.11 但 `python3` 还是 3.8
**说明**：这是正常的。不要修改系统默认 `python3`，直接用 `python3.11` 命令即可。venv 激活后或使用绝对路径时，都是 3.11。
