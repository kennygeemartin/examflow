import importlib.util
import json
import os
import pathlib
import sys
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'app'))
import server
from hosting import hosted_store
from postgres import Row, SCHEMA, Connection


class Hosting(unittest.TestCase):
    def test_postgres_queries_are_scoped_to_application_schema(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        connection = MagicMock()
        psycopg = SimpleNamespace(connect=MagicMock(return_value=connection))
        rows = SimpleNamespace(dict_row=object())
        with patch.dict(sys.modules, {'psycopg': psycopg, 'psycopg.rows': rows}):
            Connection('postgresql://unused-test-placeholder')
        self.assertEqual(connection.execute.call_args_list[-1].args[0], 'SET LOCAL search_path TO examflow, pg_catalog')
        self.assertTrue(SCHEMA.strip().startswith('CREATE SCHEMA IF NOT EXISTS examflow;'))

    def test_missing_database_fails_clearly(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'DATABASE_URL'):
                hosted_store()

    def test_row_supports_existing_named_and_index_access(self):
        row = Row(id='CSC301', title='Database systems')
        self.assertEqual(row[0], 'CSC301')
        self.assertEqual(row['title'], 'Database systems')
        self.assertEqual(dict(row), {'id': 'CSC301', 'title': 'Database systems'})

    def test_routes_cover_public_interface_and_api(self):
        config = json.loads((ROOT / 'vercel.json').read_text())
        self.assertEqual(config['outputDirectory'], 'public')
        self.assertTrue((ROOT / 'public').is_dir())
        self.assertEqual({r['src'] for r in config['routes']}, {'/', '/style.css', '/client.js', '/assets/examination-background.png', '/api/.*'})

    def test_serverless_entry_renders_without_database(self):
        spec = importlib.util.spec_from_file_location('vercel_entry', ROOT / 'api' / 'index.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        previous = server.store
        server.store = None
        http = server.ThreadingHTTPServer(('127.0.0.1', 0), module.handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        url = 'http://127.0.0.1:' + str(http.server_port)
        try:
            with urllib.request.urlopen(url) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b'ExamFlow', response.read())
            with patch.dict(os.environ, {}, clear=True):
                request = urllib.request.Request(url + '/api/state', b'{}', {'X-Exam-Client': '1'})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(request)
                self.assertEqual(caught.exception.code, 503)
                self.assertIn('DATABASE_URL', json.loads(caught.exception.read())['error'])
        finally:
            http.shutdown()
            http.server_close()
            thread.join()
            server.store = previous


if __name__ == '__main__':
    unittest.main()
