# GDB MCP Server

An MCP (Model Context Protocol) server that provides AI assistants with programmatic access to GDB debugging sessions. Supports both **local** and **SSH remote** debugging — the MCP Server runs locally, connects to remote GDB via SSH.

## Features

- **SSH Remote Debugging**: Debug programs on remote servers — only GDB needed on remote, no Python/MCP deployment
- **Local Mode**: Works with local GDB when no SSH parameters are provided
- **Full GDB Control**: Start sessions, execute commands, control program execution
- **Thread Analysis**: Inspect threads, get backtraces, analyze thread states
- **Breakpoint Management**: Set conditional/temporary breakpoints
- **Variable Inspection**: Evaluate expressions, inspect variables and registers
- **Core Dump Analysis**: Load and analyze core dumps with sysroot support
- **Session Timeout**: Auto-cleanup of idle sessions (default: 30 min, configurable)

## Architecture

```
MCP Client (IDE)  ──stdio──►  MCP Server (local)  ──SSH──►  GDB --interpreter=mi (remote)
                                    ↑                              ↓
                              Local MI parsing              Remote program debugging
```

## Quick Start

### 1. Install

```bash
cd /path/to/gdb-mcp
pip install -e .
```

### 2. Configure MCP Client

Add to your MCP client config (Claude Desktop / CodeBuddy IDE):

**Local debugging only:**
```json
{
  "mcpServers": {
    "gdb": {
      "command": "gdb-mcp-server"
    }
  }
}
```

**Remote debugging (recommended — pre-configure SSH):**
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

With SSH defaults configured, AI only needs `program`/`core` paths — no SSH params needed per call.

> **Windows note:** If `gdb-mcp-server` is not in PATH, use the full path:
> `C:\\Users\\<user>\\AppData\\Local\\Python\\...\\Scripts\\gdb-mcp-server.exe`
> or use `{"command": "python", "args": ["-m", "gdb_mcp"]}` instead.

**Config file locations:**
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

### 3. Start Debugging

Ask AI:
```
分析远程服务器上的 coredump：
- 可执行文件：/home/user/myapp
- Core 文件：/home/user/core.12345
```

**For detailed installation methods, see [INSTALL.md](INSTALL.md).**
**For remote coredump debugging guide, see [deploy/REMOTE_DEBUG_GUIDE.md](deploy/REMOTE_DEBUG_GUIDE.md).**

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GDB_PATH` | Path to GDB executable | `gdb` |
| `GDB_MCP_LOG_LEVEL` | Log level (DEBUG/INFO/WARNING/ERROR) | `INFO` |
| `GDB_SESSION_TIMEOUT` | Session idle timeout in seconds | `1800` (30 min) |
| `GDB_SSH_HOST` | Default SSH host | — |
| `GDB_SSH_USER` | Default SSH username | — |
| `GDB_SSH_PORT` | Default SSH port | `22` |
| `GDB_SSH_KEY` | Default SSH private key path | — |
| `GDB_SSH_OPTIONS` | Extra SSH options (comma-separated) | — |

Tool parameters (`ssh_host`, `gdb_path`, etc.) always override environment defaults.

## Available Tools (22)

**Session**: `gdb_start_session`, `gdb_execute_command`, `gdb_call_function`, `gdb_get_status`, `gdb_stop_session`

**Threads & Frames**: `gdb_get_threads`, `gdb_select_thread`, `gdb_get_backtrace`, `gdb_select_frame`, `gdb_get_frame_info`

**Breakpoints**: `gdb_set_breakpoint`, `gdb_list_breakpoints`, `gdb_delete_breakpoint`, `gdb_enable_breakpoint`, `gdb_disable_breakpoint`

**Execution**: `gdb_continue`, `gdb_step`, `gdb_next`, `gdb_interrupt`

**Data**: `gdb_evaluate_expression`, `gdb_get_variables`, `gdb_get_registers`

**For detailed tool documentation, see [TOOLS.md](TOOLS.md).**

## Usage Examples

### Remote Debugging
```json
{
  "program": "/home/dev/myapp",
  "ssh_host": "devbox",
  "ssh_user": "dev"
}
```

### Remote Core Dump with Sysroot
```json
{
  "program": "/path/to/executable",
  "core": "/path/to/core.dump",
  "ssh_host": "debug-server",
  "init_commands": ["set sysroot /path/to/sysroot"]
}
```

### Local Debugging (no SSH)
```json
{
  "program": "/path/to/local/app"
}
```

## How It Works

1. **GDB/MI Protocol**: Same interface used by VS Code and CLion
2. **Built-in MI Parser**: Self-contained, zero external GDB dependencies
3. **Dual-Mode Controller**: `LocalController` (subprocess) + `SSHController` (SSH tunnel)
4. **Session Management**: Multiple concurrent sessions with idle timeout auto-cleanup

## Troubleshooting

**Timeout / Commands Not Responding**: Program is running — use `gdb_interrupt` to pause it first.

**Missing Debug Symbols**: Check `warnings` in `gdb_start_session` response. Compile with `-g`.

**Session expired**: Idle sessions auto-close after timeout. Start a new session.

**For more, see [INSTALL.md](INSTALL.md#troubleshooting).**

## License

MIT

## References

- [GDB/MI Protocol](https://sourceware.org/gdb/current/onlinedocs/gdb/GDB_002fMI.html)
- [Model Context Protocol](https://modelcontextprotocol.io/)
