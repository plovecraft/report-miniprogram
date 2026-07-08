import os

import pytest


@pytest.fixture(autouse=True)
def disable_env_llm_for_offline_tests(monkeypatch):
    for name in [
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_TIMEOUT",
        "LLM_TEMPERATURE",
        "VISION_RECOGNITION_REVIEW_THRESHOLD",
        "VISION_RECOGNITION_TEMPERATURE",
        "VISION_RECOGNITION_TIMEOUT",
        "VISION_RECOGNITION_ENABLED",
        "LLM_SEND_TEMPERATURE",
        "LLM_STREAM",
        "TABLE_FEATURE_ENABLED",
    ]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TABLE_FEATURE_ENABLED", "1")
    os.environ["LLM_DISABLE_FOR_TESTS"] = "1"
    yield
    os.environ.pop("LLM_DISABLE_FOR_TESTS", None)
