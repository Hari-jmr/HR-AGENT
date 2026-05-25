import os

from backend.core.env import ENV_FILE


def _csv_env(name, default=''):
    value = os.environ.get(name, default)
    return [item.strip() for item in value.split(',') if item.strip()]


def _float_env(name):
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError:
        return None

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me')

    DB_HOST = os.environ.get('DB_HOST', '127.0.0.1')
    DB_PORT = int(os.environ.get('DB_PORT', 5432))
    DB_NAME = os.environ.get('DB_NAME', '')
    DB_USER = os.environ.get('DB_USER', '')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '')

    OPENROUTER_API_KEY = os.environ.get(
        'OPENROUTER_API_KEY',
        ''
    )
    OPENROUTER_MODEL = os.environ.get('OPENROUTER_MODEL', 'openrouter/auto')
    OPENROUTER_PROVIDER_SORT = os.environ.get('OPENROUTER_PROVIDER_SORT', 'price')
    OPENROUTER_AUTO_ALLOWED_MODELS = _csv_env(
        'OPENROUTER_AUTO_ALLOWED_MODELS',
        'openai/gpt-4o-mini,google/gemini-2.5-flash-lite,openai/gpt-5-nano*,openai/gpt-oss-120b'
    )
    OPENROUTER_MAX_PRICE_PROMPT = _float_env('OPENROUTER_MAX_PRICE_PROMPT')
    OPENROUTER_MAX_PRICE_COMPLETION = _float_env('OPENROUTER_MAX_PRICE_COMPLETION')
    OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1/chat/completions'
