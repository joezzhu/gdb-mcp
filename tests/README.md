# Tests

## Run Tests

```bash
pip install -e ".[dev]"

# All unit tests
pytest -m "not integration"

# All tests including integration (requires GDB)
pytest

# Specific file
pytest tests/test_process_controller.py -v
```

## Test Files

| File | Tests | Description |
|------|-------|-------------|
| `test_gdb_interface.py` | 44 | GDBSession: init, start, commands, breakpoints, threads, execution, errors, SSH mode |
| `test_process_controller.py` | 25 | LocalController + SSHController: start, write, read, interrupt, exit, SSH command building |
| `test_server.py` | 28 | Pydantic models: StartSessionArgs (including SSH params), validation |
| `test_session_manager.py` | 6 | SessionManager: create, get, remove, thread safety |
| `test_session_routing.py` | 7 | call_tool routing: session lookup, expired session error, stop cleanup |
| `test_gdb_integration.py` | ~25 | Integration: real GDB + compiled C++ program (requires GDB) |
| `test_multi_session.py` | ~8 | Integration: multi-session isolation (requires GDB) |

## Markers

- `@pytest.mark.integration` — requires real GDB installed
- `@pytest.mark.slow` — long-running tests

## Mock Patterns

Tests mock `GDBProcessController` (not the old `GdbController` from pygdbmi):

```python
from gdb_mcp.process_controller import GDBProcessController

# Mock the controller directly
session.controller = MagicMock(spec=GDBProcessController)

# Mock LocalController class for start() tests
@patch("gdb_mcp.gdb_interface.LocalController")

# Mock SSHController class for SSH mode tests
@patch("gdb_mcp.gdb_interface.SSHController")

# Mock session_manager for routing tests (set was_expired for expired session tests)
@patch("gdb_mcp.server.session_manager")
mock_manager.was_expired.return_value = False
```
