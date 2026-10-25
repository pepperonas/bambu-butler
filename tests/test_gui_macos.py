"""macOS GUI adapter with a scripted osascript double (no real System Events calls)."""

import pytest

from bambu_butler import gui_macos


@pytest.fixture
def fake_macos(monkeypatch):
    """Simulate System Events; ``windows`` is a list of title lists returned on successive polls."""
    state = {"windows": [[]], "calls": 0, "clock": 0.0}

    def osascript(script, timeout=10):
        if "UI elements enabled" in script:
            return True, "true"
        if "name of processes" in script:
            return True, "true"
        if "every window" in script:
            seq = state["windows"]
            titles = seq[min(state["calls"], len(seq) - 1)]
            state["calls"] += 1
            return True, ", ".join(titles)
        raise AssertionError(f"unexpected script: {script}")

    monkeypatch.setattr(gui_macos, "current_os", lambda: "macos")
    monkeypatch.setattr(gui_macos, "_osascript", osascript)
    monkeypatch.setattr(gui_macos.shutil, "which", lambda name: "/usr/bin/osascript")
    # Simulated clock: sleep advances it, so wait loops finish instantly and deterministically.
    monkeypatch.setattr(gui_macos.time, "monotonic", lambda: state["clock"])
    monkeypatch.setattr(gui_macos.time, "sleep", lambda s: state.__setitem__("clock", state["clock"] + s))
    return state


def test_check_reports_missing_window_for_expected_file(fake_macos):
    # Observed on a cold start: the app runs, but no window exists yet. That must not pass silently.
    info = gui_macos.check("wh3mf")
    assert info.expected_found is False
    assert any("wh3mf" in p for p in info.problems)


def test_check_without_expectation_has_no_verdict(fake_macos):
    info = gui_macos.check()
    assert info.expected_found is None and info.problems == []


def test_wait_polls_until_the_project_window_appears(fake_macos):
    fake_macos["windows"] = [[], [], ["wh3mf"]]
    info = gui_macos.wait_for_window("wh3mf", timeout=30, interval=1)
    assert info.expected_found is True and info.window_titles == ["wh3mf"]
    assert info.problems == [] and fake_macos["calls"] == 3


def test_wait_gives_up_with_a_clear_problem(fake_macos):
    fake_macos["windows"] = [["Update verfügbar"]]
    info = gui_macos.wait_for_window("wh3mf", timeout=3, interval=1)
    assert info.expected_found is False
    assert any("wh3mf" in p for p in info.problems)
    assert fake_macos["calls"] == 4  # t=0, 1, 2, 3


def test_wait_respects_wall_clock_timeout(fake_macos, monkeypatch):
    # Each real check takes ~0.8 s of osascript calls; observed 57 s for a 30 s limit when counting attempts.
    real_check = gui_macos.check

    def slow_check(expected_file=None):
        fake_macos["clock"] += 0.8
        return real_check(expected_file)

    monkeypatch.setattr(gui_macos, "check", slow_check)
    info = gui_macos.wait_for_window("wh3mf", timeout=30, interval=1)
    assert info.expected_found is False
    assert fake_macos["clock"] <= 30 + 0.8
