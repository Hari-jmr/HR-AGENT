# JMR HRMS Chatbot — Complete Code Structure (A to Z)

> **Project**: JMR HR Agent  
> **Stack**: FastAPI (Python 3.13) + Next.js 14 (React/TypeScript)  
> **Database**: PostgreSQL (Odoo 8 HRMS schema)  
> **LLM Provider**: OpenRouter (configurable model)  
> **Generated**: 2026-05-27

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Repository Layout](#2-repository-layout)
3. [Data Flow](#3-data-flow)
4. [Backend — Entry Point](#4-backend--entry-point)
5. [Backend — Core (Config / Env / Settings)](#5-backend--core-config--env--settings)
6. [Backend — API Layer (Routes / Deps / Router)](#6-backend--api-layer-routes--deps--router)
7. [Backend — Schemas (Pydantic Models)](#7-backend--schemas-pydantic-models)
8. [Backend — Services](#8-backend--services)
9. [Frontend](#9-frontend)
10. [Deployment & Configuration](#10-deployment--configuration)
11. [Helper & Utility Scripts](#11-helper--utility-scripts)
12. [Security Architecture](#12-security-architecture)
13. [Database Tables Reference](#13-database-tables-reference)
14. [Environment Variables Reference](#14-environment-variables-reference)
15. [API Endpoint Reference](#15-api-endpoint-reference)
16. [File Summary Table](#16-file-summary-table)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         BROWSER / CLIENT                        │
│                    Next.js 14  (port 3001)                      │
│              frontend/components/hr-agent-app.tsx               │
└────────────────────────┬────────────────────────────────────────┘
                         │  /backend/* → /api/*  (Next.js rewrite)
┌────────────────────────▼────────────────────────────────────────┐
│                    FastAPI Backend  (port 5000)                  │
│                         backend/main.py                         │
│  ┌─────────────┐   ┌──────────────┐   ┌───────────────────────┐ │
│  │  Auth Layer │   │  Chat Layer  │   │   Session Middleware   │ │
│  │  /api/auth  │   │  /api/chat   │   │   (Starlette)         │ │
│  └──────┬──────┘   └──────┬───────┘   └───────────────────────┘ │
│         │                 │                                      │
│  ┌──────▼─────────────────▼──────────────────────────────────┐  │
│  │                    Services Layer                          │  │
│  │   auth_service.py │ chat_service.py │ llm_helper.py       │  │
│  │                   db_helper.py                             │  │
│  └──────────────────────┬────────────────────────────────────┘  │
└─────────────────────────│───────────────────────────────────────┘
                          │
          ┌───────────────┴───────────────┐
          │                               │
┌─────────▼───────────┐       ┌───────────▼────────────┐
│  PostgreSQL (Odoo 8) │       │  OpenRouter LLM API    │
│  192.168.1.52:5432   │       │  (GPT-4o-mini / auto)  │
└─────────────────────┘       └────────────────────────┘
```

**Core principles**:
- **Employee isolation**: Every DB query is automatically scoped to the logged-in employee's `employee_id`.
- **Write guard**: LLM-level check refuses any data-modification intent before SQL is generated.
- **SQL validation**: Only `SELECT` queries are allowed; `DROP/DELETE/INSERT/UPDATE` are blocked at the DB layer.
- **LLM-driven routing**: No hardcoded keyword matching — the LLM decides whether to query the DB or answer directly.
- **Structured responses**: LLM output is parsed into typed `ChatStructuredResponse` objects (summary + sections).

---

## 2. Repository Layout

```
JMRHRMS_full_handover_20260522/
│
├── app.py                        # Uvicorn entry point
├── requirements.txt              # Python dependencies
├── pyproject.toml                # PEP 518 project metadata (uv)
├── uv.lock                       # Locked dependency manifest
├── Dockerfile                    # Backend Docker image
├── docker-compose.yml            # Multi-container setup
├── .env                          # Local environment variables (not committed)
├── .env.example                  # Template for .env
├── .gitignore
├── .dockerignore
├── README.md
├── scenario_tests.py             # Chat routing test suite
│
├── backend/                      # FastAPI application
│   ├── main.py                   # App factory, middleware, exception handlers
│   ├── api/
│   │   ├── deps.py               # FastAPI dependency functions (session guards)
│   │   ├── router.py             # Root API router
│   │   └── routes/
│   │       ├── auth.py           # /api/auth/* endpoints
│   │       └── chat.py           # /api/chat, /api/clear endpoints
│   ├── core/
│   │   ├── config.py             # DB + LLM configuration (env vars)
│   │   ├── env.py                # .env file loader
│   │   └── settings.py           # App-level settings (name, host, CORS)
│   ├── schemas/
│   │   ├── auth.py               # LoginRequest, AuthResponse, EmployeeProfile
│   │   ├── chat.py               # ChatRequest, ChatResponse, ChatStructuredResponse
│   │   ├── common.py             # ErrorResponse, StatusResponse, ErrorDetail
│   │   └── policies.py           # Placeholder schema stubs
│   └── services/
│       ├── auth_service.py       # Authentication business logic
│       ├── chat_service.py       # Chat orchestration (LLM → DB → format)
│       ├── db_helper.py          # DB connection, schema, SQL validation, isolation
│       ├── llm_helper.py         # OpenRouter LLM calls, SQL generation, formatting
│       └── text2sql_service.py   # Thin alias / re-export of llm_helper
│
├── frontend/                     # Next.js 14 application
│   ├── Dockerfile                # Frontend Docker image
│   ├── next.config.mjs           # Next.js config (API proxy rewrite)
│   ├── package.json              # Node dependencies
│   ├── tsconfig.json             # TypeScript config
│   ├── next-env.d.ts
│   ├── app/
│   │   ├── globals.css           # Global CSS
│   │   ├── layout.tsx            # Root layout (fonts, metadata)
│   │   └── page.tsx              # Home page (renders HrAgentApp)
│   └── components/
│       └── hr-agent-app.tsx      # Main chat UI component (~800 lines)
│
├── docs/                         # Documentation and DB exports
│   ├── db-export/                # Database schema exports
│   └── notes/
│       └── tables-and-login.md   # DB table notes and login info
│
├── exports/
│   └── hr_agent_test_data_snapshot.20260522.json  # Test data snapshot
│
├── helper/                       # One-off developer utility scripts
│   ├── check_*.py                # DB inspection / verification scripts
│   ├── download_policies.py      # Policy document downloader
│   ├── export_test_data_snapshot.py
│   ├── extract_*.py              # Data extraction utilities
│   ├── parse_dump*.py            # Dump parsing utilities
│   ├── restore_and_check.py
│   ├── search_dumps.py
│   ├── seed_test_accounts.py     # Create test user accounts
│   ├── ssh_live_server.py
│   ├── test_*.py                 # Ad-hoc live tests
│   ├── try_*.py                  # Exploratory scripts
│   └── ...
│
├── old/
│   └── templates/                # Archived Flask HTML templates (no longer active)
│
└── policies/
    ├── extracted/                # Extracted policy text
    └── pdfs/                     # Policy PDF files
```

---

## 3. Data Flow

### Chat Request (Happy Path)

```
1. User types message in hr-agent-app.tsx
   └─▶ POST /backend/chat  (Next.js rewrite → :5000/api/chat)

2. backend/api/routes/chat.py  →  chat()
   ├── Validates non-empty message
   ├── Resolves session via get_session_employee() dependency
   └─▶ handle_chat_message(session, message, employee)

3. backend/services/chat_service.py  →  handle_chat_message()
   ├── Sanitizes chat history for LLM (strips extra UI metadata)
   └─▶ chat(user_message, employee_info, history)   [llm_helper.py]

4. backend/services/llm_helper.py  →  chat()
   ├── [Write guard]  _is_write_attempt(message) → refuse if DELETE/UPDATE/DROP intent
   ├── [LLM call]     generate_sql_or_answer(message, employee, history)
   │     ├── Sends system prompt + schema + employee context + history to OpenRouter
   │     └── Returns (sql, None)  or  (None, direct_answer)
   │
   ├── [If SQL path]:
   │     ├── validate_sql(sql)                    → blocks non-SELECT
   │     ├── enforce_employee_isolation(sql, ...)  → injects WHERE filter
   │     ├── execute_safe_query(sql, limit=50)     → runs query safely
   │     └── format_result(message, rows, employee) → LLM formats results
   │
   └── [If direct answer path]:
         └── Returns answer text directly

5. chat_service.py  →  _build_structured_response(response_text)
   ├── Parses LLM output into ChatStructuredResponse
   │     (summary + list/paragraph sections)
   └── Appends turn to session chat_history (keeps last 20 messages)

6. chat.py  →  Returns ChatResponse(response, structured, sql, data_source)

7. hr-agent-app.tsx  →  renderMessageBody(message)
   └── Renders structured sections or plain text
```

### Authentication Flow

```
1. User fills login form in hr-agent-app.tsx
   └─▶ POST /backend/auth/login  {username, password}

2. backend/api/routes/auth.py  →  login()
   └─▶ login_user(session, username, password)   [auth_service.py]

3. backend/services/auth_service.py  →  login_user()
   ├── authenticate_user(username, password)
   │     ├── Query res_users WHERE login = username
   │     └── Verify password (bcrypt or plaintext fallback via passlib)
   ├── get_employee_info(user_id)       → hr_employee JOIN joins
   ├── check_is_hr(user_id)            → res_groups membership check
   └── _start_user_session(session, user)   → populate session dict

4. Returns AuthResponse(authenticated, employee, is_hr, login, chat_history)
```

---

## 4. Backend — Entry Point

### `app.py`

| Item | Detail |
|------|--------|
| **Purpose** | Start the FastAPI application with Uvicorn |
| **Binds to** | `0.0.0.0:5000` |
| **Module** | `backend.main:app` |
| **Reload** | `False` (production mode) |
| **Extra** | Suppresses verbose `httpx` / `httpcore` / `openai` log output |

```python
# Minimal representation
uvicorn.run("backend.main:app", host="0.0.0.0", port=5000, reload=False)
```

---

## 5. Backend — Core (Config / Env / Settings)

### `backend/core/env.py`

Loads `.env` from the project root via `python-dotenv`.

| Symbol | Type | Purpose |
|--------|------|---------|
| `ROOT_DIR` | `Path` | Absolute path to the repo root |
| `ENV_FILE` | `Path` | `ROOT_DIR / ".env"` |

Calls `load_dotenv(ENV_FILE)` at import time so all other modules can read `os.environ`.

---

### `backend/core/config.py`

Database and LLM configuration loaded from environment variables.

| Class | `Config` |
|-------|---------|

| Attribute | Env Var | Default | Purpose |
|-----------|---------|---------|---------|
| `DB_HOST` | `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `DB_NAME` | — | Database name |
| `DB_USER` | `DB_USER` | — | DB username |
| `DB_PASSWORD` | `DB_PASSWORD` | — | DB password |
| `OPENROUTER_API_KEY` | `OPENROUTER_API_KEY` | — | LLM API key |
| `OPENROUTER_MODEL` | `OPENROUTER_MODEL` | `openrouter/auto` | LLM model |
| `OPENROUTER_BASE_URL` | — | `https://openrouter.ai/api/v1` | LLM base URL |
| `OPENROUTER_AUTO_ALLOWED_MODELS` | `OPENROUTER_AUTO_ALLOWED_MODELS` | `[]` | CSV model allowlist |
| `OPENROUTER_MAX_PRICE_PROMPT` | `OPENROUTER_MAX_PRICE_PROMPT` | `None` | Cost cap (prompt tokens) |
| `OPENROUTER_MAX_PRICE_COMPLETION` | `OPENROUTER_MAX_PRICE_COMPLETION` | `None` | Cost cap (completion tokens) |

Helper functions: `_csv_env(key)` → `list[str]`, `_float_env(key)` → `float | None`.

Exported singleton: `Config` (class-level attributes, no instantiation needed).

---

### `backend/core/settings.py`

Application-level settings (distinct from DB/LLM config).

| Class | `Settings` |
|-------|-----------|

| Attribute | Env Var | Default | Purpose |
|-----------|---------|---------|---------|
| `APP_NAME` | `APP_NAME` | `JMR HR Agent API` | Display name |
| `APP_VERSION` | `APP_VERSION` | `1.0.0` | Version string |
| `SECRET_KEY` | `SECRET_KEY` | — | Session encryption key |
| `HOST` | `APP_HOST` | `0.0.0.0` | Server bind host |
| `PORT` | `APP_PORT` | `5000` | Server bind port |
| `ALLOWED_ORIGINS` | `ALLOWED_ORIGINS` | `[]` | CORS origin whitelist (CSV) |

Exported singleton: `settings = Settings()`.

---

## 6. Backend — API Layer (Routes / Deps / Router)

### `backend/main.py`

App factory and global middleware.

| Function / Class | Purpose |
|-----------------|---------|
| `create_app()` | Creates and configures the `FastAPI` instance |
| `handle_http_exception(request, exc)` | Formats `HTTPException` → `ErrorResponse` JSON |
| `handle_validation_exception(request, exc)` | Formats `RequestValidationError` → `ErrorResponse` with `ErrorDetail` list |
| `ErrorDetail` | `(field: str, message: str)` |
| `ErrorResponse` | `(error: str, details: list[ErrorDetail])` |
| `StatusResponse` | `(status: str)` |

**Middleware stack** (applied in order):

1. `SessionMiddleware(app, secret_key=settings.SECRET_KEY)` — Starlette cookie-based sessions
2. `CORSMiddleware` — Allows configured origins, credentials, all methods/headers

**Routes registered on the app**:

| Method | Path | Handler | Response |
|--------|------|---------|----------|
| `GET` | `/health` | inline | `StatusResponse(status='ok')` |
| `*` | `/api/*` | `api_router` | (see route files) |

---

### `backend/api/deps.py`

Reusable FastAPI dependency functions (injected via `Depends`).

| Function | Returns | Raises | Purpose |
|----------|---------|--------|---------|
| `get_session_employee(request)` | `dict` (employee info) | `401` if no session | Guard any authenticated endpoint |
| `get_session_context(request)` | `dict` with `employee`, `is_hr`, `login` | `401` if no session | Richer session context |
| `require_hr_session(request)` | `dict` | `403` if not HR | Guard HR-only endpoints |

---

### `backend/api/router.py`

Combines all route modules into a single `APIRouter`.

```python
api_router.include_router(auth.router, prefix="/auth")
api_router.include_router(chat.router)          # no prefix
```

---

### `backend/api/routes/auth.py`

| Method | Path | Request Body | Response | Description |
|--------|------|-------------|----------|-------------|
| `POST` | `/api/auth/login` | `LoginRequest` | `AuthResponse` | Authenticate user, start session |
| `GET` | `/api/auth/me` | — | `AuthResponse` | Check current session |
| `POST` | `/api/auth/logout` | — | `StatusResponse` | Clear session |

**Error codes**:
- `400` — General validation / logic error
- `401` — Invalid credentials
- `422` — Pydantic validation failure

---

### `backend/api/routes/chat.py`

| Method | Path | Request Body | Auth Required | Response | Description |
|--------|------|-------------|---------------|----------|-------------|
| `POST` | `/api/chat` | `ChatRequest` | Yes (session) | `ChatResponse` | Process chat message |
| `POST` | `/api/clear` | — | Yes (session) | `StatusResponse` | Clear chat history |

**Error codes**:
- `400` — Empty message
- `401` — Not authenticated
- `422` — Pydantic validation failure

---

## 7. Backend — Schemas (Pydantic Models)

### `backend/schemas/auth.py`

```
LoginRequest
  username: str
  password: str

EmployeeProfile                          (ConfigDict extra='allow')
  name: str
  job_title: str | None
  department: str | None
  emp_code: str | None
  work_location: str | None
  mobile_phone: str | None
  work_email: str | None
  manager: str | None

AuthResponse
  authenticated: bool
  employee: EmployeeProfile | None
  is_hr: bool
  login: str | None
  chat_history: list[dict] | None
```

---

### `backend/schemas/chat.py`

```
ChatRequest
  message: str

ChatSection
  kind: Literal['paragraph', 'list']
  title: str | None
  content: str | None          # for paragraph sections
  items: list[str] | None      # for list sections

ChatStructuredResponse
  summary: str | None
  sections: list[ChatSection]

ChatHistoryEntry
  role: Literal['user', 'assistant']
  content: str
  structured: ChatStructuredResponse | None

ChatResponse
  response: str                 # raw text response
  structured: ChatStructuredResponse | None
  sql: str | None               # SQL query used (if any)
  data_source: str | None       # label: 'database', 'llm', etc.
```

---

### `backend/schemas/common.py`

```
ErrorDetail
  field: str
  message: str

ErrorResponse
  error: str
  details: list[ErrorDetail]

StatusResponse
  status: str

NamedResource
  name: str

SizedResource
  name: str
  size: int
```

---

### `backend/schemas/policies.py`

Placeholder stubs (`NamedResource`, `SizedResource`) — policy endpoints were removed; file kept for import compatibility.

---

## 8. Backend — Services

### `backend/services/auth_service.py`

Business logic for authentication and session management.

| Function | Signature | Purpose |
|----------|-----------|---------|
| `authenticate_user` | `(username, password) → dict \| None` | Query `res_users`, verify password (bcrypt + plaintext) |
| `get_employee_info` | `(user_id) → dict` | `hr_employee` JOIN with department, designation, manager |
| `check_is_hr` | `(user_id) → bool` | Check `res_groups` membership for HR roles |
| `_start_user_session` | `(session, user) → None` | Populate session dict with user data and empty chat history |
| `login_user` | `(session, username, password) → AuthResponse` | Orchestrate full login flow |
| `build_auth_payload` | `(session, include_history) → AuthResponse` | Build `AuthResponse` from current session |
| `logout_user` | `(session) → None` | Clear all session keys |

**Password verification**: Uses `passlib` with bcrypt; falls back to plaintext comparison for legacy Odoo passwords.

---

### `backend/services/chat_service.py`

Chat orchestration — coordinates LLM calls, history management, and response formatting.

| Function | Signature | Purpose |
|----------|-----------|---------|
| `handle_chat_message` | `(session, user_message, employee) → ChatResponse` | Main entry point for chat API |
| `_sanitize_history_for_llm` | `(history) → list[dict]` | Filter to `role`/`content` only (removes UI metadata) |
| `_build_structured_response` | `(response_text) → ChatStructuredResponse` | Parse flat LLM text into `summary + sections` |
| `_clean_line_prefix` | `(value) → str` | Strip bullet points and list numbering |
| `clear_chat_history` | `(session) → None` | Reset `chat_history` in session |

**History management**: Keeps last 20 `ChatHistoryEntry` objects in session. Older entries are trimmed automatically.

**Structured response parsing logic**:
- Lines starting with `- `, `* `, `• `, or `N. ` → collapsed into a `list` section
- Multi-sentence non-list lines → `paragraph` section
- First line/short intro → `summary`

---

### `backend/services/db_helper.py`

**The security perimeter.** ~1000 lines of DB connection, schema, validation, and employee isolation.

#### Constants

| Constant | Type | Purpose |
|----------|------|---------|
| `HR_SCHEMA` | `str` | Static fallback schema description (23 Odoo tables with business rules) |
| `_HR_TABLES` | `list[str]` | Allowlist of accessible table names |
| `_PERSONAL_TABLES` | `dict` | `table → (employee_filter_col, optional_emp_code_col)` for isolation mapping |
| `_DANGEROUS_KW` | `re.Pattern` | Regex matching write/DDL keywords for SQL validation |

#### Key Functions

| Function | Purpose |
|----------|---------|
| `get_connection()` | Create `psycopg2` connection using `Config.DB_*` credentials |
| `get_schema()` | Fetch live schema from `information_schema.columns` (cached); falls back to `HR_SCHEMA` |
| `authenticate_user(login, password)` | Verify credentials against `res_users` (used by auth_service) |
| `get_employee_info(user_id)` | Fetch `hr_employee` profile with JOINs |
| `check_is_hr(user_id)` | Check HR group membership |
| `validate_sql(sql)` | Block non-SELECT, SQL comments, and dangerous keywords |
| `enforce_employee_isolation(sql, employee_id, emp_code)` | Inject `WHERE employee_id = X` or block unsafe queries |
| `execute_safe_query(sql, params, limit)` | Run query through full validation pipeline, return `{columns, rows, count}` |

#### `validate_sql(sql)` Rules

1. Strips SQL comments (`--` and `/* */`)
2. Checks first token is `SELECT` (case-insensitive)
3. Scans for `_DANGEROUS_KW` regex: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`, `TRUNCATE`, `EXEC`, `EXECUTE`, `GRANT`, `REVOKE`
4. Raises `ValueError` with descriptive message on any violation

#### `enforce_employee_isolation(sql, employee_id, emp_code)` Rules

For tables listed in `_PERSONAL_TABLES`:
- If SQL contains a simple `WHERE` clause → appends `AND employee_id = {id}`
- If SQL has no `WHERE` → adds `WHERE employee_id = {id}`
- If SQL contains subqueries or CTEs (`WITH`, nested `SELECT`) → **blocked entirely** unless the employee filter is already present

---

### `backend/services/llm_helper.py`

**LLM integration core.** ~800 lines. Text-to-SQL generation and result formatting via OpenRouter.

#### System Prompt (`_SQL_SYSTEM`)

The 500+ line system prompt encodes:

| Section | Content |
|---------|---------|
| **HR Concepts** | 11 HR data domains: EMPLOYEE PROFILE, ATTENDANCE, LEAVE BALANCE, PAYROLL, EXPENSE, TIMESHEET, PROJECTS, HOLIDAYS, SUPPORT, DOCUMENTS, GENERAL |
| **Table mapping** | Which tables + columns to query per concept |
| **SQL templates** | Exact query patterns to follow for each concept |
| **Date handling** | Rules for "today", "this month", "last month", "YTD", fiscal year, etc. |
| **Business rules** | Leave balance formula: `SUM(add) - SUM(remove)`, payroll net calc, etc. |
| **Isolation rule** | `employee_id` filter is always MANDATORY |
| **Location calendars** | `_LOCATION_TO_CALENDAR` mapping for holiday queries |
| **Output format** | Return bare SQL or `ANSWER: <text>` for direct answers |

#### Key Functions

| Function | Signature | Purpose |
|----------|-----------|---------|
| `_get_llm()` | `() → ChatOpenAI` | Singleton LLM client (lazy init) |
| `_resolve_holiday_location` | `(work_location) → str` | Map employee location to holiday calendar name |
| `generate_sql_or_answer` | `(message, employee_info, history) → (sql\|None, answer\|None)` | Core LLM call — decides SQL or direct answer |
| `format_result` | `(message, rows, employee_info) → str` | LLM formats raw DB rows into natural language |
| `_clean_sql` | `(text) → str` | Strip markdown fences and LLM prefixes (`sql`, `SELECT:`, etc.) |
| `_is_write_attempt` | `(message) → bool` | Detect DELETE/UPDATE/DROP intent in user message |
| `chat` | `(user_message, employee_info, history) → dict` | Top-level function: write guard → SQL/answer → format → return |

#### Location to Calendar Mapping (`_LOCATION_TO_CALENDAR`)

| Location Keywords | Calendar |
|------------------|----------|
| bangalore, bengaluru | Karnataka |
| chennai, tamil | Tamil Nadu |
| mumbai, maharashtra | Maharashtra |
| delhi, ncr | Delhi |
| hyderabad, telangana | Telangana |
| kolkata, west bengal | West Bengal |
| (default) | National |

---

### `backend/services/text2sql_service.py`

Thin re-export / alias for `llm_helper.py`. Imports and re-exports `generate_sql_or_answer` and related functions. Kept for backwards compatibility with imports.

---

## 9. Frontend

### `frontend/app/layout.tsx`

Root Next.js App Router layout.

| Item | Value |
|------|-------|
| Fonts | Manrope (sans-serif), IBM Plex Mono (monospace) |
| Page title | `JMR HR Agent` |
| Body class | Font CSS variables + `antialiased` |

---

### `frontend/app/page.tsx`

Single-line home route — renders `<HrAgentApp />`.

---

### `frontend/app/globals.css`

Tailwind CSS base + custom CSS variables for dark/light theme tokens.

---

### `frontend/components/hr-agent-app.tsx`

**Main UI component (~800 lines).** Handles everything: authentication, chat, session restore, structured message rendering.

#### TypeScript Types

```typescript
type AuthState = 'loading' | 'guest' | 'authenticated'

interface Employee {
  name: string
  job_title?: string
  department?: string
  emp_code?: string
}

interface ChatSection {
  kind: 'paragraph' | 'list'
  title?: string
  content?: string
  items?: string[]
}

interface ChatStructuredResponse {
  summary?: string
  sections: ChatSection[]
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  structured?: ChatStructuredResponse
}
```

#### State Variables

| State | Type | Purpose |
|-------|------|---------|
| `authState` | `AuthState` | Current auth status |
| `employee` | `Employee \| null` | Logged-in user profile |
| `isHr` | `boolean` | Whether user is HR staff |
| `messages` | `Message[]` | Chat turn history |
| `input` | `string` | Current typed input |
| `showLoginModal` | `boolean` | Login modal visibility |
| `isSubmitting` | `boolean` | Chat send in-progress |
| `isLoggingIn` | `boolean` | Login in-progress |
| `error` | `string \| null` | Error message to display |

#### Key Functions

| Function | Purpose |
|----------|---------|
| `loadSession()` | On mount: GET `/backend/auth/me`, restore history if authenticated |
| `handleLogin(event)` | POST `/backend/auth/login`, populate state on success |
| `handleLogout()` | POST `/backend/auth/logout`, reset to guest state |
| `handleSend(event)` | POST `/backend/chat`, append user + assistant messages |
| `handleClear()` | POST `/backend/clear`, reset messages array |
| `renderSidebar()` | Left panel with conversation title + employee name |
| `renderPromptComposer()` | Text input + send button (disabled when not authenticated) |
| `renderLoginModal()` | Sign-in modal (username + password form) |
| `renderMessageBody(message)` | Render assistant turn: structured (summary/sections) or plain text |
| `renderSuggestions()` | Three quick-start prompt buttons for new users |

#### Suggested Prompts (shown to new authenticated users)

1. "What is my current leave balance?"
2. "Show my latest payroll summary"
3. "What is my attendance summary for this month?"

#### API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/backend/auth/me` | `GET` | Check session on page load |
| `/backend/auth/login` | `POST` | Login |
| `/backend/auth/logout` | `POST` | Logout |
| `/backend/chat` | `POST` | Send message |
| `/backend/clear` | `POST` | Clear history |

> All `/backend/*` calls are rewritten by Next.js to `http://backend:5000/api/*`

---

### `frontend/next.config.mjs`

| Setting | Value | Purpose |
|---------|-------|---------|
| `output` | `'standalone'` | Self-contained build for Docker |
| Rewrite: `/backend/:path*` | → `http://backend:5000/api/:path*` | Proxy to FastAPI backend |
| `NEXT_PUBLIC_BACKEND_URL` | env var | Override backend URL in custom deployments |

---

### `frontend/package.json`

| Script | Command | Purpose |
|--------|---------|---------|
| `dev` | `next dev` | Development server (hot reload) |
| `build` | `next build` | Production build |
| `start` | `next start` | Run production server |

| Key Dependency | Version | Purpose |
|----------------|---------|---------|
| `next` | `14.2.5` | React framework |
| `react` | `18.3.1` | UI library |
| `react-dom` | `18.3.1` | DOM rendering |
| `typescript` | latest | Type safety |

---

## 10. Deployment & Configuration

### `Dockerfile` (Backend)

```
Base:    python:3.13-slim
Tool:    uv (fast Python package manager)
Steps:   1. Install uv
         2. Copy pyproject.toml + uv.lock
         3. uv sync --frozen (install deps)
         4. Copy app.py + backend/
         5. EXPOSE 5000
         6. CMD: uvicorn backend.main:app --host 0.0.0.0 --port 5000
```

### `frontend/Dockerfile` (Frontend)

```
Base:    node:20-alpine
Steps:   1. Install dependencies (npm ci)
         2. next build (output: standalone)
         3. EXPOSE 3000
         4. CMD: node server.js
```

### `docker-compose.yml`

| Service | Build Context | Port | Depends On | Env |
|---------|--------------|------|------------|-----|
| `backend` | `.` (root) | `5000:5000` | — | `.env` file |
| `frontend` | `./frontend` | `3001:3000` | `backend` | `NEXT_PUBLIC_BACKEND_URL=http://backend:5000` |

Both services use `restart: unless-stopped`.

### Local Development

```bash
# Backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python app.py                  # http://localhost:5000
# Swagger UI: http://localhost:5000/docs

# Frontend
cd frontend
npm install
npm run dev                    # http://localhost:3000
```

### Docker

```bash
docker-compose up --build
# Frontend: http://localhost:3001
# Backend API: http://localhost:5000/docs
```

---

## 11. Helper & Utility Scripts

All in `helper/` — one-off developer tools, not part of the production runtime.

| Script | Purpose |
|--------|---------|
| `check_att.py` | Verify attendance records in DB |
| `check_cols.py` | Inspect table columns |
| `check_ctc.py` | Check CTC / salary data |
| `check_datas_big.py` | Large-data DB inspection |
| `check_db.py` | General DB health checks |
| `check_dump_toc.py` | Inspect pg_dump TOC |
| `check_dumps.py` | Check database dumps |
| `check_filestore.py` | Check Odoo filestore |
| `check_fnames.py` | Check filenames in attachments |
| `check_14gb.py` | Inspect 14GB dump file |
| `download_policies.py` | Download policy PDFs from Odoo DMS |
| `export_test_data_snapshot.py` | Export test data to JSON snapshot |
| `extract_from_dump.py` | Extract specific data from pg_dump |
| `extract_knowledge.py` | Extract knowledge base text |
| `parse_dump_data.py` | Parse dump data files |
| `parse_dump2.py` / `parse_dump3.py` | Alternative dump parsers |
| `restore_and_check.py` | Restore DB from dump and verify |
| `search_dumps.py` | Search within dump files |
| `seed_test_accounts.py` | Create test user accounts in DB |
| `ssh_live_server.py` | SSH tunnel to live server |
| `test_dms_read.py` | Test Odoo DMS document reading |
| `test_dms_search.py` | Test DMS search |
| `test_leave_balance.py` | Test leave balance queries |
| `try_live_auth.py` | Test authentication against live DB |
| `try_live_download.py` | Test document download |
| `try_pg_live.py` | Test live PostgreSQL connection |
| `try_ssh_live.py` | Test SSH connection to live server |
| `try_web_access.py` | Test Odoo web API access |

---

## 12. Security Architecture

### Layer 1 — Authentication (Session-Based)

- **Cookie-based sessions** via `starlette.middleware.sessions.SessionMiddleware`
- **Password verification**: `passlib` with bcrypt; plaintext fallback for legacy Odoo accounts
- Session stores: `user_id`, `employee` dict, `is_hr` flag, `login`, `chat_history`
- Sessions expire on browser close (no persistent cookie by default)

### Layer 2 — Write Guard (LLM Layer)

```python
def _is_write_attempt(message: str) -> bool:
    # Detects DELETE / UPDATE / DROP / modify intent in user message
    # Returns polite refusal BEFORE any SQL is generated
```

### Layer 3 — SQL Validation (DB Layer)

```python
def validate_sql(sql: str) -> None:
    # 1. Strip SQL comments
    # 2. Ensure first token is SELECT
    # 3. Scan for dangerous keywords: INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/TRUNCATE/EXEC/GRANT/REVOKE
    # Raises ValueError on any violation
```

### Layer 4 — Employee Isolation (DB Layer)

```python
def enforce_employee_isolation(sql, employee_id, emp_code):
    # For each table in _PERSONAL_TABLES:
    #   - Simple query with WHERE: append "AND employee_id = {id}"
    #   - Simple query without WHERE: add "WHERE employee_id = {id}"
    #   - Complex query (subquery/CTE) without safe filter: BLOCKED
```

**No cross-employee data access** — even HR users are scoped to their own `employee_id` through the chatbot.

### Layer 5 — CORS

Configured via `ALLOWED_ORIGINS` env var. Only whitelisted origins may send credentials.

### Layer 6 — Result Limit

All DB queries are capped at **50 rows** by default in `execute_safe_query(limit=50)`.

---

## 13. Database Tables Reference

All queries are restricted to these 23 Odoo 8 HRMS tables:

| Table | Domain | Key Columns |
|-------|--------|-------------|
| `hr_employee` | Employee | `id`, `name`, `emp_code`, `job_id`, `department_id`, `work_location` |
| `hr_holidays` | Leave | `employee_id`, `holiday_status_id`, `type` (add/remove), `number_of_days` |
| `hr_holidays_status` | Leave types | `id`, `name`, `code` |
| `hr_daily_attendance` | Attendance | `employee_id`, `attendance_date`, `check_in`, `check_out` |
| `hr_attendance` | Attendance | `employee_id`, `check_in`, `check_out` |
| `hr_monthly_attendance` | Attendance | `employee_id`, `month`, `year`, `present_days` |
| `hr_payroll_monthly_line` | Payroll | `employee_id`, `month`, `year`, `basic`, `gross`, `net` |
| `hr_salary_payment_line` | Payroll | `employee_id`, `payment_date`, `amount` |
| `hr_employee_salary_income` | Payroll | `employee_id`, `income_type`, `amount` |
| `hr_employee_bonus` | Payroll | `employee_id`, `bonus_type`, `amount`, `date` |
| `hr_expense_expense` | Expenses | `employee_id`, `name`, `total_amount`, `state`, `date` |
| `hr_expense_line` | Expenses | `expense_id`, `name`, `unit_amount` |
| `hr_timesheet_sheet_sheet` | Timesheets | `employee_id`, `date_from`, `date_to`, `total_attendance` |
| `project_project` | Projects | `id`, `name`, `state` |
| `project_task` | Projects | `project_id`, `user_id`, `name`, `stage_id` |
| `hr_public_holidays` | Holidays | `calendar_id`, `name`, `date` |
| `resource_calendar_leaves` | Holidays | `calendar_id`, `name`, `date_from`, `date_to` |
| `helpdesk_ticket` | Support | `employee_id`, `name`, `description`, `stage_id` |
| `ir_attachment` | Documents | `res_model`, `res_id`, `name`, `type` |
| `res_users` | Auth | `id`, `login`, `password`, `employee_id` |
| `res_groups` | Auth | `id`, `name`, `category_id` |
| `hr_department` | Structure | `id`, `name` |
| `hr_job` | Structure | `id`, `name` |

**Leave balance formula**: `SUM(number_of_days) WHERE type='add'` minus `SUM(number_of_days) WHERE type='remove'` grouped by `holiday_status_id`.

---

## 14. Environment Variables Reference

All read from `.env` at project root (via `backend/core/env.py`).

| Variable | Required | Example | Purpose |
|----------|----------|---------|---------|
| `SECRET_KEY` | Yes | `jmr-hrms-2026-secret` | Session cookie encryption |
| `DB_HOST` | Yes | `192.168.1.52` | PostgreSQL host |
| `DB_PORT` | Yes | `5432` | PostgreSQL port |
| `DB_NAME` | Yes | `mar_9_26` | Database name |
| `DB_USER` | Yes | `user1` | DB username |
| `DB_PASSWORD` | Yes | `***` | DB password |
| `OPENROUTER_API_KEY` | Yes | `sk-or-v1-...` | LLM API key |
| `OPENROUTER_MODEL` | No | `openai/gpt-4o-mini` | LLM model name |
| `OPENROUTER_PROVIDER_SORT` | No | `price` | Route by cheapest provider |
| `OPENROUTER_AUTO_ALLOWED_MODELS` | No | `gemini/...,gpt-...` | CSV allowlist for auto routing |
| `OPENROUTER_MAX_PRICE_PROMPT` | No | `0.001` | Max cost per 1K prompt tokens |
| `OPENROUTER_MAX_PRICE_COMPLETION` | No | `0.002` | Max cost per 1K completion tokens |
| `APP_NAME` | No | `JMR HR Agent API` | App display name |
| `APP_VERSION` | No | `1.0.0` | App version |
| `APP_HOST` | No | `0.0.0.0` | Bind host |
| `APP_PORT` | No | `5000` | Bind port |
| `ALLOWED_ORIGINS` | No | `http://localhost:3001,...` | CORS origins (CSV) |

---

## 15. API Endpoint Reference

Base URL: `http://localhost:5000`  
Frontend proxy: `/backend/*` → `/api/*`

| Method | Path | Auth | Request | Response | Description |
|--------|------|------|---------|----------|-------------|
| `GET` | `/health` | No | — | `{status: "ok"}` | Health check |
| `POST` | `/api/auth/login` | No | `{username, password}` | `AuthResponse` | Login |
| `GET` | `/api/auth/me` | No | — | `AuthResponse` | Session check |
| `POST` | `/api/auth/logout` | Session | — | `{status: "ok"}` | Logout |
| `POST` | `/api/chat` | Session | `{message: string}` | `ChatResponse` | Send chat message |
| `POST` | `/api/clear` | Session | — | `{status: "ok"}` | Clear chat history |

### `AuthResponse` Shape

```json
{
  "authenticated": true,
  "employee": {
    "name": "John Smith",
    "job_title": "Software Engineer",
    "department": "Engineering",
    "emp_code": "EMP001",
    "work_location": "Bangalore"
  },
  "is_hr": false,
  "login": "john.smith",
  "chat_history": [...]
}
```

### `ChatResponse` Shape

```json
{
  "response": "Your current Casual Leave balance is 5 days.",
  "structured": {
    "summary": "Leave Balance Summary",
    "sections": [
      {
        "kind": "list",
        "title": "Current Balances",
        "items": ["Casual Leave: 5 days", "Sick Leave: 3 days"]
      }
    ]
  },
  "sql": "SELECT ... FROM hr_holidays WHERE employee_id = 42 ...",
  "data_source": "database"
}
```

### Error Response Shape

```json
{
  "error": "Invalid credentials",
  "details": [
    {"field": "username", "message": "User not found"}
  ]
}
```

---

## 16. File Summary Table

| File | Lines (approx) | Role | Key Exports / Functions |
|------|---------------|------|------------------------|
| `app.py` | 16 | Entry point | Uvicorn runner |
| `backend/main.py` | 75 | App factory | `create_app()`, exception handlers |
| `backend/api/deps.py` | 23 | DI dependencies | `get_session_employee()`, `require_hr_session()` |
| `backend/api/router.py` | 8 | Route combiner | `api_router` |
| `backend/api/routes/auth.py` | 40 | Auth endpoints | `/login`, `/me`, `/logout` |
| `backend/api/routes/chat.py` | 32 | Chat endpoints | `/chat`, `/clear` |
| `backend/core/config.py` | 35 | DB+LLM config | `Config` |
| `backend/core/env.py` | 8 | .env loader | `ROOT_DIR`, `load_dotenv()` |
| `backend/core/settings.py` | 20 | App settings | `settings` singleton |
| `backend/schemas/auth.py` | 20 | Auth models | `LoginRequest`, `AuthResponse`, `EmployeeProfile` |
| `backend/schemas/chat.py` | 35 | Chat models | `ChatRequest`, `ChatResponse`, `ChatStructuredResponse` |
| `backend/schemas/common.py` | 13 | Generic models | `ErrorResponse`, `StatusResponse` |
| `backend/schemas/policies.py` | 7 | Stub | `NamedResource` |
| `backend/services/auth_service.py` | 50 | Auth logic | `login_user()`, `logout_user()`, `build_auth_payload()` |
| `backend/services/chat_service.py` | 70 | Chat orchestration | `handle_chat_message()`, `clear_chat_history()` |
| `backend/services/db_helper.py` | ~1000 | **DB + security core** | `validate_sql()`, `enforce_employee_isolation()`, `execute_safe_query()` |
| `backend/services/llm_helper.py` | ~800 | **LLM + SQL gen core** | `chat()`, `generate_sql_or_answer()`, `format_result()` |
| `backend/services/text2sql_service.py` | ~10 | Alias | Re-exports from `llm_helper` |
| `frontend/app/page.tsx` | 4 | Home route | Renders `<HrAgentApp />` |
| `frontend/app/layout.tsx` | 25 | Root layout | Fonts, metadata |
| `frontend/app/globals.css` | — | Global styles | Tailwind base + CSS vars |
| `frontend/components/hr-agent-app.tsx` | ~800 | **Main UI** | All chat/auth UI logic |
| `frontend/next.config.mjs` | 15 | Next.js config | API proxy rewrite |
| `frontend/package.json` | 21 | Node deps | `next`, `react`, `typescript` |
| `requirements.txt` | 13 | Python deps | `fastapi`, `langchain`, `psycopg2` |
| `pyproject.toml` | 20 | Project metadata | Python 3.13+, `uv` config |
| `docker-compose.yml` | 18 | Containers | `backend` + `frontend` services |
| `Dockerfile` | 18 | Backend image | `python:3.13-slim` + `uv` |
| `frontend/Dockerfile` | ~20 | Frontend image | `node:20-alpine` + `next build` |
| `scenario_tests.py` | 50+ | Tests | Chat routing test suite |

---

*End of CODE_STRUCTURE.md*
