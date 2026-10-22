import time


def seed(store):
    with store.db() as db:
        if db.execute('SELECT COUNT(*) FROM users').fetchone()[0]:
            print('Existing database preserved; demo seeding skipped.')
            return
        for uid, name, role in [('admin', 'System Administrator', 'administrator'), ('lecturer', 'Dr. Ada Okafor', 'lecturer'), ('moderator', 'Prof. Tunde Bello', 'moderator'), ('candidate', 'Alex Johnson', 'candidate')]:
            store.add_user(db, uid, name, role, 'DemoExam2026!')
        store.put(db, 'course', dict(id='CSC301', title='Database Systems', lecturers=['lecturer'], moderators=['moderator'], candidates=['candidate']))
        criteria = [
            {'description': 'Explains atomicity', '0': 'Absent or incorrect', '1': 'Mentions all-or-nothing execution', '2': 'Explains all-or-nothing execution and rollback on failure'},
            {'description': 'Explains consistency', '0': 'Absent or incorrect', '1': 'Mentions valid database state', '2': 'Explains preservation of constraints before and after a transaction'},
            {'description': 'Explains isolation', '0': 'Absent or incorrect', '1': 'Mentions concurrent transactions', '2': 'Explains transactions behaving as if executed independently'}]
        store.put(db, 'question', dict(id='q-demo-v1', course='CSC301', text='Explain atomicity, consistency and isolation in database transactions. Illustrate each property with an example.', reference='Atomicity ensures every operation succeeds together or all changes are rolled back. Consistency preserves database constraints. Isolation ensures concurrent transactions do not expose intermediate states.', alternatives='Equivalent explanations with valid banking or inventory examples are acceptable.', criteria=criteria, status='approved', parent=None, author='lecturer', approved_by='lecturer', created_at=time.time(), maximum=6))
        store.put(db, 'exam', dict(id='exam-demo-v1', course='CSC301', title='Database Systems · Theory assessment', questions=['q-demo-v1'], status='scheduled', author='lecturer', approved_by='admin', start=time.time()-60, end=time.time()+86400, duration=45))
    print('Demo accounts: admin / lecturer / moderator / candidate. Password: DemoExam2026!')
