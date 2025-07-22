from flask import Flask, request, jsonify, send_file
from faster_whisper import WhisperModel
from google import genai
from google.genai import types
import tempfile
import os
import requests
from flask_cors import CORS
import wave
import base64
import subprocess
import logging
from datetime import datetime

app = Flask(__name__)
CORS(app)

# إعداد نظام السجلات
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('voice_app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# إعداد Whisper
model = WhisperModel("base", compute_type="int8")

# إعداد Google Gemini TTS - استخدام متغيرات البيئة
GEMINI_API_KEY = "AIzaSyAHGHJG_jsdk97QlqkmAlmN4uCDbSPC0cE"
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY environment variable not set")
    raise ValueError("Missing GEMINI_API_KEY")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# إعداد ElevenLabs - استخدام متغيرات البيئة
ELEVENLABS_API_KEY ="sk_d9f948149d73eda013af98e7158dd81c3fc0cdf326233691"
if not ELEVENLABS_API_KEY:
    logger.error("ELEVENLABS_API_KEY environment variable not set")
    raise ValueError("Missing ELEVENLABS_API_KEY")

# تكوين الأصوات المختلفة
VOICE_MODELS = {
    "gemini": {
        "name": "Gemini AI",
        "description": "صوت ذكي وواضح من Google"
    },
    "elevenlabs": {
        "name": "ElevenLabs Arabic Voice",
        "description": "صوت عربي طبيعي من ElevenLabs",
        "voice_id": "QRq5hPRAKf5ZhSlTBH6r"
    },
    "gtts": {
        "name": "Google TTS",
        "description": "صوت Google التقليدي"
    }
}

# Middleware لتسجيل جميع الطلبات
@app.before_request
def log_request_info():
    logger.info(f"Request: {request.method} {request.url} - IP: {request.remote_addr}")

@app.after_request
def log_response_info(response):
    logger.info(f"Response: {response.status_code} - {request.method} {request.url}")
    return response

# دالة لحفظ PCM إلى MP3 عبر WAV مؤقت
def pcm_to_mp3(pcm_bytes, temp_wav="temp.wav", mp3_file="out.mp3", channels=1, rate=24000, sample_width=2):
    try:
        if isinstance(pcm_bytes, str):
            pcm_bytes = base64.b64decode(pcm_bytes)
        
        with wave.open(temp_wav, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(rate)
            wf.writeframes(pcm_bytes)

        result = subprocess.run(['ffmpeg', '-y', '-i', temp_wav, mp3_file],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if os.path.exists(temp_wav):
            os.remove(temp_wav)
        
        return result.returncode == 0
    except Exception as e:
        logger.error(f"PCM to MP3 conversion failed: {e}")
        return False

# دالة لتوليد الصوت باستخدام Gemini
def generate_gemini_audio(text):
    try:
        logger.info("Generating audio using Gemini TTS")
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=f"Say in a friendly tone with saudia arabian accent: {text}",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name='kore'
                        )
                    )
                )
            )
        )

        if response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'inline_data') and part.inline_data:
                    audio_data = part.inline_data.data
                    if pcm_to_mp3(audio_data):
                        logger.info("✅ Gemini audio generated successfully")
                        return True
        
        logger.warning("No audio data received from Gemini")
        return False
    except Exception as e:
        logger.error(f"❌ Gemini TTS error: {e}")
        return False

# دالة لتوليد الصوت باستخدام ElevenLabs API المباشر
def generate_elevenlabs_audio(text, voice_id):
    try:
        logger.info("Generating audio using ElevenLabs TTS")
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
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            with open("out.mp3", "wb") as f:
                f.write(response.content)
            logger.info("✅ ElevenLabs audio generated successfully")
            return True
        else:
            logger.error(f"❌ ElevenLabs API error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ ElevenLabs error: {e}")
        return False

# دالة لتوليد الصوت باستخدام gTTS
def generate_gtts_audio(text):
    try:
        logger.info("Generating audio using gTTS")
        from gtts import gTTS
        tts = gTTS(text=text, lang='ar')
        tts.save("out.mp3")
        logger.info("✅ gTTS audio generated successfully")
        return True
    except Exception as e:
        logger.error(f"❌ gTTS error: {e}")
        return False

# دالة لتنظيف الملفات المؤقتة
def cleanup_temp_files():
    temp_files = ['out.wav', 'out.mp3', 'temp.wav']
    for f in temp_files:
        if os.path.exists(f):
            try:
                os.remove(f)
                logger.debug(f"Cleaned up temp file: {f}")
            except Exception as e:
                logger.warning(f"Failed to remove {f}: {e}")

@app.route('/voice-models', methods=['GET'])
def get_voice_models():
    """إرجاع قائمة بالنماذج الصوتية المتاحة"""
    logger.info("Voice models requested")
    return jsonify({
        "models": VOICE_MODELS,
        "default": "gemini"
    })

@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    start_time = datetime.now()
    logger.info("Starting transcription process")
    
    # تنظيف الملفات السابقة
    cleanup_temp_files()

    if 'audio' not in request.files:
        logger.warning("No audio file in request")
        return jsonify({'error': 'No audio file uploaded'}), 400

    # الحصول على النموذج الصوتي المختار
    voice_model = request.form.get('voice_model', 'gemini')
    if voice_model not in VOICE_MODELS:
        logger.warning(f"Invalid voice model requested: {voice_model}, using default")
        voice_model = 'gemini'

    logger.info(f"Using voice model: {voice_model}")

    # تفريغ الصوت
    file = request.files['audio']
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        file.save(tmp.name)
        try:
            logger.info("Starting Whisper transcription")
            segments, _ = model.transcribe(tmp.name)
            text = " ".join([seg.text.strip() for seg in segments])
            logger.info(f"Transcription completed: {len(text)} characters")
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return jsonify({'error': 'Transcription failed'}), 500
        finally:
            os.remove(tmp.name)

    # إرسال النص إلى n8n
    webhook_url = "https://n8n.ai.oofoq.com/webhook/from-whisper"
    try:
        logger.info("Sending request to n8n webhook")
        res = requests.post(webhook_url, json={"text": text}, timeout=30)
        n8n_response = res.json()
        output_text = (
            n8n_response.get("output") or 
            n8n_response.get("response") or 
            n8n_response.get("message") or 
            str(n8n_response)
        )
        logger.info("Successfully received response from n8n")
    except Exception as e:
        logger.error(f"⚠️ Failed to send to n8n: {e}")
        output_text = "عذرًا، حدث خطأ أثناء الاتصال بالمساعد."

    # توليد الصوت حسب النموذج المختار
    audio_generated = False
    
    if voice_model == "gemini":
        audio_generated = generate_gemini_audio(output_text)
    elif voice_model == "elevenlabs":
        voice_config = VOICE_MODELS[voice_model]
        audio_generated = generate_elevenlabs_audio(output_text, voice_config["voice_id"])
    elif voice_model == "gtts":
        audio_generated = generate_gtts_audio(output_text)
    
    # fallback إلى gTTS في حالة الفشل
    if not audio_generated:
        logger.warning("⚠️ Primary TTS failed, falling back to gTTS")
        audio_generated = generate_gtts_audio(output_text)

    processing_time = (datetime.now() - start_time).total_seconds()
    logger.info(f"Transcription process completed in {processing_time:.2f} seconds")

    return jsonify({
        "transcription": text,
        "n8n_reply": output_text,
        "audio_ready": audio_generated,
        "audio_url": "/audio",
        "voice_model_used": voice_model,
        "voice_model_name": VOICE_MODELS[voice_model]["name"],
        "processing_time": processing_time
    })

@app.route('/audio')
def get_audio():
    if os.path.exists('out.mp3'):
        logger.info("Serving audio file")
        return send_file('out.mp3', mimetype='audio/mp3')
    else:
        logger.warning("Audio file not found")
        return jsonify({'error': 'Audio file not found'}), 404

@app.route('/test-voice/<voice_model>')
def test_voice(voice_model):
    """اختبار صوت معين"""
    logger.info(f"Testing voice model: {voice_model}")
    
    if voice_model not in VOICE_MODELS:
        logger.warning(f"Invalid voice model for testing: {voice_model}")
        return jsonify({'error': 'Invalid voice model'}), 400
    
    test_text = "مرحباً، هذا اختبار للصوت. كيف يبدو؟"
    
    # تنظيف الملفات السابقة
    cleanup_temp_files()
    
    audio_generated = False
    
    if voice_model == "gemini":
        audio_generated = generate_gemini_audio(test_text)
    elif voice_model == "elevenlabs":
        voice_config = VOICE_MODELS[voice_model]
        audio_generated = generate_elevenlabs_audio(test_text, voice_config["voice_id"])
    elif voice_model == "gtts":
        audio_generated = generate_gtts_audio(test_text)
    
    if not audio_generated:
        logger.warning("Primary voice test failed, using gTTS fallback")
        audio_generated = generate_gtts_audio(test_text)
    
    return jsonify({
        "test_text": test_text,
        "audio_ready": audio_generated,
        "audio_url": "/audio",
        "voice_model": voice_model
    })

@app.route('/health')
def health():
    logger.debug("Health check requested")
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'voice_models': list(VOICE_MODELS.keys())
    })

# معالج الأخطاء العام
@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(404)
def not_found(error):
    logger.warning(f"404 error: {request.url}")
    return jsonify({'error': 'Not found'}), 404

if __name__ == '__main__':
    logger.info("Starting Voice Processing Server")
    app.run(debug=False, host='0.0.0.0', port=5005)
