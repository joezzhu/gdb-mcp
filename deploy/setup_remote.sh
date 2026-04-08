#!/usr/bin/env bash
# ============================================================
# GDB MCP Server - 远程 Coredump 调试环境一键部署脚本
# ============================================================
# 用法：
#   chmod +x deploy/setup_remote.sh
#   ./deploy/setup_remote.sh [--config path/to/config.env]
#
# 功能：
#   1. 检查系统依赖（Python >= 3.10, GDB）
#   2. 创建 Python 虚拟环境
#   3. 安装 gdb-mcp-server 及依赖
#   4. 创建调试工作目录
#   5. 生成客户端配置模板
#   6. 验证安装
# ============================================================

set -euo pipefail

# --- 颜色输出 ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
fatal()   { error "$*"; exit 1; }

# --- 默认配置 ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 默认值（可通过 config.env 覆盖）
GDB_MCP_INSTALL_DIR="${PROJECT_DIR}"
GDB_MCP_VENV_DIR="${PROJECT_DIR}/venv"
GDB_MCP_LOG_LEVEL="INFO"
GDB_PATH=""
DEBUG_WORK_DIR="/data/debug"
COREDUMP_DIR="/data/debug/coredumps"
EXECUTABLE_DIR="/data/debug/executables"
SYSROOT_DIR="/data/debug/sysroot"
PYTHON_MIN_VERSION="3.10"

# --- 参数解析 ---
CONFIG_FILE="${SCRIPT_DIR}/config.env"

while [[ $# -gt 0 ]]; do
    case $1 in
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --help|-h)
            echo "用法: $0 [--config path/to/config.env]"
            echo ""
            echo "选项:"
            echo "  --config FILE    指定配置文件路径（默认: deploy/config.env）"
            echo "  --help, -h       显示帮助信息"
            exit 0
            ;;
        *)
            fatal "未知参数: $1（使用 --help 查看帮助）"
            ;;
    esac
done

# --- 加载配置 ---
if [[ -f "${CONFIG_FILE}" ]]; then
    info "加载配置文件: ${CONFIG_FILE}"
    # shellcheck source=/dev/null
    source "${CONFIG_FILE}"
    success "配置已加载"
else
    warn "配置文件不存在: ${CONFIG_FILE}，使用默认值"
fi

# ============================================================
# 检查函数
# ============================================================

check_python() {
    info "检查 Python 版本..."

    local python_cmd=""
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            python_cmd="$cmd"
            break
        fi
    done

    if [[ -z "$python_cmd" ]]; then
        fatal "未找到 Python。请安装 Python ${PYTHON_MIN_VERSION}+：
  Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip
  CentOS/RHEL:   sudo yum install python3 python3-pip"
    fi

    # 检查版本
    local version
    version=$($python_cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    local major minor
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)
    local req_major req_minor
    req_major=$(echo "${PYTHON_MIN_VERSION}" | cut -d. -f1)
    req_minor=$(echo "${PYTHON_MIN_VERSION}" | cut -d. -f2)

    if [[ "$major" -lt "$req_major" ]] || { [[ "$major" -eq "$req_major" ]] && [[ "$minor" -lt "$req_minor" ]]; }; then
        fatal "Python 版本 ${version} 不满足要求（需要 >= ${PYTHON_MIN_VERSION}）"
    fi

    # 检查 venv 模块
    if ! $python_cmd -m venv --help &>/dev/null; then
        fatal "Python venv 模块不可用。请安装：
  Ubuntu/Debian: sudo apt install python3-venv
  CentOS/RHEL:   sudo yum install python3-venv（或 pip install virtualenv）"
    fi

    PYTHON_CMD="$python_cmd"
    success "Python ${version} (${python_cmd}) ✓"
}

check_gdb() {
    info "检查 GDB..."

    local gdb_cmd="${GDB_PATH:-gdb}"

    if ! command -v "$gdb_cmd" &>/dev/null; then
        fatal "未找到 GDB（${gdb_cmd}）。请安装：
  Ubuntu/Debian: sudo apt install gdb
  CentOS/RHEL:   sudo yum install gdb
  macOS:         brew install gdb"
    fi

    local gdb_version
    gdb_version=$($gdb_cmd --version | head -1)
    success "GDB: ${gdb_version} ✓"
}

check_project() {
    info "检查项目文件..."

    if [[ ! -f "${GDB_MCP_INSTALL_DIR}/pyproject.toml" ]]; then
        fatal "未找到 pyproject.toml，请确认 GDB_MCP_INSTALL_DIR=${GDB_MCP_INSTALL_DIR} 正确"
    fi

    if [[ ! -d "${GDB_MCP_INSTALL_DIR}/src/gdb_mcp" ]]; then
        fatal "未找到 src/gdb_mcp/ 目录"
    fi

    success "项目文件完整 ✓"
}

# ============================================================
# 安装函数
# ============================================================

create_venv() {
    info "创建 Python 虚拟环境: ${GDB_MCP_VENV_DIR}"

    if [[ -d "${GDB_MCP_VENV_DIR}" ]]; then
        warn "虚拟环境已存在，跳过创建"
        return 0
    fi

    $PYTHON_CMD -m venv "${GDB_MCP_VENV_DIR}"
    success "虚拟环境创建完成 ✓"
}

install_package() {
    info "安装 gdb-mcp-server 到虚拟环境..."

    local pip_cmd="${GDB_MCP_VENV_DIR}/bin/pip"
    local python_venv="${GDB_MCP_VENV_DIR}/bin/python"

    # 升级 pip
    "$python_venv" -m pip install --upgrade pip --quiet

    # 安装项目（可编辑模式，便于更新）
    cd "${GDB_MCP_INSTALL_DIR}"
    "$pip_cmd" install -e . --quiet

    success "gdb-mcp-server 安装完成 ✓"
}

create_directories() {
    info "创建调试工作目录..."

    local dirs=("${DEBUG_WORK_DIR}" "${COREDUMP_DIR}" "${EXECUTABLE_DIR}" "${SYSROOT_DIR}")

    for dir in "${dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir" 2>/dev/null || {
                warn "无法创建 ${dir}（可能需要 sudo 权限），跳过"
                continue
            }
            success "创建目录: ${dir}"
        else
            info "目录已存在: ${dir}"
        fi
    done
}

# ============================================================
# 验证函数
# ============================================================

verify_installation() {
    info "验证安装..."

    local python_venv="${GDB_MCP_VENV_DIR}/bin/python"

    # 检查 Python 可执行文件
    if [[ ! -x "$python_venv" ]]; then
        fatal "虚拟环境 Python 不存在: ${python_venv}"
    fi

    # 检查模块导入
    if ! "$python_venv" -c "import gdb_mcp; print(f'gdb-mcp-server v{gdb_mcp.__version__}')" 2>/dev/null; then
        fatal "无法导入 gdb_mcp 模块"
    fi

    # 检查依赖
    if ! "$python_venv" -c "import mcp; import pygdbmi" 2>/dev/null; then
        fatal "依赖包未正确安装（mcp 或 pygdbmi）"
    fi

    success "安装验证通过 ✓"
}

# ============================================================
# 生成配置
# ============================================================

generate_client_configs() {
    info "生成客户端配置模板..."

    local python_venv="${GDB_MCP_VENV_DIR}/bin/python"
    local hostname
    hostname=$(hostname -f 2>/dev/null || hostname)
    local current_user
    current_user=$(whoami)
    local output_dir="${SCRIPT_DIR}/generated"

    mkdir -p "${output_dir}"

    # SSH stdio 模式配置（完整参数版）
    cat > "${output_dir}/mcp_config_ssh.json" << EOF
{
  "mcpServers": {
    "gdb-remote": {
      "command": "ssh",
      "args": [
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "${current_user}@${hostname}",
        "${python_venv}", "-m", "gdb_mcp"
      ]
    }
  }
}
EOF
    success "MCP 客户端配置: ${output_dir}/mcp_config_ssh.json"

    # SSH config 别名版（需要本地 ~/.ssh/config 配置 gdb-remote Host）
    cat > "${output_dir}/mcp_config_ssh_alias.json" << EOF
{
  "mcpServers": {
    "gdb-remote": {
      "command": "ssh",
      "args": [
        "gdb-remote",
        "${python_venv}", "-m", "gdb_mcp"
      ]
    }
  }
}
EOF
    success "MCP 客户端配置(别名): ${output_dir}/mcp_config_ssh_alias.json"

    # SSH config 模板
    cat > "${output_dir}/ssh_config_snippet" << EOF
# 将以下内容追加到本地 ~/.ssh/config
Host gdb-remote
    HostName ${hostname}
    User ${current_user}
    Port 22
    # IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 60
    ServerAliveCountMax 3
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ControlPersist 600
EOF
    success "SSH config 模板: ${output_dir}/ssh_config_snippet"

    # 示例 coredump 分析 prompt
    cat > "${output_dir}/example_prompts.md" << EOF
# Coredump 分析示例 Prompt

## 基本分析

\`\`\`
请加载以下文件进行 coredump 分析：
- 可执行文件：${EXECUTABLE_DIR}/your_program
- Core 文件：${COREDUMP_DIR}/core.XXXXX

请告诉我：
1. 程序崩溃时有多少个线程？
2. 崩溃线程的完整调用栈
3. 崩溃时的局部变量值
4. 可能的崩溃原因
\`\`\`

## 带 Sysroot 的分析

\`\`\`
使用以下配置分析 coredump：
- 可执行文件：${EXECUTABLE_DIR}/your_program
- Core 文件：${COREDUMP_DIR}/core.XXXXX
- Sysroot：${SYSROOT_DIR}
- 库搜索路径：${SYSROOT_DIR}/usr/lib:${SYSROOT_DIR}/lib

请分析崩溃原因并检查所有线程的状态。
\`\`\`
EOF
    success "示例 Prompt: ${output_dir}/example_prompts.md"
}

# ============================================================
# 主流程
# ============================================================

main() {
    echo ""
    echo "============================================================"
    echo "  GDB MCP Server - 远程 Coredump 调试环境部署"
    echo "============================================================"
    echo ""

    # 1. 系统检查
    info "=== 步骤 1/5: 系统依赖检查 ==="
    check_python
    check_gdb
    check_project
    echo ""

    # 2. 创建虚拟环境
    info "=== 步骤 2/5: 创建虚拟环境 ==="
    create_venv
    echo ""

    # 3. 安装软件包
    info "=== 步骤 3/5: 安装 gdb-mcp-server ==="
    install_package
    echo ""

    # 4. 创建工作目录
    info "=== 步骤 4/5: 创建调试工作目录 ==="
    create_directories
    echo ""

    # 5. 验证 & 生成配置
    info "=== 步骤 5/5: 验证安装 & 生成配置 ==="
    verify_installation
    generate_client_configs
    echo ""

    # 完成
    echo "============================================================"
    success "部署完成！"
    echo ""
    echo "后续步骤："
    echo "  1. 将 coredump 文件放入:    ${COREDUMP_DIR}/"
    echo "  2. 将可执行文件放入:         ${EXECUTABLE_DIR}/"
    echo "  3. 将 sysroot 放入（如需）:  ${SYSROOT_DIR}/"
    echo ""
    echo "客户端配置文件已生成在: ${SCRIPT_DIR}/generated/"
    echo "  - MCP 配置:       mcp_config_ssh.json"
    echo "  - MCP 配置(别名): mcp_config_ssh_alias.json"
    echo "  - SSH config:     ssh_config_snippet"
    echo "  - 示例提示:       example_prompts.md"
    echo ""
    echo "手动测试命令（在本机执行）："
    echo "  ${GDB_MCP_VENV_DIR}/bin/python -m gdb_mcp"
    echo ""
    echo "远程 SSH 测试命令（在本地客户端执行）："
    echo "  ssh ${current_user}@${hostname} \"${GDB_MCP_VENV_DIR}/bin/python -m gdb_mcp\""
    echo "============================================================"
}

main "$@"
