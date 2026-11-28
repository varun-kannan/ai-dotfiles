"""Round 21 regression tests for session-start's install lock recognition."""
import importlib.util
import os
import subprocess
from unittest import mock

from helpers import ROOT, Sandbox, make


_spec = importlib.util.spec_from_file_location(
    "session_start_lock_under_test", ROOT / "agents" / "claude-code" / "hooks" / "session-start.py"
)
session_start = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(session_start)


def process_start_time(pid):
    try:
        result = subprocess.run(
            ["/bin/ps", "-o", "lstart=", "-p", str(pid)],
            capture_output=True,
            text=True,
            env=dict(os.environ, LC_ALL="C"),
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.replace(" ", "").strip() if result.returncode == 0 else ""


class InstallRunning(Sandbox):
    def setUp(self):
        super().setUp()
        session_start.SHARED = self.shared

    def running_installer(self):
        script = make(self.tmp / "running") / "install.sh"
        script.write_text("#!/bin/bash\nsleep 30\n", encoding="utf-8")
        process = subprocess.Popen(["/bin/bash", str(script)])
        self.addCleanup(self.stop, process)
        return process

    @staticmethod
    def stop(process):
        if process.poll() is None:
            process.kill()
            process.wait()

    def test_new_lock_with_live_owners_start_time_is_running(self):
        process = self.running_installer()
        started = process_start_time(process.pid)
        if not started:
            self.skipTest("ps process start times are unavailable in this sandbox")
        os.symlink("%d:%s" % (process.pid, started), self.shared / ".install.lock")
        self.assertTrue(session_start._install_running())

    def test_new_lock_with_wrong_start_time_is_not_running(self):
        process = self.running_installer()
        if not process_start_time(process.pid):
            self.skipTest("ps process start times are unavailable in this sandbox")
        os.symlink("%d:wrong" % process.pid, self.shared / ".install.lock")
        self.assertFalse(session_start._install_running())

    def test_new_lock_with_dead_pid_is_not_running(self):
        process = subprocess.Popen(["/usr/bin/true"])
        process.wait()
        os.symlink("%d:anything" % process.pid, self.shared / ".install.lock")
        self.assertFalse(session_start._install_running())

    def test_malformed_lock_target_is_not_running(self):
        os.symlink("not-a-pid:start", self.shared / ".install.lock")
        self.assertFalse(session_start._install_running())

    def test_process_inspection_failures_are_not_running(self):
        os.symlink("%d:expected" % os.getpid(), self.shared / ".install.lock")
        cases = (
            subprocess.CalledProcessError(1, ["/bin/ps"]),
            subprocess.CompletedProcess(["/bin/ps"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["/bin/ps"], 0, stdout="not a start time\n", stderr=""),
        )
        for result in cases:
            with self.subTest(result=result):
                effect = result if isinstance(result, Exception) else None
                with mock.patch.object(session_start.subprocess, "run", side_effect=effect,
                                       return_value=None if effect else result):
                    self.assertFalse(session_start._install_running())

    def test_plain_pid_lock_for_install_command_is_running(self):
        process = self.running_installer()
        try:
            command = subprocess.run(
                ["/bin/ps", "-p", str(process.pid), "-o", "command="],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            self.skipTest("ps command lines are unavailable in this sandbox")
        if command.returncode != 0 or "install.sh" not in command.stdout:
            self.skipTest("ps command lines are unavailable in this sandbox")
        os.symlink(str(process.pid), self.shared / ".install.lock")
        self.assertTrue(session_start._install_running())
