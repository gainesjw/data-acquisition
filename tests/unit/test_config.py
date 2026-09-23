import pytest

from src.config import get_settings


@pytest.mark.parametrize("name", ["STORAGE_ACCOUNT_NAME", "CONTAINER_NAME"])
@pytest.mark.parametrize("value", [None, "", "  ", "$(unresolved)"])
def test_settings_require_explicit_values(monkeypatch, name, value):
    if value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        get_settings()


def test_settings_use_selected_container(monkeypatch):
    monkeypatch.setenv("CONTAINER_NAME", "another-container")
    assert get_settings().container_name == "another-container"
