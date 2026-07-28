import os
from dataclasses import dataclass
from pathlib import Path

from src.config import WorkerConfig, load_config


@dataclass(frozen=True)
class BackendConfig:
    database_url: str
    redis_url: str
    redis_password: str
    storage_dir: Path
    task_queue: str
    content_queue: str
    speaking_queue: str
    anki_review_queue: str
    daily_hour: int
    daily_minute: int
    timezone: str
    worker: WorkerConfig

    def __repr__(self) -> str:
        return (
            "BackendConfig("
            "database_url='***', "
            f"redis_url={self.redis_url!r}, "
            f"redis_password={'***' if self.redis_password else ''!r}, "
            f"storage_dir={str(self.storage_dir)!r}, "
            f"task_queue={self.task_queue!r}, "
            f"content_queue={self.content_queue!r}, "
            f"speaking_queue={self.speaking_queue!r}, "
            f"anki_review_queue={self.anki_review_queue!r}, "
            f"timezone={self.timezone!r})"
        )


def load_backend_config(path: Path = Path("config.yaml")) -> BackendConfig:
    worker = load_config(path)
    return BackendConfig(
        database_url=os.getenv(
            "DATABASE_URL",
            "mysql+pymysql://listening_lab@127.0.0.1:3306/listening_lab?charset=utf8mb4",
        ),
        redis_url=worker.redis_url,
        redis_password=worker.redis_password,
        storage_dir=Path(
            os.getenv("STORAGE_DIR", worker.audio_output_dir or "./storage")
        ).expanduser().resolve(),
        task_queue=os.getenv("TASK_QUEUE", "queue:python:tts_tasks"),
        content_queue=os.getenv("CONTENT_QUEUE", "queue:python:content_tasks"),
        speaking_queue=os.getenv("SPEAKING_QUEUE", "queue:python:speaking_answers"),
        anki_review_queue=os.getenv("ANKI_REVIEW_QUEUE", "queue:python:anki_review"),
        daily_hour=int(os.getenv("DAILY_PLAN_HOUR", "6")),
        daily_minute=int(os.getenv("DAILY_PLAN_MINUTE", "0")),
        timezone=os.getenv("APP_TIMEZONE", "Asia/Shanghai"),
        worker=worker,
    )
