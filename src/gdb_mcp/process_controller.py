"""GDB process controller abstraction layer.

Provides a unified interface for managing GDB processes, supporting both
local subprocess and SSH remote connections.

Classes:
    GDBProcessController: Abstract base class defining the interface.
    LocalController: Manages a local GDB subprocess via subprocess.Popen.
    SSHController: Manages a remote GDB process via SSH subprocess.
"""

import logging
import os
import signal
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .mi_parser import parse_response, response_is_finished

logger = logging.getLogger(__name__)

# Default timeout for reading responses
DEFAULT_READ_TIMEOUT_SEC = 0.1


class GDBProcessController(ABC):
    """Abstract base class for GDB process controllers.

    Defines a unified interface that GDBSession uses to communicate with
    GDB regardless of whether it's a local or remote (SSH) process.
    """

    @abstractmethod
    def start(self) -> None:
        """Start the GDB process."""
        ...

    @abstractmethod
    def write(self, data: str) -> None:
        """Write data (a command string) to GDB's stdin.

        Args:
            data: The string to write (should include trailing newline).
        """
        ...

    @abstractmethod
    def read_response(self, timeout_sec: float = DEFAULT_READ_TIMEOUT_SEC) -> List[Dict[str, Any]]:
        """Read and parse GDB MI responses from stdout.

        Reads available output from GDB's stdout, splits into lines,
        and parses each line using the MI parser.

        Args:
            timeout_sec: Maximum time to wait for output.

        Returns:
            List of parsed response dicts. Empty list if no output available.
        """
        ...

    @abstractmethod
    def is_alive(self) -> bool:
        """Check if the GDB process is still running.

        Returns:
            True if the process is alive, False otherwise.
        """
        ...

    @abstractmethod
    def interrupt(self) -> None:
        """Interrupt the running program in GDB.

        For local: sends SIGINT to the GDB process.
        For SSH: sends -exec-interrupt MI command.
        """
        ...

    @abstractmethod
    def exit(self) -> None:
        """Terminate the GDB process and clean up resources."""
        ...

    @property
    @abstractmethod
    def pid(self) -> Optional[int]:
        """Return the PID of the local subprocess (ssh or gdb), or None."""
        ...


class LocalController(GDBProcessController):
    """Controls a local GDB subprocess via subprocess.Popen.

    This is the equivalent of what pygdbmi's GdbController does internally.
    """

    def __init__(self, command: List[str], time_to_check_for_additional_output_sec: float = 1.0):
        """Initialize the local controller.

        Args:
            command: The full GDB command list, e.g. ["gdb", "--quiet", "--interpreter=mi", ...].
            time_to_check_for_additional_output_sec: Time to wait for additional output
                after initial response is received.
        """
        self._command = command
        self._process: Optional[subprocess.Popen] = None
        self._time_to_check = time_to_check_for_additional_output_sec
        self._read_buffer = ""

    def start(self) -> None:
        """Start the local GDB process."""
        logger.info(f"Starting local GDB: {' '.join(self._command)}")
        self._process = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,  # Unbuffered
        )
        logger.info(f"Local GDB started with PID {self._process.pid}")

    def write(self, data: str) -> None:
        """Write data to GDB's stdin."""
        if not self._process or not self._process.stdin:
            raise BrokenPipeError("GDB process stdin is not available")
        self._process.stdin.write(data.encode())
        self._process.stdin.flush()

    def read_response(self, timeout_sec: float = DEFAULT_READ_TIMEOUT_SEC) -> List[Dict[str, Any]]:
        """Read and parse available MI output from GDB stdout."""
        if not self._process or not self._process.stdout:
            return []

        import select

        responses: List[Dict[str, Any]] = []
        end_time = time.time() + timeout_sec

        while time.time() < end_time:
            # Use select to check if data is available (non-blocking)
            if sys.platform == "win32":
                # Windows: can't use select on pipes, use a different approach
                # Try to read with a small timeout by checking if data is available
                raw_data = self._try_read_windows()
            else:
                ready, _, _ = select.select([self._process.stdout], [], [], max(0, end_time - time.time()))
                if not ready:
                    break
                raw_data = self._process.stdout.read(65536)

            if not raw_data:
                break

            self._read_buffer += raw_data.decode("utf-8", errors="replace")

            # Process complete lines
            while "\n" in self._read_buffer:
                line, self._read_buffer = self._read_buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                parsed = parse_response(line)
                if parsed["type"] != "done":  # Skip (gdb) prompts in response list
                    responses.append(parsed)

        return responses

    def _try_read_windows(self) -> bytes:
        """Try to read available data from stdout on Windows (non-blocking)."""
        import msvcrt
        import ctypes
        from ctypes import wintypes

        if not self._process or not self._process.stdout:
            return b""

        # Use PeekNamedPipe to check if data is available
        handle = msvcrt.get_osfhandle(self._process.stdout.fileno())
        avail = ctypes.c_ulong(0)

        PIPE_HANDLE = ctypes.c_void_p(handle)
        result = ctypes.windll.kernel32.PeekNamedPipe(
            PIPE_HANDLE,
            None,
            ctypes.c_ulong(0),
            None,
            ctypes.byref(avail),
            None,
        )

        if result and avail.value > 0:
            return self._process.stdout.read(avail.value)
        return b""

    def is_alive(self) -> bool:
        """Check if the GDB process is still running."""
        if not self._process:
            return False
        return self._process.poll() is None

    def interrupt(self) -> None:
        """Send SIGINT to the local GDB process."""
        if not self._process:
            raise RuntimeError("No GDB process running")

        if sys.platform == "win32":
            # Windows: use CTRL_BREAK_EVENT or terminate
            # subprocess.Popen on Windows doesn't support SIGINT easily
            # Use -exec-interrupt via stdin instead
            try:
                self.write("-exec-interrupt\n")
            except Exception:
                # Fallback: try to send Ctrl+C via GenerateConsoleCtrlEvent
                import ctypes
                ctypes.windll.kernel32.GenerateConsoleCtrlEvent(0, self._process.pid)
        else:
            os.kill(self._process.pid, signal.SIGINT)

    def exit(self) -> None:
        """Terminate the GDB process."""
        if not self._process:
            return

        try:
            # Try graceful exit first
            if self._process.stdin:
                try:
                    self._process.stdin.write(b"-gdb-exit\n")
                    self._process.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass

            # Wait briefly for graceful exit
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                # Force kill
                self._process.kill()
                self._process.wait(timeout=2)
        except Exception as e:
            logger.warning(f"Error during GDB exit: {e}")
            try:
                self._process.kill()
            except Exception:
                pass
        finally:
            self._process = None

    @property
    def pid(self) -> Optional[int]:
        """Return the PID of the local GDB process."""
        if self._process:
            return self._process.pid
        return None

    @property
    def process(self) -> Optional[subprocess.Popen]:
        """Return the underlying subprocess.Popen object (for compatibility checks)."""
        return self._process


class SSHController(GDBProcessController):
    """Controls a remote GDB process via SSH.

    Starts a local SSH subprocess that connects to the remote host and
    launches GDB there. Communication happens through the SSH tunnel's
    stdin/stdout pipes, which transparently forward to the remote GDB's
    stdin/stdout.
    """

    def __init__(
        self,
        ssh_host: str,
        gdb_command: List[str],
        ssh_user: Optional[str] = None,
        ssh_port: int = 22,
        ssh_key: Optional[str] = None,
        ssh_options: Optional[List[str]] = None,
        working_dir: Optional[str] = None,
    ):
        """Initialize the SSH controller.

        Args:
            ssh_host: Remote host to connect to.
            gdb_command: The GDB command and arguments to run on the remote host.
            ssh_user: SSH username (optional, uses SSH config default if not set).
            ssh_port: SSH port (default: 22).
            ssh_key: Path to SSH private key file (optional).
            ssh_options: Additional SSH options (e.g., ["-o", "StrictHostKeyChecking=no"]).
            working_dir: Remote working directory to cd into before starting GDB.
        """
        self._ssh_host = ssh_host
        self._ssh_user = ssh_user
        self._ssh_port = ssh_port
        self._ssh_key = ssh_key
        self._ssh_options = ssh_options or []
        self._gdb_command = gdb_command
        self._working_dir = working_dir
        self._process: Optional[subprocess.Popen] = None
        self._read_buffer = ""

    def _build_ssh_command(self) -> List[str]:
        """Build the full SSH command list.

        Returns:
            Command list like: ["ssh", "-p", "22", "-o", "BatchMode=yes", "user@host", "cd /dir && gdb ..."]
        """
        ssh_cmd = ["ssh"]

        # Port
        if self._ssh_port != 22:
            ssh_cmd.extend(["-p", str(self._ssh_port)])

        # Key file
        if self._ssh_key:
            ssh_cmd.extend(["-i", self._ssh_key])

        # BatchMode to avoid password prompts hanging
        ssh_cmd.extend(["-o", "BatchMode=yes"])

        # Disable host key checking prompts (common in automation)
        # Users can override via ssh_options
        ssh_cmd.extend(["-o", "StrictHostKeyChecking=accept-new"])

        # Allocate a pseudo-TTY for signal forwarding
        ssh_cmd.append("-tt")

        # Additional user-specified SSH options
        ssh_cmd.extend(self._ssh_options)

        # Target: user@host or just host
        if self._ssh_user:
            ssh_cmd.append(f"{self._ssh_user}@{self._ssh_host}")
        else:
            ssh_cmd.append(self._ssh_host)

        # Remote command: optionally cd to working dir, then run GDB
        remote_cmd_parts = []
        if self._working_dir:
            # Use shell quoting for the directory path
            remote_cmd_parts.append(f"cd {self._shell_quote(self._working_dir)} &&")

        remote_cmd_parts.extend(self._gdb_command)
        remote_cmd = " ".join(remote_cmd_parts)

        ssh_cmd.append(remote_cmd)

        return ssh_cmd

    @staticmethod
    def _shell_quote(s: str) -> str:
        """Quote a string for use in a remote shell command."""
        # Simple single-quote wrapping with escaping
        return "'" + s.replace("'", "'\\''") + "'"

    def start(self) -> None:
        """Start the SSH connection and remote GDB process."""
        ssh_command = self._build_ssh_command()
        logger.info(f"Starting SSH GDB: {' '.join(ssh_command)}")

        self._process = subprocess.Popen(
            ssh_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        logger.info(f"SSH process started with local PID {self._process.pid}")

    def write(self, data: str) -> None:
        """Write data to the remote GDB's stdin via SSH tunnel."""
        if not self._process or not self._process.stdin:
            raise BrokenPipeError("SSH process stdin is not available")
        self._process.stdin.write(data.encode())
        self._process.stdin.flush()

    def read_response(self, timeout_sec: float = DEFAULT_READ_TIMEOUT_SEC) -> List[Dict[str, Any]]:
        """Read and parse available MI output from the remote GDB via SSH stdout."""
        if not self._process or not self._process.stdout:
            return []

        import select

        responses: List[Dict[str, Any]] = []
        end_time = time.time() + timeout_sec

        while time.time() < end_time:
            if sys.platform == "win32":
                raw_data = self._try_read_windows()
            else:
                ready, _, _ = select.select([self._process.stdout], [], [], max(0, end_time - time.time()))
                if not ready:
                    break
                raw_data = self._process.stdout.read(65536)

            if not raw_data:
                break

            self._read_buffer += raw_data.decode("utf-8", errors="replace")

            # Process complete lines
            while "\n" in self._read_buffer:
                line, self._read_buffer = self._read_buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                # Filter out SSH-specific noise (e.g., "Connection to host closed.")
                if self._is_ssh_noise(line):
                    logger.debug(f"Filtered SSH noise: {line}")
                    continue

                parsed = parse_response(line)
                if parsed["type"] != "done":  # Skip (gdb) prompts
                    responses.append(parsed)

        return responses

    def _try_read_windows(self) -> bytes:
        """Try to read available data from stdout on Windows (non-blocking)."""
        import msvcrt
        import ctypes

        if not self._process or not self._process.stdout:
            return b""

        handle = msvcrt.get_osfhandle(self._process.stdout.fileno())
        avail = ctypes.c_ulong(0)

        PIPE_HANDLE = ctypes.c_void_p(handle)
        result = ctypes.windll.kernel32.PeekNamedPipe(
            PIPE_HANDLE,
            None,
            ctypes.c_ulong(0),
            None,
            ctypes.byref(avail),
            None,
        )

        if result and avail.value > 0:
            return self._process.stdout.read(avail.value)
        return b""

    @staticmethod
    def _is_ssh_noise(line: str) -> bool:
        """Check if a line is SSH connection noise rather than GDB output."""
        ssh_noise_patterns = [
            "Connection to ",
            "Warning: Permanently added",
            "Pseudo-terminal will not be allocated",
            "stdin: is not a tty",
        ]
        return any(line.startswith(pattern) or pattern in line for pattern in ssh_noise_patterns)

    def is_alive(self) -> bool:
        """Check if the SSH subprocess (and thus the remote GDB) is still running."""
        if not self._process:
            return False
        return self._process.poll() is None

    def interrupt(self) -> None:
        """Interrupt the running program on the remote GDB.

        Since we can't send SIGINT to the remote process directly,
        we send the -exec-interrupt MI command through stdin.
        """
        if not self._process:
            raise RuntimeError("No SSH/GDB process running")

        # Send MI interrupt command
        try:
            self.write("-exec-interrupt\n")
        except (BrokenPipeError, OSError) as e:
            logger.error(f"Failed to send interrupt via SSH: {e}")
            raise

    def exit(self) -> None:
        """Terminate the remote GDB and close the SSH connection."""
        if not self._process:
            return

        try:
            # Try graceful exit first
            if self._process.stdin:
                try:
                    self._process.stdin.write(b"-gdb-exit\n")
                    self._process.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass

            # Wait briefly for graceful exit
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                # Force kill the SSH process
                self._process.kill()
                self._process.wait(timeout=2)
        except Exception as e:
            logger.warning(f"Error during SSH/GDB exit: {e}")
            try:
                self._process.kill()
            except Exception:
                pass
        finally:
            self._process = None

    @property
    def pid(self) -> Optional[int]:
        """Return the PID of the local SSH subprocess."""
        if self._process:
            return self._process.pid
        return None

    @property
    def process(self) -> Optional[subprocess.Popen]:
        """Return the underlying subprocess.Popen object."""
        return self._process
