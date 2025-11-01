from dotenv import load_dotenv
import os

# Загружаем .env локально (на Render переменные окружения задаются через панель/Blueprint)
load_dotenv()

def _get_env_required(key: str) -> str:
	value = os.getenv(key)
	if not value:
		raise RuntimeError(f"Required environment variable {key} is not set")
	return value

BOT_TOKEN: str = _get_env_required("BOT_TOKEN")

# ADMIN_ID опционален: если не задан или неверный, будет None
_admin_raw = os.getenv("ADMIN_ID")
try:
	ADMIN_ID = int(_admin_raw) if _admin_raw else None
except ValueError:
	ADMIN_ID = None

DATABASE_URL: str = _get_env_required("DATABASE_URL")