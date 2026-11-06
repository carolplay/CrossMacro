"""Bounded, temporary pixels; durable OCR and execution metadata only."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time


class ObservationStore:
    def __init__(self, root, keep=2):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.work = Path(tempfile.mkdtemp(prefix='.observation-work-', dir=self.root))
        self.keep = keep
        self.pending = []

    def allocate(self, destination, label):
        while len(self.pending) >= self.keep:
            self._retire(self.pending.pop(0))
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix='frame-', dir=self.work))
        self.pending.append((folder, destination))
        return folder

    def record(self, frame, destination, label, observation):
        path = Path(destination) / (label + '-observation.json')
        image = observation.image_path
        path.write_text(json.dumps({
            'observed_unix': time.time(), 'image_retained': False,
            'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
            'width': observation.ocr_data['width'],
            'height': observation.ocr_data['height'],
            'ocr': label + '-ocr.json',
            'policy': 'temporary_pixels_structured_logs_only',
        }, indent=2) + '\n')
        observation.evidence_path = path
        self.flush(frame, destination)

    @staticmethod
    def flush(frame, destination):
        # OCR used later by assertions is also flushed when this frame retires.
        for source in Path(frame).rglob('*.json'):
            target = Path(destination) / source.relative_to(frame)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def _retire(self, item):
        frame, destination = item
        self.flush(frame, destination)
        shutil.rmtree(frame)

    def close(self):
        for item in self.pending:
            self._retire(item)
        self.pending.clear()
        shutil.rmtree(self.work)
