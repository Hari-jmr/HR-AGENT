"""
Unit tests for HR Agent Backend Services.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from backend.services.intent_classifier import (
    HRIntent,
    classify_intent,
    is_readonly_intent,
    get_intent_response,
)
from backend.services.db_helper import (
    validate_sql,
    enforce_employee_isolation,
    _PERSONAL_TABLES,
)


class TestIntentClassifier:
    """Tests for intent classification."""

    def test_greeting_patterns(self):
        assert classify_intent("hi") == HRIntent.GREETING
        assert classify_intent("hello") == HRIntent.GREETING
        assert classify_intent("Hello!") == HRIntent.GREETING
        assert classify_intent("good morning") == HRIntent.GREETING

    def test_goodbye_patterns(self):
        assert classify_intent("bye") == HRIntent.GOODBYE
        assert classify_intent("goodbye") == HRIntent.GOODBYE
        assert classify_intent("see you") == HRIntent.GOODBYE

    def test_thanks_patterns(self):
        assert classify_intent("thanks") == HRIntent.THANKS
        assert classify_intent("thank you") == HRIntent.THANKS

    def test_write_request_detection(self):
        assert classify_intent("update my phone number") == HRIntent.WRITE_REQUEST
        assert classify_intent("delete my record") == HRIntent.WRITE_REQUEST
        assert classify_intent("change my salary") == HRIntent.WRITE_REQUEST
        assert classify_intent("modify my attendance") == HRIntent.WRITE_REQUEST

    def test_other_user_detection(self):
        assert classify_intent("what is John's salary?") == HRIntent.OTHER_USER
        assert classify_intent("show me Mary's leave balance") == HRIntent.OTHER_USER
        assert classify_intent("someone else's details") == HRIntent.OTHER_USER

    def test_payroll_keyword_matching(self):
        assert classify_intent("payroll") == HRIntent.SALARY
        assert classify_intent("my payroll") == HRIntent.SALARY
        assert classify_intent("salary") == HRIntent.SALARY
        assert classify_intent("my salary") == HRIntent.SALARY
        assert classify_intent("show payroll") == HRIntent.SALARY

    def test_is_readonly_intent(self):
        assert is_readonly_intent(HRIntent.LEAVE_BALANCE) == True
        assert is_readonly_intent(HRIntent.SALARY) == True
        assert is_readonly_intent(HRIntent.ATTENDANCE) == True
        assert is_readonly_intent(HRIntent.WRITE_REQUEST) == False
        assert is_readonly_intent(HRIntent.OTHER_USER) == False

    def test_get_intent_response_write(self):
        response = get_intent_response(HRIntent.WRITE_REQUEST)
        assert response is not None
        assert "not able" in response.lower() or "only" in response.lower()

    def test_get_intent_response_other_user(self):
        response = get_intent_response(HRIntent.OTHER_USER)
        assert response is not None
        assert "own data" in response.lower() or "privacy" in response.lower()

    def test_get_intent_response_greeting(self):
        response = get_intent_response(HRIntent.GREETING)
        assert response is not None
        assert "hello" in response.lower() or "hi" in response.lower()

    def test_empty_message(self):
        assert classify_intent("") == HRIntent.UNKNOWN
        assert classify_intent("   ") == HRIntent.UNKNOWN


class TestSQLValidation:
    """Tests for SQL validation."""

    def test_valid_select(self):
        valid, msg = validate_sql("SELECT * FROM hr_employee WHERE id = 1")
        assert valid == True
        assert msg == "OK"

    def test_block_insert(self):
        valid, msg = validate_sql("INSERT INTO hr_employee VALUES (1, 'test')")
        assert valid == False
        assert "select" in msg.lower()

    def test_block_update(self):
        valid, msg = validate_sql("UPDATE hr_employee SET name = 'test' WHERE id = 1")
        assert valid == False

    def test_block_delete(self):
        valid, msg = validate_sql("DELETE FROM hr_employee WHERE id = 1")
        assert valid == False

    def test_block_drop(self):
        valid, msg = validate_sql("DROP TABLE hr_employee")
        assert valid == False

    def test_block_union_injection(self):
        valid, msg = validate_sql(
            "SELECT * FROM hr_employee WHERE id = 1 UNION SELECT * FROM res_users"
        )
        assert valid == False
        assert "union" in msg.lower()

    def test_block_comments(self):
        valid, msg = validate_sql("SELECT * FROM hr_employee WHERE id = 1 -- comment")
        assert valid == False
        assert "comment" in msg.lower()

    def test_block_multiple_statements(self):
        valid, msg = validate_sql(
            "SELECT * FROM hr_employee; DROP TABLE hr_employee;"
        )
        assert valid == False

    def test_block_file_operations(self):
        valid, msg = validate_sql(
            "SELECT * INTO OUTFILE '/tmp/data.txt' FROM hr_employee"
        )
        assert valid == False


class TestEmployeeIsolation:
    """Tests for employee isolation enforcement."""

    def test_simple_isolation_injection(self):
        sql = "SELECT * FROM hr_holidays WHERE name = 'test'"
        safe_sql, reason = enforce_employee_isolation(sql, 123, "EMP001")
        assert reason is None
        assert "employee_id = 123" in safe_sql.lower()

    def test_already_isolated(self):
        sql = "SELECT * FROM hr_holidays WHERE employee_id = 123"
        safe_sql, reason = enforce_employee_isolation(sql, 123, "EMP001")
        assert reason is None
        assert safe_sql == sql

    def test_payroll_emp_id_column(self):
        sql = "SELECT * FROM hr_payroll_monthly_line WHERE gross_sal > 0"
        safe_sql, reason = enforce_employee_isolation(sql, 123, "EMP001")
        assert reason is None
        assert "emp_id = 123" in safe_sql.lower()

    def test_complex_query_blocked(self):
        sql = """
            SELECT * FROM hr_holidays 
            WHERE employee_id IN (SELECT id FROM hr_employee)
        """
        safe_sql, reason = enforce_employee_isolation(sql, 123, "EMP001")
        assert reason is not None
        assert "complex" in reason.lower() or "blocked" in reason.lower()

    def test_cte_blocked(self):
        sql = """
            WITH emp AS (SELECT * FROM hr_employee)
            SELECT * FROM emp
        """
        safe_sql, reason = enforce_employee_isolation(sql, 123, "EMP001")
        assert reason is not None

    def test_public_tables_no_isolation(self):
        sql = "SELECT name FROM project_project WHERE active = TRUE"
        safe_sql, reason = enforce_employee_isolation(sql, 123, "EMP001")
        assert reason is None
        assert "employee_id" not in safe_sql.lower()

    def test_multiple_personal_tables_with_subquery(self):
        sql = """
            SELECT h.* FROM hr_holidays h 
            WHERE h.employee_id IN (SELECT id FROM hr_employee WHERE id = 123)
        """
        safe_sql, reason = enforce_employee_isolation(sql, 123, "EMP001")
        assert reason is not None


class TestPersonalTablesMapping:
    """Tests for personal tables configuration."""

    def test_hr_employee_in_personal_tables(self):
        assert "hr_employee" in _PERSONAL_TABLES
        assert _PERSONAL_TABLES["hr_employee"][0] == "id"

    def test_payroll_uses_emp_id(self):
        assert "hr_payroll_monthly_line" in _PERSONAL_TABLES
        assert _PERSONAL_TABLES["hr_payroll_monthly_line"][0] == "emp_id"

    def test_holidays_uses_employee_id(self):
        assert "hr_holidays" in _PERSONAL_TABLES
        assert _PERSONAL_TABLES["hr_holidays"][0] == "employee_id"


class TestChatService:
    """Tests for chat service integration."""

    @patch("backend.services.db_helper.get_connection")
    def test_authenticate_user_success(self, mock_get_conn):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            "id": 1,
            "login": "testuser",
            "password": "testpass",
            "password_crypt": None,
            "active": True,
        }
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value = mock_conn
        
        from backend.services.db_helper import authenticate_user
        result = authenticate_user("testuser", "testpass")
        assert result is not None
        assert result["login"] == "testuser"

    @patch("backend.services.db_helper.get_connection")
    def test_authenticate_user_failure(self, mock_get_conn):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value = mock_conn
        
        from backend.services.db_helper import authenticate_user
        result = authenticate_user("wronguser", "wrongpass")
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
