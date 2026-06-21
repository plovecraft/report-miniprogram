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
    ]:
        monkeypatch.delenv(name, raising=False)
    os.environ["LLM_DISABLE_FOR_TESTS"] = "1"
    yield
    os.environ.pop("LLM_DISABLE_FOR_TESTS", None)
