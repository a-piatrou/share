"""Typed application settings (pydantic-settings), read from env / .env.

Phase-1 core does NOT call Claude; the ANTHROPIC_* vars are read here so the wiring exists
for the Phase-2 feature modules, but nothing in this package depends on a credential being set.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_version: str = "0.1.0"

    # --- Datastores ---
    # async SQLAlchemy URL (postgresql+asyncpg://). Matches docker-compose postgres service.
    database_url: str = Field(
        default="postgresql+asyncpg://ghostwire:ghostwire@localhost:5432/ghostwire"
    )
    # Weaviate REST host:port (gRPC inferred). docker-compose maps weaviate:8080 -> localhost:8080.
    weaviate_host: str = "localhost"
    weaviate_http_port: int = 8080
    weaviate_grpc_port: int = 50051

    # text2vec-transformers sidecar (POST /vectors). docker-compose maps :8080 -> localhost:9090.
    t2v_url: str = "http://localhost:9090"

    # --- Claude credentials (a pool; see app/llm/claude_client.py) ---
    anthropic_api_key: str | None = None
    anthropic_auth_token: str | None = None
    anthropic_auth_token_1: str | None = None
    anthropic_auth_token_2: str | None = None
    anthropic_auth_token_3: str | None = None
    anthropic_auth_token_4: str | None = None

    # --- Observability ---
    otel_exporter_otlp_endpoint: str | None = None  # e.g. http://localhost:4317; None => no export
    service_name: str = "ghostwire-backend"

    def claude_credentials(self) -> list[tuple[str, str]]:
        """Ordered (kind, value) credentials for the Claude pool: Console api_key first (if set),
        then every configured OAuth token. The client round-robins + fails over across them."""
        creds: list[tuple[str, str]] = []
        if self.anthropic_api_key:
            creds.append(("api_key", self.anthropic_api_key))
        for t in (
            self.anthropic_auth_token,
            self.anthropic_auth_token_1,
            self.anthropic_auth_token_2,
            self.anthropic_auth_token_3,
            self.anthropic_auth_token_4,
        ):
            if t:
                creds.append(("oauth", t))
        return creds


@lru_cache
def get_settings() -> Settings:
    return Settings()
