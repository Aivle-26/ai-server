from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class RuntimeLayoutTest(unittest.TestCase):
    def test_shell_scripts_have_valid_bash_syntax(self) -> None:
        if os.name == "nt":
            self.skipTest("Bash syntax is validated separately on Windows")

        bash = shutil.which("bash")
        if not bash:
            self.skipTest("bash is not available")

        for relative_path in (
            "scripts/deploy.sh",
            "scripts/rollback.sh",
            "scripts/health-check.sh",
        ):
            with self.subTest(script=relative_path):
                subprocess.run(
                    [bash, "-n", str(REPOSITORY_ROOT / relative_path)],
                    check=True,
                    capture_output=True,
                    text=True,
                )

    def test_workflow_uses_versioned_remote_scripts(self) -> None:
        workflow_path = REPOSITORY_ROOT / ".github/workflows/ai-main-deploy.yml"
        if not workflow_path.exists():
            self.skipTest("GitHub metadata is excluded from the runtime archive")
        workflow = workflow_path.read_text(encoding="utf-8")

        self.assertIn("--exclude='./sample_data'", workflow)
        self.assertIn("concurrency:", workflow)
        self.assertIn("/scripts/deploy.sh", workflow)
        self.assertIn("/scripts/health-check.sh", workflow)
        self.assertIn("aipm-ai-server.service", workflow)
        self.assertIn("aipm-ai-release-${GITHUB_SHA}.*", workflow)
        self.assertNotIn("REMOTE_DEPLOY", workflow)
        self.assertNotIn("aipm-backend", workflow)
        self.assertNotIn("aipm-ai-test", workflow)
        self.assertNotIn("/ai-test/health", workflow)

    def test_deploy_keeps_live_dependencies_immutable_until_cutover(self) -> None:
        deploy_script = (REPOSITORY_ROOT / "scripts/deploy.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn('CANDIDATE_VENV="$VENV_ROOT/$DEPLOYMENT_ID"', deploy_script)
        self.assertIn('cp -al "$VENV_DIR/."', deploy_script)
        self.assertIn('ln -s "venvs/$DEPLOYMENT_ID" "$VENV_DIR"', deploy_script)
        self.assertIn("rollback_failed_deployment", deploy_script)
        self.assertIn('/tmp/aipm-ai-*.tar.gz)', deploy_script)
        self.assertNotIn(
            '"$VENV_DIR/bin/python" -m pip install',
            deploy_script,
        )
        self.assertNotIn("aipm-ai-test", deploy_script)

    def test_systemd_unit_uses_operating_names_and_loopback(self) -> None:
        unit = (
            REPOSITORY_ROOT / "deploy/systemd/aipm-ai-server.service"
        ).read_text(encoding="utf-8")

        self.assertIn("EnvironmentFile=/etc/aipm/ai-server.env", unit)
        self.assertIn("/opt/aipm/ai-server/.venv/bin/python", unit)
        self.assertIn("--host 127.0.0.1 --port 8090", unit)
        self.assertNotIn("aipm-ai-test.env", unit)

    def test_health_and_rollback_use_only_the_new_runtime(self) -> None:
        health_script = (
            REPOSITORY_ROOT / "scripts/health-check.sh"
        ).read_text(encoding="utf-8")
        rollback_script = (
            REPOSITORY_ROOT / "scripts/rollback.sh"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'HEALTH_URL="http://127.0.0.1:8090/health"',
            health_script,
        )
        self.assertNotIn("AI_HEALTH_URL", health_script)
        self.assertIn('SERVICE_NAME="aipm-ai-server.service"', rollback_script)
        self.assertNotIn("aipm-ai-test", rollback_script)


if __name__ == "__main__":
    unittest.main()
