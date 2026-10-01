import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "backend_deployment", Path(__file__).resolve().parents[2] / "deploy" / "deploy_backend.py"
)
deployment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment)


class BackendDeploymentTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.override = self.base / "systemd" / "20-git-release.conf"
        self.base_patch = patch.object(deployment, "BASE", self.base)
        self.override_patch = patch.object(deployment, "DROP_IN", self.override)
        self.base_patch.start()
        self.override_patch.start()
        self.addCleanup(self.base_patch.stop)
        self.addCleanup(self.override_patch.stop)

    def activate(self):
        deployment.activate("new-sha", self.base / "releases" / "new-sha", self.base / "release-venvs" / "new-sha")

    @patch.object(deployment, "restart_and_check")
    def test_first_deploy_records_legacy_rollback_and_preserves_environment(self, restart):
        self.activate()
        record = json.loads((self.base / "deployment-state.json").read_text())
        self.assertEqual("legacy-scp", record["previous"])
        self.assertIsNone(record["previous_override"])
        text = self.override.read_text()
        self.assertIn("release-venvs/new-sha/bin/uvicorn", text)
        self.assertIn("WorkingDirectory=", text)
        self.assertNotIn("EnvironmentFile", text)
        deployment.rollback()
        self.assertFalse(self.override.exists())
        self.assertEqual(2, restart.call_count)
        self.assertEqual("legacy-scp", json.loads((self.base / "deployment-state.json").read_text())["current"])

    @patch.object(deployment, "restart_and_check", side_effect=[RuntimeError("unhealthy"), None])
    def test_failed_deployment_restores_exact_override_and_state(self, restart):
        old = "[Service]\nWorkingDirectory=/previous\n"
        deployment.write_atomic(self.override, old)
        state = '{"current":"old-sha"}'
        (self.base / "deployment-state.json").write_text(state)
        with self.assertRaisesRegex(RuntimeError, "unhealthy"):
            self.activate()
        self.assertEqual(old, self.override.read_text())
        self.assertEqual(state, (self.base / "deployment-state.json").read_text())
        self.assertEqual(2, restart.call_count)

    @patch.object(deployment, "restart_and_check", side_effect=[RuntimeError("unhealthy"), None])
    def test_failed_first_deployment_removes_new_override(self, restart):
        with self.assertRaisesRegex(RuntimeError, "unhealthy"):
            self.activate()
        self.assertFalse(self.override.exists())
        self.assertFalse((self.base / "deployment-state.json").exists())

    @patch.object(deployment, "run")
    def test_dirty_repository_is_rejected_before_pull_or_restart(self, command):
        (self.base / "repository").mkdir()
        command.side_effect = [deployment.REPOSITORY_URL + "\n", " M api.py\n"]
        with self.assertRaisesRegex(RuntimeError, "local edits"):
            deployment.prepare_release()
        self.assertEqual(2, command.call_count)
        self.assertFalse(self.override.exists())

    @patch.object(deployment, "run")
    def test_non_fast_forward_pull_is_rejected_before_release(self, command):
        (self.base / "repository").mkdir()
        error = deployment.subprocess.CalledProcessError(1, ["git", "merge"])
        command.side_effect = [deployment.REPOSITORY_URL + "\n", "", "main\n", None, error]
        with self.assertRaises(deployment.subprocess.CalledProcessError):
            deployment.prepare_release()
        self.assertFalse((self.base / "releases").exists())
        self.assertFalse(self.override.exists())

    @patch.object(deployment, "urlopen")
    @patch.object(deployment, "run")
    def test_health_requires_up_payload(self, command, request):
        from io import StringIO
        request.side_effect = [StringIO('{"status":"DOWN"}'), StringIO('{"status":"UP"}')]
        with patch.object(deployment.time, "sleep") as sleep:
            deployment.restart_and_check()
        self.assertEqual(2, request.call_count)
        sleep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
