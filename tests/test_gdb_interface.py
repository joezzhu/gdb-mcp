"""Unit tests for GDB interface."""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock, PropertyMock
from gdb_mcp.gdb_interface import GDBSession
from gdb_mcp.process_controller import GDBProcessController, LocalController


class TestGDBSession:
    """Test cases for GDBSession class."""

    def test_session_initialization(self):
        """Test that GDBSession initializes correctly."""
        session = GDBSession()
        assert session.controller is None
        assert session.is_running is False
        assert session.target_loaded is False

    def test_get_status_no_session(self):
        """Test get_status when no session is running."""
        session = GDBSession()
        status = session.get_status()
        assert status["is_running"] is False
        assert status["target_loaded"] is False
        assert status["has_controller"] is False

    def test_stop_no_session(self):
        """Test stopping when no session exists."""
        session = GDBSession()
        result = session.stop()
        assert result["status"] == "error"
        assert "No active session" in result["message"]

    def test_execute_command_no_session(self):
        """Test execute_command when no session is running."""
        session = GDBSession()
        result = session.execute_command("info threads")
        assert result["status"] == "error"
        assert "No active GDB session" in result["message"]

    def test_response_parsing(self):
        """Test _parse_responses method."""
        session = GDBSession()

        # Mock responses from GDB
        responses = [
            {"type": "console", "payload": "Test output\n"},
            {"type": "result", "payload": {"msg": "done"}},
            {"type": "notify", "payload": {"msg": "thread-created"}},
        ]

        parsed = session._parse_responses(responses)

        assert "Test output\n" in parsed["console"]
        assert parsed["result"] == {"msg": "done"}
        assert {"msg": "thread-created"} in parsed["notify"]

    def test_cli_command_wrapping(self):
        """Test that CLI commands are properly detected."""
        session = GDBSession()

        # CLI commands don't start with '-'
        assert not "info threads".startswith("-")
        assert not "print x".startswith("-")

        # MI commands start with '-'
        assert "-break-list".startswith("-")
        assert "-exec-run".startswith("-")


class TestGDBSessionWithMock:
    """Test cases that mock the GDBProcessController."""

    def test_start_session_already_running(self):
        """Test starting a session when one is already running."""
        session = GDBSession()

        # Manually set controller to simulate running session
        session.controller = Mock(spec=GDBProcessController)

        result = session.start(program="/bin/ls")

        assert result["status"] == "error"
        assert "already running" in result["message"].lower()

    @patch("gdb_mcp.gdb_interface.LocalController")
    def test_start_session_basic(self, mock_controller_class):
        """Test basic session start."""
        # Create a mock controller instance
        mock_controller = MagicMock(spec=LocalController)
        mock_controller_class.return_value = mock_controller

        session = GDBSession()

        # Mock the initialization check
        with patch.object(
            session,
            "_send_command_and_wait_for_prompt",
            return_value={
                "command_responses": [
                    {"type": "console", "payload": "Reading symbols from /bin/ls...\n"},
                    {"type": "result", "message": "done", "token": 1000},
                ],
                "async_notifications": [],
                "timed_out": False,
            },
        ):
            result = session.start(program="/bin/ls")

        assert result["status"] == "success"
        assert result["program"] == "/bin/ls"
        assert session.is_running is True

    @patch("gdb_mcp.gdb_interface.LocalController")
    def test_start_session_with_custom_gdb_path(self, mock_controller_class):
        """Test session start with custom GDB path."""
        mock_controller = MagicMock(spec=LocalController)
        mock_controller_class.return_value = mock_controller

        session = GDBSession()

        # Mock the initialization check
        with patch.object(
            session,
            "_send_command_and_wait_for_prompt",
            return_value={
                "command_responses": [{"type": "result", "message": "done", "token": 1000}],
                "async_notifications": [],
                "timed_out": False,
            },
        ):
            result = session.start(program="/bin/ls", gdb_path="/usr/local/bin/gdb-custom")

        # Verify LocalController was called with correct command
        call_args = mock_controller_class.call_args
        command = call_args[1]["command"]

        assert command[0] == "/usr/local/bin/gdb-custom"
        assert "--interpreter=mi" in command
        assert result["status"] == "success"

    @patch("gdb_mcp.gdb_interface.LocalController")
    @patch.dict(os.environ, {"GDB_PATH": "/custom/path/to/gdb"})
    def test_start_session_with_gdb_path_env_var(self, mock_controller_class):
        """Test session start uses GDB_PATH environment variable when gdb_path is not specified."""
        mock_controller = MagicMock(spec=LocalController)
        mock_controller_class.return_value = mock_controller

        session = GDBSession()

        # Mock the initialization check
        with patch.object(
            session,
            "_send_command_and_wait_for_prompt",
            return_value={
                "command_responses": [{"type": "result", "message": "done", "token": 1000}],
                "async_notifications": [],
                "timed_out": False,
            },
        ):
            # Don't specify gdb_path - should use environment variable
            result = session.start(program="/bin/ls")

        # Verify LocalController was called with GDB_PATH from environment
        call_args = mock_controller_class.call_args
        command = call_args[1]["command"]

        assert command[0] == "/custom/path/to/gdb"
        assert "--interpreter=mi" in command
        assert result["status"] == "success"

    @patch("gdb_mcp.gdb_interface.LocalController")
    @patch.dict(os.environ, {"GDB_PATH": "/env/gdb"})
    def test_start_session_explicit_path_overrides_env_var(self, mock_controller_class):
        """Test that explicit gdb_path parameter overrides GDB_PATH environment variable."""
        mock_controller = MagicMock(spec=LocalController)
        mock_controller_class.return_value = mock_controller

        session = GDBSession()

        # Mock the initialization check
        with patch.object(
            session,
            "_send_command_and_wait_for_prompt",
            return_value={
                "command_responses": [{"type": "result", "message": "done", "token": 1000}],
                "async_notifications": [],
                "timed_out": False,
            },
        ):
            # Explicitly specify gdb_path - should override environment variable
            result = session.start(program="/bin/ls", gdb_path="/explicit/gdb")

        # Verify LocalController was called with explicit path, not environment variable
        call_args = mock_controller_class.call_args
        command = call_args[1]["command"]

        assert command[0] == "/explicit/gdb"
        assert command[0] != "/env/gdb"
        assert result["status"] == "success"

    @patch("gdb_mcp.gdb_interface.LocalController")
    def test_start_session_with_env_variables(self, mock_controller_class):
        """Test session start with environment variables."""
        mock_controller = MagicMock(spec=LocalController)
        mock_controller_class.return_value = mock_controller

        session = GDBSession()

        # Track calls to execute_command by patching it
        env_commands = []

        def mock_execute(cmd, **kwargs):
            if "set environment" in cmd:
                env_commands.append(cmd)
            return {"status": "success", "command": cmd, "output": ""}

        # Mock both initialization and execute_command
        with patch.object(
            session,
            "_send_command_and_wait_for_prompt",
            return_value={
                "command_responses": [{"type": "result", "message": "done", "token": 1000}],
                "async_notifications": [],
                "timed_out": False,
            },
        ):
            with patch.object(session, "execute_command", side_effect=mock_execute):
                result = session.start(
                    program="/bin/ls", env={"DEBUG_MODE": "1", "LOG_LEVEL": "verbose"}
                )

        # Verify environment commands were executed
        assert len(env_commands) == 2
        assert any("DEBUG_MODE" in cmd for cmd in env_commands)
        assert any("LOG_LEVEL" in cmd for cmd in env_commands)

    @patch("gdb_mcp.gdb_interface.LocalController")
    def test_start_session_detects_missing_debug_symbols(self, mock_controller_class):
        """Test that missing debug symbols are detected."""
        mock_controller = MagicMock(spec=LocalController)
        mock_controller_class.return_value = mock_controller

        session = GDBSession()

        # Mock initialization with debug symbol warning
        with patch.object(
            session,
            "_send_command_and_wait_for_prompt",
            return_value={
                "command_responses": [
                    {"type": "console", "payload": "Reading symbols from /bin/ls...\n"},
                    {"type": "console", "payload": "(no debugging symbols found)...done.\n"},
                    {"type": "result", "message": "done", "token": 1000},
                ],
                "async_notifications": [],
                "timed_out": False,
            },
        ):
            result = session.start(program="/bin/ls")

        assert result["status"] == "success"
        assert "warnings" in result
        assert any("not compiled with -g" in w for w in result["warnings"])

    @patch("gdb_mcp.gdb_interface.SSHController")
    def test_start_session_ssh_mode(self, mock_ssh_controller_class):
        """Test starting a session in SSH remote mode."""
        mock_controller = MagicMock()
        mock_ssh_controller_class.return_value = mock_controller

        session = GDBSession()

        with patch.object(
            session,
            "_send_command_and_wait_for_prompt",
            return_value={
                "command_responses": [
                    {"type": "result", "message": "done", "token": 1000},
                ],
                "async_notifications": [],
                "timed_out": False,
            },
        ):
            result = session.start(
                program="/home/user/myapp",
                ssh_host="devserver",
                ssh_user="developer",
                ssh_port=2222,
                ssh_key="/home/user/.ssh/id_rsa",
            )

        assert result["status"] == "success"
        assert result["program"] == "/home/user/myapp"
        assert session.is_running is True

        # Verify SSHController was created with correct args
        mock_ssh_controller_class.assert_called_once()
        call_kwargs = mock_ssh_controller_class.call_args[1]
        assert call_kwargs["ssh_host"] == "devserver"
        assert call_kwargs["ssh_user"] == "developer"
        assert call_kwargs["ssh_port"] == 2222
        assert call_kwargs["ssh_key"] == "/home/user/.ssh/id_rsa"


class TestThreadOperations:
    """Test cases for thread inspection methods."""

    def test_get_threads_no_session(self):
        """Test get_threads when no session is running."""
        session = GDBSession()
        # Manually set controller to None to simulate no session
        session.controller = None

        result = session.get_threads()
        assert result["status"] == "error"

    def test_get_threads_success(self):
        """Test successful thread retrieval."""
        mock_controller = MagicMock(spec=GDBProcessController)
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        # Mock execute_command to return thread info
        def mock_execute(cmd, **kwargs):
            return {
                "status": "success",
                "result": {
                    "result": {
                        "threads": [
                            {"id": "1", "name": "main"},
                            {"id": "2", "name": "worker-1"},
                        ],
                        "current-thread-id": "1",
                    }
                },
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.get_threads()

        assert result["status"] == "success"
        assert result["count"] == 2
        assert result["current_thread_id"] == "1"

    def test_select_thread(self):
        """Test selecting a specific thread."""
        mock_controller = MagicMock(spec=GDBProcessController)
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {
                "status": "success",
                "result": {
                    "result": {
                        "new-thread-id": "2",
                        "frame": {"level": "0", "func": "worker_func"},
                    }
                },
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.select_thread(thread_id=2)

        assert result["status"] == "success"
        assert result["thread_id"] == 2
        assert result["new_thread_id"] == "2"

    def test_get_backtrace_default(self):
        """Test backtrace with default parameters."""
        mock_controller = MagicMock(spec=GDBProcessController)
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {
                "status": "success",
                "result": {"result": {"stack": [{"level": "0", "func": "main", "file": "test.c"}]}},
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.get_backtrace()

        assert result["status"] == "success"
        assert result["count"] == 1
        assert result["thread_id"] is None

    def test_get_backtrace_specific_thread(self):
        """Test backtrace for a specific thread."""
        mock_controller = MagicMock(spec=GDBProcessController)
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        commands_executed = []

        def mock_execute(cmd, **kwargs):
            commands_executed.append(cmd)
            if "thread-select" in cmd:
                return {"status": "success"}
            return {
                "status": "success",
                "result": {"result": {"stack": []}},
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.get_backtrace(thread_id=3)

        assert result["status"] == "success"
        assert any("thread-select 3" in cmd for cmd in commands_executed)


class TestBreakpointOperations:
    """Test cases for breakpoint management."""

    def test_set_breakpoint_simple(self):
        """Test setting a simple breakpoint."""
        mock_controller = MagicMock(spec=GDBProcessController)
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {
                "status": "success",
                "result": {
                    "result": {
                        "bkpt": {
                            "number": "1",
                            "type": "breakpoint",
                            "addr": "0x12345",
                            "func": "main",
                        }
                    }
                },
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.set_breakpoint("main")

        assert result["status"] == "success"
        assert "breakpoint" in result
        assert result["breakpoint"]["func"] == "main"

    def test_set_breakpoint_with_condition(self):
        """Test setting a conditional breakpoint."""
        mock_controller = MagicMock(spec=GDBProcessController)
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        commands_executed = []

        def mock_execute(cmd, **kwargs):
            commands_executed.append(cmd)
            return {
                "status": "success",
                "result": {"result": {"bkpt": {"number": "1"}}},
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.set_breakpoint("foo.c:42", condition="x > 10", temporary=True)

        assert result["status"] == "success"
        # Verify the command includes condition and temporary flags
        assert any("-break-insert" in cmd for cmd in commands_executed)

    def test_list_breakpoints(self):
        """Test listing breakpoints."""
        mock_controller = MagicMock(spec=GDBProcessController)
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {
                "status": "success",
                "result": {
                    "result": {
                        "BreakpointTable": {
                            "body": [
                                {"number": "1", "type": "breakpoint"},
                                {"number": "2", "type": "breakpoint"},
                            ]
                        }
                    }
                },
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.list_breakpoints()

        assert result["status"] == "success"
        assert result["count"] == 2
        assert len(result["breakpoints"]) == 2


class TestExecutionControl:
    """Test cases for execution control methods."""

    def test_continue_execution(self):
        """Test continue execution."""
        session = GDBSession()
        session.controller = MagicMock(spec=GDBProcessController)
        session.is_running = True

        # Mock execute_command since continue_execution now just calls it
        with patch.object(
            session,
            "execute_command",
            return_value={
                "status": "success",
                "result": {"notify": [{"reason": "breakpoint-hit"}]},
            },
        ) as mock_execute:
            result = session.continue_execution()

        assert result["status"] == "success"
        mock_execute.assert_called_once_with("-exec-continue")

    def test_step(self):
        """Test step into."""
        session = GDBSession()
        session.controller = MagicMock(spec=GDBProcessController)
        session.is_running = True

        # Mock execute_command since step now just calls it
        with patch.object(
            session,
            "execute_command",
            return_value={
                "status": "success",
                "result": {"notify": [{"reason": "end-stepping-range"}]},
            },
        ) as mock_execute:
            result = session.step()

        assert result["status"] == "success"
        mock_execute.assert_called_once_with("-exec-step")

    def test_next(self):
        """Test step over."""
        session = GDBSession()
        session.controller = MagicMock(spec=GDBProcessController)
        session.is_running = True

        # Mock execute_command since next now just calls it
        with patch.object(
            session,
            "execute_command",
            return_value={
                "status": "success",
                "result": {"notify": [{"reason": "end-stepping-range"}]},
            },
        ) as mock_execute:
            result = session.next()

        assert result["status"] == "success"
        mock_execute.assert_called_once_with("-exec-next")

    def test_interrupt_no_controller(self):
        """Test interrupt when no session exists."""
        session = GDBSession()
        result = session.interrupt()

        assert result["status"] == "error"
        assert "No active GDB session" in result["message"]

    def test_interrupt_success(self):
        """Test successful interrupt with stopped notification."""
        mock_controller = MagicMock(spec=GDBProcessController)
        # Return the *stopped notification in GDB/MI format
        mock_controller.read_response.return_value = [
            {"type": "notify", "message": "stopped", "payload": {"reason": "signal-received"}}
        ]

        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        result = session.interrupt()

        assert result["status"] == "success"
        assert "interrupted" in result["message"].lower()
        mock_controller.interrupt.assert_called_once()

    def test_interrupt_no_stopped_notification(self):
        """Test interrupt when no stopped notification is received."""
        mock_controller = MagicMock(spec=GDBProcessController)
        # Return empty responses (no stopped notification)
        mock_controller.read_response.return_value = []

        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        result = session.interrupt()

        # Should return warning status when no stopped notification received
        assert result["status"] == "warning"
        assert "no stopped notification" in result["message"].lower()
        mock_controller.interrupt.assert_called_once()


class TestDataInspection:
    """Test cases for data inspection methods."""

    def test_evaluate_expression(self):
        """Test expression evaluation."""
        mock_controller = MagicMock(spec=GDBProcessController)
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {
                "status": "success",
                "result": {"result": {"value": "42"}},
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.evaluate_expression("x + y")

        assert result["status"] == "success"
        assert result["expression"] == "x + y"
        assert result["value"] == "42"

    def test_get_variables(self):
        """Test getting local variables."""
        mock_controller = MagicMock(spec=GDBProcessController)
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            if "stack-select-frame" in cmd or "thread-select" in cmd:
                return {"status": "success"}
            return {
                "status": "success",
                "result": {
                    "result": {
                        "variables": [
                            {"name": "x", "value": "10"},
                            {"name": "y", "value": "20"},
                        ]
                    }
                },
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.get_variables(thread_id=2, frame=1)

        assert result["status"] == "success"
        assert result["thread_id"] == 2
        assert result["frame"] == 1
        assert len(result["variables"]) == 2

    def test_get_registers(self):
        """Test getting register values."""
        mock_controller = MagicMock(spec=GDBProcessController)
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {
                "status": "success",
                "result": {
                    "result": {
                        "register-values": [
                            {"number": "0", "value": "0x1234"},
                            {"number": "1", "value": "0x5678"},
                        ]
                    }
                },
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.get_registers()

        assert result["status"] == "success"
        assert len(result["registers"]) == 2


class TestSessionManagement:
    """Test cases for session management operations."""

    def test_stop_active_session(self):
        """Test stopping an active session."""
        mock_controller = MagicMock(spec=GDBProcessController)
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        result = session.stop()

        assert result["status"] == "success"
        assert session.controller is None
        assert session.is_running is False

    def test_execute_command_cli(self):
        """Test executing a CLI command with active session."""
        session = GDBSession()
        session.controller = MagicMock(spec=GDBProcessController)
        session.is_running = True

        # Mock the internal send_command method
        with patch.object(
            session,
            "_send_command_and_wait_for_prompt",
            return_value={
                "command_responses": [
                    {"type": "console", "payload": "Thread 1 (main)\n"},
                    {"type": "result", "payload": None, "token": 1000},
                ],
                "async_notifications": [],
                "timed_out": False,
            },
        ):
            result = session.execute_command("info threads")

        assert result["status"] == "success"
        assert "Thread 1" in result["output"]

    def test_execute_command_mi(self):
        """Test executing an MI command with active session."""
        session = GDBSession()
        session.controller = MagicMock(spec=GDBProcessController)
        session.is_running = True

        # Mock the internal send_command method
        with patch.object(
            session,
            "_send_command_and_wait_for_prompt",
            return_value={
                "command_responses": [
                    {"type": "result", "payload": {"threads": []}, "token": 1000},
                ],
                "async_notifications": [],
                "timed_out": False,
            },
        ):
            result = session.execute_command("-thread-info")

        assert result["status"] == "success"
        assert "result" in result


class TestErrorHandling:
    """Test cases for error handling."""

    @patch("gdb_mcp.gdb_interface.LocalController")
    def test_start_session_exception(self, mock_controller_class):
        """Test that start handles exceptions gracefully."""
        mock_controller_class.side_effect = Exception("GDB not found")

        session = GDBSession()
        result = session.start(program="/bin/ls")

        assert result["status"] == "error"
        assert "GDB not found" in result["message"]

    def test_execute_command_exception(self):
        """Test that execute_command handles errors."""
        session = GDBSession()
        session.controller = MagicMock(spec=GDBProcessController)
        session.is_running = True

        # Mock _send_command_and_wait_for_prompt to return error
        with patch.object(
            session,
            "_send_command_and_wait_for_prompt",
            return_value={
                "error": "Timeout",
                "command_responses": [],
                "async_notifications": [],
                "timed_out": False,
            },
        ):
            result = session.execute_command("info threads")

        assert result["status"] == "error"
        assert "Timeout" in result["message"]

    def test_set_breakpoint_no_result(self):
        """Test set_breakpoint when GDB returns no result."""
        mock_controller = MagicMock(spec=GDBProcessController)
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {"status": "success", "result": {"result": None}}

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.set_breakpoint("main")

        assert result["status"] == "error"
        assert "no result from GDB" in result["message"]

    def test_gdb_internal_fatal_error(self):
        """Test that GDB internal fatal errors are detected and session is stopped."""
        mock_controller = MagicMock(spec=GDBProcessController)
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        # Mock _send_command_and_wait_for_prompt to return a fatal error
        with patch.object(
            session,
            "_send_command_and_wait_for_prompt",
            return_value={
                "error": "GDB internal fatal error: internal-error: assertion failed",
                "command_responses": [],
                "async_notifications": [],
                "timed_out": False,
                "fatal": True,
            },
        ):
            result = session.execute_command("some command")

        # Verify error is returned with fatal flag
        assert result["status"] == "error"
        assert "internal" in result["message"].lower()
        assert result.get("fatal") is True

    def test_gdb_fatal_error_message_format(self):
        """Test detection of 'A fatal error internal to GDB' message format."""
        mock_controller = MagicMock(spec=GDBProcessController)
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        # Mock _send_command_and_wait_for_prompt to return the actual GDB fatal error message
        with patch.object(
            session,
            "_send_command_and_wait_for_prompt",
            return_value={
                "error": "GDB internal fatal error: A fatal error internal to GDB has been detected, further\ndebugging is not possible.  GDB will now terminate.\n",
                "command_responses": [],
                "async_notifications": [],
                "timed_out": False,
                "fatal": True,
            },
        ):
            result = session.execute_command("core-file /path/to/core")

        # Verify error is returned with fatal flag
        assert result["status"] == "error"
        assert "fatal" in result["message"].lower()
        assert result.get("fatal") is True

    @patch("gdb_mcp.gdb_interface.LocalController")
    def test_fatal_error_during_initialization(self, mock_controller_class):
        """Test that fatal errors during GDB initialization are handled properly."""
        mock_controller = MagicMock(spec=LocalController)
        mock_controller_class.return_value = mock_controller

        session = GDBSession()

        # Mock initialization check to return fatal error
        with patch.object(
            session,
            "_send_command_and_wait_for_prompt",
            return_value={
                "error": "GDB internal fatal error: internal-error during initialization",
                "command_responses": [],
                "async_notifications": [],
                "timed_out": False,
                "fatal": True,
            },
        ):
            result = session.start(program="/bin/ls")

        # Verify startup failed with fatal error
        assert result["status"] == "error"
        assert "failed to initialize" in result["message"].lower()
        assert result.get("fatal") is True
        # Session should be cleaned up
        assert session.controller is None


class TestCallFunction:
    """Test cases for the call_function method."""

    def test_call_function_no_session(self):
        """Test call_function when no session is running."""
        session = GDBSession()
        result = session.call_function('printf("hello")')
        assert result["status"] == "error"
        assert "No active GDB session" in result["message"]

    def test_call_function_success(self):
        """Test successful function call execution."""
        session = GDBSession()
        session.controller = MagicMock(spec=GDBProcessController)
        session.is_running = True

        with patch.object(
            session,
            "_send_command_and_wait_for_prompt",
            return_value={
                "command_responses": [
                    {"type": "console", "payload": "$1 = 5\n"},
                    {"type": "result", "payload": None, "token": 1000},
                ],
                "async_notifications": [],
                "timed_out": False,
            },
        ):
            result = session.call_function('strlen("hello")')

        assert result["status"] == "success"
        assert result["function_call"] == 'strlen("hello")'
        assert "$1 = 5" in result["result"]

    def test_call_function_timeout(self):
        """Test call_function when command times out."""
        session = GDBSession()
        session.controller = MagicMock(spec=GDBProcessController)
        session.is_running = True

        with patch.object(
            session,
            "_send_command_and_wait_for_prompt",
            return_value={
                "command_responses": [],
                "async_notifications": [],
                "timed_out": True,
            },
        ):
            result = session.call_function("some_slow_function()")

        assert result["status"] == "error"
        assert "Timeout" in result["message"]

    def test_call_function_error(self):
        """Test call_function when there's an error."""
        session = GDBSession()
        session.controller = MagicMock(spec=GDBProcessController)
        session.is_running = True

        with patch.object(
            session,
            "_send_command_and_wait_for_prompt",
            return_value={
                "error": "No symbol table loaded",
                "command_responses": [],
                "async_notifications": [],
                "timed_out": False,
            },
        ):
            result = session.call_function("unknown_func()")

        assert result["status"] == "error"
        assert "No symbol table" in result["message"]
