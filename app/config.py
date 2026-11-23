import os
from pathlib import Path


class Settings:
    database_url = os.environ["DATABASE_URL"]
    admin_token = os.environ["ADMIN_TOKEN"]
    data_dir = Path(os.getenv("DATA_DIR", "/data"))
    embed_provider = os.getenv("EMBED_PROVIDER", "ollama")  # "ollama" or "none"
    ollama_url = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
    embed_model = os.getenv("EMBED_MODEL", "nomic-embed-text")
    embed_dim = int(os.getenv("EMBED_DIM", "768"))
    max_file_bytes = int(os.getenv("MAX_FILE_BYTES", str(2_000_000)))


settings = Settings()
