FROM python:3.11-slim

# System dependencies: SDL2 (pygame), PortAudio (pyaudio), ALSA (aplay for TTS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsdl2-2.0-0 \
    portaudio19-dev \
    alsa-utils \
    libasound2 \
    wget \
    unzip \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download Vosk model (small en-us, ~40MB)
RUN wget -q https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -O /tmp/vosk-model.zip \
    && unzip -q /tmp/vosk-model.zip -d /tmp \
    && mv /tmp/vosk-model-small-en-us-0.15 /app/vosk-model \
    && rm /tmp/vosk-model.zip

# Download Piper TTS binary (x86_64)
RUN mkdir -p /app/piper/piper \
    && wget -q https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz -O /tmp/piper.tar.gz \
    && tar -xzf /tmp/piper.tar.gz -C /app/piper/piper/ --strip-components=0 \
    && rm /tmp/piper.tar.gz

# Download Piper voice models (English + Indonesian)
RUN mkdir -p /app/piper-voices \
    && wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx -P /app/piper-voices \
    && wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json -P /app/piper-voices \
    && wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/id/id_ID/news_tts/medium/id_ID-news_tts-medium.onnx -P /app/piper-voices \
    && wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/id/id_ID/news_tts/medium/id_ID-news_tts-medium.onnx.json -P /app/piper-voices

COPY robot_eyes.py .

# Default: windowed demo mode (no hardware needed)
CMD ["python3", "robot_eyes.py", "--window", "--demo"]
