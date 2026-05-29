"""
Thin alias for backwards compatibility.

The text-to-SQL pipeline now lives in:
  - backend.services.llm_engine       (LLM call: NL -> SQL or direct answer)
  - backend.services.sql_generator    (rule_engine -> llm_engine router)
  - backend.services.result_processor (rows -> NL answer)
  - backend.services.llm_helper       (chat orchestrator with cache + isolation)

Existing imports of `generate_sql_or_answer` keep working via the re-export below.
"""

from backend.services.llm_engine import generate_sql as _generate_sql
from backend.services.result_processor import format_result

__all__ = ['generate_sql_or_answer', 'format_result']


def generate_sql_or_answer(
    user_message: str,
    employee_info: dict,
    history: list[dict] | None = None,
) -> tuple[str | None, str | None]:
    """Backwards-compatible alias for llm_engine.generate_sql."""
    return _generate_sql(user_message, employee_info, history)
