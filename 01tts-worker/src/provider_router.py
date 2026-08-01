import hashlib
import logging
from typing import Any

from src.deepseek_service import DeepSeekService

LOGGER = logging.getLogger("tts-worker.providers")


class ProviderRouter:
    """Rotate daily generation providers and fail over without changing callers."""

    def __init__(self, providers: list[tuple[str, DeepSeekService]]):
        self.providers = [(name, provider) for name, provider in providers if provider.api_key]
        if not self.providers:
            raise ValueError("At least one configured generation provider is required")

    def generate_lesson(
        self,
        prompt: str,
        metadata: dict[str, Any] | None = None,
        max_retries: int = 1,
    ) -> dict[str, Any]:
        identity = str((metadata or {}).get("uuid") or prompt)
        offset = int(hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8], 16)
        ordered = self.providers[offset % len(self.providers):] + self.providers[:offset % len(self.providers)]
        errors = []
        for name, provider in ordered:
            try:
                LOGGER.info("Generating lesson with provider=%s model=%s", name, provider.model)
                provider_retries = max_retries
                if name.lower() == "deepseek":
                    # DeepSeek occasionally returns a truncated JSON object. A second
                    # attempt is faster and more reliable than waiting for the slower
                    # fallback provider to time out.
                    provider_retries = max(2, max_retries)
                return provider.generate_lesson(
                    prompt,
                    metadata=metadata,
                    max_retries=provider_retries,
                )
            except Exception as error:
                LOGGER.warning("Provider %s failed; trying fallback: %s", name, error)
                errors.append(f"{name}: {error}")
        raise RuntimeError("All lesson providers failed: " + " | ".join(errors))

    def generate_long_lesson(
        self,
        prompt: str,
        metadata: dict[str, Any] | None = None,
        max_retries: int = 1,
    ) -> dict[str, Any]:
        # Long daily lessons intentionally prefer DeepSeek for consistent length and
        # schema behavior. Other configured providers remain a reliability fallback.
        ordered = list(self.providers)
        errors = []
        for name, provider in ordered:
            try:
                LOGGER.info("Generating long lesson with provider=%s model=%s", name, provider.model)
                return provider.generate_long_lesson(
                    prompt, metadata=metadata, max_retries=max_retries
                )
            except Exception as error:
                LOGGER.warning("Long lesson provider %s failed: %s", name, error)
                errors.append(f"{name}: {error}")
        raise RuntimeError("All long-lesson providers failed: " + " | ".join(errors))

    def generate_dialogue_lesson(
        self,
        prompt: str,
        metadata: dict[str, Any] | None = None,
        max_retries: int = 1,
    ) -> dict[str, Any]:
        """Prefer DeepSeek for daily dialogue and retain configured fallback."""
        errors = []
        for name, provider in self.providers:
            try:
                LOGGER.info(
                    "Generating dialogue lesson with provider=%s model=%s",
                    name,
                    provider.model,
                )
                return provider.generate_dialogue_lesson(
                    prompt,
                    metadata=metadata,
                    max_retries=max_retries,
                )
            except Exception as error:
                LOGGER.warning("Dialogue provider %s failed: %s", name, error)
                errors.append(f"{name}: {error}")
        raise RuntimeError(
            "All dialogue-lesson providers failed: " + " | ".join(errors)
        )
