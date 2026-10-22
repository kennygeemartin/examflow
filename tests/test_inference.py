"""Integration checks against the actual supplied model and tokenizer."""
import importlib.util
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'app'))
from inference import MODEL, TOKENIZER, generate, status


@unittest.skipUnless(MODEL.exists() and TOKENIZER.exists(), 'Original model and tokenizer have not been supplied')
class TokenizerIntegration(unittest.TestCase):
    def test_vocabulary_and_provenance(self):
        saved = json.loads(TOKENIZER.read_text(encoding='utf-8'))
        index = saved['config']['word_index']
        index = json.loads(index) if isinstance(index, str) else index
        self.assertEqual(len(index), 1167)
        self.assertEqual(set(index.values()), set(range(1, 1168)))
        info = status()
        self.assertEqual(len(info['tokenizer_sha256']), 64)
        self.assertEqual(info['input_length'], 47)

    @unittest.skipUnless(importlib.util.find_spec('tensorflow'), 'Install requirements-model.txt')
    def test_real_generation(self):
        result = generate('explain the', 10)
        self.assertEqual(result['status'], 'draft_requires_lecturer_approval')
        self.assertEqual(len(result['text'].split()), 12)
        self.assertEqual(len(result['model_version']), 64)
        self.assertEqual(len(result['tokenizer_version']), 64)
        print('\nActual model output:', result['text'])

    @unittest.skipUnless(importlib.util.find_spec('tensorflow'), 'Install requirements-model.txt')
    def test_unrecognized_prompt_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'no recognized training words'):
            generate('zzzznonexistenttokenzzzz', 3)


if __name__ == '__main__':
    unittest.main()
