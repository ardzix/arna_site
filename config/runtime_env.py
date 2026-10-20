"""Load complete backend configuration from the release's immutable secret."""
import json
import os
from pathlib import Path


def load_runtime_env():
    name = os.environ.get('SITE_RUNTIME_SECRET_PATH')
    if not name:
        return False
    values = json.loads(Path(name).read_text())
    if not isinstance(values, dict) or not all(isinstance(k, str) and isinstance(v, str) for k,v in values.items()):
        raise RuntimeError('ArnaSite runtime secret must be a JSON object of string values')
    os.environ.update(values)
    return True
