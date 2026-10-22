"""No heuristic is substituted for a trained academic marking model."""
import hashlib
import importlib.util
import json
import pathlib
import zipfile
from functools import lru_cache

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL = ROOT / 'exam_question_generator_lstm.keras'
TOKENIZER = ROOT / 'models' / 'tokenizer.json'


def status():
    if not MODEL.exists():
        return dict(generator='model_required', input_length=47, vocabulary=1168,
                    model_sha256=None, architecture='Sequential', tokenizer_sha256=None,
                    marking='not_configured', message='Supply the trained Keras model and original tokenizer to enable question drafting. Human review is available.')
    with zipfile.ZipFile(MODEL) as z:
        config = json.loads(z.read('config.json'))
    available = importlib.util.find_spec('tensorflow') is not None
    return dict(generator=('ready' if available else 'runtime_required') if TOKENIZER.exists() else 'tokenizer_required', input_length=47, vocabulary=1168,
                model_sha256=hashlib.sha256(MODEL.read_bytes()).hexdigest(), architecture=config['class_name'],
                tokenizer_sha256=hashlib.sha256(TOKENIZER.read_bytes()).hexdigest() if TOKENIZER.exists() else None,
                marking='not_configured', message='Criterion recommendations require a separately trained and validated three-class marking model. Human review is available.')


@lru_cache(maxsize=1)
def load_artifacts(model_modified, tokenizer_modified):
    import tensorflow as tf
    tokenizer = tf.keras.preprocessing.text.tokenizer_from_json(TOKENIZER.read_text(encoding='utf-8'))
    if not tokenizer.word_index or max(tokenizer.word_index.values()) >= 1168:
        raise ValueError('Tokenizer vocabulary exceeds the trained model vocabulary or is empty.')
    model = tf.keras.models.load_model(MODEL, compile=False, safe_mode=True)
    if model.input_shape[-1] != 47 or model.output_shape[-1] != 1168:
        raise ValueError('Unexpected model input or output dimensions.')
    return model, tokenizer


def generate(seed, count=25):
    if not MODEL.exists():
        raise ValueError('Add the trained model at exam_question_generator_lstm.keras to enable generation.')
    if not TOKENIZER.exists():
        raise ValueError('Add the ORIGINAL training tokenizer to models/tokenizer.json. A new tokenizer cannot safely replace it.')
    import numpy as np
    import tensorflow as tf
    model, tokenizer = load_artifacts(MODEL.stat().st_mtime_ns, TOKENIZER.stat().st_mtime_ns)
    tokens = tokenizer.texts_to_sequences([seed])[0]
    if not tokens:
        raise ValueError('The prompt contains no recognized training words.')
    words = []
    for _ in range(min(max(int(count), 1), 60)):
        sequence = tf.keras.utils.pad_sequences([tokens], maxlen=47, padding='pre', truncating='pre')
        probabilities = model(sequence, training=False).numpy()[0]
        probabilities[0] = 0
        index = int(np.argmax(probabilities))
        if index not in tokenizer.index_word:
            raise ValueError('Tokenizer does not match model output indices.')
        words.append(tokenizer.index_word[index])
        tokens.append(index)
    versions = status()
    return dict(text=seed.strip() + ' ' + ' '.join(words), seed=seed, model_version=versions['model_sha256'], tokenizer_version=versions['tokenizer_sha256'], status='draft_requires_lecturer_approval')
