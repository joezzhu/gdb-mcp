# Installation Guide

## Prerequisites

- **Local machine**: Python 3.10+, SSH client (Windows 10+ has OpenSSH built-in)
- **Remote server** (for SSH mode): GDB installed, SSH accessible — no Python needed

## Method 1: pip install (Recommended)

```bash
cd /path/to/gdb-mcp
pip install -e .
```

## Method 2: pipx install (Isolated)

```bash
pip install pipx
pipx install /path/to/gdb-mcp
```

## Verify Installation

```bash
gdb-mcp-server        # pipx method
# or
python -m gdb_mcp     # pip method

# Should output: INFO:gdb_mcp.server:GDB MCP Server starting...
# Press Ctrl+C to exit
```

> **Windows**: If `gdb-mcp-server` is not found, the Scripts directory is not in PATH. Use full path:
> `C:\Users\<user>\AppData\Local\Python\...\Scripts\gdb-mcp-server.exe`

---

## Configure MCP Client

### Config File Locations

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

### Local Debugging Only

```json
{
  "mcpServers": {
    "gdb": {
      "command": "gdb-mcp-server"
    }
  }
}
```

### Remote Debugging via SSH (Recommended)

Pre-configure SSH parameters so every `gdb_start_session` call auto-connects to the remote server:

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

### Using venv Python Path (if command not in PATH)

**macOS/Linux:**
```json
{
  "mcpServers": {
    "gdb": {
      "command": "/path/to/gdb-mcp/venv/bin/python",
      "args": ["-m", "gdb_mcp"],
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

**Windows:**
```json
{
  "mcpServers": {
    "gdb": {
      "command": "C:\\Users\\yourname\\AppData\\Local\\Python\\...\\python.exe",
      "args": ["-m", "gdb_mcp"],
      "env": {
        "GDB_SSH_HOST": "your-server-ip",
        "GDB_SSH_USER": "yourname",
        "GDB_SSH_PORT": "22",
        "GDB_SSH_KEY": "D:\\path\\to\\key"
      }
    }
  }
}
```

### Restart your MCP client after config changes.

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GDB_PATH` | GDB executable path | `gdb` |
| `GDB_MCP_LOG_LEVEL` | Log level | `INFO` |
| `GDB_SESSION_TIMEOUT` | Idle timeout (seconds) | `1800` |
| `GDB_SSH_HOST` | Default SSH host | — |
| `GDB_SSH_USER` | Default SSH user | — |
| `GDB_SSH_PORT` | Default SSH port | `22` |
| `GDB_SSH_KEY` | Default SSH key path | — |
| `GDB_SSH_OPTIONS` | Extra SSH options (comma-sep) | — |

---

## Troubleshooting

### "Command not found" / "executable file not found in %PATH%"
Use the full path to `gdb-mcp-server.exe` or use `python -m gdb_mcp`.

### "Module not found: gdb_mcp"
Re-install: `pip install -e .`

### "GDB not found"
Install GDB on the machine where GDB runs (local or remote):
```bash
sudo apt install gdb           # Ubuntu/Debian
sudo yum install gdb           # CentOS/RHEL
brew install gdb               # macOS
```

### SSH connection issues
```bash
# Test SSH connectivity
ssh -p PORT -i /path/to/key user@host "gdb --version"

# Verbose debug
ssh -vvv -p PORT -i /path/to/key user@host "echo OK"
```

### Session expired
Sessions auto-close after idle timeout (default 30 min). Set `GDB_SESSION_TIMEOUT` to change.
