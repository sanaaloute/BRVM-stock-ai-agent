"""Voice-to-text tests: whisper-first ordering and Google fallback (no audio needed).

Run:
    .venv/Scripts/python tests/test_voice_to_text.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.bot.voice_to_text as vtt  # noqa: E402


class _FakeSegment:
    def __init__(self, text):
        self.text = text


class _FakeWhisper:
    def __init__(self):
        self.calls = []

    def transcribe(self, path, language=None, vad_filter=False):
        self.calls.append((path, language, vad_filter))
        return [_FakeSegment(" cours "), _FakeSegment(" NTLC ?")], None


def _reset(monkey_model=None, monkey_google=None):
    vtt._get_whisper_model_saved = getattr(vtt, "_get_whisper_model_saved", vtt._get_whisper_model)
    vtt._google_to_text_saved = getattr(vtt, "_google_to_text_saved", vtt._google_to_text)
    if monkey_model is not None:
        vtt._get_whisper_model = monkey_model
    if monkey_google is not None:
        vtt._google_to_text = monkey_google


def _restore():
    vtt._get_whisper_model = vtt._get_whisper_model_saved
    vtt._google_to_text = vtt._google_to_text_saved


def test_missing_file_returns_none():
    assert vtt.voice_to_text("/nonexistent/audio.ogg") is None


def test_whisper_is_primary():
    fake = _FakeWhisper()
    _reset(monkey_model=lambda: fake,
           monkey_google=lambda *a, **k: (_ for _ in ()).throw(AssertionError("google must not be called")))
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg") as f:
            text = vtt.voice_to_text(f.name, "fr-FR")
        assert text == "cours NTLC ?", repr(text)
        # "fr-FR" must be mapped to whisper's bare "fr"
        assert fake.calls[0][1] == "fr", fake.calls
    finally:
        _restore()


def test_fallback_to_google_when_whisper_unavailable():
    _reset(monkey_model=lambda: None, monkey_google=lambda path, lang: "bonjour")
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg") as f:
            text = vtt.voice_to_text(f.name, "fr-FR")
        assert text == "bonjour", repr(text)
    finally:
        _restore()


def test_fallback_to_google_when_whisper_returns_empty():
    class _Empty(_FakeWhisper):
        def transcribe(self, path, language=None, vad_filter=False):
            return [_FakeSegment("   ")], None

    _reset(monkey_model=lambda: _Empty(), monkey_google=lambda path, lang: "secours")
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg") as f:
            text = vtt.voice_to_text(f.name, "fr-FR")
        assert text == "secours", repr(text)
    finally:
        _restore()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
