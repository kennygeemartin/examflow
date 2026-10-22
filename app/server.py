import argparse
import http.cookies
import json
import pathlib
import secrets
import sqlite3
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from domain import Store, Error
from inference import status, generate

ROOT = pathlib.Path(__file__).resolve().parent
store = None
failures = {}


class Handler(BaseHTTPRequestHandler):
    secure_cookie = False

    def reply(self, status_code, data, cookie=None, content_type='application/json'):
        body = json.dumps(data).encode() if content_type == 'application/json' else data
        self.send_response(status_code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'")
        if cookie:
            if self.secure_cookie:
                cookie += '; Secure'
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)

    def token(self):
        cookies = http.cookies.SimpleCookie(self.headers.get('Cookie', ''))
        return cookies['session'].value if 'session' in cookies else ''

    def do_GET(self):
        path = self.path.split('?')[0]
        if path in ['/', '/style.css', '/client.js']:
            name = 'index.html' if path == '/' else path[1:]
            mime = {'index.html': 'text/html; charset=utf-8', 'style.css': 'text/css', 'client.js': 'text/javascript'}[name]
            self.reply(200, (ROOT / name).read_bytes(), content_type=mime)
        else:
            self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        try:
            # Custom request header prevents cross-site form submissions, without CORS access.
            if self.headers.get('X-Exam-Client') != '1':
                raise Error('Invalid request origin.', 403)
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2000000:
                raise Error('Request exceeds the permitted size.', 413)
            p = json.loads(self.rfile.read(length))
            action = self.path.removeprefix('/api/')
            if action == 'login':
                ip = self.client_address[0]
                recent = [t for t in failures.get(ip, []) if time.time() - t < 300]
                if len(recent) >= 10:
                    raise Error('Too many attempts. Try again in five minutes.', 429)
                try:
                    token = store.login(p['id'], p['password'])
                except Error:
                    failures[ip] = recent + [time.time()]
                    raise
                failures.pop(ip, None)
                self.reply(200, {'ok': True}, 'session=' + token + '; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800')
                return
            if action in ['model', 'generate']:
                with store.db() as db:
                    u = store.user(db, self.token())
                    store.require(u, 'lecturer', 'administrator' if action == 'model' else 'lecturer')
                if action == 'model':
                    result = status()
                else:
                    result = generate(p['seed'], p.get('count', 25))
                    with store.db() as db:
                        result['id'] = secrets.token_hex(12)
                        result['author'] = u['id']
                        store.put(db, 'generated_draft', result)
                        store.audit(db, u, 'generate_draft', result['id'], result['model_version'])
            else:
                result = store.dispatch(self.token(), action, p)
            self.reply(200, result, 'session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0' if action == 'logout' else None)
        except Error as e:
            self.reply(e.status, {'error': str(e)})
        except (ValueError, KeyError, TypeError, sqlite3.IntegrityError) as e:
            self.reply(400, {'error': 'Invalid request: ' + str(e)})
        except ImportError:
            self.reply(503, {'error': 'Generation needs TensorFlow and NumPy. Install requirements-model.txt in your Python environment.'})
        except Exception as e:
            print('Request failed:', repr(e))
            # Codes identify database failures without exposing queries or credentials.
            details = {'error': 'The operation failed. No save acknowledgement was issued. Check the server console.'}
            sqlstate = getattr(e, 'sqlstate', None)
            if isinstance(sqlstate, str) and len(sqlstate) == 5 and sqlstate.isalnum():
                details['database_error_code'] = sqlstate
            details['error_type'] = type(e).__name__
            self.reply(500, details)


def main():
    global store
    store = Store(str(ROOT.parent / 'examinations.sqlite3'))
    parser = argparse.ArgumentParser()
    parser.add_argument('--init', action='store_true', help='Create administrator account interactively')
    parser.add_argument('--demo', action='store_true', help='Initialize isolated demonstration data')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    if args.init:
        import getpass
        with store.db() as db:
            store.add_user(db, input('Administrator ID: ').strip(), input('Full name: ').strip(), 'administrator', getpass.getpass('Password (10+ characters): '))
        print('Administrator created.')
        return
    if args.demo:
        from seed import seed
        seed(store)
    def expire_attempts():
        while True:
            try:
                with store.db() as db:
                    for attempt in store.all(db, 'attempt'):
                        if attempt['status'] == 'active' and time.time() >= attempt['deadline']:
                            store.finish(db, attempt, 'timeout')
            except Exception as exc:
                print('Deadline sweep failed:', repr(exc))
            time.sleep(1)
    threading.Thread(target=expire_attempts, daemon=True).start()
    print(f'ExamFlow is available at http://127.0.0.1:{args.port}. Press Ctrl+C to stop.')
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
