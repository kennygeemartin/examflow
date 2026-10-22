import http.cookiejar
import json
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'app'))
import server
from domain import Store
from seed import seed


class HTTPIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).resolve().parent)
        server.store = Store(str(pathlib.Path(cls.temp.name) / 'http.sqlite3'))
        seed(server.store)
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.url = 'http://127.0.0.1:' + str(cls.http.server_port)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def setUp(self):
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def post(self, action, data=None, custom_header=True):
        headers = {'Content-Type': 'application/json'}
        if custom_header:
            headers['X-Exam-Client'] = '1'
        request = urllib.request.Request(self.url + '/api/' + action, json.dumps(data or {}).encode(), headers)
        return self.client.open(request)

    def test_static_and_authenticated_flow(self):
        for path in ['/', '/client.js', '/browser_inference.js', '/style.css',
                     '/assets/examination-background.png', '/assets/generator/model.json',
                     '/assets/generator/tokenizer.json', '/assets/generator/group1-shard1of1.bin']:
            with self.client.open(self.url + path) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(response.read())
                if path.endswith('.bin'):
                    self.assertEqual(response.headers['Content-Type'], 'application/octet-stream')
        with self.post('login', {'id': 'candidate', 'password': 'DemoExam2026!'}) as response:
            self.assertIn('HttpOnly', response.headers['Set-Cookie'])
        with self.post('state') as response:
            data = json.load(response)
            self.assertEqual(data['user']['role'], 'candidate')
            self.assertEqual(data['questions'], [])
        with self.post('start', {'id': 'exam-demo-v1'}) as response:
            attempt = json.load(response)
        with self.post('save', {'id': attempt['id'], 'revision': 0, 'answers': {'q-demo-v1': 'HTTP-saved answer'}}) as response:
            self.assertEqual(json.load(response)['revision'], 1)
        # A second read verifies the acknowledgement corresponds to committed data.
        with self.post('state') as response:
            self.assertEqual(json.load(response)['attempts'][0]['answers']['q-demo-v1'], 'HTTP-saved answer')
        with self.post('logout'):
            pass
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.post('state')
        self.assertEqual(context.exception.code, 401)

    def test_cross_site_form_and_direct_database_access_denied(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.post('login', {'id':'candidate','password':'DemoExam2026!'}, custom_header=False)
        self.assertEqual(context.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.client.open(self.url + '/examinations.sqlite3')
        self.assertEqual(context.exception.code, 404)

    def test_browser_generation_is_authenticated_versioned_and_stored(self):
        with self.post('login', {'id': 'lecturer', 'password': 'DemoExam2026!'}) as response:
            self.assertEqual(response.status, 200)
        with self.post('model') as response:
            model = json.load(response)
        self.assertEqual(model['generator'], 'browser_ready')
        draft = {
            'text': 'explain the concept of learning',
            'seed': 'explain the concept of',
            'model_version': model['model_sha256'],
            'tokenizer_version': model['tokenizer_sha256'],
            'status': 'draft_requires_lecturer_approval',
        }
        with self.post('store_browser_draft', draft) as response:
            result = json.load(response)
        self.assertEqual(result['text'], draft['text'])
        self.assertEqual(result['author'], 'lecturer')
        self.assertEqual(result['model_version'], model['model_sha256'])


if __name__ == '__main__':
    unittest.main()
