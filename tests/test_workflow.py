import pathlib
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'app'))
from domain import Store, Error, digest
from seed import seed


class Workflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).resolve().parent)
        self.store = Store(str(pathlib.Path(self.temp.name) / 'test.sqlite'))
        seed(self.store)
        self.tokens = {u: self.store.login(u, 'DemoExam2026!') for u in ['admin', 'candidate', 'lecturer', 'moderator']}

    def tearDown(self):
        self.temp.cleanup()

    def call(self, user, action, **data):
        return self.store.dispatch(self.tokens[user], action, data)

    def start(self):
        return self.call('candidate', 'start', id='exam-demo-v1')

    def submit(self):
        a = self.start()
        a = self.call('candidate', 'save', id=a['id'], revision=0, answers={'q-demo-v1': 'All changes succeed or roll back.'})
        return self.call('candidate', 'submit', id=a['id'], revision=a['revision'])

    def test_workflow_and_release_visibility(self):
        a = self.submit()
        self.assertEqual(a['checksum'], digest(a['answers']))
        self.assertEqual(len(self.call('candidate', 'state')['reviews']), 0)
        marks = {'q-demo-v1': [2, 1, 0]}
        self.call('lecturer', 'review', id=a['id'], marks=marks, reason='Checked all criterion anchors.')
        r = self.call('moderator', 'review', id=a['id'], marks=marks, reason='Independent moderation completed.')
        self.assertEqual(len(self.call('candidate', 'state')['reviews']), 0)
        self.call('moderator', 'publish', id=r['id'])
        released = self.call('candidate', 'state')['reviews'][0]
        self.assertEqual(released['total'], 3)
        self.assertNotIn('marks', released)

    def test_candidate_cannot_access_reference_or_mark(self):
        self.assertFalse(self.call('candidate', 'state')['questions'])
        a = self.start()
        q = self.call('candidate', 'state')['questions'][0]
        self.assertNotIn('reference', q)
        self.assertNotIn('criteria', q)
        with self.assertRaises(Error):
            self.call('candidate', 'review', id=a['id'], marks={'q-demo-v1': [2,2,2]}, reason='No')

    def test_admin_cannot_edit_marks(self):
        a = self.submit()
        with self.assertRaises(Error):
            self.call('admin', 'review', id=a['id'], marks={'q-demo-v1': [2,2,2]}, reason='No')

    def test_reconnect_retains_deadline_and_rejects_stale_save(self):
        a = self.start()
        self.assertEqual(a['deadline'], self.start()['deadline'])
        self.call('candidate', 'save', id=a['id'], revision=0, answers={'q-demo-v1': ''})
        with self.assertRaises(Error) as context:
            self.call('candidate', 'save', id=a['id'], revision=0, answers={'q-demo-v1': 'stale'})
        self.assertEqual(context.exception.status, 409)

    def test_timeout_uses_last_saved_answer(self):
        a = self.start()
        a = self.call('candidate', 'save', id=a['id'], revision=0, answers={'q-demo-v1': 'Stored answer'})
        with self.store.db() as db:
            a['deadline'] = time.time() - 1
            self.store.put(db, 'attempt', a)
        result = self.call('candidate', 'save', id=a['id'], revision=1, answers={'q-demo-v1': 'Late unsaved text'})
        self.assertEqual(result['status'], 'submitted')
        self.assertEqual(result['answers']['q-demo-v1'], 'Stored answer')
        self.assertEqual(result['reason'], 'timeout')

    def test_mark_bounds_and_moderation_required(self):
        a = self.submit()
        with self.assertRaises(Error):
            self.call('lecturer', 'review', id=a['id'], marks={'q-demo-v1': [3,0,0]}, reason='Invalid')
        with self.assertRaises(Error):
            self.call('moderator', 'review', id=a['id'], marks={'q-demo-v1': [2,0,0]}, reason='Too early')
        r = self.call('lecturer', 'review', id=a['id'], marks={'q-demo-v1': [2,0,0]}, reason='Review')
        with self.assertRaises(Error):
            self.call('moderator', 'publish', id=r['id'])

    def test_new_version_does_not_change_frozen_paper(self):
        q = self.call('lecturer', 'state')['questions'][0]
        new = self.call('lecturer', 'question', course=q['course'], text='Revised question', reference=q['reference'], criteria=q['criteria'], parent=q['id'])
        self.assertNotEqual(new['id'], q['id'])
        self.assertEqual(self.call('lecturer', 'state')['exams'][0]['questions'], ['q-demo-v1'])
        with self.assertRaises(Error):
            self.call('admin', 'schedule', id='exam-demo-v1', start=time.time(), end=time.time()+7200, duration=30)

    def test_unassigned_staff_denied(self):
        with self.store.db() as db:
            self.store.add_user(db, 'outsider', 'Other Lecturer', 'lecturer', 'LongPassword123')
        token = self.store.login('outsider', 'LongPassword123')
        self.assertEqual(self.store.dispatch(token, 'state', {})['courses'], [])
        with self.assertRaises(Error):
            self.store.dispatch(token, 'approve_question', {'id': 'q-demo-v1'})

    def test_submission_is_immutable_and_receipt_stable(self):
        a = self.submit()
        b = self.call('candidate', 'save', id=a['id'], revision=a['revision'], answers={'q-demo-v1':'Changed'})
        self.assertEqual(a, b)
        self.assertEqual(a['receipt'], self.call('candidate', 'submit', id=a['id'], revision=1)['receipt'])


if __name__ == '__main__':
    unittest.main()
