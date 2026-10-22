# Deploy ExamFlow on Vercel

The repository includes `api/index.py` and `vercel.json` so Vercel can serve the interface and route `/api/*` requests to a Python function. SQLite is for local development; the hosted application uses PostgreSQL. Do not use a `/tmp` SQLite database for examination data: it is not shared durable storage.

## Vercel project settings

1. Import `kennygeemartin/examflow`, branch `main`, root directory `.`.
2. Framework preset: **Other**. Clear any manually configured build command or output directory so `vercel.json` controls them. No npm build is needed.
3. Open **Storage** in the Vercel project and create/connect a PostgreSQL database, for example Neon. Follow the provider's setup flow. If it requires choosing a paid plan, review its price before proceeding.
4. In **Settings → Environment Variables**, confirm a PostgreSQL connection string exists as `DATABASE_URL` for **Production**. If the integration used a different name, add `DATABASE_URL` with the provider's connection string. Keep the provider's SSL parameters. Do not paste credentials into source code or chat.
5. Add `EXAMFLOW_ADMIN_PASSWORD` with a unique password of at least 10 characters. Optionally set `EXAMFLOW_ADMIN_ID` (default `admin`) and `EXAMFLOW_ADMIN_NAME`.
6. Redeploy the latest `main` commit. Changes to environment variables take effect on a new deployment.
7. Open the production URL and sign in with the configured administrator ID and password. Tables and the initial administrator are created on the first API request. Create staff and candidate accounts, course assignments, approved questions and papers through the application.

The administrator password variable only creates the first administrator in an empty database; changing the variable does not overwrite an existing user's password.

For a disposable demonstration only, set `EXAMFLOW_DEMO=true` before the first deployment against an **empty** database. This creates the familiar `admin`, `lecturer`, `moderator`, `candidate` accounts with password `DemoExam2026!` and a paper available for 24 hours. Demo seeding preserves an existing database. Never use public demo credentials with real academic data.

## Expected behavior

- `/` serves the sign-in interface even before a database is configured.
- An API request without `DATABASE_URL` returns a JSON setup message with HTTP 503.
- Sessions, answer revisions, receipts and academic reviews persist in PostgreSQL across function instances and deployments.
- Hosted tables live in the dedicated `examflow` schema to avoid collisions with existing tables in `public`. Existing public tables are left untouched.
- PostgreSQL transactions serialize modifications to preserve the current SQLite workflow's save semantics. This is intentionally conservative; load-test before large cohorts.
- The serverless entry point does not start a background server or timeout thread. Each authenticated operation finalizes expired scripts based on their saved server deadline. Even if a candidate disconnects, a later save cannot add time or change the final saved answer. Operational finalization is lazy until the next authenticated request; a scheduler would be needed for immediate unattended processing.
- HTTPS deployments use Secure, HttpOnly, SameSite session cookies.
- The model and tokenizer are not in GitHub or the Vercel bundle. The model screen reports `model_required`; question generation needs a separate inference deployment. Human examination and review functions do not require TensorFlow.

## Troubleshooting

**404 NOT_FOUND:** check that Production is using the latest commit, the project root is `.`, the framework is Other, and project overrides do not supersede `vercel.json`. Check the deployment build log for discovery of `api/index.py`.

**Connect a PostgreSQL database:** `DATABASE_URL` is absent, misnamed, or not assigned to Production. Configure it and redeploy.

**Database connection failed:** check provider availability, credentials, SSL settings and the connection string. Do not publish the connection URL in logs.

**Invalid account or password:** hosted accounts are separate from the SQLite database on your PC. Use your configured bootstrap administrator or explicitly seed a separate demo database.

## Local operation

`start.ps1` continues to use SQLite and the local model. The Vercel entry point always requires PostgreSQL. Install hosted dependencies with `python -m pip install -r requirements.txt`; TensorFlow is not part of that file.
