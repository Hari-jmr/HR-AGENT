from fastapi import HTTPException, Request, status


def get_session_employee(request: Request) -> dict:
    employee = request.session.get('employee')
    if not employee:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Not authenticated')
    return employee


def get_session_context(request: Request) -> dict:
    employee = get_session_employee(request)
    return {
        'employee': employee,
        'is_hr': request.session.get('is_hr', False),
        'login': request.session.get('login'),
    }


def require_hr_session(request: Request) -> dict:
    context = get_session_context(request)
    if not context['is_hr']:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only HR team members can perform this action')
    return context