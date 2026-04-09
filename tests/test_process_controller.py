"""Unit tests for process_controller module."""

import subprocess
import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from gdb_mcp.process_controller import (
    GDBProcessController,
    LocalController,
    SSHController,
)


class TestLocalController:
    """Test cases for LocalController."""

    def test_init(self):
        """Test LocalController initialization."""
        ctrl = LocalController(command=["gdb", "--quiet", "--interpreter=mi"])
        assert ctrl._command == ["gdb", "--quiet", "--interpreter=mi"]
        assert ctrl._process is None
        assert ctrl.pid is None

    @patch("gdb_mcp.process_controller.subprocess.Popen")
    def test_start(self, mock_popen):
        """Test starting a local GDB process."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        ctrl = LocalController(command=["gdb", "--quiet", "--interpreter=mi"])
        ctrl.start()

        mock_popen.assert_called_once_with(
            ["gdb", "--quiet", "--interpreter=mi"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        assert ctrl.pid == 12345

    @patch("gdb_mcp.process_controller.subprocess.Popen")
    def test_write(self, mock_popen):
        """Test writing to GDB stdin."""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process

        ctrl = LocalController(command=["gdb"])
        ctrl.start()
        ctrl.write("test command\n")

        mock_process.stdin.write.assert_called_once_with(b"test command\n")
        mock_process.stdin.flush.assert_called_once()

    def test_write_no_process(self):
        """Test writing when no process is running."""
        ctrl = LocalController(command=["gdb"])
        with pytest.raises(BrokenPipeError):
            ctrl.write("test\n")

    @patch("gdb_mcp.process_controller.subprocess.Popen")
    def test_is_alive_running(self, mock_popen):
        """Test is_alive when process is running."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Still running
        mock_popen.return_value = mock_process

        ctrl = LocalController(command=["gdb"])
        ctrl.start()
        assert ctrl.is_alive() is True

    @patch("gdb_mcp.process_controller.subprocess.Popen")
    def test_is_alive_exited(self, mock_popen):
        """Test is_alive when process has exited."""
        mock_process = MagicMock()
        mock_process.poll.return_value = 0  # Exited
        mock_popen.return_value = mock_process

        ctrl = LocalController(command=["gdb"])
        ctrl.start()
        assert ctrl.is_alive() is False

    def test_is_alive_no_process(self):
        """Test is_alive when no process exists."""
        ctrl = LocalController(command=["gdb"])
        assert ctrl.is_alive() is False

    @patch("gdb_mcp.process_controller.subprocess.Popen")
    def test_exit(self, mock_popen):
        """Test exiting the GDB process."""
        mock_process = MagicMock()
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        ctrl = LocalController(command=["gdb"])
        ctrl.start()
        ctrl.exit()

        # Should try graceful exit first
        mock_process.stdin.write.assert_called_with(b"-gdb-exit\n")
        assert ctrl._process is None

    def test_exit_no_process(self):
        """Test exit when no process is running."""
        ctrl = LocalController(command=["gdb"])
        ctrl.exit()  # Should not raise

    @patch("gdb_mcp.process_controller.subprocess.Popen")
    def test_process_property(self, mock_popen):
        """Test process property."""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process

        ctrl = LocalController(command=["gdb"])
        ctrl.start()
        assert ctrl.process is mock_process


class TestSSHController:
    """Test cases for SSHController."""

    def test_init(self):
        """Test SSHController initialization."""
        ctrl = SSHController(
            ssh_host="devserver",
            gdb_command=["gdb", "--quiet", "--interpreter=mi", "/path/to/app"],
            ssh_user="developer",
            ssh_port=2222,
            ssh_key="/home/user/.ssh/id_rsa",
        )
        assert ctrl._ssh_host == "devserver"
        assert ctrl._ssh_user == "developer"
        assert ctrl._ssh_port == 2222
        assert ctrl._ssh_key == "/home/user/.ssh/id_rsa"
        assert ctrl._process is None

    def test_build_ssh_command_basic(self):
        """Test SSH command building with basic parameters."""
        ctrl = SSHController(
            ssh_host="myhost",
            gdb_command=["gdb", "--quiet", "--interpreter=mi"],
        )
        cmd = ctrl._build_ssh_command()

        assert cmd[0] == "ssh"
        assert "myhost" in cmd
        assert "-o" in cmd
        assert "BatchMode=yes" in cmd
        # Should include -tt for pseudo-TTY
        assert "-tt" in cmd

    def test_build_ssh_command_with_user(self):
        """Test SSH command building with user."""
        ctrl = SSHController(
            ssh_host="myhost",
            gdb_command=["gdb", "--quiet", "--interpreter=mi"],
            ssh_user="testuser",
        )
        cmd = ctrl._build_ssh_command()

        assert "testuser@myhost" in cmd

    def test_build_ssh_command_with_port(self):
        """Test SSH command building with non-default port."""
        ctrl = SSHController(
            ssh_host="myhost",
            gdb_command=["gdb", "--quiet", "--interpreter=mi"],
            ssh_port=2222,
        )
        cmd = ctrl._build_ssh_command()

        # Find -p and its value
        idx = cmd.index("-p")
        assert cmd[idx + 1] == "2222"

    def test_build_ssh_command_with_key(self):
        """Test SSH command building with key file."""
        ctrl = SSHController(
            ssh_host="myhost",
            gdb_command=["gdb", "--quiet", "--interpreter=mi"],
            ssh_key="/path/to/key",
        )
        cmd = ctrl._build_ssh_command()

        idx = cmd.index("-i")
        assert cmd[idx + 1] == "/path/to/key"

    def test_build_ssh_command_with_working_dir(self):
        """Test SSH command building with working directory."""
        ctrl = SSHController(
            ssh_host="myhost",
            gdb_command=["gdb", "--quiet", "--interpreter=mi"],
            working_dir="/home/user/project",
        )
        cmd = ctrl._build_ssh_command()

        # The remote command should include cd
        remote_cmd = cmd[-1]
        assert "cd" in remote_cmd
        assert "/home/user/project" in remote_cmd

    def test_build_ssh_command_with_ssh_options(self):
        """Test SSH command building with extra options."""
        ctrl = SSHController(
            ssh_host="myhost",
            gdb_command=["gdb", "--quiet", "--interpreter=mi"],
            ssh_options=["-o", "ProxyJump=bastion", "-o", "ConnectTimeout=10"],
        )
        cmd = ctrl._build_ssh_command()

        # Extra options should be included
        assert "ProxyJump=bastion" in cmd
        assert "ConnectTimeout=10" in cmd

    def test_build_ssh_command_default_port_not_included(self):
        """Test SSH command building with default port (22) doesn't add -p."""
        ctrl = SSHController(
            ssh_host="myhost",
            gdb_command=["gdb", "--quiet", "--interpreter=mi"],
            ssh_port=22,
        )
        cmd = ctrl._build_ssh_command()

        assert "-p" not in cmd

    @patch("gdb_mcp.process_controller.subprocess.Popen")
    def test_start(self, mock_popen):
        """Test starting an SSH connection."""
        mock_process = MagicMock()
        mock_process.pid = 54321
        mock_popen.return_value = mock_process

        ctrl = SSHController(
            ssh_host="myhost",
            gdb_command=["gdb", "--quiet", "--interpreter=mi"],
        )
        ctrl.start()

        assert mock_popen.called
        assert ctrl.pid == 54321

    @patch("gdb_mcp.process_controller.subprocess.Popen")
    def test_write(self, mock_popen):
        """Test writing to remote GDB via SSH."""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process

        ctrl = SSHController(
            ssh_host="myhost",
            gdb_command=["gdb"],
        )
        ctrl.start()
        ctrl.write("-exec-run\n")

        mock_process.stdin.write.assert_called_once_with(b"-exec-run\n")
        mock_process.stdin.flush.assert_called_once()

    @patch("gdb_mcp.process_controller.subprocess.Popen")
    def test_interrupt(self, mock_popen):
        """Test interrupt sends -exec-interrupt via stdin."""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process

        ctrl = SSHController(
            ssh_host="myhost",
            gdb_command=["gdb"],
        )
        ctrl.start()
        ctrl.interrupt()

        # Should write -exec-interrupt
        mock_process.stdin.write.assert_called_with(b"-exec-interrupt\n")

    @patch("gdb_mcp.process_controller.subprocess.Popen")
    def test_is_alive(self, mock_popen):
        """Test is_alive for SSH controller."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process

        ctrl = SSHController(
            ssh_host="myhost",
            gdb_command=["gdb"],
        )
        ctrl.start()
        assert ctrl.is_alive() is True

        mock_process.poll.return_value = 0
        assert ctrl.is_alive() is False

    @patch("gdb_mcp.process_controller.subprocess.Popen")
    def test_exit(self, mock_popen):
        """Test SSH controller exit."""
        mock_process = MagicMock()
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        ctrl = SSHController(
            ssh_host="myhost",
            gdb_command=["gdb"],
        )
        ctrl.start()
        ctrl.exit()

        mock_process.stdin.write.assert_called_with(b"-gdb-exit\n")
        assert ctrl._process is None

    def test_is_ssh_noise(self):
        """Test SSH noise detection."""
        assert SSHController._is_ssh_noise("Connection to host closed.") is True
        assert SSHController._is_ssh_noise("Warning: Permanently added 'host' to known hosts.") is True
        assert SSHController._is_ssh_noise("~\"Reading symbols...\"") is False
        assert SSHController._is_ssh_noise("(gdb)") is False

    def test_shell_quote(self):
        """Test shell quoting."""
        assert SSHController._shell_quote("/simple/path") == "'/simple/path'"
        assert SSHController._shell_quote("path with spaces") == "'path with spaces'"
        assert SSHController._shell_quote("it's a test") == "'it'\\''s a test'"
