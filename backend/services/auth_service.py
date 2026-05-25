import json

from backend.schemas.auth import AuthResponse
from backend.services.db_helper import authenticate_user, check_is_hr, get_employee_info


def _start_user_session(session: dict, user: dict):
    employee = get_employee_info(user['id'])
    if not employee:
        return None, 'No employee record found for this user.'

    is_hr = check_is_hr(user['id'])
    session['user_id'] = user['id']
    session['login'] = user['login']
    session['employee'] = json.loads(json.dumps(employee, default=str))
    session['is_hr'] = is_hr
    session['chat_history'] = []
    return session, None


def login_user(session: dict, username: str, password: str):
    username = username.strip()
    if not username or not password:
        return None, 'Please enter both username and password.'

    user = authenticate_user(username, password)
    if not user:
        return None, 'Invalid username or password.'

    return _start_user_session(session, user)


def build_auth_payload(session: dict, include_history: bool = False):
    return AuthResponse(
        authenticated=True,
        employee=session.get('employee'),
        is_hr=session.get('is_hr', False),
        login=session.get('login'),
        chat_history=session.get('chat_history', []) if include_history else [],
    )


def logout_user(session: dict):
    session.clear()