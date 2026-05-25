# JMR HRMS Chatbot

## Overview

This repository contains the current JMR HR assistant stack:

- FastAPI backend under `backend/`
- Next.js frontend under `frontend/`
- PostgreSQL/Odoo-backed employee and HR data access
- OpenRouter + LangChain based query generation for live HRMS questions
- Deterministic handling for common leave and payroll prompts

The active system is a read-only HR assistant. It authenticates users against Odoo user records, resolves their employee profile, answers supported HRMS data questions, and returns structured Pydantic API responses.

## Current Architecture

### Backend

The backend entry point is `backend.main:app`.

Key layers:

- `backend/api/routes/auth.py`
  Session-based login, logout, and session inspection endpoints.
- `backend/api/routes/chat.py`
  Chat and chat-history clear endpoints.
- `backend/services/auth_service.py`
  Authenticates users, resolves employee details, and starts sessions.
- `backend/services/chat_service.py`
  Normalizes chat history, calls the chat engine, and shapes typed responses.
- `backend/services/llm_helper.py`
  Main orchestration layer for deterministic paths, Text-to-SQL, guardrails, and final answers.
- `backend/services/text2sql_service.py`
  LangChain/OpenRouter Text-to-SQL generation scoped to supported HR domains.
- `backend/services/db_helper.py`
  Database connection, employee lookup, HR-role detection, SQL validation, and safe read-only execution.
- `backend/schemas/`
  Pydantic request and response models for auth, chat, and common payloads.

### Frontend

The frontend is a Next.js app in `frontend/`.

It:

- manages login state
- calls the backend through `/backend/*` rewrites
- renders structured assistant responses
- keeps the user experience chat-first and session-aware

### API Flow

1. User signs in from the frontend.
2. Frontend calls `/backend/auth/login` which rewrites to `/api/auth/login`.
3. Backend validates the user and stores session state.
4. User sends a chat message to `/backend/chat`.
5. `chat_service` forwards the request to `llm_helper`.
6. `llm_helper` chooses one of these paths:
   - deterministic leave balance
   - deterministic latest payroll summary
   - generic Text-to-SQL for supported live-data questions
   - contact-HR fallback for unsupported policy-style questions
7. Results are returned as a structured Pydantic response.

## Supported Question Types

The current system works best for live HRMS data already available in the database.

Examples:

- leave balances
- latest payroll summary
- attendance summaries
- timesheet summaries
- expense claim summaries
- employee details such as manager, department, designation, or joining date

Examples of employee prompts:

- `Show my leave balance`
- `What was my latest payroll summary?`
- `Summarize my attendance for the last 30 days`
- `Who is my manager?`
- `Show my recent expense claims`

Examples of HR prompts:

- `Show attendance summary for the finance team`
- `Show the latest payroll summary for employee 2881`
- `List employees who joined in the last 30 days`

## Current Limitations

The system does not currently have a live document-backed policy knowledge source.

That means questions such as these do not return full policy content:

- travel policy
- insurance policy rules
- leave encashment rules
- ERP how-to guidance based on handbook or SOP documents

Those cases currently fall back to:

- `No HR policy data found for this question. Please contact HR for details.`

## Security Model

Core runtime safety rules:

- read-only database access
- only `SELECT` queries are allowed
- dangerous SQL keywords are blocked
- non-HR users are restricted to their own data
- response payloads are typed with Pydantic models

The employee-isolation rule is enforced both in prompting and in backend validation before SQL execution.

## Active Endpoints

- `GET /health`
  Returns service health.
- `POST /api/auth/login`
  Authenticates user and starts a session.
- `GET /api/auth/me`
  Returns current session state and employee info.
- `POST /api/auth/logout`
  Clears the session.
- `POST /api/chat`
  Accepts a chat message and returns a typed chat response.
- `POST /api/clear`
  Clears chat history from the session.

## Structured API Responses

The backend now returns typed Pydantic response objects.

Examples:

- auth responses use `AuthResponse`
- chat responses use `ChatResponse`
- health, logout, and clear use `StatusResponse`
- validation and HTTP errors use `ErrorResponse`

This keeps the API contract consistent across success and error paths.

## Repository Layout

- `app.py`
  Compatibility runner for `backend.main:app`.
- `backend/`
  Active FastAPI backend.
- `frontend/`
  Active Next.js frontend.
- `docs/notes/AGENT_WORKFLOW_AND_SAMPLE_QUESTIONS.md`
  Technical workflow, active modules, and sample prompts.
- `docs/notes/NON_TECHNICAL_SYSTEM_OVERVIEW.md`
  Plain-language overview for non-technical stakeholders.
- `helper/`
  Investigation and one-off utility scripts. Not part of the active runtime.
- `old/templates/`
  Archived legacy UI templates. Not part of the active runtime.

## Local Development

### Backend with `uv`

1. Install dependencies:

   ```powershell
   uv sync
   ```

2. Start the FastAPI backend:

   ```powershell
   uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 5000
   ```

### Backend with `.venv` or pip

1. Install from `requirements.txt` into a virtual environment.
2. Start the backend with either of these commands:

   ```powershell
   .\.venv\Scripts\python.exe app.py
   ```

   or

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 5000
   ```

### Frontend

1. Start the backend on port `5000`.
2. Open a second terminal.
3. Go to `frontend/`.
4. Install packages if needed:

   ```powershell
   npm install
   ```

5. Start the development server:

   ```powershell
   npm run dev
   ```

6. Open `http://127.0.0.1:3000`.

### Frontend Rewrite Behavior

The Next.js app rewrites:

- `/backend/auth/*` -> `/api/auth/*`
- `/backend/chat` -> `/api/chat`
- `/backend/clear` -> `/api/clear`

If the backend is not running on `127.0.0.1:5000`, set `NEXT_PUBLIC_BACKEND_URL` before starting the frontend.

## Docker

The repository Dockerfile currently packages the backend service only.

It now aligns with the project runtime by using Python 3.13 and launching:

```text
uvicorn backend.main:app --host 0.0.0.0 --port 5000
```

Build image:

```powershell
podman build -t jmrhrms .
```

Run container:

```powershell
podman run -d --name jmrhrms -p 5000:5000 --restart=always jmrhrms
```

Notes:

- this image serves the FastAPI backend only
- the frontend remains a separate Next.js process unless you add a dedicated frontend container
- runtime configuration should be passed through environment variables instead of relying on code defaults

## Configuration and Secrets

Configuration is read from the backend settings/config layer and can be overridden with environment variables.

Important operational note:

- default values in config are convenient for local recovery, but they should not be treated as a secure production secret strategy
- move sensitive runtime values such as database credentials, session secrets, and API keys into environment variables or a secret manager
- rotate exposed secrets before production hardening

## Recommended Next Steps

1. Externalize and rotate secrets.
2. Add automated tests for auth, chat, and SQL guardrails.
3. Tighten SQL validation with stronger parsing or allowlist logic.
4. Keep removing stale documentation and old helper residue as the active architecture stabilizes.

## Operational Checks

When validating a deployment:

1. Confirm the backend starts and binds to port `5000`.
2. Confirm `GET /health` returns HTTP `200`.
3. Test `POST /api/auth/login` with a valid employee account.
4. Test one leave or payroll query through `/api/chat`.
5. Confirm no write operations are executed against the database.

## Non-Negotiable Constraint

The assistant must remain read-only against production HRMS data.

It must never alter database records during normal chatbot operation.

# HR-AGENT
