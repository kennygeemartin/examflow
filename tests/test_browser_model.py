"""Validation for the public browser inference bundle."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'app'))
import browser_model


class BrowserModelTests(unittest.TestCase):
    def test_exported_bundle_has_expected_model_and_tokenizer(self):
        status = browser_model.status()
        self.assertEqual(status['generator'], 'browser_ready')
        self.assertEqual(status['runtime'], 'browser')
        self.assertEqual(status['input_length'], 47)
        self.assertEqual(status['vocabulary'], 1168)
        self.assertEqual(len(status['model_sha256']), 64)
        self.assertEqual(len(status['tokenizer_sha256']), 64)
        self.assertIn('group1-shard1of1.bin', browser_model.asset_files())

    def test_draft_must_match_the_deployed_model_hashes(self):
        status = browser_model.status()
        payload = {
            'text': 'explain the concept of learning',
            'seed': 'explain the concept of',
            'model_version': status['model_sha256'],
            'tokenizer_version': status['tokenizer_sha256'],
            'status': 'draft_requires_lecturer_approval',
        }
        result = browser_model.validate_draft(payload)
        self.assertEqual(result['text'], payload['text'])
        self.assertEqual(result['status'], 'draft_requires_lecturer_approval')
        payload['model_version'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'model version changed'):
            browser_model.validate_draft(payload)

    def test_unapproved_or_oversized_drafts_are_rejected(self):
        status = browser_model.status()
        payload = {
            'text': 'x' * 12001,
            'seed': 'explain the',
            'model_version': status['model_sha256'],
            'tokenizer_version': status['tokenizer_sha256'],
            'status': 'draft_requires_lecturer_approval',
        }
        with self.assertRaisesRegex(ValueError, 'invalid or too long'):
            browser_model.validate_draft(payload)
        payload['text'] = 'explain the concept of a generated question'
        payload['status'] = 'approved'
        with self.assertRaisesRegex(ValueError, 'remain unapproved'):
            browser_model.validate_draft(payload)

    def test_asset_paths_are_allowlisted(self):
        self.assertNotIn('../metadata.json', browser_model.asset_files())
        self.assertNotIn('exam_question_generator_lstm.keras', browser_model.asset_files())


if __name__ == '__main__':
    unittest.main()
