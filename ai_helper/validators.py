import json
from pathlib import Path
from django.conf import settings


class SchemaValidationError(Exception):
    pass


def _schema_path(filename: str) -> Path:
    base_dir = Path(settings.BASE_DIR)
    return base_dir / 'ai_schemas' / filename


def validate_payload(schema_filename: str, payload: dict):
    try:
        import jsonschema
    except ImportError as exc:
        raise SchemaValidationError('jsonschema package is not installed.') from exc

    schema_file = _schema_path(schema_filename)
    if not schema_file.exists():
        raise SchemaValidationError(f'Schema not found: {schema_file}')

    with schema_file.open('r', encoding='utf-8') as f:
        schema = json.load(f)

    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)

    if errors:
        messages = []
        for e in errors[:50]:
            path = '.'.join(str(p) for p in e.path) if e.path else '$'
            messages.append({'path': path, 'message': e.message})
        raise SchemaValidationError(messages)

    return {'valid': True, 'schema': schema_filename}
