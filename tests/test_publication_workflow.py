"""The caller must grant the exact shared package contract, not a guessed API."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
class WorkflowContractTests(unittest.TestCase):
    def test_packager_has_oidc_and_runtime_input(self):
        source=(ROOT/'.github/workflows/addon-validations.yml').read_text()
        package=source.split('  package:',1)[1]
        self.assertIn('      id-token: write',package)
        self.assertIn('      contents: read',package)
        self.assertIn('      runtime_entries_json:',package)
        self.assertNotIn('      runtime_entries:',package)
    def test_notifier_accepts_only_omega_successful_non_pr(self):
        source=(ROOT/'.github/workflows/notify-repository.yml').read_text()
        self.assertIn('branches: [omega]',source)
        self.assertIn("head_branch == 'omega'",source)
        self.assertIn("conclusion == 'success'",source)
        self.assertIn('expected_branch: omega',source)
        self.assertIn('addon_id: skin.arctic.fuse.3',source)
        self.assertNotIn("event == 'pull_request'",source)
