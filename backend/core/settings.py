import os

from backend.core.env import ENV_FILE


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(',') if item.strip()]


class Settings:
    def __init__(self) -> None:
        self.APP_NAME = os.getenv('APP_NAME', 'JMR HR Agent API')
        self.APP_VERSION = os.getenv('APP_VERSION', '1.0.0')
        self.SECRET_KEY = os.getenv('SECRET_KEY', 'change-me')
        self.HOST = os.getenv('APP_HOST', '0.0.0.0')
        self.PORT = int(os.getenv('APP_PORT', '5000'))
        self.ALLOWED_ORIGINS = _split_csv(
            os.getenv(
                'ALLOWED_ORIGINS',
                'http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:5000,http://localhost:5000',
            )
        )


settings = Settings()