================================================================================
GTM AUTOMATION — PRODUCTION SETUP & HANDOFF
================================================================================

This README lists the manual steps required to bring the GTM Automation app
fully online (browser-testable, end-to-end). Everything else (code, migrations,
wiring, deployment scaffolding) is done.

--------------------------------------------------------------------------------
0. PREREQUISITES
--------------------------------------------------------------------------------
  * Python 3.13
  * Node 20+ and npm
  * sqlite3 CLI (optional but useful)
  * (Production only) nginx, systemd, a TLS certificate

--------------------------------------------------------------------------------
1. BACKEND — first time setup
--------------------------------------------------------------------------------
  cd gtm-automation/backend
  python3.13 -m venv .venv
  source .venv/bin/activate
  pip install -r pip_requirements.txt
  cp .env.example .env             # edit values — see step 2
  python setup_database.py         # applies all migrations through 015
  export PYTHONPATH=$PYTHONPATH:.
  uvicorn main:app --host 127.0.0.1 --port 5214 --reload

Backend on http://127.0.0.1:5214
  GET  /                  → service banner
  GET  /health            → {"ok": true, ...}
  GET  /docs              → OpenAPI Swagger UI
  POST /auth/register     → first user becomes admin

--------------------------------------------------------------------------------
2. BACKEND — required .env values (in backend/.env)
--------------------------------------------------------------------------------
You MUST set:

  JWT_SECRET=<long random string>
      Generate with:
        python3 -c "import secrets; print(secrets.token_urlsafe(48))"
      In production, also set:
        ALLOW_REGISTRATION=false  (after creating your admin)

You SHOULD set ONE LLM provider key (otherwise the system falls back to
heuristic adapters — replies still work, just templated):

  OPENAI_APIKEY=sk-...
  ANTHROPIC_API_KEY=sk-ant-...
  GOOGLE_GENAI_APIKEY=...
  LLM_REPLY_MODEL=gpt-4o-mini   (default)

You SHOULD pick an email provider for real sends. Default is "fake" which
just logs to the database without sending.

  EMAIL_PROVIDER=fake | smtp | sendgrid | postmark

  # If smtp:
  SMTP_HOST=smtp.example.com
  SMTP_PORT=587
  SMTP_USER=...
  SMTP_PASS=...
  SMTP_FROM=hello@yourdomain.com
  SMTP_USE_TLS=true

  # If sendgrid:
  SENDGRID_API_KEY=SG.xxx
  SENDGRID_FROM=hello@yourdomain.com

  # If postmark:
  POSTMARK_SERVER_TOKEN=xxx
  POSTMARK_FROM=hello@yourdomain.com

Optional:
  SENTRY_DSN=https://...
  RATE_LIMIT_PER_MINUTE=120
  CORS_ORIGINS=http://localhost:5320,https://gtm.example.com

--------------------------------------------------------------------------------
3. FRONTEND — first time setup
--------------------------------------------------------------------------------
  cd gtm-automation/frontend
  npm install
  cp .env.example .env             # edit VITE_API_BASE if needed
  npm run dev

Frontend on http://localhost:5320

--------------------------------------------------------------------------------
4. STARTING THE APP (DAY-TO-DAY)
--------------------------------------------------------------------------------
Every time you want to use the app, run BOTH of these in separate terminals:

  Terminal 1 — backend:
    cd gtm-automation/backend
    source .venv/bin/activate
    export PYTHONPATH=$PYTHONPATH:.
    uvicorn main:app --host 127.0.0.1 --port 5214 --reload

  Terminal 2 — frontend:
    cd gtm-automation/frontend
    npm run dev

  Then open: http://localhost:5320

  Verify the backend is healthy before trying to register:
    curl http://127.0.0.1:5214/health
    → {"ok": true, ...}

--------------------------------------------------------------------------------
5. REGISTER YOUR FIRST USER AND CREATE A PROJECT
--------------------------------------------------------------------------------
Step 1 — Register via the browser:
  a. Open http://localhost:5320
  b. You are redirected to /login → click "Don't have an account? Register"
  c. Enter your full name, email, and a password (≥ 8 chars).
  d. Click Register.
     The FIRST user ever registered is automatically set to role=admin.
  e. You land on the dashboard. Your initials + role appear top-right.

Step 2 — (Optional) Register via curl instead of the browser:
    curl -s -X POST http://127.0.0.1:5214/auth/register \
      -H "Content-Type: application/json" \
      -d '{"email":"you@example.com","password":"yourpassword","full_name":"Your Name"}' \
      | python3 -m json.tool
    # Copy the access_token from the response.

Step 3 — Lock down registration after your account is created:
  Edit backend/.env and set:
    ALLOW_REGISTRATION=false
  Then restart the backend. New self-registrations will return 403.

Step 4 — Create your first project:
  a. In the browser: click the project switcher (top-left) → "New project"
     → type a name → Save. You are now inside project #1.
  b. Or via curl (replace <token> with your access_token from step 2):
       curl -s -X POST http://127.0.0.1:5214/projects \
         -H "Authorization: Bearer <token>" \
         -H "Content-Type: application/json" \
         -d '{"name":"My GTM Project"}' | python3 -m json.tool

Step 5 — Start the GTM workflow:
  ICPs → Companies → Contacts → Signals → Leads → Outreach → Sends → Replies
  Each step has a dedicated page in the left nav and a pipeline run type.

--------------------------------------------------------------------------------
6. END-TO-END SMOKE TEST IN BROWSER
--------------------------------------------------------------------------------
  1. Open http://localhost:5320
  2. You will be redirected to /login then /register (no token yet)
  3. Register with any email + password ≥ 8 chars.
     The FIRST user is automatically promoted to role=admin.
  4. After registering you land on the dashboard. Top-right corner shows
     your initials, name, role, and a logout button.
  5. Create a Project (top-left ProjectSwitcher → New project).
  6. Go to ICPs → create an ICP.
  7. Go to Companies → create a company; or use Pipeline Runs to ingest.
  8. Pipeline Runs → "Run Pipeline" → pick run_type and execute.
  9. Outreach / Sends / Replies / Inbox / Reasoning all work end-to-end.
 10. Logout → token cleared → redirect to /login.

If you set OPENAI_APIKEY, draft replies in the Inbox use the LLM adapter.
Otherwise they fall back to the heuristic adapter.

--------------------------------------------------------------------------------
7. PRODUCTION DEPLOYMENT — option A (Docker Compose)
--------------------------------------------------------------------------------
  cd gtm-automation
  cp backend/.env.example backend/.env   # fill in real values, see step 2
  cd _ops
  docker compose up -d --build

Frontend served on port 8080, backend on internal 5214.
Put your own nginx + TLS in front of port 8080 if exposing publicly.

--------------------------------------------------------------------------------
8. PRODUCTION DEPLOYMENT — option B (systemd + nginx)
--------------------------------------------------------------------------------
  # On the server (one-time):
  sudo mkdir -p /opt/gtm-automation /var/www/gtm-automation
  sudo chown -R $USER:$USER /opt/gtm-automation /var/www/gtm-automation
  git clone <your-repo-url> /opt/gtm-automation
  cd /opt/gtm-automation/backend
  cp .env.example .env                 # edit; set JWT_SECRET etc.
  sudo cp /opt/gtm-automation/_ops/gtm-api.service /etc/systemd/system/
  sudo cp /opt/gtm-automation/_ops/gtm-automation.nginx.conf \
          /etc/nginx/sites-available/gtm-automation
  sudo ln -s /etc/nginx/sites-available/gtm-automation \
             /etc/nginx/sites-enabled/gtm-automation

  # First deploy + every subsequent deploy:
  cd /opt/gtm-automation
  ./_ops/deploy.sh

  # One-time service enable:
  sudo systemctl daemon-reload
  sudo systemctl enable --now gtm-api.service

  # TLS (recommended): use certbot, then uncomment the 443 block in the
  # nginx site file and reload nginx.

--------------------------------------------------------------------------------
9. SECURITY CHECKLIST
--------------------------------------------------------------------------------
  [ ] JWT_SECRET set to a strong random value (NOT the default).
  [ ] ALLOW_REGISTRATION=false after the admin account is created.
  [ ] CORS_ORIGINS limited to your real frontend origin(s).
  [ ] EMAIL_PROVIDER set to smtp/sendgrid/postmark, NOT "fake".
  [ ] At least one LLM provider key configured.
  [ ] HTTPS terminated at nginx (or load balancer).
  [ ] Database file gtm-automation/backend/data/gtm.sqlite is backed up.
  [ ] SENTRY_DSN configured for error monitoring.
  [ ] Rate limit RATE_LIMIT_PER_MINUTE tuned for your traffic.

--------------------------------------------------------------------------------
10. WHAT'S IMPLEMENTED
--------------------------------------------------------------------------------
  Backend
  -------
    * JWT auth (register/login/me/change-password) — backend/api_auth.py
    * Bcrypt password hashing — backend/auth.py
    * Project-scoped access control helpers — auth.require_project_access()
    * Real LLM reply drafter (litellm-backed) with heuristic fallback
        — backend/pipeline/modules/llm_reply_adapter.py
        — backend/services/llm_factory.py
        — backend/vtlib/generative_llm.py  (reused class)
    * LLM reply classifier auto-installed at startup
    * Real email senders: SMTP / SendGrid / Postmark, selectable via
      EMAIL_PROVIDER env — backend/services/email_sender.py
    * In-process rate limiting middleware — backend/middleware.py
    * Structured request/error logging middleware
    * Optional Sentry integration (SENTRY_DSN)
    * Audit log + users + project_members tables — migration 015_auth.sql
    * Lifespan-based startup wires LLM/email defaults from env
    * Global Bearer-token guard on all routers EXCEPT /health and /auth/*

  Frontend
  --------
    * AuthProvider + useAuth() — frontend/src/state/authStore.tsx
    * Login + Register pages
    * ProtectedRoute wrapping AppShell
    * axios request interceptor injects Bearer token
    * 401 response → clears token + redirects to /login
    * AppShell shows user avatar/name/role + logout button

  Ops
  ---
    * _ops/Dockerfile.backend
    * _ops/Dockerfile.frontend
    * _ops/docker-compose.yml
    * _ops/nginx.conf  (in-container)
    * _ops/gtm-automation.nginx.conf  (host nginx)
    * _ops/gtm-api.service  (systemd)
    * _ops/deploy.sh

--------------------------------------------------------------------------------
11. WHAT YOU STILL NEED TO PROVIDE / DO YOURSELF
--------------------------------------------------------------------------------
  1. API keys — at minimum OPENAI_APIKEY in backend/.env for real LLM drafts.
  2. Email provider credentials (SMTP/SendGrid/Postmark) in backend/.env.
  3. JWT_SECRET — strong random value in backend/.env.
  4. Domain + DNS pointing at your server (production).
  5. TLS certificate (e.g. certbot/Let's Encrypt).
  6. nginx server_name in _ops/gtm-automation.nginx.conf — replace
     "gtm.example.com" with your real hostname.
  7. SENTRY_DSN if you want error monitoring (optional).
  8. Backup strategy for backend/data/gtm.sqlite.
  9. Decide if registration stays open or only admins create users
     (ALLOW_REGISTRATION env).
================================================================================
