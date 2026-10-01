import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.backend_config import load_backend_config
from src.config import load_config


class WorkerConfigTest(unittest.TestCase):
    def test_loads_yaml_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(
                """
redis:
  url: redis://redis.internal:6379/2
  password: redis-from-file
server:
  url: http://tts-server:8080
audio:
  output_dir: ./my_output
news:
  sources: "https://news.rss, https://tech.rss"
deepseek:
  model: deepseek-chat
  api_key: file-key
""",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "DEEPSEEK_API_KEY": "deepseek-from-environment",
                    "OPENAI_API_KEY": "openai-from-environment",
                },
                clear=True,
            ):
                config = load_config(path)

            self.assertEqual("redis://redis.internal:6379/2", config.redis_url)
            self.assertEqual("redis-from-file", config.redis_password)
            self.assertEqual("http://tts-server:8080", config.server_url)
            self.assertEqual("./my_output", config.audio_output_dir)
            self.assertEqual(["https://news.rss", "https://tech.rss"], config.news_sources)
            self.assertEqual("deepseek-chat", config.deepseek_model)
            # Environment variable takes precedence over file key
            self.assertEqual("deepseek-from-environment", config.deepseek_api_key)
            self.assertEqual("openai-from-environment", config.openai_api_key)

    def test_environment_overrides_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text("redis:\n  url: redis://file:6379/0\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "REDIS_URL": "redis://environment:6379/1",
                    "REDIS_PASSWORD": "redis-from-environment",
                },
                clear=True,
            ):
                config = load_config(path)

            self.assertEqual("redis://environment:6379/1", config.redis_url)
            self.assertEqual("redis-from-environment", config.redis_password)

    def test_sanitized_repr_masks_api_keys(self):
        with patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "secret-deepseek-key-12345",
                "OPENAI_API_KEY": "secret-openai-key-67890",
                "REDIS_PASSWORD": "secret-redis-pass",
            },
            clear=True,
        ):
            config = load_config(Path("non-existent-config.yaml"))
            repr_str = repr(config)
            self.assertNotIn("secret-deepseek-key-12345", repr_str)
            self.assertNotIn("secret-openai-key-67890", repr_str)
            self.assertNotIn("secret-redis-pass", repr_str)
            self.assertIn("deepseek_api_key='***'", repr_str)

    def test_daily_dialogue_defaults_to_six_am_shanghai(self):
        with patch.dict(os.environ, {}, clear=True):
            config = load_backend_config(Path("non-existent-config.yaml"))
        self.assertEqual(6, config.daily_hour)
        self.assertEqual(0, config.daily_minute)
        self.assertEqual("Asia/Shanghai", config.timezone)


if __name__ == "__main__":
    unittest.main()
