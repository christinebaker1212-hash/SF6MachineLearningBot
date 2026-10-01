import pytest

from sf6bot.config import load_config


@pytest.fixture
def cfg(tmp_path):
    c = load_config(local="/nonexistent.yaml")
    c["recording"]["root"] = str(tmp_path / "runs")
    c["overlay"]["enabled"] = False
    c["input"]["backend"] = "mock"
    return c
