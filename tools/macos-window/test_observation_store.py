import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from observation_store import ObservationStore
import window_macro as macro


class ObservationStoreTests(unittest.TestCase):
    def test_pixels_bounded_and_ocr_survives_late_assertion_and_close(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ObservationStore(root)
            first = None
            for index in range(8):
                destination = root / 'results'
                frame = store.allocate(destination, str(index))
                if first is None:
                    first = frame
                image = frame / 'capture.jpg'
                image.write_bytes(b'private pixels')
                (frame / 'capture-ocr.json').write_text('{"lines":[]}')
                observed = macro.Observation('', image, {'width': 788, 'height': 1079})
                store.record(frame, destination, str(index), observed)
                late = frame / 'derived' / 'late-ocr.json'
                late.parent.mkdir()
                late.write_text('{"late":true}')
                (late.parent / 'crop.png').write_bytes(b'temporary crop')
                self.assertLessEqual(len(list(store.work.iterdir())), 2)
            self.assertFalse(first.exists())
            self.assertTrue((destination / 'derived/late-ocr.json').exists())
            store.close()
            self.assertFalse(list(root.rglob('*.jpg')))
            self.assertFalse(list(root.rglob('*.png')))
            self.assertEqual(len(list(destination.glob('*-observation.json'))), 8)
            self.assertFalse(json.loads((destination / '7-observation.json').read_text())['image_retained'])

    def test_process_close_failure_still_discards_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            client = object.__new__(macro.CuaMcp)
            client._observation_store = ObservationStore(directory)
            frame = client._observation_store.allocate(Path(directory)/'result', 'failure')
            (frame/'failure.png').write_bytes(b'pixels')
            client._close_process = Mock(side_effect=RuntimeError('process error'))
            with self.assertRaisesRegex(RuntimeError, 'process error'):
                client.close()
            self.assertFalse(list(Path(directory).rglob('*.png')))

    def test_failure_before_input_records_exact_step(self):
        with tempfile.TemporaryDirectory() as directory:
            flow = json.loads((Path(__file__).parent/'example-profile.json').read_text())
            client = Mock()
            client.observe.return_value = 'unexpected page'
            with self.assertRaises(RuntimeError):
                macro.execute({'log_dir':directory}, flow, '01-check-city', backend=client)
            report = json.loads(next(Path(directory).glob('*/result.json')).read_text())
            self.assertEqual(report['failed_step']['name'], '01-check-city')
            self.assertEqual(report['failed_step']['phase'], 'verify_before')
            self.assertFalse(report['steps'])


if __name__ == '__main__':
    unittest.main()
