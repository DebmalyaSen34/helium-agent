from app.config import load_config


def test_env_override_is_typed():
    assert load_config({"APP_RETRIES": "5"})["retries"] == 5
