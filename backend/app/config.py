from pathlib import Path

from pydantic_settings import BaseSettings

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"


class Settings(BaseSettings):
    data_dir: Path = REPO_ROOT / "data"
    host: str = "127.0.0.1"
    port: int = 8000

    model_config = {
        "env_prefix": "JOBSCOUT_",
        "env_file": str(REPO_ROOT / ".env"),
        "extra": "ignore",
    }

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jobscout.db"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def secret_key_path(self) -> Path:
        return self.data_dir / "secret.key"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.files_dir.mkdir(parents=True, exist_ok=True)
