# HR Agent Workflow and Sample Questions

## 1. What is actively used

### `backend/services/db_helper.py`
Yes, this file is actively used in the live runtime.

It is used for:
- database connection creation
- login authentication against `res_users`
- employee profile lookup from `hr_employee`
- HR-role detection
- SQL safety validation
- safe read-only SQL execution
- data-source tagging for debug/admin metadata

Current live imports:
- `backend/services/auth_service.py`
- `backend/services/llm_helper.py`
- `backend/services/text2sql_service.py`

### `backend/services/llm_helper.py`
Yes, this file is also actively used in the live runtime.

It is the main chat decision engine.

It is used for:
- detecting common deterministic questions
- building the system prompt
- calling the OpenRouter LLM
- extracting SQL from model output
- enforcing employee data isolation
- executing SQL through `db_helper`
- formatting final answers
- returning the raw answer text, SQL, and data-source metadata

Current live import:
- `backend/services/chat_service.py`

## 2. Is there anything duplicating?

### Active runtime duplication
No important active runtime duplication remains in the current backend flow.

The live path is:
- `backend/api/routes/auth.py`
- `backend/api/routes/chat.py`
- `backend/services/auth_service.py`
- `backend/services/chat_service.py`
- `backend/services/llm_helper.py`
- `backend/services/db_helper.py`
- `backend/services/text2sql_service.py`

### Cleaned-up duplicates
These old duplicates were already removed:
- root `backend/llm_helper.py`
- root `backend/knowledge_base.py`
- `backend/services/knowledge_base.py`

### Remaining non-runtime files
The `helper/` folder still contains investigation/export scripts, but those are offline utilities, not part of the active chat runtime.

### One thing to be aware of
`README.md` still contains some older handover content about policy PDF ingestion and uploads. That file is now historical in parts and should not be treated as the exact live behavior.

## 3. End-to-end agent flow

```mermaid
flowchart TD
    A[User types question in Next.js UI] --> B[/backend/chat]
    B --> C[FastAPI /api/chat route]
    C --> D[chat_service.handle_chat_message]
    D --> E[llm_helper.chat]
    E --> F{Deterministic rule match?}
    F -->|Yes| G[Run fixed SQL path]
    F -->|No| H[LangChain Text-to-SQL]
    H --> I{SQL generated?}
    I -->|No| J[Policy fallback: contact HR]
    I -->|Yes| K[Validate SQL and enforce employee isolation]
    G --> K
    K --> L[db_helper.execute_safe_query]
    L --> M[LLM formats result or fallback formatter]
    M --> N[chat_service builds structured Pydantic response]
    N --> O[Frontend renders summary and sections]
```

## 4. How each layer works

### Frontend
File:
- `frontend/components/hr-agent-app.tsx`

What it does:
- checks session with `/backend/auth/me`
- sends login to `/backend/auth/login`
- sends chat question to `/backend/chat`
- renders the structured response returned by the backend
- keeps chat history in the session-backed backend flow

### FastAPI routes
Files:
- `backend/api/routes/auth.py`
- `backend/api/routes/chat.py`

What they do:
- expose typed Pydantic request and response models
- enforce authentication for chat
- return structured success and error responses

### `auth_service.py`
File:
- `backend/services/auth_service.py`

What it does:
- validates credentials using `db_helper.authenticate_user`
- resolves employee profile
- detects whether the user is HR
- writes session data
- returns typed auth payloads

### `chat_service.py`
File:
- `backend/services/chat_service.py`

What it does:
- receives the user message and session history
- strips stored UI metadata before sending history to the LLM layer
- calls `llm_helper.chat(...)`
- converts the returned answer text into a structured response:
  - `response`
  - `structured.summary`
  - `structured.sections`
  - `sql`
  - `data_source`
- stores the assistant reply back into session history

### `llm_helper.py`
File:
- `backend/services/llm_helper.py`

This is the main orchestration layer.

It decides between three paths:

#### Path 1: deterministic leave-balance flow
Used for questions like:
- `show my leave balance`
- `my cl`
- `how many sick leaves do i have`

What happens:
- it detects leave-balance intent using keyword rules
- it runs a fixed SQL query against `hr_holidays` and `hr_holidays_status`
- it formats the answer directly without depending on generic Text-to-SQL generation

Why this path exists:
- it is faster
- it is more reliable
- it prevents variation in a very common query type

#### Path 2: deterministic latest-payroll-summary flow
Used for questions like:
- `what was my latest payroll summary`
- `show my latest salary summary`

What happens:
- it detects payroll-summary intent
- it runs a fixed SQL query against payroll tables
- it returns a direct factual summary

Why this path exists:
- payroll summary is common and sensitive
- deterministic SQL is safer and more stable than free-form model generation

#### Path 3: generic Text-to-SQL flow
Used for broader live-data questions.

What happens:
- `llm_helper` asks `text2sql_service.generate_text2sql_query(...)` for SQL
- if SQL is produced, it is validated and executed
- if the first execution fails, the model gets one retry chance to repair the SQL
- the results are then formatted into a final user response

If Text-to-SQL says `NO_SQL`:
- the system treats the question as a non-database policy/how-to type query
- because there is no active document-backed policy source now, the response is:
  - `No HR policy data found for this question. Please contact HR for details.`

### `text2sql_service.py`
File:
- `backend/services/text2sql_service.py`

What it does:
- uses LangChain SQL generation
- uses OpenRouter through `ChatOpenAI`
- narrows candidate tables by domain before generating SQL
- returns either:
  - one SQL query
  - or `None` when the model returns `NO_SQL`

Domain narrowing currently supports:
- leave
- attendance
- payroll
- timesheet
- expense
- employee profile/manager/department info

### `db_helper.py`
File:
- `backend/services/db_helper.py`

What it does in the chat path:
- blocks non-`SELECT` SQL
- blocks dangerous keywords like `DROP`, `DELETE`, `UPDATE`, `INSERT`
- appends `LIMIT` automatically when missing
- runs the query safely
- returns rows, columns, row count, and source metadata

## 5. Security and data access behavior

### Employee users
Employee users are only supposed to see their own data.

Enforcement happens in two places:
- the Text-to-SQL prompt tells the model to filter by the logged-in employee
- `llm_helper.py` has a hard isolation check that blocks SQL touching personal tables if the employee filter is missing

### HR users
HR users can ask broader employee-data questions because their role allows wider access.

## 6. What kinds of questions work now

### A. Leave questions
Examples:
- leave balance
- CL, SL, EL, PL balances
- remaining leave days
- leave summary

### B. Payroll questions
Examples:
- latest payroll summary
- salary summary
- gross pay
- net pay
- deductions
- annual CTC
- bonus-related data if present in supported tables

### C. Attendance questions
Examples:
- last 30 days attendance summary
- present count
- absent count
- worked hours
- sign-in and sign-out history

### D. Timesheet questions
Examples:
- submitted timesheets
- logged hours
- timesheet period details
- project time tracking summaries

### E. Expense questions
Examples:
- expense claims
- reimbursement claims
- latest submitted expense
- expense amount summaries

### F. Employee profile questions
Examples:
- manager name
- department
- designation
- joining date
- employee code

## 7. What does not really work now

### Policy questions
Policy questions do not have a real knowledge source anymore.

Examples:
- travel policy
- leave encashment policy rules
- insurance eligibility rules
- harassment policy details
- onsite allowance rules

Current behavior:
- these return the fallback contact-HR message

### ERP how-to questions
Questions like these are also not backed by a live policy/guide source now:
- how to apply leave in ERP
- how to submit timesheet
- how to create travel request

These also currently fall back to contact HR when they are not answerable from live HRMS data.

## 8. Sample questions employees can ask

### Leave
- Show my leave balance
- How many casual leave days do I have?
- My CL balance
- My sick leave balance
- How many optional holidays are left for me?
- Show all my leave balances

### Payroll
- What was my latest payroll summary?
- Show my latest salary details
- What is my latest net pay?
- What are my latest deductions?
- Show my annual CTC

### Attendance
- Summarize my attendance for the last 30 days
- How many days was I present this month?
- How many absences do I have this month?
- Show my recent attendance records
- What were my sign-in and sign-out timings yesterday?

### Timesheet
- Show my latest timesheet
- How many hours did I log this week?
- Show my submitted timesheets
- What is the status of my latest timesheet?

### Expenses
- Show my latest expense claim
- What expenses have I submitted recently?
- Summarize my expense claims this month
- What is the status of my last reimbursement?

### Employee profile
- Who is my manager?
- What is my department?
- What is my designation?
- What is my employee code?
- What is my date of joining?

## 9. Sample questions HR users can ask

### Cross-employee questions
- Show the latest payroll summary for employee 2881
- Which employees have submitted expense claims this month?
- Show attendance summary for the sales team
- List employees who joined in the last 30 days
- Show timesheet status across the HR department

Note:
These depend on how clearly the question maps to supported tables and fields. HR mode has broader access, but it still depends on supported schema and Text-to-SQL quality.

## 10. Practical rules for asking better questions

Best results usually come from questions that are:
- about live employee data already present in the listed HR tables
- specific about time range, metric, or entity
- phrased as one clear request instead of many mixed requests

Good examples:
- `Summarize my attendance for the last 30 days`
- `Show my latest payroll summary`
- `Who is my reporting manager?`

Less reliable examples:
- `Explain every HR policy related to travel, bonus, allowance, and insurance`
- `How do I do all HR tasks in ERP?`
- `Give me rules if I resign during probation and want gratuity and bonus and travel reimbursement`

## 11. Quick summary

If the question is about live HRMS data in the database, the agent can usually answer.

If the question is about policy text, handbook guidance, ERP instructions, or document-based rules, the current system does not have a live knowledge source for that and will ask the user to contact HR.
