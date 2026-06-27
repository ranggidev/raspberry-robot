FROM python:3.11-slim

# System dependencies: SDL2 (pygame), PortAudio (pyaudio), ALSA (aplay), ffmpeg (whisper), Mesa (display)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsdl2-2.0-0 \
    portaudio19-dev \
    alsa-utils \
    libasound2 \
    libasound2-plugins \
    ffmpeg \
    mesa-utils \
    libgl1-mesa-dri \
    wget \
    unzip \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# ALSA config: route default device to real hardware with auto format conversion
RUN printf 'pcm.!default {\n    type plug\n    slave { pcm "plughw:0,0" }\n}\nctl.!default {\n    type hw\n    card 0\n}\n' > /etc/asound.conf

WORKDIR /app

# Python dependencies (PyTorch CPU-only for Whisper)
COPY requirements.txt .
RUN pip install --no-cache-dir torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Pre-download Whisper small model (~460MB)
RUN python3 -c "import whisper; whisper.load_model('small')"

# Download Piper TTS binary (x86_64)
RUN mkdir -p /app/piper/piper \
    && wget -q https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz -O /tmp/piper.tar.gz \
    && tar -xzf /tmp/piper.tar.gz -C /app/piper/piper/ --strip-components=1 \
    && chmod +x /app/piper/piper/piper \
    && rm /tmp/piper.tar.gz

# Download Piper voice models (English + Indonesian)
RUN mkdir -p /app/piper-voices \
    && wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx -P /app/piper-voices \
    && wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json -P /app/piper-voices \
    && wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/id/id_ID/news_tts/medium/id_ID-news_tts-medium.onnx -P /app/piper-voices \
    && wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/id/id_ID/news_tts/medium/id_ID-news_tts-medium.onnx.json -P /app/piper-voices

COPY robot_eyes.py .

# Default: windowed mode with real microphone
CMD ["python3", "robot_eyes.py", "--window", "--mic"]
