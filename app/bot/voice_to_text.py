"""Voice/audio to text: faster-whisper (local, default) with Google Speech fallback."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Lazy-loaded singleton: the model is loaded on first voice note, not at import.
_whisper_model = None
_whisper_unavailable = False


def _get_whisper_model():
    global _whisper_model, _whisper_unavailable
    if _whisper_unavailable:
        return None
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel

            import config

            _whisper_model = WhisperModel(
                config.WHISPER_MODEL,
                device="cpu",
                compute_type=config.WHISPER_COMPUTE_TYPE,
            )
            logger.info(
                "Whisper model loaded: %s (%s)",
                config.WHISPER_MODEL,
                config.WHISPER_COMPUTE_TYPE,
            )
        except Exception as e:
            _whisper_unavailable = True
            logger.warning(
                "faster-whisper unavailable, falling back to Google Speech: %s", e
            )
            return None
    return _whisper_model


def _whisper_to_text(path: Path, language: str) -> str | None:
    """Transcribe with faster-whisper. Decodes ogg/opus/mp3 directly (PyAV)."""
    model = _get_whisper_model()
    if model is None:
        return None
    # "fr-FR" -> "fr" (whisper uses bare language codes)
    lang = (language or "fr").split("-")[0].split("_")[0].lower() or None
    try:
        segments, _info = model.transcribe(str(path), language=lang, vad_filter=True)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text or None
    except Exception as e:
        logger.warning("Whisper transcription failed for %s: %s", path, e)
        return None


def _google_to_text(path: Path, language: str) -> str | None:
    """Fallback: pydub (ffmpeg) conversion to WAV + Google Speech Recognition."""
    try:
        import speech_recognition as sr
    except ImportError:
        logger.error("SpeechRecognition not installed. pip install SpeechRecognition pydub")
        return None

    wav_path = path
    if path.suffix.lower() in (".ogg", ".oga", ".opus", ".m4a", ".mp3"):
        try:
            from pydub import AudioSegment

            seg = AudioSegment.from_file(str(path), format=path.suffix.lstrip(".").lower())
            wav_path = path.with_suffix(".wav")
            seg.export(str(wav_path), format="wav")
        except Exception as e:
            logger.warning("Could not convert %s to wav: %s", path, e)
            return None

    try:
        r = sr.Recognizer()
        with sr.AudioFile(str(wav_path)) as source:
            r.adjust_for_ambient_noise(source, duration=0.3)
            audio = r.record(source)
        try:
            text = r.recognize_google(audio, language=language)
            return (text or "").strip() or None
        except sr.UnknownValueError:
            logger.info("Speech not understood for %s", path)
            return None
        except sr.RequestError as e:
            logger.warning("Speech recognition request failed: %s", e)
            return None
    except Exception as e:
        logger.warning("Voice-to-text failed for %s: %s", path, e)
        return None
    finally:
        if wav_path != path and Path(wav_path).exists():
            try:
                Path(wav_path).unlink(missing_ok=True)
            except OSError:
                pass


def voice_to_text(audio_path: str | Path, language: str = "fr-FR") -> str | None:
    """Transcribe a voice note. Tries local whisper first, then Google Speech."""
    path = Path(audio_path)
    if not path.exists():
        logger.warning("Audio file not found: %s", path)
        return None
    text = _whisper_to_text(path, language)
    if text:
        return text
    return _google_to_text(path, language)
