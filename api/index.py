import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('DATA_DIR', '/tmp/new_cartube-data')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import Handler as handler  # noqa: E402
