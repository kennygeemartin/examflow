# ExamFlow

A local browser application for preparing, conducting and reviewing subjective examinations. Built from the two supplied system descriptions. The application server uses Python's standard library and SQLite; it needs no npm packages or cloud service.

## Start

Use Python 3.10 or newer. In PowerShell in this folder:

```powershell
.\start.ps1 -Demo
```

For a fresh GitHub checkout, install Python first. The portable `.runtime` folder, local database, trained model and tokenizer are excluded from the repository. To enable question generation, install `requirements-model.txt` (or the recorded `requirements-model.lock.txt`) in your Python environment, then supply the model at `exam_question_generator_lstm.keras` and its original tokenizer at `models/tokenizer.json`. The examination and human marking workflows can run without these artifacts.

Open **http://127.0.0.1:8080**. Demo account IDs: `admin`, `lecturer`, `moderator`, `candidate`. All use `DemoExam2026!`. The sample examination window lasts 24 hours from initial seeding. Demo data is only inserted into an empty database. Use separate browser profiles for simultaneous roles, or sign out between accounts.

For a clean installation, use a new database and run `python app/server.py --init`, then `python app/server.py`. Do not use demo credentials with real examination data. The included Windows portable runtime runs the application and can also host its local TensorFlow dependencies.

## Try the complete workflow

1. Candidate: enter the sample examination, write answers, save, and submit. Download the receipt.
2. Lecturer: open Marking review; inspect the frozen answer, reference and rubric. Record three criterion marks and an academic justification.
3. Moderator: independently inspect the script, approve a moderated version, then publish it.
4. Candidate: open Results to see the published total.
5. Administrator: inspect Audit trail. Administrators can manage accounts, assignments and schedules, but cannot mark scripts.

For a new paper, the administrator first creates accounts and a course with lecturer, moderator and candidate assignments. The lecturer creates a question with three criteria and three anchors per criterion, explicitly approves it, then prepares a paper. The administrator schedules that frozen paper.

## Your model

`exam_question_generator_lstm.keras` is preserved. Inspection shows a 47-token input, a 1,168-entry embedding, a bidirectional LSTM and a 1,168-class softmax vocabulary head. It is a next-word question generator, **not a criterion classifier**.

The supplied `tokenizer.json` has been copied to `models/tokenizer.json`. It contains 1,167 word indices, compatible with the model's 1,168-entry vocabulary including padding index zero. This establishes dimensional compatibility; the original training notebook is still needed to confirm preprocessing and provenance. The adapter uses the tokenizer's recorded normalization and pre-padding/pre-truncation to 47 tokens. Export the notebook too so these settings can be verified before academic use. To export again, use [export_from_colab.py](export_from_colab.py) in the original Colab runtime; do not fit a replacement tokenizer on a new corpus.

With a full Python installation:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-model.txt
.\.venv\Scripts\python.exe app/server.py
```

On this machine, TensorFlow and its dependencies are also installed in `.runtime`, so `start.ps1` can run generation directly. Exact installed versions are recorded in `requirements-model.lock.txt`. The supplied model/tokenizer passed the three checks in `tests/test_inference.py`, including real ten-token generation and rejection of an unknown-word prompt. Initial model loading is slower than subsequent requests.

Draft extraction loads the model with `compile=False` and safe deserialization, predicts actual vocabulary tokens, records the model and tokenizer SHA-256 hashes and seed, and stores output in the preparation area. Model loading is cached between requests and refreshed when either artifact changes. Copy a reviewed draft into Question bank and add its approved reference and rubric. Model output cannot enter a paper until the question version is approved.

**Automated marking is intentionally unavailable until a separately trained and validated three-class criterion scorer is supplied.** No text similarity heuristic is presented as trained-model marking. All currently recorded marks are explicitly human academic decisions. The eventual scorer requires its encoder, classifier, feature pipeline, label order, confidence thresholds and validation evidence. Add these before implementing real recommendations, evidence retrieval or confidence-based review routing.

## Integrity controls

- Passwords use salted PBKDF2 hashes. Sessions are HttpOnly, SameSite cookies, expire after eight hours, and are checked server-side. Login attempts are rate limited in memory.
- Every server action checks role and course assignment. Candidate responses never include references, rubrics or unreleased academic decisions.
- Questions and rubrics become new records when revised. Scheduled paper content and timing are frozen. No questions are generated during an examination.
- A resumed attempt retains its original server deadline. SQLite transactions serialize saves and reject stale revisions. Acknowledgements are sent after commit. Each successful save retains a timestamped answer revision. The browser autosaves every 20 seconds and offers explicit save.
- Submission finalizes the last server-acknowledged revision, preserves answer text and issues a reference and SHA-256 checksum. Timeout uses saved content and discards unsaved browser content. A periodic server sweep finalizes expired attempts, including disconnected ones.
- Criterion marks are independently bounded to integer 0, 1 or 2. Three criteria make a question maximum of six. Lecturer review precedes moderator approval; only moderated results can be published. Amendments create additional review versions and retain older publications.
- Academic decisions, question versions and operational events have an audit history. Receipt checksums cover canonical JSON answers: sorted keys, compact separators, UTF-8 and unescaped Unicode.

## Tests and operation

```powershell
python -m unittest discover -s tests -v
```

The server binds to loopback only. This is an initial local implementation: institution-wide deployment still needs HTTPS hosting, institutional authentication, operational backups and recovery drills, accessibility/user acceptance testing, and load testing. The trained marking model remains an external dependency. CSV import, reference extraction, cohort reports and a recovery administration screen are not implemented.

All application data resides in `examinations.sqlite3` and its SQLite WAL/SHM files. Stop the server before copying all database files for a consistent backup, or use SQLite's backup API. Do not remove or reset the database to clear demo data without first preserving anything you need. Audit records are application-controlled, not tamper-proof against a person who can directly edit the database.
