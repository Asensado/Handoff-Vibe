# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Asensado
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from handoff_ui.lifecycle import acquire_lease, stop_backend


class Lifecycle(unittest.TestCase):
    def test_lease_is_global_and_released_on_close(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with acquire_lease(folder, 'engine.lock'):
                result = subprocess.run([sys.executable, '-c',
                    'from pathlib import Path; from handoff_ui.lifecycle import acquire_lease; '
                    'acquire_lease(Path(__import__("sys").argv[1]), "engine.lock")', directory],
                    capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'BlockingIOError', result.stderr)
            with acquire_lease(folder, 'engine.lock'):
                pass

    def test_stop_kills_owned_process_group(self):
        child = subprocess.Popen([sys.executable, '-u', '-c',
            'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); '
            'print("ready", flush=True); time.sleep(60)'],
            start_new_session=True, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'ready')
            stop_backend(child, timeout=0.05)
            self.assertEqual(child.returncode, -9)
        finally:
            if child.poll() is None:
                os.killpg(child.pid, 9)
                child.wait()
            child.stdout.close()


class NativeGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.tmp.name) / 'guard'
        harness = Path(cls.tmp.name) / 'main.c'
        harness.write_text('#include <stdio.h>\n#include <unistd.h>\n'
            '#include "process_guard.h"\nint main(void) { '
            'if (handoff_process_guard() < 0) return 5; '
            'puts("ready"); fflush(stdout); pause(); return 0; }\n')
        root = Path(__file__).resolve().parents[1]
        subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-I', str(root / 'native'),
                        str(harness), str(root / 'native/process_guard.c'), '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_standalone_backend_exclusion(self):
        env = dict(os.environ, XDG_RUNTIME_DIR=self.tmp.name)
        env.pop('HANDOFF_SUPERVISOR_PID', None)
        child = subprocess.Popen([self.binary], env=env, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'ready')
            other = subprocess.run([self.binary], env=env, capture_output=True, timeout=2)
            self.assertEqual(other.returncode, 5)
        finally:
            child.terminate()
            child.wait(timeout=2)
            child.stdout.close()

    def test_wrong_supervisor_is_rejected(self):
        result = subprocess.run([self.binary], env=dict(os.environ,
            XDG_RUNTIME_DIR=self.tmp.name, HANDOFF_SUPERVISOR_PID='1'), capture_output=True, timeout=2)
        self.assertEqual(result.returncode, 5)

    def test_backend_dies_with_supervisor(self):
        # Inherit stdout: EOF arrives only once both parent and guarded backend exit.
        script = ('import os,subprocess,sys,time; '
                  'env=dict(os.environ,HANDOFF_SUPERVISOR_PID=str(os.getpid())); '
                  'p=subprocess.Popen([sys.argv[1]],env=env); time.sleep(60)')
        parent = subprocess.Popen([sys.executable, '-c', script, str(self.binary)],
            env=dict(os.environ, XDG_RUNTIME_DIR=self.tmp.name), stdout=subprocess.PIPE, text=True,
            start_new_session=True)
        try:
            self.assertEqual(parent.stdout.readline().strip(), 'ready')
            parent.kill()
            _, _ = parent.communicate(timeout=2)
        finally:
            os.killpg(parent.pid, 9) if parent.poll() is None else None
            parent.wait()
