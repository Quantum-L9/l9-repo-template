"""Process settings with safe defaults (PackageTemplate pattern, generic)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ExampleConfig(BaseSettings):
    """Runtime configuration for the example package.

    Reads L9_EXAMPLE_* env vars. Safe at import — never raises on missing env.
    """

    model_config = SettingsConfigDict(
        env_prefix="L9_EXAMPLE_",
        frozen=True,
        extra="forbid",
        populate_by_name=True,
    )

    enabled: bool = True
    service_name: str = "l9-example-pkg"

    def validate_safe(self) -> list[str]:
        warnings: list[str] = []
        if not self.enabled:
            warnings.append("capability disabled via L9_EXAMPLE_ENABLED=false")
        return warnings


@lru_cache
def get_example_config() -> ExampleConfig:
    return ExampleConfig()
