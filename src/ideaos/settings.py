"""Process settings with safe defaults."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class IdeaOSConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IDEAOS_",
        frozen=True,
        extra="forbid",
        populate_by_name=True,
    )

    enabled: bool = True
    service_name: str = "ideaos"

    def validate_safe(self) -> list[str]:
        warnings: list[str] = []
        if not self.enabled:
            warnings.append("capability disabled via IDEAOS_ENABLED=false")
        return warnings


@lru_cache
def get_example_config() -> IdeaOSConfig:
    return IdeaOSConfig()
