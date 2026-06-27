# 🤖 AI Robot Eyes — Voice Assistant

Robot AI dengan mata lucu animasi yang bisa mendengar (STT), berbicara (TTS), dan merespons suara user via LLM (Ollama). Berjalan di **Raspberry Pi 4** dan **Ubuntu/Linux** via Docker.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%204%20%7C%20Ubuntu-red)
![Docker](https://img.shields.io/badge/Docker-Ready-blue)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Fitur

### 👁️ Mata Animasi
- **7 Ekspresi**: Neutral, Happy, Thinking, Surprised, Sleepy, Listening, Speaking
- **Blink otomatis** dengan timing random
- **Look around** — mata mengikuti target secara smooth
- **Sparkle particles** — efek ambient background
- **Delta-time animation** — konsisten di framerate apapun

### 🎤 Speech-to-Text (Vosk)
- Offline speech recognition
- Background thread — tidak blocking animasi
- Real-time partial & final text display
- Shared mic stream (tidak konflik hardware)

### 🔊 Text-to-Speech (Piper)
- Offline neural TTS — suara natural
- **2 Bahasa**: English (`en_US-lessac-medium`) & Indonesia (`id_ID-news_tts-medium`)
- Language toggle (L key)
- Mouth animation synced saat berbicara

### 🗣️ Mouth Animation
- Mulut terbuka/tutup sinkron dengan level audio
- Variasi bentuk elliptical
- Tongue hint saat mulut terbuka lebar
- Berfungsi untuk mic input dan TTS output

### 🧠 AI Brain (Ollama)
- Local LLM via Ollama — tidak perlu API key
- Default model: `gemma3:1b` (configurable)
- Background thread — tidak blocking animasi
- Auto-respond pipeline: STT → LLM → TTS

---

## 🛠️ Hardware yang Dibutuhkan

| Komponen | Status | Keterangan |
|----------|--------|------------|
| Raspberry Pi 4 (4GB+) | ✅ Wajib | OS: Raspberry Pi OS (Debian) |
| Monitor HDMI | ✅ Wajib | Untuk tampilan mata robot |
| USB Microphone | ⚠️ Untuk STT | ~30-50rb, untuk voice recognition |
| Speaker / Headphone | ⚠️ Untuk TTS | Untuk mendengar suara robot |
| Keyboard | ✅ Wajib | Untuk kontrol |
| Internet | ⚠️ Untuk setup | Hanya saat install dependencies |

---

## 📦 Setup

### 1. Clone Repository

```bash
cd /home/pi
git clone <your-repo-url> Ai
cd Ai
```

### 2. Install Python Dependencies

```bash
# System dependencies
sudo apt-get update
sudo apt-get install -y portaudio19-dev python3-pyaudio

# Python packages
pip3 install --break-system-packages vosk pyaudio
```

### 3. Download Vosk Model (STT)

```bash
cd /home/pi/Ai
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -O vosk-model.zip
unzip vosk-model.zip
mv vosk-model-small-en-us-0.15 vosk-model
rm vosk-model.zip
```

### 4. Setup Piper TTS

```bash
cd /home/pi/Ai

# Download Piper binary
mkdir -p piper
wget https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz -O piper.tar.gz
tar -xzf piper.tar.gz -C piper/ --strip-components=0
rm piper.tar.gz

# Download voice models
mkdir -p piper-voices
cd piper-voices

# English voice
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json

# Indonesian voice
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/id/id_ID/news_tts/medium/id_ID-news_tts-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/id/id_ID/news_tts/medium/id_ID-news_tts-medium.onnx.json
```

### 5. Jalankan!

```bash
cd /home/pi/Ai
python3 robot_eyes.py
```

---

## 🐳 Setup Docker (Ubuntu / Linux)

### Prerequisites
- Docker & Docker Compose
- Ollama (install dari [ollama.ai](https://ollama.ai))

### 1. Clone & Pull Model

```bash
git clone <your-repo-url> raspberry-robot
cd raspberry-robot
ollama pull gemma3:1b
```

### 2. Jalankan!

```bash
./start.sh
```

Atau manual:
```bash
xhost +local:docker
docker compose up
```

### Docker Commands

```bash
docker compose up          # Jalankan (foreground)
docker compose up -d       # Jalankan (background)
docker compose down        # Stop container
docker compose build       # Rebuild image
docker compose logs -f     # Lihat logs
```

### Environment Variables

| Variable | Default | Keterangan |
|----------|---------|------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL Ollama server |
| `OLLAMA_MODEL` | `gemma3:1b` | Model LLM yang digunakan |

### Ganti Model LLM

```bash
# Pull model lain
ollama pull llama3.2

# Edit docker-compose.yml
environment:
  - OLLAMA_MODEL=llama3.2
```

---

## 🎮 Kontrol

| Tombol | Fungsi |
|--------|--------|
| `1` | Neutral expression |
| `2` | Happy expression |
| `3` | Thinking expression |
| `4` | Surprised expression |
| `5` | Sleepy expression |
| `6` | Listening expression |
| `V` | Toggle voice recognition (STT) |
| `G` | Toggle auto-respond (STT → LLM → TTS) |
| `T` | Test TTS — speak demo phrase |
| `L` | Toggle bahasa TTS (EN ↔ ID) |
| `D` | Toggle demo talking animation |
| `A` | Toggle auto expression |
| `SPACE` | Manual blink |
| `ESC` / `Q` | Quit |

### Command Line Options

```bash
python3 robot_eyes.py                      # Auto-detect mic, fallback ke demo
python3 robot_eyes.py --demo               # Force demo mode (tanpa mic)
python3 robot_eyes.py --mic                # Force real microphone mode
python3 robot_eyes.py --window             # Window mode 250×250
python3 robot_eyes.py --window 320x240     # Window mode custom size
```

---

## 📁 Struktur Project

```
raspberry-robot/
├── robot_eyes.py           # Main script (semua fitur)
├── Dockerfile              # Docker image definition
├── docker-compose.yml      # Docker compose config
├── requirements.txt        # Python dependencies
├── start.sh                # Quick start script
├── .dockerignore           # Docker ignore rules
├── .gitignore              # Git ignore rules
├── README.md               # Dokumentasi ini
├── vosk-model/             # Vosk STT model (download/Docker)
├── piper/                  # Piper TTS binary (download/Docker)
└── piper-voices/           # TTS voice models (download/Docker)
```

> **Note**: Folder `vosk-model/`, `piper/`, dan `piper-voices/` di-exclude dari git. Di Docker, semua didownload otomatis saat build. Untuk Raspberry Pi, download manual sesuai instruktur di atas.

---

## 🏗️ Arsitektur

```
┌─────────────────────────────────────────────────┐
│                   Main Loop (60 FPS)             │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │  Eyes     │  │  Mouth   │  │  Sparkle │      │
│  │ Animation │  │Animation │  │ Particles│      │
│  └─────┬────┘  └────┬─────┘  └──────────┘      │
│        │             │                           │
│  ┌─────┴─────────────┴─────┐                    │
│  │      RobotFace          │                    │
│  │   (Expression State)    │                    │
│  └────────────┬────────────┘                    │
│               │                                 │
│  ┌────────────┴────────────────────────┐        │
│  │          Audio Pipeline             │        │
│  │                                     │        │
│  │  ┌─────────────┐  ┌─────────────┐  │        │
│  │  │ AudioLevel  │  │   Speaker   │  │        │
│  │  │  Detector   │  │  (Piper)    │  │        │
│  │  │  (PyAudio)  │  │  TTS → aplay│  │        │
│  │  └──────┬──────┘  └─────────────┘  │        │
│  │         │                           │        │
│  │  ┌──────┴──────┐  ┌─────────────┐  │        │
│  │  │VoiceRecog.  │  │  Brain      │  │        │
│  │  │  (Vosk)     │  │ (Ollama)    │  │        │
│  │  │ STT thread  │  │ LLM thread  │  │        │
│  │  └─────────────┘  └─────────────┘  │        │
│  └─────────────────────────────────────┘        │
└─────────────────────────────────────────────────┘
```

### Key Design Decisions

- **Single mic stream**: `AudioLevelDetector` membaca mic, lalu feed raw audio ke `VoiceRecognizer` via subscriber callback. Tidak ada dual mic stream yang bisa konflik.
- **Threaded STT, TTS, & LLM**: Vosk, Piper, dan Ollama berjalan di background thread, tidak blocking animasi.
- **Simulated TTS mouth**: Karena Piper output langsung ke `aplay`, level audio di-simulasi untuk drive mulut animation.
- **Delta-time animation**: Semua animasi pakai `dt` (delta time), jadi konsisten di framerate apapun.

---

## 🔧 Troubleshooting

### "pyaudio not installed"
```bash
sudo apt-get install -y portaudio19-dev python3-pyaudio
```

### "Vosk model not found"
```bash
cd /home/pi/Ai
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -O vosk-model.zip
unzip vosk-model.zip && mv vosk-model-small-en-us-0.15 vosk-model && rm vosk-model.zip
```

### "Piper binary not found"
Download Piper binary sesuai instruktur di bagian Setup.

### Tidak ada suara dari TTS
- Cek apakah speaker/headphone tercolok
- Test manual: `aplay /home/pi/Ai/test_tts.wav`
- Cek alsamixer: `alsamixer` → pastikan volume tidak muted

### Animasi lambat
- Pastikan power supply 5V 3A
- Gunakan active cooler/fan untuk Pi 4
- Kurangi jumlah sparkle particles

### Docker: "Cannot open display"
```bash
xhost +local:docker
```

### Docker: "Ollama not reachable"
Pastikan Ollama berjalan di host:
```bash
ollama serve
ollama pull gemma3:1b
```

### Docker: mic tidak terdeteksi
Cek ALSA device di container:
```bash
docker exec robot-eyes arecord -l
```

---

## 📊 Spesifikasi yang Diverifikasi

| Komponen | Status | Detail |
|----------|--------|--------|
| Raspberry Pi 4 Model B | ✅ | 4 core ARM Cortex-A72, 4GB RAM |
| Python 3.11.2 | ✅ | |
| Pygame 2.1.2 | ✅ | Untuk animasi mata |
| PyAudio 0.2.13 | ✅ | Untuk mic input |
| Vosk 0.3.45 | ✅ | STT offline |
| Piper TTS | ✅ | Neural TTS offline |
| HDMI Display | ✅ | 800x480 + 1920x1080 |
| Audio Output | ✅ | Headphone jack + HDMI audio |
| I2C Interface | ✅ | `/dev/i2c-20`, `/dev/i2c-21` |

---

## 📄 License

MIT License

---

## 🙏 Credits

- [Vosk](https://alphacephei.com/vosk/) — Offline speech recognition
- [Piper TTS](https://github.com/rhasspy/piper) — Offline neural text-to-speech
- [Pygame](https://www.pygame.org/) — Graphics and animation
- [Raspberry Pi](https://www.raspberrypi.org/) — Hardware platform
