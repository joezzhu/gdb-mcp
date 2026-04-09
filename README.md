# GDB MCP Server

An MCP (Model Context Protocol) server that provides AI assistants with programmatic access to GDB debugging sessions. This allows AI models to interact with debuggers in the same way IDEs like VS Code and CLion do, using the GDB/MI (Machine Interface) protocol.

## Features

- **Full GDB Control**: Start sessions, execute commands, control program execution
- **SSH Remote Debugging**: Debug programs on remote servers — MCP Server runs locally, connects to remote GDB via SSH
- **Local Mode Compatible**: Works with local GDB when no SSH parameters are provided
- **Thread Analysis**: Inspect threads, get backtraces, analyze thread states
- **Breakpoint Management**: Set conditional breakpoints, temporary breakpoints
- **Variable Inspection**: Evaluate expressions, inspect variables and registers
- **Core Dump Analysis**: Load and analyze core dumps with custom initialization
- **Flexible Initialization**: Run GDB scripts or commands on startup
- **Zero Remote Dependencies**: Remote server only needs GDB installed — no Python, no MCP deployment needed

## Architecture

This server uses the **GDB/MI (Machine Interface)** protocol, the same interface used by professional IDEs. It supports two modes:

**Local mode** (default): MCP Server starts a local GDB subprocess directly.

**SSH remote mode**: MCP Server runs locally and connects to a remote GDB via SSH:

```
MCP Client (IDE)  ──stdio──►  MCP Server (local)  ──SSH──►  GDB --interpreter=mi (remote)
                                    ↑                              ↓
                              Local MI parsing              Remote program debugging
```

Both modes provide:
- Structured, machine-parseable output
- Full access to GDB's debugging capabilities
- Reliable command execution and response handling

## Installation

### Prerequisites

- Python 3.10 or higher (on the local machine where MCP Server runs)
- GDB installed (locally and/or on the remote server)
- SSH client (for remote debugging mode)

### Quick Start

```bash
# Install pipx if needed
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Install gdb-mcp-server
cd /path/to/gdb-mcp
pipx install .
```

**For alternative installation methods (virtual environment, manual setup), see [INSTALL.md](INSTALL.md).**

## Configuration

### Claude Desktop

Add this to your Claude Desktop configuration file:

**Location:**
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

**Configuration:**
```json
{
  "mcpServers": {
    "gdb": {
      "command": "gdb-mcp-server"
    }
  }
}
```

**For other installation methods and MCP clients, see [INSTALL.md](INSTALL.md#step-5-configure-your-mcp-client).**

## Environment Variables

The GDB MCP Server supports the following environment variables:

### `GDB_PATH`

Specify the path to the GDB executable to use. This is useful when:
- You have multiple GDB versions installed
- GDB is installed in a non-standard location
- You want to use a custom or patched GDB build

**Default**: `gdb` (resolved via system PATH)

**Example**:
```bash
export GDB_PATH=/usr/local/bin/gdb-13.2
gdb-mcp-server
```

**Note**: The `gdb_path` parameter in the `gdb_start_session` tool overrides this environment variable if both are specified.

### `GDB_MCP_LOG_LEVEL`

Set the logging level for the server.

**Default**: `INFO`
**Options**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

**Example**:
```bash
export GDB_MCP_LOG_LEVEL=DEBUG
gdb-mcp-server
```

### SSH Default Parameters

Pre-configure SSH connection parameters so that `gdb_start_session` automatically uses SSH remote mode without needing to pass SSH parameters every time. Tool parameters always override these defaults.

| Environment Variable | Description | Example |
|---------------------|-------------|---------|
| `GDB_SSH_HOST` | Default SSH host | `9.134.194.81` |
| `GDB_SSH_USER` | Default SSH username | `joezzhu` |
| `GDB_SSH_PORT` | Default SSH port (default: 22) | `36000` |
| `GDB_SSH_KEY` | Default SSH private key path | `D:\joezzhu\pc7.key` |
| `GDB_SSH_OPTIONS` | Extra SSH options (comma-separated) | `-o,ProxyJump=bastion` |

**Example MCP client configuration with SSH defaults:**

```json
{
  "mcpServers": {
    "gdb": {
      "command": "gdb-mcp-server",
      "env": {
        "GDB_SSH_HOST": "9.134.194.81",
        "GDB_SSH_USER": "joezzhu",
        "GDB_SSH_PORT": "36000",
        "GDB_SSH_KEY": "D:\\joezzhu\\pc7.key"
      }
    }
  }
}
```

With this configuration, AI just needs to provide `program`/`core` paths — SSH connection is automatic:
```json
{"program": "/home/user/myapp", "core": "/home/user/core.12345"}
```

## Available Tools

The GDB MCP Server provides 22 tools for controlling GDB debugging sessions:

**Session Management:**
- `gdb_start_session` - Start a new GDB session with optional initialization
- `gdb_execute_command` - Execute GDB commands (CLI or MI format)
- `gdb_call_function` - Call a function in the target process (dedicated tool for separate permissioning)
- `gdb_get_status` - Get current session status
- `gdb_stop_session` - Stop the current session

**Thread & Frame Navigation:**
- `gdb_get_threads` - List all threads
- `gdb_select_thread` - Select a specific thread
- `gdb_get_backtrace` - Get stack trace for a thread
- `gdb_select_frame` - Select a specific stack frame
- `gdb_get_frame_info` - Get information about the current frame

**Breakpoint Management:**
- `gdb_set_breakpoint` - Set breakpoints with optional conditions
- `gdb_list_breakpoints` - List all breakpoints with structured data
- `gdb_delete_breakpoint` - Delete a breakpoint by number
- `gdb_enable_breakpoint` - Enable a breakpoint
- `gdb_disable_breakpoint` - Disable a breakpoint

**Execution Control:**
- `gdb_continue` - Continue execution
- `gdb_step` - Step into functions
- `gdb_next` - Step over functions
- `gdb_interrupt` - Pause a running program

**Data Inspection:**
- `gdb_evaluate_expression` - Evaluate expressions
- `gdb_get_variables` - Get local variables
- `gdb_get_registers` - Get CPU registers

**For detailed documentation of each tool including parameters, return values, and examples, see [TOOLS.md](TOOLS.md).**

## Usage Examples

### Example 1: SSH Remote Debugging

**User**: "Debug the program /home/dev/myapp on server devbox, set a breakpoint at main and run."

**AI Actions**:
1. Start session with SSH parameters:
```json
{
  "program": "/home/dev/myapp",
  "ssh_host": "devbox",
  "ssh_user": "dev"
}
```
2. Set breakpoint: `gdb_set_breakpoint` with `location="main"`
3. Run: `gdb_execute_command` with `command="run"`

### Example 2: Remote Core Dump Analysis

**User**: "Load the core dump at /tmp/core.12345 on server 10.0.0.5, set the sysroot to /opt/sysroot, and tell me how many threads there were when it crashed."

**AI Actions**:
1. Start session with SSH and init commands:
```json
{
  "program": "/path/to/executable",
  "core": "/tmp/core.12345",
  "ssh_host": "10.0.0.5",
  "ssh_user": "root",
  "init_commands": [
    "set sysroot /opt/sysroot"
  ]
}
```
2. Get threads: `gdb_get_threads`
3. Report: "There were 8 threads when the program crashed."

### Example 3: Conditional Breakpoint Investigation

**User**: "Set a breakpoint at process_data but only when the count variable is greater than 100, then continue execution."

**AI Actions**:
1. Set conditional breakpoint:
```json
{
  "location": "process_data",
  "condition": "count > 100"
}
```
2. Continue execution: `gdb_continue`
3. When hit, inspect state

**For more detailed usage examples and workflows, see [examples/USAGE_GUIDE.md](examples/USAGE_GUIDE.md) and [examples/README.md](examples/README.md).**

## Advanced Usage

### Custom GDB Initialization Scripts

Create a `.gdb` file with your setup commands:

```gdb
# setup.gdb
file /path/to/myprogram
core-file /path/to/core

# Set up symbol paths
set sysroot /opt/sysroot
set solib-search-path /opt/libs:/usr/local/lib

# Convenience settings
set print pretty on
set print array on
set pagination off
```

Then use it:
```json
{
  "init_commands": ["source setup.gdb"]
}
```

### Python Initialization Scripts

You can also use GDB's Python API:

```python
# init.py
import gdb
gdb.execute("file /path/to/program")
gdb.execute("core-file /path/to/core")
# Custom analysis
```

Use with:
```json
{
  "init_commands": ["source init.py"]
}
```

### Working with Running Processes

While this server primarily works with core dumps and executables, you can attach to running processes:

```json
{
  "init_commands": [
    "attach 12345"  // PID of running process
  ]
}
```

Note: This requires appropriate permissions (usually root or same user).

## Troubleshooting

### Common Issues

**GDB Not Found**
```bash
which gdb
gdb --version
```

**Timeout Errors / Commands Not Responding**

The program is likely still running! When a program is running, GDB is busy and won't respond to other commands.

**Solution:** Use `gdb_interrupt` to pause the running program, then other commands will work.

**Program States:**
- **Not started**: Use `gdb_execute_command` with "run" or "start"
- **Running**: Program is executing - use `gdb_interrupt` to pause it
- **Paused** (at breakpoint): Use `gdb_continue`, `gdb_step`, `gdb_next`, inspect variables
- **Finished**: Program has exited - restart with "run" if needed

**Missing Debug Symbols**

Always check the `warnings` field in `gdb_start_session` response! Compile your programs with the `-g` flag.

**For detailed troubleshooting, installation issues, and more solutions, see [INSTALL.md](INSTALL.md#troubleshooting).**

## How It Works

1. **GDB/MI Protocol**: The server communicates with GDB using the Machine Interface (MI) protocol, the same interface used by IDEs like VS Code and CLion.

2. **Built-in MI Parser**: A self-contained GDB/MI output parser handles all protocol details and response parsing — no external GDB library dependencies.

3. **Dual-Mode Process Controller**: An abstraction layer supports both local subprocess and SSH remote connections:
   - **LocalController**: Starts GDB directly via `subprocess.Popen`
   - **SSHController**: Starts GDB on a remote server via `ssh` subprocess, with MI protocol transparently tunneled through SSH stdin/stdout

4. **MCP Integration**: The server exposes GDB functionality as MCP tools, allowing AI assistants to:
   - Understand the available debugging operations
   - Execute commands with proper parameters
   - Interpret structured responses

5. **Session Management**: Multiple GDB sessions can be maintained simultaneously, allowing stateful debugging across multiple tool calls.

## Contributing

Contributions welcome! Areas for improvement:
- Additional GDB commands (e.g., watchpoints, memory inspection)
- Better error handling and recovery
- Enhanced output formatting

## License

MIT

## References

- [GDB Machine Interface (MI)](https://sourceware.org/gdb/current/onlinedocs/gdb/GDB_002fMI.html)
- [Model Context Protocol](https://modelcontextprotocol.io/)
