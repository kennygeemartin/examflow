import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager


class Error(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


class Store:
    def __init__(self, path):
        self.path = path
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT, role TEXT, salt TEXT, password TEXT);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT, expires REAL);
            CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, kind TEXT, body TEXT);
            CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY, at REAL, actor TEXT, action TEXT, record_id TEXT, detail TEXT);
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def add_user(self, db, uid, name, role, password):
        if role not in ['candidate', 'lecturer', 'moderator', 'administrator'] or len(password) < 10:
            raise Error('Choose a valid role and a password of at least 10 characters.')
        salt = secrets.token_hex(16)
        hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 260000).hex()
        db.execute('INSERT INTO users VALUES(?,?,?,?,?)', (uid, name, role, salt, hashed))

    def login(self, uid, password):
        with self.db() as db:
            u = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
            if not u or not secrets.compare_digest(u['password'], hashlib.pbkdf2_hmac('sha256', password.encode(), u['salt'].encode(), 260000).hex()):
                raise Error('Invalid account or password.', 401)
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (token, uid, time.time() + 28800))
            return token

    def user(self, db, token):
        u = db.execute('SELECT u.id,u.name,u.role FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=? AND s.expires>?', (token, time.time())).fetchone()
        if not u:
            raise Error('Please sign in.', 401)
        return dict(u)

    def get(self, db, rid):
        row = db.execute('SELECT body FROM records WHERE id=?', (rid,)).fetchone()
        if not row:
            raise Error('Record not found.', 404)
        return json.loads(row[0])

    def all(self, db, kind):
        return [json.loads(r[0]) for r in db.execute('SELECT body FROM records WHERE kind=? ORDER BY rowid DESC', (kind,))]

    def put(self, db, kind, obj):
        existing = db.execute('SELECT kind FROM records WHERE id=?', (obj['id'],)).fetchone()
        if existing and existing[0] != kind:
            raise Error('This identifier is already used by another record type.')
        db.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body', (obj['id'], kind, json.dumps(obj)))
        return obj

    def audit(self, db, user, action, rid, detail=''):
        db.execute('INSERT INTO audit(at,actor,action,record_id,detail) VALUES(?,?,?,?,?)', (time.time(), user['id'], action, rid, detail))

    def require(self, user, *roles):
        if user['role'] not in roles:
            raise Error('Your role cannot perform this action.', 403)

    def assigned(self, user, course, key='lecturers'):
        if user['id'] not in course[key]:
            raise Error('You are not assigned to this course.', 403)

    def finish(self, db, a, reason):
        if a['status'] == 'active':
            a.update(status='submitted', submitted_at=time.time(), reason=reason, checksum=digest(a['answers']), receipt='REC-' + secrets.token_hex(8).upper())
            self.put(db, 'attempt', a)
            self.audit(db, {'id': a['candidate']}, 'submit', a['id'], reason)
        return a

    def dispatch(self, token, action, p):
        with self.db() as db:
            u = self.user(db, token)
            now = time.time()
            for a in self.all(db, 'attempt'):
                if a['status'] == 'active' and now >= a['deadline']:
                    self.finish(db, a, 'timeout')
            if action == 'state':
                return self.state(db, u)
            if action == 'logout':
                db.execute('DELETE FROM sessions WHERE token=?', (token,))
                return {'ok': True}
            if action == 'user':
                self.require(u, 'administrator')
                self.add_user(db, p['id'], p['name'], p['role'], p['password'])
                self.audit(db, u, 'create_user', p['id'])
                return {'ok': True}
            if action == 'course':
                self.require(u, 'administrator')
                obj = {'id': p['id'], 'title': p['title'], 'lecturers': p['lecturers'], 'moderators': p['moderators'], 'candidates': p['candidates']}
                for key, role in [('lecturers', 'lecturer'), ('moderators', 'moderator'), ('candidates', 'candidate')]:
                    for uid in obj[key]:
                        row = db.execute('SELECT role FROM users WHERE id=?', (uid,)).fetchone()
                        if not row or row[0] != role:
                            raise Error('Unknown user or incorrect role: ' + uid)
                self.put(db, 'course', obj)
                self.audit(db, u, 'save_course', obj['id'])
                return obj
            if action == 'question':
                self.require(u, 'lecturer')
                self.assigned(u, self.get(db, p['course']))
                criteria = p['criteria']
                if len(criteria) != 3 or any(not c.get('description', '').strip() or not all(str(c.get(str(i), '')).strip() for i in range(3)) for c in criteria):
                    raise Error('Provide three criteria with descriptions and anchors for classes 0, 1 and 2.')
                if not p['text'].strip() or not p['reference'].strip():
                    raise Error('Question and reference answer are required.')
                parent = p.get('parent')
                if parent and self.get(db, parent)['course'] != p['course']:
                    raise Error('Version course mismatch.')
                obj = dict(id=secrets.token_hex(12), course=p['course'], text=p['text'], reference=p['reference'], alternatives=p.get('alternatives', ''), criteria=criteria, status='draft', parent=parent, author=u['id'], created_at=now, maximum=6)
                self.put(db, 'question', obj)
                self.audit(db, u, 'question_version', obj['id'])
                return obj
            if action == 'approve_question':
                self.require(u, 'lecturer')
                q = self.get(db, p['id'])
                self.assigned(u, self.get(db, q['course']))
                if q['status'] != 'draft':
                    raise Error('This version is already approved.')
                q.update(status='approved', approved_by=u['id'], approved_at=now)
                self.put(db, 'question', q)
                self.audit(db, u, action, q['id'])
                return q
            if action == 'exam':
                self.require(u, 'lecturer')
                c = self.get(db, p['course'])
                self.assigned(u, c)
                if not p['questions'] or len(set(p['questions'])) != len(p['questions']):
                    raise Error('Select unique approved questions.')
                for qid in p['questions']:
                    q = self.get(db, qid)
                    if q.get('status') != 'approved' or q.get('course') != c['id']:
                        raise Error('Only approved question versions from this course are allowed.')
                obj = dict(id=secrets.token_hex(12), course=c['id'], title=p['title'], questions=p['questions'], status='prepared', author=u['id'])
                self.put(db, 'exam', obj)
                self.audit(db, u, 'prepare_exam', obj['id'])
                return obj
            if action == 'schedule':
                self.require(u, 'administrator')
                e = self.get(db, p['id'])
                if e['status'] != 'prepared':
                    raise Error('Scheduled papers are frozen; prepare a new paper to change one.')
                start, end, duration = float(p['start']), float(p['end']), int(p['duration'])
                if end <= start or duration < 1 or duration * 60 > end - start:
                    raise Error('Invalid examination window or duration.')
                e.update(start=start, end=end, duration=duration, status='scheduled', approved_by=u['id'])
                self.put(db, 'exam', e)
                self.audit(db, u, action, e['id'])
                return e
            if action == 'start':
                self.require(u, 'candidate')
                e = self.get(db, p['id'])
                self.assigned(u, self.get(db, e['course']), 'candidates')
                if e['status'] != 'scheduled' or not e['start'] <= now < e['end']:
                    raise Error('The examination window is closed.')
                existing = [a for a in self.all(db, 'attempt') if a['exam'] == e['id'] and a['candidate'] == u['id']]
                if existing:
                    return existing[0]
                obj = dict(id=secrets.token_hex(12), exam=e['id'], candidate=u['id'], started_at=now, deadline=min(e['end'], now + e['duration'] * 60), answers={qid: '' for qid in e['questions']}, revision=0, status='active')
                self.put(db, 'attempt', obj)
                self.audit(db, u, 'start', obj['id'])
                return obj
            if action in ['save', 'submit']:
                self.require(u, 'candidate')
                a = self.get(db, p['id'])
                if a['candidate'] != u['id']:
                    raise Error('This script belongs to another candidate.', 403)
                if a['status'] != 'active':
                    return a
                if int(p['revision']) != a['revision']:
                    raise Error('A newer revision exists. Reload before saving.', 409)
                if action == 'save':
                    if set(p['answers']) != set(a['answers']) or any(not isinstance(v, str) or len(v) > 100000 for v in p['answers'].values()):
                        raise Error('Invalid answer set.')
                    a.update(answers=p['answers'], revision=a['revision'] + 1, saved_at=now)
                    self.put(db, 'attempt', a)
                    self.put(db, 'revision', dict(id=a['id'] + ':' + str(a['revision']), attempt=a['id'], revision=a['revision'], answers=a['answers'], saved_at=now))
                    self.audit(db, u, 'save', a['id'], str(a['revision']))
                    return a
                return self.finish(db, a, 'candidate')
            if action == 'review':
                self.require(u, 'lecturer', 'moderator')
                a = self.get(db, p['id'])
                e = self.get(db, a['exam'])
                c = self.get(db, e['course'])
                self.assigned(u, c, 'moderators' if u['role'] == 'moderator' else 'lecturers')
                if a['status'] != 'submitted':
                    raise Error('Only finalized scripts can be marked.')
                if set(p['marks']) != set(e['questions']) or any(len(v) != 3 or any(type(x) is not int or x not in [0, 1, 2] for x in v) for v in p['marks'].values()):
                    raise Error('Each question requires three integer criterion marks between 0 and 2.')
                if not p.get('reason', '').strip():
                    raise Error('An academic justification is required.')
                previous = [r for r in self.all(db, 'review') if r['attempt'] == a['id']]
                if u['role'] == 'moderator' and not any(r['stage'] == 'lecturer' for r in previous):
                    raise Error('A lecturer must review this script first.')
                obj = dict(id=secrets.token_hex(12), attempt=a['id'], marks=p['marks'], total=sum(sum(v) for v in p['marks'].values()), reason=p['reason'], stage=u['role'], author=u['id'], at=now, version=len(previous) + 1, published=False, model_version=None)
                self.put(db, 'review', obj)
                self.audit(db, u, 'academic_review', obj['id'], p['reason'])
                return obj
            if action == 'publish':
                self.require(u, 'moderator')
                r = self.get(db, p['id'])
                a = self.get(db, r['attempt'])
                self.assigned(u, self.get(db, self.get(db, a['exam'])['course']), 'moderators')
                latest = next(x for x in self.all(db, 'review') if x['attempt'] == a['id'])
                if latest['id'] != r['id'] or r['stage'] != 'moderator':
                    raise Error('Only the latest moderated result can be published.')
                r.update(published=True, published_at=now)
                self.put(db, 'review', r)
                self.audit(db, u, action, r['id'])
                return r
            raise Error('Unknown action.', 404)

    def state(self, db, u):
        role = u['role']
        key = {'candidate': 'candidates', 'lecturer': 'lecturers', 'moderator': 'moderators'}.get(role)
        courses = [c for c in self.all(db, 'course') if role == 'administrator' or u['id'] in c[key]]
        ids = {c['id'] for c in courses}
        exams = [e for e in self.all(db, 'exam') if e['course'] in ids and (role != 'candidate' or e['status'] == 'scheduled')]
        eids = {e['id'] for e in exams}
        attempts = [a for a in self.all(db, 'attempt') if a['exam'] in eids and (role != 'candidate' or a['candidate'] == u['id'])]
        aids = {a['id'] for a in attempts}
        reviews = [r for r in self.all(db, 'review') if r['attempt'] in aids and (role != 'candidate' or r['published'])]
        questions = [q for q in self.all(db, 'question') if q['course'] in ids]
        if role == 'candidate':
            visible = {qid for a in attempts for qid in self.get(db, a['exam'])['questions']}
            questions = [{k: q[k] for k in ['id', 'text', 'maximum']} for q in questions if q['id'] in visible]
            reviews = [{k: r[k] for k in ['id', 'attempt', 'total', 'version', 'published_at']} for r in reviews]
        users = [dict(r) for r in db.execute('SELECT id,name,role FROM users')] if role == 'administrator' else []
        audit = [dict(r) for r in db.execute('SELECT * FROM audit ORDER BY seq DESC LIMIT 200')] if role == 'administrator' else []
        return dict(user=u, server_time=time.time(), courses=courses, exams=exams, attempts=attempts, questions=questions, reviews=reviews, users=users, audit=audit)
