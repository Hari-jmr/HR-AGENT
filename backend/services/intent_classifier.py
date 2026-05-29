"""
Intent Classification Service for HR Agent.

Uses hybrid approach:
1. Exact pattern matching (fast, free)
2. Keyword matching (fast, free)
3. Semantic similarity (for variations)
4. LLM fallback (for complex cases)
"""

import re
import logging
from enum import Enum
from functools import lru_cache
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from backend.core.config import Config

logger = logging.getLogger(__name__)


class HRIntent(str, Enum):
    GREETING = "greeting"
    GOODBYE = "goodbye"
    THANKS = "thanks"
    
    LEAVE_BALANCE = "leave_balance"
    LEAVE_HISTORY = "leave_history"
    
    SALARY = "salary"
    SALARY_PAYMENT = "salary_payment"
    SALARY_COMPONENTS = "salary_components"
    CTC = "ctc"
    PAYSLIP = "payslip"
    PAYROLL = "payroll"
    
    ATTENDANCE = "attendance"
    PRESENCE_CHECK = "presence_check"
    WORKED_HOURS = "worked_hours"
    
    PROFILE = "profile"
    JOINING_DATE = "joining_date"
    MANAGER = "manager"
    DEPARTMENT = "department"
    
    TIMESHEET = "timesheet"
    PROJECT_HOURS = "project_hours"
    
    EXPENSE = "expense"
    CLAIM = "claim"
    
    HELPDESK = "helpdesk"
    TICKET = "ticket"
    
    HOLIDAY = "holiday"
    FESTIVAL = "festival"
    
    PROJECTS = "projects"
    TEAM = "team"
    BONUS = "bonus"
    
    POLICY = "policy"
    GENERAL = "general"
    
    WRITE_REQUEST = "write_request"
    OTHER_USER = "other_user"
    UNKNOWN = "unknown"


INTENT_KEYWORDS: dict[HRIntent, list[str]] = {
    HRIntent.LEAVE_BALANCE: [
        'leave balance', 'leave remaining', 'remaining leave', 'leaves left',
        'leave quota', 'leave count', 'how many leave', 'days off left',
        'casual leave', 'sick leave', 'earned leave', 'privilege leave',
        'optional leave', 'comp off', 'maternity leave', 'paternity leave',
        'birthday leave', 'bereavement leave', 'emergency leave',
        'cl balance', 'sl balance', 'pl balance', 'el balance',
        'my leaves', 'leave available', 'leave remaining', 'balance of',
        'what leave', 'which leave', 'leave types', 'type of leave',
    ],
    HRIntent.LEAVE_HISTORY: [
        'leave taken', 'leave applied', 'leave history', 'past leave',
        'approved leave', 'rejected leave', 'pending leave', 'leave request',
        'leave this month', 'leave last month', 'leave this year',
        'when did i take', 'leaves i took', 'my leave history',
        'leave status', 'leave approved', 'leave rejected',
    ],
    HRIntent.SALARY: [
        'salary', 'pay', 'earnings', 'monthly salary', 'take home',
        'net pay', 'gross pay', 'net salary', 'gross salary',
        'my pay', 'how much i earn', 'how much i get', 'my income',
        'payroll', 'payroll details', 'my payroll', 'show payroll',
        'salary details', 'salary info', 'current salary',
    ],
    HRIntent.SALARY_PAYMENT: [
        'salary paid', 'salary credited', 'salary received', 'payment date',
        'when was salary', 'when will salary', 'salary transfer',
        'last salary', 'salary deposit', 'got salary', 'receive salary',
        'when paid', 'payment received', 'credit date',
    ],
    HRIntent.SALARY_COMPONENTS: [
        'salary breakdown', 'component', 'salary structure', 'salary split',
        'basic salary', 'hra', 'special allowance', 'allowance',
        'deduction', 'pf amount', 'professional tax', 'tds amount',
        'my basic', 'my hra', 'salary details breakdown', 'component wise',
        'salary breakup', 'pay components', 'earning components',
    ],
    HRIntent.CTC: [
        'ctc', 'annual package', 'total compensation', 'cost to company',
        'yearly salary', 'annual salary', 'package', 'total package',
        'my ctc', 'my package', 'my annual', 'per year',
    ],
    HRIntent.PAYSLIP: [
        'payslip', 'salary slip', 'pay slip', 'download payslip',
        'get payslip', 'show payslip', 'my payslip', 'pay statement',
        'salary statement', 'download salary',
    ],
    HRIntent.ATTENDANCE: [
        'attendance', 'present', 'absent', 'office presence',
        'punch', 'swipe', 'login logout', 'check in check out',
        'my attendance', 'attendance record', 'attendance history',
        'days present', 'days absent', 'days worked', 'office days',
        'this month attendance', 'attendance report',
    ],
    HRIntent.PRESENCE_CHECK: [
        'was i present', 'did i come', 'was i absent', 'was i in office',
        'check presence', 'did i attend', 'my presence on',
        'present on', 'absent on', 'come to office',
    ],
    HRIntent.WORKED_HOURS: [
        'working hours', 'work hours', 'hours worked', 'total hours',
        'office hours', 'login time', 'logout time', 'punch time',
        'how many hours', 'hours logged', 'time in office',
    ],
    HRIntent.PROFILE: [
        'my profile', 'my details', 'personal info', 'my information',
        'employee details', 'my record', 'my data', 'about me',
        'employee profile', 'show profile', 'my bio',
    ],
    HRIntent.JOINING_DATE: [
        'doj', 'date of joining', 'joining date', 'joined on',
        'when did i join', 'work anniversary', 'my joining',
        'since when', 'how long working', 'tenure',
    ],
    HRIntent.MANAGER: [
        'manager', 'reporting to', 'reporting manager', 'boss',
        'supervisor', 'who is my manager', 'my manager',
        'team lead', 'lead',
    ],
    HRIntent.DEPARTMENT: [
        'department', 'dept', 'my department', 'which department',
        'my dept', 'team name', 'unit',
    ],
    HRIntent.TIMESHEET: [
        'timesheet', 'time sheet', 'my timesheet', 'timesheet status',
        'timesheet submitted', 'fill timesheet', 'timesheet entry',
    ],
    HRIntent.PROJECT_HOURS: [
        'project hours', 'hours on project', 'time on project',
        'logged hours', 'billable hours', 'hours for project',
        'project time', 'time logged',
    ],
    HRIntent.EXPENSE: [
        'expense', 'expenses', 'my expenses', 'expense claim',
        'submitted expense', 'expense report', 'my claims',
        'reimbursement', 'expense status',
    ],
    HRIntent.CLAIM: [
        'claim', 'claims', 'my claim', 'claim status',
        'travel claim', 'food claim', 'expense claim',
        'reimbursement claim', 'pending claim',
    ],
    HRIntent.HELPDESK: [
        'helpdesk', 'help desk', 'support', 'ticket', 'tickets',
        'my tickets', 'open ticket', 'support request',
        'it support', 'complaint', 'issue',
    ],
    HRIntent.TICKET: [
        'ticket', 'my ticket', 'ticket status', 'open tickets',
        'ticket number', 'support ticket', 'raise ticket',
    ],
    HRIntent.HOLIDAY: [
        'holiday', 'holidays', 'public holiday', 'holiday list',
        'upcoming holiday', 'holiday calendar', 'off days',
        'company holiday', 'declared holiday',
    ],
    HRIntent.FESTIVAL: [
        'diwali', 'holi', 'christmas', 'eid', 'pongal', 'dussehra',
        'navratri', 'gandhi jayanti', 'independence day', 'republic day',
        'good friday', 'mahashivratri', 'ganesh chaturthi',
        'onam', 'raksha bandhan', 'janmashtami', 'ramzan',
        'is diwali', 'is holi', 'is christmas', 'festival',
    ],
    HRIntent.PROJECTS: [
        'projects', 'project list', 'list of projects', 'all projects',
        'active projects', 'my projects', 'company projects',
    ],
    HRIntent.TEAM: [
        'team', 'my team', 'team members', 'colleagues',
        'team list', 'my colleagues', 'who is in my team',
    ],
    HRIntent.BONUS: [
        'bonus', 'incentive', 'performance bonus', 'reward',
        'my bonus', 'bonus amount', 'incentive amount',
    ],
    HRIntent.POLICY: [
        'policy', 'policies', 'leave policy', 'wfh policy',
        'travel policy', 'attendance policy', 'hr policy',
        'company policy', 'what is the policy',
    ],
    HRIntent.WRITE_REQUEST: [
        'update', 'modify', 'change', 'edit', 'delete',
        'remove', 'insert', 'add', 'create', 'new',
        'correct', 'fix', 'make',
    ],
    HRIntent.OTHER_USER: [
        'john', 'mary', 'someone', 'colleague', 'other',
        'another', 'else', 'his', 'her', 'their',
        "john's", "mary's", "someone's",
    ],
}

_EXACT_PATTERNS: list[tuple[re.Pattern, HRIntent]] = [
    (re.compile(r'^(hi|hello|hey|hii?|good\s*(morning|afternoon|evening))[\s!.]*$', re.I), HRIntent.GREETING),
    (re.compile(r'^(bye|goodbye|see\s*you|take\s*care|ciao|later)[\s!.]*$', re.I), HRIntent.GOODBYE),
    (re.compile(r'^(thanks?|thank\s*you|thx|ty|appreciated)[\s!.]*$', re.I), HRIntent.THANKS),
]

_NEGATION_WORDS = {'not', 'no', "don't", "didn't", "wasn't", "isn't", "haven't", "hasn't"}


def _contains_negation(message: str) -> bool:
    words = set(message.lower().split())
    return bool(words & _NEGATION_WORDS)


def _match_keywords(message: str) -> Optional[HRIntent]:
    msg_lower = message.lower()
    
    for intent, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in msg_lower:
                if not _contains_negation(message):
                    return intent
    
    return None


def _match_exact_patterns(message: str) -> Optional[HRIntent]:
    for pattern, intent in _EXACT_PATTERNS:
        if pattern.match(message):
            return intent
    return None


def _detect_security_issues(message: str) -> Optional[HRIntent]:
    msg_lower = message.lower()
    
    write_patterns = [
        r'\b(update|modify|change|edit|delete|remove|insert|add|create|new|correct|fix)\b',
        r'\bmake\s+(my|the|a)\b',
    ]
    
    data_words = ['salary', 'attendance', 'leave', 'timesheet', 'expense', 'record', 'profile', 'phone', 'email', 'address', 'details', 'data']
    
    for pattern in write_patterns:
        if re.search(pattern, msg_lower):
            for word in data_words:
                if word in msg_lower:
                    return HRIntent.WRITE_REQUEST
    
    other_user_patterns = [
        r"\b(john|mary|mike|david|sarah|jane|bob|alice|someone|colleague|other|another)\b.*\b(salary|leave|attendance|profile|details|record)\b",
        r"\b(he|she|his|her|their)\b.*\b(salary|leave|attendance|profile)\b",
        r"\bwhat\s+is\s+[a-z]+'s\s+\b",
    ]
    
    for pattern in other_user_patterns:
        if re.search(pattern, msg_lower):
            return HRIntent.OTHER_USER
    
    return None


_INTENT_SYSTEM = """Classify the HR query into ONE intent label.

INTENT LABELS:
- greeting: hellos, hi, hey
- goodbye: bye, see you
- thanks: thank you

- leave_balance: leave remaining, casual/sick/earned leave balance, days off left, leave quota
- leave_history: leaves taken, leave applied, past leaves, leave requests

- salary: salary, pay, payroll, earnings, monthly salary, take home, net/gross pay
- salary_payment: when was salary paid, salary credit/payment date
- salary_components: salary breakdown, basic, HRA, allowances, deductions
- ctc: CTC, annual package, total compensation
- payslip: payslip, salary slip, download salary statement

- attendance: attendance record, office presence, days present/absent
- presence_check: was I present on [date], did I come to office
- worked_hours: working hours, login/logout time

- profile: my profile, personal details, employee info
- joining_date: DOJ, date of joining, when did I join
- manager: my manager, reporting to
- department: my department, which department

- timesheet: timesheet status, submitted timesheet
- project_hours: project hours, hours logged

- expense: expenses, expense claims, submitted bills
- claim: reimbursement, travel/food claim

- helpdesk: tickets, support requests
- ticket: ticket status, open tickets

- holiday: public holidays, holiday list
- festival: is [festival] a holiday, Diwali, Holi

- projects: list projects, active projects
- team: my team, team members
- bonus: bonus, incentive

- policy: HR policies, leave/WFH policy
- general: general HR questions

- write_request: trying to update/delete/modify data
- other_user: asking about another employee

- unknown: cannot determine

Output ONLY the intent label."""


@lru_cache(maxsize=1)
def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=Config.OPENROUTER_MODEL,
        api_key=Config.OPENROUTER_API_KEY,
        base_url=Config.OPENROUTER_BASE_URL.removesuffix('/chat/completions'),
        temperature=0,
        default_headers={
            'HTTP-Referer': 'http://localhost:5000',
            'X-Title': 'JMR HR Agent',
        },
    )


def _classify_with_llm(message: str) -> HRIntent:
    try:
        messages = [
            SystemMessage(content=_INTENT_SYSTEM),
            HumanMessage(content=message),
        ]
        response = _get_llm().invoke(messages).content.strip().lower()
        
        for intent in HRIntent:
            if intent.value == response:
                return intent
        
        logger.warning('[INTENT_LLM_UNKNOWN] %r', response)
        return HRIntent.UNKNOWN
    except Exception as exc:
        logger.exception('[INTENT_LLM_ERROR] %s', exc)
        return HRIntent.UNKNOWN


def classify_intent(user_message: str) -> HRIntent:
    """
    Classify user message into HR intent.
    
    Priority:
    1. Security checks (write requests, other user access)
    2. Exact pattern matching
    3. Keyword matching
    4. LLM fallback
    """
    if not user_message or not user_message.strip():
        return HRIntent.UNKNOWN
    
    msg = user_message.strip()
    
    security_intent = _detect_security_issues(msg)
    if security_intent:
        logger.info('[INTENT_SECURITY] %s for: %r', security_intent.value, msg[:50])
        return security_intent
    
    exact_intent = _match_exact_patterns(msg)
    if exact_intent:
        return exact_intent
    
    keyword_intent = _match_keywords(msg)
    if keyword_intent:
        return keyword_intent
    
    return _classify_with_llm(msg)


def is_readonly_intent(intent: HRIntent) -> bool:
    readonly = {
        HRIntent.GREETING, HRIntent.GOODBYE, HRIntent.THANKS,
        HRIntent.LEAVE_BALANCE, HRIntent.LEAVE_HISTORY,
        HRIntent.SALARY, HRIntent.SALARY_PAYMENT, HRIntent.SALARY_COMPONENTS,
        HRIntent.CTC, HRIntent.PAYSLIP, HRIntent.PAYROLL,
        HRIntent.ATTENDANCE, HRIntent.PRESENCE_CHECK, HRIntent.WORKED_HOURS,
        HRIntent.PROFILE, HRIntent.JOINING_DATE, HRIntent.MANAGER, HRIntent.DEPARTMENT,
        HRIntent.TIMESHEET, HRIntent.PROJECT_HOURS,
        HRIntent.EXPENSE, HRIntent.CLAIM,
        HRIntent.HELPDESK, HRIntent.TICKET,
        HRIntent.HOLIDAY, HRIntent.FESTIVAL,
        HRIntent.PROJECTS, HRIntent.TEAM, HRIntent.BONUS,
        HRIntent.POLICY, HRIntent.GENERAL,
    }
    return intent in readonly


def get_intent_response(intent: HRIntent) -> Optional[str]:
    responses = {
        HRIntent.WRITE_REQUEST: (
            "I can only view your HR info — making changes is outside what I can do. "
            "Please reach out to HR for any updates or corrections."
        ),
        HRIntent.OTHER_USER: (
            "I can only show your own data — other employees' info is private."
        ),
        HRIntent.GREETING: (
            "Hi! I'm your HR assistant. I can help with leave balance, salary, "
            "attendance, expenses, and more. What would you like to check?"
        ),
        HRIntent.GOODBYE: "Take care! Come back anytime you have HR questions.",
        HRIntent.THANKS: "Happy to help! Anything else?",
    }
    return responses.get(intent)
