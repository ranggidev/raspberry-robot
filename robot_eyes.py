#!/usr/bin/env python3
"""
Robot Eyes Animation - Cute animated robot eyes for Raspberry Pi
Uses Pygame for smooth rendering on HDMI display (800x480)

Features:
- Smooth blinking animation
- Look around (eyes follow random targets)
- Multiple expressions: neutral, happy, thinking, surprised, sleepy
- Mouth talking animation synced to audio level (real mic or demo mode)
- Delta-time based animation for consistent speed
- Keyboard controls to switch expressions

Controls:
  1 - Neutral
  2 - Happy
  3 - Thinking
  4 - Surprised
  5 - Sleepy
  SPACE - Manual blink
  D - Toggle demo talking animation
  ESC / Q - Quit

Usage:
  python3 robot_eyes.py              # Auto-detect mic, fallback to demo
  python3 robot_eyes.py --demo       # Force demo mode (no mic needed)
  python3 robot_eyes.py --mic        # Force real microphone mode
"""

import pygame
import math
import random
import sys
import os
import time
import struct
import array
import threading
import subprocess
import urllib.request
import urllib.error
from enum import Enum, auto
from dataclasses import dataclass
from typing import Tuple, List, Optional

# Configuration file for API key
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# Optional: pyaudio for real microphone input
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False

# Queue for audio data sharing between AudioLevelDetector and VoiceRecognizer
import queue as _queue

# Optional: vosk for speech-to-text
try:
    import vosk
    import json as _json
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False

# Piper TTS paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PIPER_BIN = os.path.join(BASE_DIR, "piper", "piper", "piper")
PIPER_VOICES_DIR = os.path.join(BASE_DIR, "piper-voices")

# Available TTS voice models per language
TTS_VOICES = {
    "en": {
        "model": os.path.join(PIPER_VOICES_DIR, "en_US-lessac-medium.onnx"),
        "config": os.path.join(PIPER_VOICES_DIR, "en_US-lessac-medium.onnx.json"),
        "sample_rate": 22050,
        "label": "English",
        "phrases": [
            "Hello! I am your robot assistant.",
            "How are you today?",
            "I can see you with my cute eyes!",
            "The weather looks nice outside.",
            "Let me know if you need help!",
            "I am happy to talk with you.",
        ],
    },
    "id": {
        "model": os.path.join(PIPER_VOICES_DIR, "id_ID-news_tts-medium.onnx"),
        "config": os.path.join(PIPER_VOICES_DIR, "id_ID-news_tts-medium.onnx.json"),
        "sample_rate": 22050,
        "label": "Indonesia",
        "phrases": [
            "Halo! Saya adalah robot asistenmu.",
            "Apa kabar hari ini?",
            "Aku bisa melihatmu dengan mata lucuku!",
            "Cuaca hari ini sangat bagus.",
            "Beritahu aku jika kamu butuh bantuan!",
            "Aku senang bisa berbicara denganmu.",
        ],
    },
}


# =============================================================================
# Configuration
# =============================================================================
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 480
FPS = 60
FONT_SCALE = 1.0  # Overridden in --window mode to scale fonts

# Colors
COLOR_BG = (10, 10, 30)
COLOR_EYE_WHITE = (240, 240, 250)
COLOR_IRIS = (0, 200, 255)
COLOR_HAPPY = (255, 220, 50)
COLOR_EYELID = (10, 10, 30)
COLOR_EYEBROW = (80, 80, 120)
COLOR_MOUTH = (0, 200, 255)
COLOR_MOUTH_INNER = (0, 120, 180)


# =============================================================================
# Utility Functions
# =============================================================================
def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_color(c1: Tuple, c2: Tuple, t: float) -> Tuple:
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))


def clamp(value: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(value, max_val))


# =============================================================================
# Audio Level Detector
# =============================================================================
class AudioLevelDetector:
    """
    Captures microphone audio and computes RMS audio level (0.0 - 1.0).
    Falls back to demo mode if pyaudio is not available or no mic is found.
    Optionally feeds raw audio data to subscribers (e.g. VoiceRecognizer)
    via a callback, so only ONE mic stream is opened.
    """

    def __init__(self, chunk_size: int = 256, sample_rate: int = 16000,
                 channels: int = 1, demo_mode: bool = False):
        self.chunk_size = chunk_size
        self.sample_rate = sample_rate
        self.channels = channels
        self.demo_mode = demo_mode
        self.level = 0.0
        self.smooth_level = 0.0
        self.is_talking = False
        self.talk_threshold = 0.05

        # Demo mode state
        self.demo_time = 0.0
        self.demo_talking = False

        # Pyaudio state
        self.pa: Optional[pyaudio.PyAudio] = None
        self.stream = None
        self.mic_available = False

        # Audio data subscribers (list of callbacks that receive raw PCM bytes)
        self._audio_subscribers: list = []

        if not demo_mode and PYAUDIO_AVAILABLE:
            self._init_mic()
        elif not demo_mode and not PYAUDIO_AVAILABLE:
            print("   ⚠️  pyaudio not installed, using demo mode")
            print("   Install with: pip3 install pyaudio")
            self.demo_mode = True

    def _init_mic(self):
        """Initialize microphone stream."""
        try:
            self.pa = pyaudio.PyAudio()
            # Find default input device
            info = self.pa.get_default_input_device_info()
            print(f"   🎤 Using mic: {info['name']}")

            self.stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
            )
            self.mic_available = True
        except Exception as e:
            print(f"   ⚠️  Mic init failed: {e}")
            print("   Falling back to demo mode")
            self.demo_mode = True
            if self.pa:
                self.pa.terminate()
                self.pa = None

    def update(self, dt: float):
        """Update audio level from mic or demo simulation."""
        if self.demo_mode:
            self._update_demo(dt)
        elif self.mic_available:
            self._update_mic()
        else:
            self.level = 0.0

        # Smooth the level for animation
        smooth_speed = 15.0 if self.is_talking else 8.0
        self.smooth_level = lerp(self.smooth_level, self.level, smooth_speed * dt)

        # Talking state
        self.is_talking = self.smooth_level > self.talk_threshold

    def subscribe_audio(self, callback):
        """Register a callback that receives raw PCM bytes from the mic.
        Used by VoiceRecognizer to avoid opening a second mic stream.
        """
        self._audio_subscribers.append(callback)

    def unsubscribe_audio(self, callback):
        """Remove an audio subscriber."""
        if callback in self._audio_subscribers:
            self._audio_subscribers.remove(callback)

    def _update_mic(self):
        """Read audio chunk and compute RMS level."""
        try:
            data = self.stream.read(self.chunk_size, exception_on_overflow=False)
            # Feed raw audio to subscribers (e.g. VoiceRecognizer)
            for cb in self._audio_subscribers:
                try:
                    cb(data)
                except Exception:
                    pass
            # Convert 16-bit PCM to float samples
            count = len(data) // 2
            shorts = struct.unpack(f'{count}h', data)
            # Compute RMS
            sum_sq = sum(s * s for s in shorts)
            rms = math.sqrt(sum_sq / count) if count > 0 else 0
            # Normalize to 0.0 - 1.0 (max 16-bit = 32768)
            self.level = clamp(rms / 8000.0, 0.0, 1.0)
        except Exception:
            self.level = 0.0

    def _update_demo(self, dt: float):
        """Simulate talking with random patterns."""
        self.demo_time += dt

        # Simulate talking bursts
        if not self.demo_talking:
            # Random chance to start talking
            if random.random() < dt * 0.3:
                self.demo_talking = True
        else:
            # Random chance to stop talking
            if random.random() < dt * 0.8:
                self.demo_talking = False

        if self.demo_talking:
            # Simulate speech-like waveform
            base = 0.3 + 0.3 * math.sin(self.demo_time * 4)
            modulation = 0.2 * math.sin(self.demo_time * 12)
            modulation += 0.1 * math.sin(self.demo_time * 20)
            noise = random.uniform(-0.05, 0.05)
            self.level = clamp(base + modulation + noise, 0.0, 1.0)
        else:
            # Ambient noise
            self.level = random.uniform(0.0, 0.02)

    def set_demo_talking(self, talking: bool):
        """Manually set demo talking state."""
        self.demo_talking = talking

    def cleanup(self):
        """Close mic stream."""
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.pa:
            self.pa.terminate()


# =============================================================================
# Expression Enum
# =============================================================================
class Expression(Enum):
    NEUTRAL = auto()
    HAPPY = auto()
    THINKING = auto()
    SURPRISED = auto()
    SLEEPY = auto()
    ANGRY = auto()
    LISTENING = auto()
    SPEAKING = auto()


# =============================================================================
# Eye Configuration per Expression
# =============================================================================
@dataclass
class EyeStyle:
    eye_width: int = 130
    eye_height: int = 70
    eyelid_openness: float = 0.0
    eye_tilt: float = 0.0
    eyebrow_offset_y: int = -60
    eyebrow_visible: bool = False
    eyebrow_angle: float = 0.0
    mouth_visible: bool = False
    mouth_type: str = "none"
    blush_visible: bool = False


EXPRESSION_STYLES = {
    Expression.NEUTRAL: EyeStyle(
        eye_width=140, eye_height=70,
        eyelid_openness=0.0, eyebrow_visible=False,
    ),
    Expression.HAPPY: EyeStyle(
        eye_width=140, eye_height=55,
        eyelid_openness=0.25, eyebrow_visible=True, eyebrow_offset_y=-65,
        eyebrow_angle=0.0, mouth_visible=True, mouth_type="smile",
        blush_visible=True,
    ),
    Expression.THINKING: EyeStyle(
        eye_width=135, eye_height=65,
        eyelid_openness=0.1, eyebrow_visible=True, eyebrow_offset_y=-70,
        eyebrow_angle=0.15,
    ),
    Expression.SURPRISED: EyeStyle(
        eye_width=155, eye_height=85,
        eyelid_openness=0.0, eyebrow_visible=True, eyebrow_offset_y=-80,
        eyebrow_angle=-0.1,
    ),
    Expression.SLEEPY: EyeStyle(
        eye_width=140, eye_height=70,
        eyelid_openness=0.55, eyebrow_visible=False,
    ),
    Expression.ANGRY: EyeStyle(
        eye_width=130, eye_height=62,
        eyelid_openness=0.15, eyebrow_visible=True, eyebrow_offset_y=-55,
        eyebrow_angle=0.35, eye_tilt=0.08,
    ),
    Expression.LISTENING: EyeStyle(
        eye_width=145, eye_height=78,
        eyelid_openness=0.0, eyebrow_visible=True, eyebrow_offset_y=-75,
        eyebrow_angle=-0.05,
    ),
    Expression.SPEAKING: EyeStyle(
        eye_width=140, eye_height=75,
        eyelid_openness=0.0, eyebrow_visible=True, eyebrow_offset_y=-68,
        eyebrow_angle=0.0, mouth_visible=True, mouth_type="talking",
    ),
}


# =============================================================================
# Single Eye Class
# =============================================================================
class Eye:
    def __init__(self, center_x: int, center_y: int, flipped: bool = False):
        self.center_x = center_x
        self.center_y = center_y
        self.flipped = flipped

        self.current_width = 130.0
        self.current_height = 70.0
        self.current_eyelid = 0.0
        self.current_tilt = 0.0

        self.look_x = 0.0
        self.look_y = 0.0
        self.target_look_x = 0.0
        self.target_look_y = 0.0

        self.blink_timer = 0.0
        self.blink_interval = 3.0
        self.blink_progress = 0.0
        self.is_blinking = False
        self.blink_speed = 8.0

        self.smooth = 6.0

    def trigger_blink(self):
        if not self.is_blinking:
            self.is_blinking = True
            self.blink_progress = 0.0

    def update(self, dt: float, style: EyeStyle):
        self.blink_timer += dt
        if self.blink_timer >= self.blink_interval and not self.is_blinking:
            self.trigger_blink()
            self.blink_timer = 0.0
            self.blink_interval = random.uniform(2.0, 5.0)

        if self.is_blinking:
            self.blink_progress += dt * self.blink_speed
            if self.blink_progress >= 1.0:
                self.blink_progress = 0.0
                self.is_blinking = False

        blink_eyelid = 0.0
        if self.is_blinking:
            blink_eyelid = math.sin(self.blink_progress * math.pi)

        total_eyelid = clamp(style.eyelid_openness + blink_eyelid, 0.0, 1.0)

        spd = self.smooth * dt
        self.current_width = lerp(self.current_width, style.eye_width, spd)

        # Curiosity: eyes get taller when looking far to the sides (RoboEyes style)
        curiosity = 1.0 + abs(self.target_look_x) * 0.4
        effective_height = style.eye_height * curiosity
        self.current_height = lerp(self.current_height, effective_height, spd)

        self.current_eyelid = lerp(self.current_eyelid, total_eyelid, spd * 1.5)
        self.current_tilt = lerp(self.current_tilt, style.eye_tilt, spd)

        self.look_x = lerp(self.look_x, self.target_look_x, 3.0 * dt)
        self.look_y = lerp(self.look_y, self.target_look_y, 3.0 * dt)

    def draw(self, surface: pygame.Surface, style: EyeStyle):
        cx = self.center_x
        cy = self.center_y

        # Shift eye position for look direction (RoboEyes style: entire eye moves)
        look_ox = int(self.look_x * 40)
        look_oy = int(self.look_y * 30)
        cx += look_ox
        cy += look_oy

        # Apply eye tilt (for ANGRY expression)
        if abs(self.current_tilt) > 0.001:
            tilt_shift = int(self.current_tilt * 60)
            if self.flipped:
                tilt_shift = -tilt_shift
            cx += tilt_shift

        open_height = self.current_height * (1.0 - self.current_eyelid * 0.95)
        if open_height < 2:
            open_height = 2

        eye_w = self.current_width
        eye_h = int(open_height)
        corner_r = 12

        # Subtle glow behind the eye
        glow_rect = pygame.Rect(
            cx - eye_w // 2 - 10, cy - eye_h // 2 - 10,
            eye_w + 20, eye_h + 20,
        )
        pygame.draw.rect(surface, (40, 200, 255, 15), glow_rect, border_radius=corner_r + 4)

        # Main eye — simple white rounded rectangle (robot style!)
        eye_rect = pygame.Rect(
            cx - eye_w // 2, cy - eye_h // 2,
            eye_w, eye_h,
        )
        pygame.draw.rect(surface, COLOR_EYE_WHITE, eye_rect, border_radius=corner_r)

        # Thin border for definition
        pygame.draw.rect(surface, (200, 200, 220), eye_rect, width=2, border_radius=corner_r)

        # Eyelid overlay (blink / sleepy)
        if self.current_eyelid > 0.01:
            lid_height = int(eye_h * self.current_eyelid)
            if lid_height > 0:
                lid_rect = pygame.Rect(
                    cx - eye_w // 2 - 2, cy - eye_h // 2 - 2,
                    eye_w + 4, lid_height,
                )
                pygame.draw.rect(surface, COLOR_BG, lid_rect, border_radius=corner_r)

        # Eyebrow
        if style.eyebrow_visible:
            brow_y = cy + style.eyebrow_offset_y
            brow_len = eye_w * 0.5
            angle = style.eyebrow_angle
            if self.flipped:
                angle = -angle
            bx1 = cx - brow_len * math.cos(angle)
            by1 = brow_y - brow_len * math.sin(angle)
            bx2 = cx + brow_len * math.cos(angle)
            by2 = brow_y + brow_len * math.sin(angle)
            pygame.draw.line(surface, COLOR_EYEBROW, (int(bx1), int(by1)), (int(bx2), int(by2)), 4)

        # Blush
        if style.blush_visible:
            blush_surf = pygame.Surface((50, 25), pygame.SRCALPHA)
            blush_color = (255, 120, 120, 60)
            pygame.draw.ellipse(blush_surf, blush_color, (0, 0, 50, 25))
            blush_x = cx - 25 + (-20 if not self.flipped else 20)
            blush_y = cy + eye_h // 2 - 5
            surface.blit(blush_surf, (blush_x, blush_y))


# =============================================================================
# Mouth Class (with audio-synced talking animation)
# =============================================================================
class Mouth:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
        self.current_type = "none"
        self.target_type = "none"

        # Talking animation state
        self.talk_level = 0.0       # 0.0 - 1.0, drives mouth opening
        self.target_talk_level = 0.0
        self.talk_phase = 0.0       # For varied mouth shapes
        self.mouth_open_amount = 0.0  # Current interpolated open amount
        self.is_talking = False

    def set_talking(self, audio_level: float, is_talking: bool):
        """Set the audio level (0.0-1.0) to drive mouth animation."""
        self.target_talk_level = audio_level
        self.is_talking = is_talking

    def update(self, dt: float, style: EyeStyle):
        self.target_type = style.mouth_type if style.mouth_visible else "none"
        self.current_type = self.target_type

        # Smooth talk level
        speed = 20.0 if self.is_talking else 10.0
        self.talk_level = lerp(self.talk_level, self.target_talk_level, speed * dt)

        # Mouth open amount (smoothed)
        self.mouth_open_amount = lerp(self.mouth_open_amount, self.talk_level, 12.0 * dt)

        # Phase for varied shapes during talking
        if self.is_talking:
            self.talk_phase += dt * 15.0

    def draw(self, surface: pygame.Surface):
        open_amt = self.mouth_open_amount

        if self.current_type == "smile":
            self._draw_smile(surface, open_amt)
        elif self.current_type == "o":
            self._draw_o_mouth(surface, open_amt)
        elif self.current_type == "talking" or (self.is_talking and open_amt > 0.02):
            self._draw_talking_mouth(surface, open_amt)
        elif self.current_type == "line":
            self._draw_line_mouth(surface)

    def _draw_smile(self, surface: pygame.Surface, open_amt: float):
        """Draw a curved smile that opens slightly when talking."""
        base_rx = 40
        base_ry = 18
        # When talking, the smile opens up a bit
        open_boost = open_amt * 12

        points = []
        for i in range(24):
            t = i / 23.0
            angle = math.pi * 0.1 + t * math.pi * 0.8
            rx = base_rx
            ry = base_ry + open_boost * (0.5 + 0.5 * math.sin(t * math.pi))
            px = self.x + rx * math.cos(angle)
            py = self.y + ry * math.sin(angle)
            points.append((int(px), int(py)))

        if len(points) > 1:
            # Draw filled shape for open mouth
            if open_amt > 0.05:
                # Draw mouth interior
                inner_points = points[:]
                pygame.draw.polygon(surface, COLOR_MOUTH_INNER, inner_points)
            pygame.draw.lines(surface, COLOR_MOUTH, False, points, 3)

    def _draw_o_mouth(self, surface: pygame.Surface, open_amt: float):
        """Draw an 'O' shape mouth (surprised)."""
        base_r = 12
        # When talking, the O gets bigger
        radius = base_r + open_amt * 10
        # Slightly vary the shape based on phase
        y_stretch = 1.0 + 0.3 * math.sin(self.talk_phase * 0.7)

        # Draw filled ellipse
        rx = int(radius)
        ry = int(radius * y_stretch)
        rect = pygame.Rect(self.x - rx, self.y - ry, rx * 2, ry * 2)

        if open_amt > 0.05:
            pygame.draw.ellipse(surface, COLOR_MOUTH_INNER, rect)
        pygame.draw.ellipse(surface, COLOR_MOUTH, rect, 3)

    def _draw_talking_mouth(self, surface: pygame.Surface, open_amt: float):
        """
        Draw a dynamic talking mouth that changes shape based on audio level.
        Creates an ellipse that opens/closes with speech rhythm.
        """
        # Base dimensions
        base_width = 35
        base_height = 5

        # Opening amount scales with audio level
        open_height = base_height + open_amt * 30

        # Slight width variation for natural look
        width_var = 1.0 + 0.15 * math.sin(self.talk_phase * 0.5)
        mouth_width = int(base_width * width_var)

        # Draw the mouth shape
        rect = pygame.Rect(
            self.x - mouth_width // 2,
            self.y - int(open_height) // 2,
            mouth_width,
            int(open_height),
        )

        # Fill interior
        if open_amt > 0.03:
            pygame.draw.ellipse(surface, COLOR_MOUTH_INNER, rect)

        # Outline
        pygame.draw.ellipse(surface, COLOR_MOUTH, rect, 3)

        # Small tongue hint when mouth is open wide
        if open_amt > 0.3:
            tongue_y = self.y + int(open_height) * 0.15
            tongue_r = int(open_height * 0.2)
            pygame.draw.circle(surface, (200, 100, 100), (self.x, tongue_y), tongue_r)

    def _draw_line_mouth(self, surface: pygame.Surface):
        """Draw a simple line mouth."""
        pygame.draw.line(
            surface, COLOR_MOUTH,
            (self.x - 25, self.y),
            (self.x + 25, self.y),
            3,
        )


# =============================================================================
# Robot Face
# =============================================================================
class RobotFace:
    def __init__(self):
        self.face_cx = SCREEN_WIDTH // 2
        self.face_cy = SCREEN_HEIGHT // 2 - 20

        eye_spacing = 160
        self.left_eye = Eye(self.face_cx - eye_spacing // 2, self.face_cy, flipped=False)
        self.right_eye = Eye(self.face_cx + eye_spacing // 2, self.face_cy, flipped=True)
        self.mouth = Mouth(self.face_cx, self.face_cy + 100)

        self.expression = Expression.NEUTRAL
        self.target_expression = Expression.NEUTRAL
        self.expression_timer = 0.0
        self.auto_expression = True

        self.look_timer = 0.0
        self.look_interval = 2.5

        self.think_dots: List[Tuple[float, float, float]] = []
        self.sweat_drops: List[SweatDrop] = []
        self.sweat_enabled = False

    def trigger_sweat(self):
        """Spawn a sweat drop above a random eye."""
        x = self.left_eye.center_x + random.randint(-30, 30) if random.random() < 0.5 else self.right_eye.center_x + random.randint(-30, 30)
        y = self.face_cy - 80 + random.randint(-10, 10)
        self.sweat_drops.append(SweatDrop(x, y))

    def set_expression(self, expr: Expression):
        self.target_expression = expr
        self.expression = expr

    def update(self, dt: float):
        style = EXPRESSION_STYLES[self.expression]
        self.left_eye.update(dt, style)
        self.right_eye.update(dt, style)
        self.mouth.update(dt, style)

        self.look_timer += dt
        if self.look_timer >= self.look_interval:
            self.look_timer = 0.0
            self.look_interval = random.uniform(1.5, 4.0)
            tx = random.uniform(-0.8, 0.8)
            ty = random.uniform(-0.5, 0.5)
            self.left_eye.target_look_x = tx
            self.left_eye.target_look_y = ty
            self.right_eye.target_look_x = tx
            self.right_eye.target_look_y = ty

        if self.auto_expression:
            self.expression_timer += dt
            if self.expression_timer > 6.0:
                self.expression_timer = 0.0
                self.set_expression(random.choice(list(Expression)))

        if self.expression == Expression.THINKING:
            if random.random() < dt * 3:
                bx = self.face_cx + random.randint(100, 160)
                by = self.face_cy - random.randint(40, 80)
                self.think_dots.append((bx, by, 0.0))
            self.think_dots = [(bx, by, age + dt) for bx, by, age in self.think_dots if age + dt < 2.0]
        else:
            self.think_dots.clear()

        # Sweat drops
        if self.sweat_enabled:
            if random.random() < dt * 1.5:
                self.trigger_sweat()
            self.sweat_drops = [d for d in self.sweat_drops if d.update(dt)]
        else:
            self.sweat_drops.clear()

    def draw(self, surface: pygame.Surface):
        style = EXPRESSION_STYLES[self.expression]
        self.left_eye.draw(surface, style)
        self.right_eye.draw(surface, style)
        self.mouth.draw(surface)

        for bx, by, age in self.think_dots:
            alpha = max(0, 255 - int(age * 128))
            size = int(6 - age * 2)
            if size > 0:
                dot_surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
                pygame.draw.circle(dot_surf, (COLOR_IRIS[0], COLOR_IRIS[1], COLOR_IRIS[2], alpha), (size, size), size)
                surface.blit(dot_surf, (int(bx) - size, int(by) - size))

        for drop in self.sweat_drops:
            drop.draw(surface)

        font = pygame.font.SysFont("monospace", max(1, int(14 * FONT_SCALE)), bold=True)
        label = font.render(f"[{self.expression.name}]  V=voice  G=auto  T=speak  L=lang  SPACE=blink", True, (60, 60, 100))
        surface.blit(label, (10, SCREEN_HEIGHT - 15))


# =============================================================================
# Sparkle
# =============================================================================
class Sparkle:
    def __init__(self):
        self.x = random.randint(0, SCREEN_WIDTH)
        self.y = random.randint(0, SCREEN_HEIGHT)
        self.size = random.uniform(1, 3)
        self.brightness = random.uniform(0.3, 1.0)
        self.speed = random.uniform(0.5, 2.0)
        self.phase = random.uniform(0, math.pi * 2)

    def update(self, dt: float):
        self.phase += self.speed * dt
        self.brightness = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(self.phase))

    def draw(self, surface: pygame.Surface):
        alpha = int(self.brightness * 100)
        s = pygame.Surface((int(self.size * 2), int(self.size * 2)), pygame.SRCALPHA)
        pygame.draw.circle(s, (100, 150, 255, alpha), (int(self.size), int(self.size)), int(self.size))
        surface.blit(s, (int(self.x), int(self.y)))


# =============================================================================
# Sweat Drop (RoboEyes style animated sweat)
# =============================================================================
class SweatDrop:
    """Animated sweat drop that appears above the eyes."""
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
        self.age = 0.0
        self.max_age = random.uniform(0.8, 1.5)
        self.vy = random.uniform(20, 40)  # Falling speed

    def update(self, dt: float) -> bool:
        """Update position. Returns False when expired."""
        self.age += dt
        if self.age > self.max_age:
            return False
        self.y += self.vy * dt
        return True

    def draw(self, surface: pygame.Surface):
        alpha = max(0, int(200 * (1.0 - self.age / self.max_age)))
        size = max(2, int(6 * (1.0 - self.age * 0.3)))
        s = pygame.Surface((size * 2, size * 3), pygame.SRCALPHA)
        # Teardrop shape: circle at top, triangle at bottom
        pygame.draw.circle(s, (100, 180, 255, alpha), (size, size), size)
        pts = [(size - size // 2, size * 2), (size + size // 2, size * 2), (size, size * 3)]
        pygame.draw.polygon(s, (100, 180, 255, alpha), pts)
        surface.blit(s, (int(self.x) - size, int(self.y) - size))


# =============================================================================
# Audio Level Bar (visual feedback)
# =============================================================================
def draw_audio_bar(surface: pygame.Surface, level: float, x: int, y: int,
                   width: int = 200, height: int = 8):
    """Draw a small audio level meter bar."""
    # Background
    bg_rect = pygame.Rect(x, y, width, height)
    pygame.draw.rect(surface, (30, 30, 50), bg_rect, border_radius=4)

    # Level fill
    fill_w = int(width * clamp(level, 0.0, 1.0))
    if fill_w > 0:
        fill_rect = pygame.Rect(x, y, fill_w, height)
        # Color based on level
        if level < 0.3:
            color = (50, 200, 100)
        elif level < 0.7:
            color = (200, 200, 50)
        else:
            color = (255, 80, 80)
        pygame.draw.rect(surface, color, fill_rect, border_radius=4)

    # Label
    font = pygame.font.SysFont("monospace", max(1, int(12 * FONT_SCALE)))
    label = "🎤 LIVE" if PYAUDIO_AVAILABLE else "🎮 DEMO"
    text = font.render(label, True, (80, 80, 120))
    surface.blit(text, (x + width + 10, y - 2))


# =============================================================================
# Speaker (Piper TTS - threaded, non-blocking)
# =============================================================================
class Speaker:
    """
    Text-to-speech using Piper TTS binary via subprocess.
    Supports multiple languages (English, Indonesian).
    Runs synthesis in a background thread so it doesn't block the animation.
    Drives mouth talking animation via a simulated audio level.
    """

    def __init__(self, language: str = "en"):
        self.piper_bin = PIPER_BIN
        self.language = language
        self.available = False
        self.is_speaking = False
        self.tts_level = 0.0        # Simulated audio level for mouth animation
        self.speech_queue: _queue.Queue = _queue.Queue(maxsize=10)
        self.thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Simulated talk animation state
        self._talk_time = 0.0

        self._check_availability()

    @property
    def model_path(self) -> str:
        return TTS_VOICES.get(self.language, TTS_VOICES["en"])["model"]

    @property
    def config_path(self) -> str:
        return TTS_VOICES.get(self.language, TTS_VOICES["en"])["config"]

    @property
    def sample_rate(self) -> int:
        return TTS_VOICES.get(self.language, TTS_VOICES["en"])["sample_rate"]

    @property
    def label(self) -> str:
        return TTS_VOICES.get(self.language, TTS_VOICES["en"])["label"]

    @property
    def phrases(self) -> list:
        return TTS_VOICES.get(self.language, TTS_VOICES["en"])["phrases"]

    def set_language(self, lang: str):
        """Switch TTS language (stops any current speech)."""
        if lang not in TTS_VOICES:
            print(f"   ⚠️  Unknown language: {lang}")
            return
        if lang == self.language:
            return
        self.stop()
        self.language = lang
        self.available = False
        self._check_availability()
        print(f"   🌐 TTS language: {self.label}")

    def toggle_language(self):
        """Toggle between available languages."""
        langs = list(TTS_VOICES.keys())
        idx = langs.index(self.language) if self.language in langs else 0
        next_lang = langs[(idx + 1) % len(langs)]
        self.set_language(next_lang)

    def _check_availability(self):
        """Check if Piper binary and current model exist."""
        if not os.path.exists(self.piper_bin):
            print("   ⚠️  Piper binary not found")
            return
        if not os.path.exists(self.model_path):
            print(f"   ⚠️  Piper model not found: {os.path.basename(self.model_path)}")
            return
        self.available = True
        print(f"   🔊 Piper TTS ready ({self.label}): {os.path.basename(self.model_path)}")

    def speak(self, text: str):
        """Queue text to be spoken. Starts the speaker thread if needed."""
        if not self.available or not text.strip():
            return
        try:
            self.speech_queue.put_nowait(text)
        except _queue.Full:
            print("   ⚠️  Speech queue full, dropping text")
            return

        if self.thread is None or not self.thread.is_alive():
            self._stop_event.clear()
            self.thread = threading.Thread(target=self._speak_loop, daemon=True)
            self.thread.start()

    def stop(self):
        """Stop speaking and clear the queue."""
        self._stop_event.set()
        self.is_speaking = False
        self.tts_level = 0.0
        # Drain queue
        while not self.speech_queue.empty():
            try:
                self.speech_queue.get_nowait()
            except _queue.Empty:
                break

    def _speak_loop(self):
        """Background thread: generate and play TTS audio."""
        while not self._stop_event.is_set():
            try:
                text = self.speech_queue.get(timeout=0.5)
            except _queue.Empty:
                continue

            self.is_speaking = True
            self._talk_time = 0.0

            # Estimate speech duration (~150 words/min = ~2.5 words/sec)
            word_count = len(text.split())
            talk_duration = max(0.5, word_count / 2.5)

            gen = None
            player = None
            try:
                # Generate TTS audio
                gen = subprocess.Popen(
                    [self.piper_bin, "--model", self.model_path,
                     "--config", self.config_path, "--output-raw"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )

                # Play audio via aplay (non-blocking from our perspective)
                player = subprocess.Popen(
                    ["aplay", "-r", str(self.sample_rate), "-f", "S16_LE",
                     "-t", "raw", "-c", "1"],
                    stdin=gen.stdout,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                gen.stdin.write(text.encode("utf-8"))
                gen.stdin.close()

                # Wait for playback to finish (with stop check)
                while player.poll() is None:
                    if self._stop_event.is_set():
                        player.kill()
                        gen.kill()
                        break
                    time.sleep(0.05)

            except Exception as e:
                print(f"   ⚠️  TTS error: {e}")
            finally:
                # Ensure subprocesses are cleaned up
                if gen and gen.poll() is None:
                    gen.kill()
                if player and player.poll() is None:
                    player.kill()

            self.is_speaking = False
            self.tts_level = 0.0

    def update(self, dt: float):
        """Update simulated mouth animation level while speaking."""
        if not self.is_speaking:
            # Decay the level smoothly
            self.tts_level = lerp(self.tts_level, 0.0, 10.0 * dt)
            return

        self._talk_time += dt

        # Simulate speech-like waveform for mouth animation
        t = self._talk_time
        base = 0.4 + 0.3 * math.sin(t * 5.0)
        mod1 = 0.15 * math.sin(t * 13.0)
        mod2 = 0.1 * math.sin(t * 21.0)
        noise = random.uniform(-0.05, 0.05)
        self.tts_level = clamp(base + mod1 + mod2 + noise, 0.0, 1.0)

    def cleanup(self):
        """Stop speaking and clean up."""
        self.stop()


# =============================================================================
# Brain (LLM via OpenRouter API)
# =============================================================================
class Brain:
    """
    AI Brain using OpenRouter API (Gemma model).
    Calls the LLM in a background thread so it doesn't block animation.
    Maintains conversation history for context.
    """

    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    DEFAULT_MODEL = "google/gemma-2-9b-it:free"
    SYSTEM_PROMPT = (
        "You are a cute robot assistant with big animated eyes. "
        "You are friendly, helpful, and speak in short sentences (1-2 sentences max). "
        "Keep responses brief since they will be spoken aloud via TTS. "
        "If asked in Indonesian, reply in Indonesian. If asked in English, reply in English. "
        "You live on a Raspberry Pi and love chatting with your owner."
    )

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self.available = bool(self.api_key)
        self.is_thinking = False
        self.response_text = ""           # Last LLM response
        self.last_user_text = ""           # Last user input
        self.response_time = 0.0           # Timestamp of last response
        self.response_display_timeout = 8.0  # Seconds to show response on screen

        # Conversation history (limited to last 10 exchanges)
        self.history: List[dict] = []
        self.max_history = 10

        # Background thread for LLM calls
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._request_queue: _queue.Queue = _queue.Queue(maxsize=5)
        self._response_queue: _queue.Queue = _queue.Queue(maxsize=5)

        # Callback for when response is ready
        self.on_response: Optional[callable] = None

        # Try loading API key from config file if not provided
        if not self.api_key:
            self._load_config()

        self._update_availability()

    def _load_config(self):
        """Load API key from config.json if it exists."""
        if os.path.exists(CONFIG_FILE):
            try:
                import json as _json_mod
                with open(CONFIG_FILE, "r") as f:
                    config = _json_mod.load(f)
                self.api_key = config.get("openrouter_api_key", "")
                if config.get("model"):
                    self.model = config["model"]
            except Exception:
                pass

    def _save_config(self):
        """Save API key to config.json."""
        try:
            import json as _json_mod
            config = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    config = _json_mod.load(f)
            config["openrouter_api_key"] = self.api_key
            config["model"] = self.model
            with open(CONFIG_FILE, "w") as f:
                _json_mod.dump(config, f, indent=2)
        except Exception as e:
            print(f"   ⚠️  Failed to save config: {e}")

    def _update_availability(self):
        """Check if Brain is ready to use."""
        self.available = bool(self.api_key)
        if self.available:
            print(f"   🧠 AI Brain ready: {self.model}")
        else:
            print("   ⚠️  AI Brain disabled (no API key)")
            print("   Set OPENROUTER_API_KEY env var or create config.json")

    def set_api_key(self, key: str):
        """Set the API key and save to config."""
        self.api_key = key.strip()
        self._update_availability()
        if self.api_key:
            self._save_config()

    def think(self, user_text: str):
        """Send user text to LLM in background thread. Non-blocking."""
        if not self.available or not user_text.strip():
            return

        self.last_user_text = user_text

        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._think_loop, daemon=True)
            self._thread.start()

        try:
            self._request_queue.put_nowait(user_text)
        except _queue.Full:
            print("   ⚠️  Brain request queue full")

    def stop(self):
        """Stop the background thread."""
        self._stop_event.set()
        self.is_thinking = False
        while not self._request_queue.empty():
            try:
                self._request_queue.get_nowait()
            except _queue.Empty:
                break
        while not self._response_queue.empty():
            try:
                self._response_queue.get_nowait()
            except _queue.Empty:
                break

    def _think_loop(self):
        """Background thread: process LLM requests."""
        while not self._stop_event.is_set():
            try:
                user_text = self._request_queue.get(timeout=0.5)
            except _queue.Empty:
                continue

            self.is_thinking = True
            response = self._call_api(user_text)
            self.is_thinking = False

            if response:
                self.response_text = response
                self.response_time = time.time()
                print(f"   🧠 AI: {response}")

                # Add to history
                self.history.append({"role": "user", "content": user_text})
                self.history.append({"role": "assistant", "content": response})
                # Trim history
                if len(self.history) > self.max_history * 2:
                    self.history = self.history[-(self.max_history * 2):]

                # Notify callback
                if self.on_response:
                    try:
                        self.on_response(response)
                    except Exception:
                        pass

    def _call_api(self, user_text: str) -> str:
        """Make the actual API call to OpenRouter."""
        try:
            messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
            messages.extend(self.history)
            messages.append({"role": "user", "content": user_text})

            payload = _json.dumps({
                "model": self.model,
                "messages": messages,
                "max_tokens": 150,
                "temperature": 0.7,
            }).encode("utf-8")

            req = urllib.request.Request(
                self.API_URL,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": "https://github.com/robot-eyes-pi",
                    "X-OpenRouter-Title": "Robot Eyes AI Assistant",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"   ⚠️  API error {e.code}: {body[:200]}")
            return ""
        except urllib.error.URLError as e:
            print(f"   ⚠️  Network error: {e.reason}")
            return ""
        except Exception as e:
            print(f"   ⚠️  LLM error: {e}")
            return ""

    def get_response_display_text(self) -> str:
        """Return response text to display (with timeout)."""
        if not self.response_text:
            return ""
        elapsed = time.time() - self.response_time
        if elapsed > self.response_display_timeout:
            return ""
        return self.response_text

    def clear_history(self):
        """Clear conversation history."""
        self.history.clear()
        print("   🧠 Conversation history cleared")

    def update(self, dt: float):
        """Update brain state."""
        pass  # Most state is managed by the background thread

    def cleanup(self):
        """Stop background thread."""
        self.stop()


# =============================================================================
# Voice Recognizer (Vosk STT - threaded, non-blocking)
# =============================================================================
class VoiceRecognizer:
    """
    Runs Vosk speech-to-text in a background thread.
    Receives audio data from AudioLevelDetector via a shared queue
    (no separate mic stream — avoids device contention).
    """

    def __init__(self, model_path: str = "vosk-model", sample_rate: int = 16000):
        self.model_path = model_path
        self.sample_rate = sample_rate
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # Recognition state
        self.is_listening = False
        self.partial_text = ""           # Live partial result
        self.final_text = ""             # Last complete sentence
        self.final_text_time = 0.0       # Timestamp of last final text
        self.silence_timeout = 3.0       # Seconds before clearing final text
        self.all_results: List[str] = []  # History of final results
        self.recognizer = None
        self.model = None

        # Audio queue — fed by AudioLevelDetector subscriber callback
        self._audio_queue: _queue.Queue = _queue.Queue(maxsize=50)

        self._init_vosk()

    def _init_vosk(self):
        """Initialize Vosk model (no mic stream — audio comes from queue)."""
        if not VOSK_AVAILABLE:
            print("   ⚠️  vosk not installed — STT disabled")
            print("   Install with: pip3 install vosk")
            return

        if not os.path.exists(self.model_path):
            print(f"   ⚠️  Vosk model not found at '{self.model_path}'")
            print("   Download from: https://alphacephei.com/vosk/models")
            return

        try:
            print(f"   🧠 Loading Vosk model from {self.model_path}...")
            vosk.SetLogLevel(-1)  # Suppress verbose logs
            self.model = vosk.Model(self.model_path)
            self.recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)
            self.recognizer.SetWords(True)
            print("   ✅ Vosk model loaded!")
        except Exception as e:
            print(f"   ⚠️  Failed to load Vosk model: {e}")

    def _feed_audio(self, data: bytes):
        """Callback: receives raw PCM audio from AudioLevelDetector."""
        if self.running:
            try:
                self._audio_queue.put_nowait(data)
            except _queue.Full:
                pass  # Drop frames if queue is full

    def start(self, audio_detector: Optional['AudioLevelDetector'] = None):
        """Start the recognition thread. Subscribes to audio_detector for mic data."""
        if self.running:
            return  # Guard against double-start
        if self.model is None:
            print("   ⚠️  Vosk model not loaded — cannot start STT")
            return

        # Subscribe to mic audio from AudioLevelDetector
        if audio_detector and audio_detector.mic_available:
            audio_detector.subscribe_audio(self._feed_audio)
            self._audio_detector_ref = audio_detector
        else:
            print("   ⚠️  No mic available — STT will receive no audio")
            return

        self.running = True
        self.is_listening = True
        self.final_text = ""
        self.partial_text = ""
        self.thread = threading.Thread(target=self._recognize_loop, daemon=True)
        self.thread.start()
        print("   🎙️  Voice recognition started!")

    def stop(self):
        """Stop the recognition thread and unsubscribe from audio."""
        self.running = False
        self.is_listening = False
        if self.thread:
            self.thread.join(timeout=2.0)
            self.thread = None
        # Unsubscribe from audio feed
        if hasattr(self, '_audio_detector_ref') and self._audio_detector_ref:
            self._audio_detector_ref.unsubscribe_audio(self._feed_audio)
            self._audio_detector_ref = None
        # Drain queue
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except _queue.Empty:
                break

    def _recognize_loop(self):
        """Background thread: pull audio from queue and feed to Vosk."""
        while self.running:
            try:
                data = self._audio_queue.get(timeout=0.5)
            except _queue.Empty:
                continue

            if self.recognizer.AcceptWaveform(data):
                result = _json.loads(self.recognizer.Result())
                text = result.get("text", "").strip()
                if text:
                    self.final_text = text
                    self.final_text_time = time.time()
                    self.all_results.append(text)
                    print(f"   🗣️  [{text}]")
                    self.partial_text = ""
            else:
                partial = _json.loads(self.recognizer.PartialResult())
                self.partial_text = partial.get("partial", "")

    def update(self, dt: float):
        """Clear stale final text after silence timeout."""
        if self.final_text and not self.partial_text:
            elapsed = time.time() - self.final_text_time
            if elapsed > self.silence_timeout:
                self.final_text = ""

    def get_display_text(self) -> str:
        """Return the current text to display (partial or final)."""
        if self.partial_text:
            return self.partial_text + "..."
        return self.final_text


# =============================================================================
# Main
# =============================================================================
def main():
    pygame.init()

    os.environ["SDL_VIDEO_WINDOW_POS"] = "0,0"

    # Parse --window flag for windowed mode (default 250x250, or custom WxH)
    window_mode = False
    window_w, window_h = 320, 240
    if '--window' in sys.argv:
        idx = sys.argv.index('--window')
        window_mode = True
        if idx + 1 < len(sys.argv) and 'x' in sys.argv[idx + 1]:
            parts = sys.argv[idx + 1].split('x')
            try:
                window_w = int(parts[0])
                window_h = int(parts[1])
            except (ValueError, IndexError):
                pass

    if window_mode:
        screen = pygame.display.set_mode((window_w, window_h))
        internal_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        scale_factor = min(window_w / SCREEN_WIDTH, window_h / SCREEN_HEIGHT)
        global FONT_SCALE
        FONT_SCALE = max(2.0, 1.0 / scale_factor) if scale_factor > 0 else 3.2
    else:
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
        internal_surf = screen

    pygame.display.set_caption("Robot Eyes - Talking Mode")
    clock = pygame.time.Clock()

    # Parse args
    force_demo = "--demo" in sys.argv
    force_mic = "--mic" in sys.argv

    demo_mode = force_demo or (not force_mic and not PYAUDIO_AVAILABLE)

    # Initialize audio (single mic stream)
    audio = AudioLevelDetector(demo_mode=demo_mode)

    face = RobotFace()
    sparkles = [Sparkle() for _ in range(30)]

    # Initialize Vosk voice recognition (uses audio's mic via subscriber)
    voice = VoiceRecognizer()
    voice_active = False  # Track if STT is running

    # Initialize Piper TTS speaker
    speaker = Speaker()

    # Initialize AI Brain (OpenRouter LLM)
    brain = Brain()
    auto_respond = False  # Auto pipeline: STT → LLM → TTS

    # Wire Brain response to TTS
    def on_brain_response(response_text: str):
        """Called from Brain thread when LLM responds."""
        if response_text and speaker.available:
            speaker.speak(response_text)
    brain.on_response = on_brain_response

    key_map = {
        pygame.K_1: Expression.NEUTRAL,
        pygame.K_2: Expression.HAPPY,
        pygame.K_3: Expression.THINKING,
        pygame.K_4: Expression.SURPRISED,
        pygame.K_5: Expression.SLEEPY,
        pygame.K_6: Expression.LISTENING,
        pygame.K_7: Expression.ANGRY,
    }

    print("🤖 Robot Eyes + AI Voice Assistant!")
    print(f"   Mode: {'🎮 Demo (simulated audio)' if audio.demo_mode else '🎤 Live Mic'}")
    print(f"   Vosk STT: {'✅ Ready' if voice.model else '❌ Not available'}")
    print(f"   Piper TTS: {'✅ Ready' if speaker.available else '❌ Not available'}")
    print(f"   AI Brain: {'✅ Ready' if brain.available else '❌ No API key (set in config.json)'}")
    print("   Controls:")
    print("   1-7=expr  V=voice  G=auto  T=speak  L=lang  S=sweat  SPACE=blink  ESC/Q=Quit")

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        dt = min(dt, 0.05)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_SPACE:
                    face.left_eye.trigger_blink()
                    face.right_eye.trigger_blink()
                    face.left_eye.blink_timer = 0
                    face.right_eye.blink_timer = 0
                elif event.key in key_map:
                    face.auto_expression = False
                    face.set_expression(key_map[event.key])
                    face.expression_timer = 0.0
                    print(f"   Expression: {key_map[event.key].name}")
                elif event.key == pygame.K_a:
                    face.auto_expression = not face.auto_expression
                    print(f"   Auto expression: {'ON' if face.auto_expression else 'OFF'}")
                elif event.key == pygame.K_d:
                    if audio.demo_mode:
                        audio.demo_talking = not audio.demo_talking
                        print(f"   Demo talking: {'ON' if audio.demo_talking else 'OFF'}")
                elif event.key == pygame.K_t:
                    # Test TTS - speak a demo phrase in current language
                    if speaker.available:
                        phrase = random.choice(speaker.phrases)
                        print(f"   🔊 Speaking ({speaker.label}): {phrase}")
                        speaker.speak(phrase)
                    else:
                        print("   ⚠️  Piper TTS not available")
                elif event.key == pygame.K_l:
                    # Toggle TTS language
                    speaker.toggle_language()
                elif event.key == pygame.K_g:
                    # Toggle auto-respond mode (STT → LLM → TTS pipeline)
                    auto_respond = not auto_respond
                    print(f"   🤖 Auto-respond: {'ON' if auto_respond else 'OFF'}")
                    if auto_respond and not voice_active and voice.model:
                        # Auto-start voice recognition when enabling auto-respond
                        voice.start(audio_detector=audio)
                        voice_active = True
                        face.auto_expression = False
                        face.set_expression(Expression.LISTENING)
                        print("   🎙️  Voice recognition AUTO-STARTED")
                elif event.key == pygame.K_v:
                    # Toggle voice recognition
                    if voice.model:
                        if voice_active:
                            voice.stop()
                            voice_active = False
                            if auto_respond:
                                auto_respond = False
                                print("   🤖 Auto-respond OFF (voice stopped)")
                            print("   🎙️  Voice recognition STOPPED")
                        else:
                            voice.start(audio_detector=audio)
                            voice_active = True
                            face.auto_expression = False
                            face.set_expression(Expression.LISTENING)
                            print("   🎙️  Voice recognition STARTED")
                    else:
                        print("   ⚠️  Voice not available (need vosk + mic)")
                elif event.key == pygame.K_s:
                    # Toggle sweat drops (RoboEyes style)
                    face.sweat_enabled = not face.sweat_enabled
                    print(f"   💧 Sweat drops: {'ON' if face.sweat_enabled else 'OFF'}")
                elif event.key == pygame.K_c:
                    # Clear brain conversation history
                    brain.clear_history()

        # Update audio
        audio.update(dt)

        # Feed audio level to mouth
        face.mouth.set_talking(audio.smooth_level, audio.is_talking)

        # Update TTS speaker
        speaker.update(dt)

        # When TTS is speaking, feed simulated level to mouth
        if speaker.is_speaking:
            face.mouth.set_talking(speaker.tts_level, True)
            face.mouth.current_type = "talking"
            if not voice_active:
                face.auto_expression = False
                face.set_expression(Expression.SPEAKING)
        # When mic is talking, show mouth on all expressions
        elif audio.is_talking:
            face.mouth.current_type = "talking"

        # Auto-respond pipeline: STT → LLM → TTS
        if auto_respond and voice_active and voice.final_text:
            user_text = voice.final_text
            voice.final_text = ""  # Consume the text
            if user_text.strip() and not brain.is_thinking and not speaker.is_speaking:
                print(f"   🤖 Auto-respond: '{user_text}' → LLM...")
                face.set_expression(Expression.THINKING)
                brain.think(user_text)

        # Voice recognition update (clear stale text)
        if voice_active:
            voice.update(dt)
            # Show LISTENING expression when listening (unless thinking or speaking)
            if not brain.is_thinking and not speaker.is_speaking:
                if face.expression != Expression.LISTENING:
                    face.set_expression(Expression.LISTENING)

        # Brain state
        if brain.is_thinking and not speaker.is_speaking:
            face.set_expression(Expression.THINKING)
        elif speaker.is_speaking:
            face.set_expression(Expression.SPEAKING)

        # Update
        face.update(dt)
        for sp in sparkles:
            sp.update(dt)

        # Draw
        internal_surf.fill(COLOR_BG)
        for sp in sparkles:
            sp.draw(internal_surf)
        face.draw(internal_surf)

        # Audio level bar
        draw_audio_bar(internal_surf, audio.smooth_level, 300, SCREEN_HEIGHT - 28)

        # Voice recognition text display
        if voice_active:
            display_text = voice.get_display_text()
            if display_text:
                font = pygame.font.SysFont("monospace", max(1, int(20 * FONT_SCALE)), bold=True)
                # Truncate if too long
                max_chars = 50
                if len(display_text) > max_chars:
                    display_text = "..." + display_text[-(max_chars - 3):]
                text_surf = font.render(display_text, True, COLOR_IRIS)
                text_rect = text_surf.get_rect(center=(SCREEN_WIDTH // 2, 40))
                internal_surf.blit(text_surf, text_rect)

            # Listening indicator (pulsing dot)
            pulse = 0.5 + 0.5 * math.sin(time.time() * 4)
            dot_alpha = int(80 + 175 * pulse)
            dot_surf = pygame.Surface((12, 12), pygame.SRCALPHA)
            pygame.draw.circle(dot_surf, (255, 60, 60, dot_alpha), (6, 6), 6)
            internal_surf.blit(dot_surf, (SCREEN_WIDTH // 2 - 6, 55))
            font_sm = pygame.font.SysFont("monospace", max(1, int(12 * FONT_SCALE)))
            rec_label = font_sm.render("LISTENING", True, (200, 80, 80))
            internal_surf.blit(rec_label, (SCREEN_WIDTH // 2 + 12, 52))

        # Voice mode indicator (top-right corner, non-overlapping)
        if voice_active:
            font_v = pygame.font.SysFont("monospace", max(1, int(14 * FONT_SCALE)))
            voice_label = font_v.render("🎙️ VOICE ACTIVE", True, (100, 200, 100))
            internal_surf.blit(voice_label, (SCREEN_WIDTH - voice_label.get_width() - 10, 10))

        # Language indicator (top-right, below voice indicator)
        lang_font = pygame.font.SysFont("monospace", max(1, int(14 * FONT_SCALE)))
        lang_label = lang_font.render(f"🌐 {speaker.label}", True, (100, 150, 220))
        lang_y = 10 if not voice_active else 30
        internal_surf.blit(lang_label, (SCREEN_WIDTH - lang_label.get_width() - 10, lang_y))

        # Speaking indicator
        if speaker.is_speaking:
            speak_font = pygame.font.SysFont("monospace", max(1, int(14 * FONT_SCALE)))
            speak_label = speak_font.render("🔊 SPEAKING", True, (255, 200, 50))
            internal_surf.blit(speak_label, (SCREEN_WIDTH - speak_label.get_width() - 10, lang_y + 20))

        # Brain thinking indicator
        if brain.is_thinking:
            think_font = pygame.font.SysFont("monospace", max(1, int(14 * FONT_SCALE)))
            # Animated thinking dots
            dots = "." * (int(time.time() * 3) % 4)
            think_label = think_font.render(f"🧠 THINKING{dots}", True, (200, 150, 255))
            internal_surf.blit(think_label, (SCREEN_WIDTH - think_label.get_width() - 10, lang_y + 40))

        # Brain status indicator (top-left, below expression)
        brain_status_color = (100, 200, 100) if brain.available else (100, 60, 60)
        brain_text = f"🧠 AI: {'ON' if brain.available else 'OFF'}"
        if auto_respond:
            brain_text += " | Auto-respond: ON"
            brain_status_color = (100, 255, 150)
        brain_font = pygame.font.SysFont("monospace", max(1, int(12 * FONT_SCALE)))
        brain_label = brain_font.render(brain_text, True, brain_status_color)
        internal_surf.blit(brain_label, (10, SCREEN_HEIGHT - 50))

        # AI response text display (center, below eyes)
        response_text = brain.get_response_display_text()
        if response_text:
            resp_font = pygame.font.SysFont("monospace", max(1, int(16 * FONT_SCALE)), bold=True)
            max_chars = 60
            if len(response_text) > max_chars:
                response_text = response_text[:max_chars - 3] + "..."
            resp_surf = resp_font.render(response_text, True, (200, 200, 255))
            resp_rect = resp_surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 70))
            internal_surf.blit(resp_surf, resp_rect)

        # Window mode: scale internal surface to window with letterboxing
        if window_mode:
            scale = min(window_w / SCREEN_WIDTH, window_h / SCREEN_HEIGHT)
            scaled_w = max(1, int(SCREEN_WIDTH * scale))
            scaled_h = max(1, int(SCREEN_HEIGHT * scale))
            scaled = pygame.transform.scale(internal_surf, (scaled_w, scaled_h))
            x_off = (window_w - scaled_w) // 2
            y_off = (window_h - scaled_h) // 2
            screen.fill((0, 0, 0))
            screen.blit(scaled, (x_off, y_off))

        pygame.display.flip()

    # Cleanup
    brain.cleanup()
    speaker.cleanup()
    if voice_active:
        voice.stop()
    audio.cleanup()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
