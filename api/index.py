"""Vercel's serverless HTTP entry point; no local database or background server."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'app'))
import server
from hosting import hosted_store


class handler(server.Handler):
    secure_cookie = True

    def do_POST(self):
        if server.store is None:
            try:
                server.store = hosted_store()
            except ValueError as exc:
                self.reply(503, {'error': str(exc)})
                return
            except Exception:
                # Never print or return a database URL, which can contain credentials.
                self.reply(503, {'error': 'Database connection failed. Check DATABASE_URL and database availability in Vercel settings.'})
                return
        super().do_POST()
