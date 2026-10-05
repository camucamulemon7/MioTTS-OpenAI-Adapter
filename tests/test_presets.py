"""Run the real seeding shell function against synthetic temporary presets."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ENTRYPOINT = Path(__file__).resolve().parents[1] / 'entrypoint.sh'

class PresetSeedingTests(unittest.TestCase):
    def check_seed(self, entries, expected_seed):
        source = ENTRYPOINT.read_text()
        function = source[source.index('seed_default_presets() {'):source.index('wait_for_http() {')]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            presets = root / 'repo' / 'presets'
            presets.mkdir(parents=True)
            defaults = root / 'defaults'
            defaults.mkdir()
            (defaults / 'synthetic.json').write_text('{}')
            for entry in entries:
                path = presets / entry
                if entry.endswith('/'):
                    path.mkdir()
                else:
                    path.write_text('preserved')
            # Substitute only the filesystem source of cp, leaving the production
            # function and its empty-directory detection untouched.
            script = '''set -euo pipefail
cp() { command cp -a "${TEST_DEFAULTS}/." "$3"; }
''' + function + '\nseed_default_presets\n'
            result = subprocess.run(['bash', '-c', script], env={**os.environ,
                'MIOTTS_REPO_DIR': str(root / 'repo'), 'TEST_DEFAULTS': str(defaults)},
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((presets / 'synthetic.json').exists(), expected_seed)
            for entry in entries:
                if not entry.endswith('/'):
                    self.assertEqual((presets / entry).read_text(), 'preserved')

    def test_empty_directory_is_seeded(self):
        self.check_seed([], True)

    def test_gitkeep_does_not_prevent_seeding(self):
        self.check_seed(['.gitkeep'], True)

    def test_existing_preset_is_preserved(self):
        self.check_seed(['.gitkeep', 'custom.json'], False)

    def test_existing_directory_is_preserved(self):
        self.check_seed(['custom/'], False)

if __name__ == '__main__':
    unittest.main()
