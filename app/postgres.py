"""Small DB-API adapter for the application's existing parameterized queries."""
class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def fetchone(self):
        row = self.cursor.fetchone()
        return Row(row) if row is not None else None

    def __iter__(self):
        for row in self.cursor:
            yield Row(row)


class Connection:
    def __init__(self, url):
        import psycopg
        from psycopg.rows import dict_row
        self.connection = psycopg.connect(url, row_factory=dict_row, connect_timeout=10)
        # Preserve SQLite's serialized write semantics across serverless instances.
        self.connection.execute('SELECT pg_advisory_xact_lock(718345902)')

    def execute(self, sql, parameters=()):
        import psycopg
        import sqlite3
        try:
            return Cursor(self.connection.execute(sql.replace('?', '%s'), parameters))
        except psycopg.IntegrityError as exc:
            raise sqlite3.IntegrityError('A duplicate or invalid record was rejected.') from exc

    def executescript(self, sql):
        for statement in sql.split(';'):
            if statement.strip():
                self.connection.execute(statement)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()


SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT, role TEXT, salt TEXT, password TEXT);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT, expires DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, kind TEXT, body TEXT, rowid BIGSERIAL UNIQUE);
CREATE TABLE IF NOT EXISTS audit(seq BIGSERIAL PRIMARY KEY, at DOUBLE PRECISION, actor TEXT, action TEXT, record_id TEXT, detail TEXT);
'''
