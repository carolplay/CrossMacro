import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class BuildIdentityGuardTests(unittest.TestCase):
    def test_adhoc_build_does_not_touch_existing_authorized_app(self):
        original = Path(__file__).resolve().parents[1] / 'build.sh'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = root / 'tools/macos-native-studio/build.sh'
            script.parent.mkdir(parents=True)
            script.write_bytes(original.read_bytes())
            stable = root / 'local-apps/Macro Studio.app'
            stable.mkdir(parents=True)
            marker = stable / 'existing-binary'
            marker.write_bytes(b'authorized binary must stay untouched')
            env = dict(os.environ, MACRO_STUDIO_APP_PATH=str(stable))
            env.pop('MACRO_STUDIO_SIGN_IDENTITY', None)
            result = subprocess.run(['/bin/sh', str(script)], env=env,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertIn('Refusing to overwrite', result.stderr)
            self.assertEqual(marker.read_bytes(), b'authorized binary must stay untouched')
            self.assertEqual(list(stable.iterdir()), [marker])
