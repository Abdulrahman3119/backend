from flask import Flask, request, jsonify, send_file
from faster_whisper import WhisperModel
import tempfile
import os
import requests
from flask_cors import CORS
import logging
from datetime import datetime

app = Flask(__name__)
CORS(app)

# إعداد السجلات
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('voice_app.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# إعداد Whisper
model = WhisperModel("base", compute_type="int8")

# إعداد ElevenLabs
ELEVENLABS_API_KEY = "sk_d9f948149d73eda013af98e7158dd81c3fc0cdf326233691"
VOICE_ID = "QRq5hPRAKf5ZhSlTBH6r"  # صوت عربي

if not ELEVENLABS_API_KEY:
    logger.error("ELEVENLABS_API_KEY not set")
    raise ValueError("Missing ELEVENLABS_API_KEY")

def cleanup_temp_files():
    for f in ['out.mp3', 'temp.wav']:
        if os.path.exists(f):
            os.remove(f)

def generate_elevenlabs_audio(text, voice_id=VOICE_ID):
    logger.info("Generating audio using ElevenLabs")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2"
    }
    try:
        res = requests.post(url, headers=headers, json=data, timeout=30)
        if res.status_code == 200:
            with open("out.mp3", "wb") as f:
                f.write(res.content)
            logger.info("✅ Audio saved successfully")
            return True
        else:
            logger.error(f"❌ ElevenLabs error: {res.status_code} - {res.text}")
            return False
    except Exception as e:
        logger.error(f"❌ ElevenLabs Exception: {e}")
        return False

@app.route('/transcribe', methods=['POST'])
def transcribe():
    cleanup_temp_files()
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file uploaded"}), 400

    audio_file = request.files['audio']
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        audio_file.save(tmp.name)
        try:
            segments, _ = model.transcribe(tmp.name)
            text = " ".join([seg.text.strip() for seg in segments])
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return jsonify({'error': 'Transcription failed'}), 500
        finally:
            os.remove(tmp.name)

    # إنشاء الصوت باستخدام ElevenLabs
    audio_ready = generate_elevenlabs_audio(text)

    return jsonify({
        "transcription": text,
        "audio_ready": audio_ready,
        "audio_url": "/audio"
    })

@app.route('/audio')
def audio():
    if os.path.exists("out.mp3"):
        return send_file("out.mp3", mimetype="audio/mp3")
    return jsonify({"error": "Audio not found"}), 404

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

if __name__ == '__main__':
    logger.info("🚀 Starting Voice Server (ElevenLabs only)")
    app.run(host="0.0.0.0", port=5005)
