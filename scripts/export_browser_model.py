"""Export the trained Keras model and original tokenizer for browser inference."""
import hashlib
import json
import pathlib
import shutil
import tempfile

import tensorflow as tf
import tensorflowjs as tfjs

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL = ROOT / 'exam_question_generator_lstm.keras'
TOKENIZER = ROOT / 'models' / 'tokenizer.json'
OUTPUT = ROOT / 'public' / 'assets' / 'generator'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_tfjs_topology(model_json):
    def normalize(value):
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, item in value.items():
            if key in ('shared_object_id', 'quantization_config', 'optional', 'ragged'):
                continue
            if key == 'dtype' and isinstance(item, dict):
                item = item.get('config', {}).get('name', 'float32')
            result[key] = normalize(item)
        if result.get('class_name') == 'InputLayer':
            config = result.get('config', {})
            if 'batch_shape' in config:
                config['batchInputShape'] = config.pop('batch_shape')
        return result

    model_json['modelTopology'] = normalize(model_json['modelTopology'])


def normalize_weight_names(model_json):
    replacements = {
        'layers/embedding/vars/0': 'embedding/embeddings',
        'layers/bidirectional/backward_layer/cell/vars/0': 'bidirectional/backward_forward_lstm/kernel',
        'layers/bidirectional/backward_layer/cell/vars/1': 'bidirectional/backward_forward_lstm/recurrent_kernel',
        'layers/bidirectional/backward_layer/cell/vars/2': 'bidirectional/backward_forward_lstm/bias',
        'layers/bidirectional/forward_layer/cell/vars/0': 'bidirectional/forward_forward_lstm/kernel',
        'layers/bidirectional/forward_layer/cell/vars/1': 'bidirectional/forward_forward_lstm/recurrent_kernel',
        'layers/bidirectional/forward_layer/cell/vars/2': 'bidirectional/forward_forward_lstm/bias',
        'layers/dense/vars/0': 'dense/kernel',
        'layers/dense/vars/1': 'dense/bias'
    }
    weights = model_json['weightsManifest'][0]['weights']
    if {weight['name'] for weight in weights} != set(replacements):
        raise ValueError('The TensorFlow.js converter produced unexpected model weights.')
    for weight in weights:
        weight['name'] = replacements[weight['name']]


def main():
    if not MODEL.is_file() or not TOKENIZER.is_file():
        raise FileNotFoundError('The original model and tokenizer are required for browser export.')
    model = tf.keras.models.load_model(MODEL, compile=False, safe_mode=True)
    if model.input_shape[-1] != 47 or model.output_shape[-1] != 1168:
        raise ValueError('Unexpected model dimensions; refusing to export.')
    tokenizer = json.loads(TOKENIZER.read_text(encoding='utf-8'))
    index = tokenizer.get('config', {}).get('word_index')
    if isinstance(index, str):
        index = json.loads(index)
    if not isinstance(index, dict) or set(index.values()) != set(range(1, 1168)):
        raise ValueError('The supplied tokenizer does not match the model vocabulary.')

    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='examflow-tfjs-') as temporary:
        export_dir = pathlib.Path(temporary) / 'model'
        tfjs.converters.save_keras_model(
            model, str(export_dir), weight_shard_size_bytes=4 * 1024 * 1024
        )
        model_json = json.loads((export_dir / 'model.json').read_text(encoding='utf-8'))
        if model_json.get('format') != 'layers-model' or not model_json.get('weightsManifest'):
            raise ValueError('TensorFlow.js produced an unexpected model format.')
        normalize_tfjs_topology(model_json)
        normalize_weight_names(model_json)
        (export_dir / 'model.json').write_text(
            json.dumps(model_json, separators=(',', ':')), encoding='utf-8'
        )
        (export_dir / 'tokenizer.json').write_bytes(TOKENIZER.read_bytes())
        metadata = {
            'model_sha256': sha256(MODEL),
            'tokenizer_sha256': sha256(TOKENIZER),
            'input_length': 47,
            'vocabulary': 1168,
            'architecture': 'Sequential'
        }
        (export_dir / 'metadata.json').write_text(
            json.dumps(metadata, separators=(',', ':')), encoding='utf-8'
        )
        expected = {'model.json', 'tokenizer.json', 'metadata.json'}
        for group in model_json['weightsManifest']:
            expected.update(group['paths'])
        for stale in OUTPUT.glob('group*-shard*of*.bin'):
            if stale.name not in expected:
                stale.unlink()
        for asset in export_dir.iterdir():
            shutil.copyfile(asset, OUTPUT / asset.name)

    print('Exported browser model assets to', OUTPUT)
    for asset in sorted(OUTPUT.iterdir()):
        print(asset.name, asset.stat().st_size)


if __name__ == '__main__':
    main()
