#!/usr/bin/env bash
# ============================================================
# GDB MCP Server - 部署验证测试脚本
# ============================================================
# 用法：
#   chmod +x deploy/test_deployment.sh
#   ./deploy/test_deployment.sh [--config path/to/config.env]
#
# 此脚本验证远程 coredump 调试环境是否正确部署。
# ============================================================

set -euo pipefail

# --- 颜色输出 ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASS=0
FAIL=0
WARN_COUNT=0

pass()  { ((PASS++)); echo -e "  ${GREEN}✓ PASS${NC}: $*"; }
fail()  { ((FAIL++)); echo -e "  ${RED}✗ FAIL${NC}: $*"; }
skip()  { ((WARN_COUNT++)); echo -e "  ${YELLOW}○ SKIP${NC}: $*"; }
info()  { echo -e "${BLUE}[TEST]${NC} $*"; }

# --- 默认配置 ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

GDB_MCP_INSTALL_DIR="${PROJECT_DIR}"
GDB_MCP_VENV_DIR="${PROJECT_DIR}/venv"
GDB_PATH=""
DEBUG_WORK_DIR="/data/debug"
COREDUMP_DIR="/data/debug/coredumps"
EXECUTABLE_DIR="/data/debug/executables"
SYSROOT_DIR="/data/debug/sysroot"

# --- 加载配置 ---
CONFIG_FILE="${SCRIPT_DIR}/config.env"

while [[ $# -gt 0 ]]; do
    case $1 in
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

if [[ -f "${CONFIG_FILE}" ]]; then
    # shellcheck source=/dev/null
    source "${CONFIG_FILE}"
fi

PYTHON_VENV="${GDB_MCP_VENV_DIR}/bin/python"
GDB_CMD="${GDB_PATH:-gdb}"

# ============================================================
# 测试用例
# ============================================================

echo ""
echo "============================================================"
echo "  GDB MCP Server - 部署验证测试"
echo "============================================================"
echo ""

# --- 1. 系统依赖 ---
info "=== 1. 系统依赖检查 ==="

# Python
if command -v python3 &>/dev/null; then
    py_ver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    py_major=$(echo "$py_ver" | cut -d. -f1)
    py_minor=$(echo "$py_ver" | cut -d. -f2)
    if [[ "$py_major" -ge 3 ]] && [[ "$py_minor" -ge 10 ]]; then
        pass "Python ${py_ver} 版本满足要求 (>= 3.10)"
    else
        fail "Python ${py_ver} 版本不满足要求 (需要 >= 3.10)"
    fi
else
    fail "Python3 未安装"
fi

# GDB
if command -v "$GDB_CMD" &>/dev/null; then
    gdb_ver=$($GDB_CMD --version | head -1)
    pass "GDB 已安装: ${gdb_ver}"
else
    fail "GDB 未安装或路径不正确: ${GDB_CMD}"
fi

# venv 模块
if python3 -m venv --help &>/dev/null 2>&1; then
    pass "Python venv 模块可用"
else
    fail "Python venv 模块不可用"
fi

echo ""

# --- 2. 项目文件 ---
info "=== 2. 项目文件检查 ==="

if [[ -f "${GDB_MCP_INSTALL_DIR}/pyproject.toml" ]]; then
    pass "pyproject.toml 存在"
else
    fail "pyproject.toml 不存在: ${GDB_MCP_INSTALL_DIR}/pyproject.toml"
fi

if [[ -d "${GDB_MCP_INSTALL_DIR}/src/gdb_mcp" ]]; then
    pass "src/gdb_mcp/ 目录存在"
else
    fail "src/gdb_mcp/ 目录不存在"
fi

for src_file in __init__.py __main__.py server.py gdb_interface.py; do
    if [[ -f "${GDB_MCP_INSTALL_DIR}/src/gdb_mcp/${src_file}" ]]; then
        pass "源文件存在: ${src_file}"
    else
        fail "源文件缺失: ${src_file}"
    fi
done

echo ""

# --- 3. 虚拟环境 ---
info "=== 3. 虚拟环境检查 ==="

if [[ -d "${GDB_MCP_VENV_DIR}" ]]; then
    pass "虚拟环境目录存在: ${GDB_MCP_VENV_DIR}"
else
    fail "虚拟环境目录不存在: ${GDB_MCP_VENV_DIR}"
fi

if [[ -x "${PYTHON_VENV}" ]]; then
    pass "虚拟环境 Python 可执行: ${PYTHON_VENV}"
else
    fail "虚拟环境 Python 不存在或不可执行: ${PYTHON_VENV}"
fi

echo ""

# --- 4. 包安装 ---
info "=== 4. 包安装检查 ==="

if [[ -x "${PYTHON_VENV}" ]]; then
    # gdb_mcp 模块
    if "${PYTHON_VENV}" -c "import gdb_mcp" 2>/dev/null; then
        version=$("${PYTHON_VENV}" -c "import gdb_mcp; print(gdb_mcp.__version__)")
        pass "gdb_mcp 模块可导入 (v${version})"
    else
        fail "gdb_mcp 模块无法导入"
    fi

    # mcp 依赖
    if "${PYTHON_VENV}" -c "import mcp" 2>/dev/null; then
        pass "mcp 依赖已安装"
    else
        fail "mcp 依赖未安装"
    fi
else
    skip "虚拟环境不存在，跳过包检查"
fi

echo ""

# --- 5. 调试目录 ---
info "=== 5. 调试工作目录检查 ==="

for dir_var in DEBUG_WORK_DIR COREDUMP_DIR EXECUTABLE_DIR SYSROOT_DIR; do
    dir_path="${!dir_var}"
    if [[ -d "$dir_path" ]]; then
        pass "目录存在: ${dir_path}"
        if [[ -w "$dir_path" ]]; then
            pass "目录可写: ${dir_path}"
        else
            fail "目录不可写: ${dir_path}"
        fi
    else
        skip "目录不存在: ${dir_path}（将在首次部署时创建）"
    fi
done

echo ""

# --- 6. 服务器启动测试 ---
info "=== 6. 服务器启动测试 ==="

if [[ -x "${PYTHON_VENV}" ]]; then
    # 尝试启动服务器（在后台，然后立即停止）
    timeout 5 "${PYTHON_VENV}" -c "
import asyncio
from gdb_mcp.server import main
async def test():
    # 只测试导入和初始化，不实际运行 stdio
    from mcp.server import Server
    server = Server('test')
    print('server_init_ok')
asyncio.run(test())
" 2>/dev/null && pass "服务器初始化成功" || fail "服务器初始化失败"
else
    skip "虚拟环境不存在，跳过启动测试"
fi

echo ""

# --- 7. 生成配置检查 ---
info "=== 7. 配置文件检查 ==="

generated_dir="${SCRIPT_DIR}/generated"
if [[ -d "$generated_dir" ]]; then
    for cfg_file in mcp_config_ssh.json mcp_config_ssh_alias.json ssh_config_snippet example_prompts.md; do
        if [[ -f "${generated_dir}/${cfg_file}" ]]; then
            pass "配置文件存在: ${cfg_file}"
        else
            skip "配置文件未生成: ${cfg_file}（运行 setup_remote.sh 生成）"
        fi
    done
else
    skip "generated/ 目录不存在（运行 setup_remote.sh 生成）"
fi

echo ""

# ============================================================
# 测试结果汇总
# ============================================================

echo "============================================================"
echo "  测试结果汇总"
echo "============================================================"
echo ""
echo -e "  ${GREEN}通过: ${PASS}${NC}"
echo -e "  ${RED}失败: ${FAIL}${NC}"
echo -e "  ${YELLOW}跳过: ${WARN_COUNT}${NC}"
echo ""

if [[ ${FAIL} -eq 0 ]]; then
    echo -e "  ${GREEN}========================================${NC}"
    echo -e "  ${GREEN}  所有关键测试通过！环境已就绪。${NC}"
    echo -e "  ${GREEN}========================================${NC}"
    exit 0
else
    echo -e "  ${RED}========================================${NC}"
    echo -e "  ${RED}  有 ${FAIL} 项测试失败，请检查上述输出。${NC}"
    echo -e "  ${RED}========================================${NC}"
    exit 1
fi
