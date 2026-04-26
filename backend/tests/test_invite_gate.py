"""Soft-launch invite gate — BETA_INVITE_ONLY behaviour."""
import pytest

from routes.auth import _invite_required, _verify_invite


def test_invite_not_required_when_env_unset(monkeypatch):
    monkeypatch.delenv("BETA_INVITE_ONLY", raising=False)
    assert _invite_required() is False
    assert _verify_invite(None) is True
    assert _verify_invite("anything") is True


def test_invite_required_when_env_true(monkeypatch):
    monkeypatch.setenv("BETA_INVITE_ONLY", "true")
    assert _invite_required() is True
    assert _verify_invite(None) is False
    assert _verify_invite("") is False
    assert _verify_invite("wrong-code") is False


@pytest.mark.parametrize("code", ["early2026", "EARLY2026", "  investai-beta  ", "Investai-Beta"])
def test_valid_invite_codes_accepted(monkeypatch, code):
    monkeypatch.setenv("BETA_INVITE_ONLY", "1")
    assert _verify_invite(code) is True


@pytest.mark.parametrize("env_value", ["false", "0", "no", "off", ""])
def test_falsy_env_values_disable_gate(monkeypatch, env_value):
    monkeypatch.setenv("BETA_INVITE_ONLY", env_value)
    assert _invite_required() is False


@pytest.mark.parametrize("env_value", ["1", "true", "TRUE", "yes", "on"])
def test_truthy_env_values_enable_gate(monkeypatch, env_value):
    monkeypatch.setenv("BETA_INVITE_ONLY", env_value)
    assert _invite_required() is True
