"""Metadata and validation for the public TensorFlow.js model bundle."""
import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
ASSET_DIR = ROOT.parent / 'public' / 'assets' / 'generator'
SHARD_NAME = re.compile(r'group\d+-shard\d+of\d+\.bin')


def asset_files():
    names = {'model.json', 'tokenizer.json', 'metadata.json'}
    model_path = ASSET_DIR / 'model.json'
    if model_path.is_file():
        try:
            model = json.loads(model_path.read_text(encoding='utf-8'))
            for group in model.get('weightsManifest', []):
                for name in group.get('paths', []):
                    if isinstance(name, str) and SHARD_NAME.fullmatch(name):
                        names.add(name)
        except (OSError, json.JSONDecodeError):
            pass
    return names


def status():
    required = ('model.json', 'tokenizer.json', 'metadata.json')
    if any(not (ASSET_DIR / name).is_file() for name in required):
        return dict(generator='model_required', input_length=47, vocabulary=1168,
                    model_sha256=None, architecture='Sequential', tokenizer_sha256=None,
                    marking='not_configured',
                    message='The browser model bundle is not installed. Human review is available.')
    try:
        model = json.loads((ASSET_DIR / 'model.json').read_text(encoding='utf-8'))
        tokenizer_bytes = (ASSET_DIR / 'tokenizer.json').read_bytes()
        tokenizer = json.loads(tokenizer_bytes)
        metadata = json.loads((ASSET_DIR / 'metadata.json').read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return dict(generator='browser_model_invalid', input_length=47, vocabulary=1168,
                    model_sha256=None, architecture='Sequential', tokenizer_sha256=None,
                    marking='not_configured',
                    message='The browser model bundle is invalid. Regenerate the browser model artifacts.')

    layers_model = model.get('modelTopology', {}).get('model_config', {})
    config = layers_model.get('config', {})
    layers = config.get('layers', [])
    tokenizer_config = tokenizer.get('config', {})
    word_index = tokenizer_config.get('word_index')
    if isinstance(word_index, str):
        try:
            word_index = json.loads(word_index)
        except json.JSONDecodeError:
            word_index = None
    paths = [path for group in model.get('weightsManifest', []) for path in group.get('paths', [])]
    hashes_valid = all(
        isinstance(metadata.get(field), str)
        and re.fullmatch(r'[0-9a-f]{64}', metadata[field])
        for field in ('model_sha256', 'tokenizer_sha256')
    )
    bundle_valid = (
        model.get('format') == 'layers-model'
        and layers_model.get('class_name') == 'Sequential'
        and config.get('build_input_shape') in ([None, 47], [None, 47, 1])
        and [layer.get('class_name') for layer in layers]
        == ['InputLayer', 'Embedding', 'Bidirectional', 'Dropout', 'Dense']
        and layers[-1].get('config', {}).get('units') == 1168
        and isinstance(word_index, dict)
        and len(word_index) == 1167
        and set(word_index.values()) == set(range(1, 1168))
        and all(isinstance(path, str) and SHARD_NAME.fullmatch(path) for path in paths)
        and all((ASSET_DIR / path).is_file() for path in paths)
        and hashes_valid
        and hashlib.sha256(tokenizer_bytes).hexdigest() == metadata['tokenizer_sha256']
    )
    if not bundle_valid:
        return dict(generator='browser_model_invalid', input_length=47, vocabulary=1168,
                    model_sha256=None, architecture='Sequential', tokenizer_sha256=None,
                    marking='not_configured',
                    message='The browser model bundle failed validation. Regenerate the browser model artifacts.')
    return dict(generator='browser_ready', runtime='browser', input_length=47, vocabulary=1168,
                model_sha256=metadata['model_sha256'], architecture='Sequential',
                tokenizer_sha256=metadata['tokenizer_sha256'], marking='not_configured',
                message='Question generation runs in the browser. Model artifacts are public and downloadable.')


def validate_draft(payload):
    if not isinstance(payload, dict):
        raise ValueError('Invalid generated draft.')
    info = status()
    if info['generator'] != 'browser_ready':
        raise ValueError('The browser model is not available.')
    seed = payload.get('seed')
    text = payload.get('text')
    if not isinstance(seed, str) or not seed.strip() or len(seed) > 2000:
        raise ValueError('Enter a question prefix of 2,000 characters or fewer.')
    if not isinstance(text, str) or not text.strip() or len(text) > 12000:
        raise ValueError('Generated question text is invalid or too long.')
    if not text.startswith(seed.strip() + ' '):
        raise ValueError('Generated question text does not match its prompt.')
    if payload.get('model_version') != info['model_sha256'] or payload.get('tokenizer_version') != info['tokenizer_sha256']:
        raise ValueError('The browser model version changed. Reload Draft extraction and try again.')
    if payload.get('status') != 'draft_requires_lecturer_approval':
        raise ValueError('Generated questions must remain unapproved drafts.')
    return dict(text=text, seed=seed, model_version=info['model_sha256'],
                tokenizer_version=info['tokenizer_sha256'],
                status='draft_requires_lecturer_approval')
