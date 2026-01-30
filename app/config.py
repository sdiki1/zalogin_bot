import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: set[int]
    db_path: str
    default_access_code: str


def _parse_admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return ids


def load_config() -> Config:
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required")

    admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))
    db_path = os.getenv("DB_PATH", "/data/bot.sqlite3")
    default_access_code = os.getenv("ACCESS_CODE", "0000")

    return Config(
        bot_token=bot_token,
        admin_ids=admin_ids,
        db_path=db_path,
        default_access_code=default_access_code,
    )
