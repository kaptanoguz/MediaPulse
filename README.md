# MediaPulse - Smart Media Archivist

MediaPulse allows you to browse, search, and watch your local video collection with a premium, Netflix-like interface. It features AI integration, automatic thumbnail generation, and multi-language support.

## Key Features

*   **Premium UI**: Stunning dark mode interface with glassmorphism effects.
*   **Media Scanning**: Automatically scans your folders for videos (MP4, MKV, AVI, etc.).
*   **AI Partner**: Chat with Grok-3 (via x.ai) about your collection or what you're watching.
*   **Smart Thumbnails**: Real-time thumbnail generation using FFmpeg.
*   **Shuffle Play**: Discovery mode to randomly pick your next watch.
*   **Favorites & Views**: Track your most-watched videos and save your favorites.
*   **Multi-Language**: Full support for Turkish and English.
*   **Settings UI**: Configure your media path and API keys directly from the browser.

## Installation

### Dependencies

Ensure you have `ffmpeg` and `vlc` installed on your system:

```bash
sudo apt update
sudo apt install ffmpeg vlc python3-venv python3-full
```

### Setup

1.  **Clone the project**:
    ```bash
    git clone https://github.com/yourusername/MediaPulse.git
    cd MediaPulse
    ```

2.  **Create a virtual environment**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install requirements**:
    ```bash
    pip install flask openai
    ```

4.  **Run the app**:
    ```bash
    python app.py
    ```

5.  **Configure**: Open `http://localhost:5000` in your browser, click the **Settings (Gear icon)**, and set your Video Path and API Key.

## Security & Privacy

*   **Private by Design**: Your video paths and API keys are stored locally in `static/settings.json`.
*   **No Cloud Storage**: MediaPulse does not upload your metadata or file names to any cloud server (except for the optional Grok AI chat).
*   **GitHub Ready**: No sensitive information is hardcoded in the source code.

## Upcoming Releases

*   `.deb` Installer for Debian/Ubuntu/Mint.
*   `.AppImage` for universal Linux compatibility.
*   Electron-based desktop application.

---

*Developed for the modern archivist.*
