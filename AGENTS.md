# AGENTS.md

## Overview

Single-file Python project for a Raspberry Pi 4 robot with animated eyes, STT, TTS, and LLM chat.
All code lives in `robot_eyes.py` (~1700 lines). No packages, no modules.

## Commands

```bash
python3 robot_eyes.py              # Run (fullscreen 800x480, needs display)
python3 robot_eyes.py --window     # Windowed mode for development
python3 robot_eyes.py --demo       # No mic required (simulated audio)
python3 robot_eyes.py --window --demo  # Best for local dev without hardware
```

There are no tests, no linter, no type checker, no build step.

## External dependencies (not in git)

These directories are gitignored and must be downloaded manually per README setup:

- `vosk-model/` — Vosk STT model (English)
- `piper/piper/piper` — Piper TTS binary (Linux aarch64)
- `piper-voices/*.onnx` — TTS voice models (English + Indonesian)

If missing, the app falls back gracefully (demo mode, no STT, no TTS).

## Runtime config

`config.json` is created at runtime to store the OpenRouter API key. Also gitignored.
Set `OPENROUTER_API_KEY` env var or the app prompts on first use.

## Architecture

- **Single mic stream**: `AudioLevelDetector` owns the PyAudio mic stream and feeds raw PCM to subscribers (like `VoiceRecognizer`) via callback. Never open a second mic stream.
- **Threading**: STT, TTS, and LLM each run in their own background daemon thread. The main thread runs the pygame 60 FPS loop. All cross-thread comms use `queue.Queue`.
- **TTS output**: Piper pipes raw audio to `aplay` via subprocess. Mouth animation level is simulated (not measured from actual audio output).
- **Delta-time animation**: All animation uses `dt` from `clock.tick()`. Frame-rate independent.
- **Expression system**: `Expression` enum maps to `EyeStyle` dataclasses. Eyes are drawn as rounded rects with eyelid overlays (background-colored cuts, not shaped paths).

## Platform quirks

- Requires a display (pygame fullscreen). Use `--window` for headless/dev machines.
- `pyaudio` needs `portaudio19-dev` system package. Without it, runs in demo mode.
- Piper binary is Linux aarch64 — won't run on x86 dev machines. Use `--demo` to skip TTS.
- `aplay` is used for audio output (ALSA). No PulseAudio/PipeWire support.
