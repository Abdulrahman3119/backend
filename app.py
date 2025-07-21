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
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs

app = Flask(__name__)
CORS(app)

# إعداد Whisper
model = WhisperModel("base", compute_type="int8")

# إعداد Google Gemini TTS
GEMINI_API_KEY = "AIzaSyAHGHJG_jsdk97QlqkmAlmN4uCDbSPC0cE"
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# إعداد ElevenLabs
ELEVENLABS_API_KEY = "sk_d9f948149d73eda013af98e7158dd81c3fc0cdf326233691"  # ضع مفتاح API الخاص بك
elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# تكوين الأصوات المختلفة
VOICE_MODELS = {
    "gemini": {
        "name": "Gemini AI",
        "description": "صوت ذكي وواضح من Google"
    },
    "elevenlabs_adam": {
        "name": "Adam - ElevenLabs", 
        "description": "صوت رجالي دافئ وودود",
        "voice_id": "pNInz6obpgDQGcFmaJgB"  # Adam voice ID
    },
    "elevenlabs_bella": {
        "name": "Bella - ElevenLabs",
        "description": "صوت نسائي عذب ومفهوم", 
        "voice_id": "EXAVITQu4vr4xnSDxMaL"  # Bella voice ID
    },
    "elevenlabs_charlie": {
        "name": "Charlie - ElevenLabs",
        "description": "صوت شبابي حيوي ومرح",
        "voice_id": "IKne3meq5aSn9XLyUdCD"  # Charlie voice ID
    }
}

# دالة لحفظ PCM إلى MP3 عبر WAV مؤقت
def pcm_to_mp3(pcm_bytes, temp_wav="temp.wav", mp3_file="out.mp3", channels=1, rate=24000, sample_width=2):
    if isinstance(pcm_bytes, str):
        pcm_bytes = base64.b64decode(pcm_bytes)
    
    with wave.open(temp_wav, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm_bytes)

    subprocess.run(['ffmpeg', '-y', '-i', temp_wav, mp3_file],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.remove(temp_wav)

# دالة لتوليد الصوت باستخدام Gemini
def generate_gemini_audio(text):
    try:
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
                    pcm_to_mp3(audio_data)
                    print("✅ Gemini audio generated")
                    return True
        return False
    except Exception as e:
        print("❌ Gemini TTS error:", e)
        return False

# دالة لتوليد الصوت باستخدام ElevenLabs
def generate_elevenlabs_audio(text, voice_id):
    try:
        # توليد الصوت
        audio_generator = elevenlabs_client.generate(
            text=text,
            voice=voice_id,
            voice_settings=VoiceSettings(
                stability=0.5,
                similarity_boost=0.75,
                style=0.5,
                use_speaker_boost=True
            ),
            model="eleven_multilingual_v2"  # يدعم العربية
        )
        
        # حفظ الصوت
        with open("out.mp3", "wb") as f:
            for chunk in audio_generator:
                f.write(chunk)
        
        print(f"✅ ElevenLabs audio generated with voice {voice_id}")
        return True
        
    except Exception as e:
        print(f"❌ ElevenLabs error: {e}")
        return False

# دالة fallback لـ gTTS
def generate_gtts_audio(text):
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang='ar')
        tts.save("out.mp3")
        print("✅ gTTS fallback successful")
        return True
    except Exception as e:
        print(f"❌ gTTS fallback error: {e}")
        return False

@app.route('/voice-models', methods=['GET'])
def get_voice_models():
    """إرجاع قائمة بالنماذج الصوتية المتاحة"""
    return jsonify({
        "models": VOICE_MODELS,
        "default": "gemini"
    })

@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    # تنظيف الملفات السابقة
    for f in ['out.wav', 'out.mp3', 'temp.wav']:
        if os.path.exists(f):
            os.remove(f)

    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file uploaded'}), 400

    # الحصول على النموذج الصوتي المختار
    voice_model = request.form.get('voice_model', 'gemini')
    if voice_model not in VOICE_MODELS:
        voice_model = 'gemini'

    # تفريغ الصوت
    file = request.files['audio']
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        file.save(tmp.name)
        try:
            segments, _ = model.transcribe(tmp.name)
            text = " ".join([seg.text.strip() for seg in segments])
        finally:
            os.remove(tmp.name)

    # إرسال النص إلى n8n
    webhook_url = "https://n8n.ai.oofoq.com/webhook/from-whisper"
    try:
        res = requests.post(webhook_url, json={"text": text}, timeout=30)
        n8n_response = res.json()
        output_text = (
            n8n_response.get("output") or 
            n8n_response.get("response") or 
            n8n_response.get("message") or 
            str(n8n_response)
        )
    except Exception as e:
        print("⚠️ Failed to send to n8n:", e)
        output_text = "عذرًا، حدث خطأ أثناء الاتصال بالمساعد."

    # توليد الصوت حسب النموذج المختار
    audio_generated = False
    
    if voice_model == "gemini":
        audio_generated = generate_gemini_audio(output_text)
    
    elif voice_model.startswith("elevenlabs_"):
        voice_config = VOICE_MODELS[voice_model]
        audio_generated = generate_elevenlabs_audio(output_text, voice_config["voice_id"])
    
    # fallback إلى gTTS في حالة الفشل
    if not audio_generated:
        audio_generated = generate_gtts_audio(output_text)

    return jsonify({
        "transcription": text,
        "n8n_reply": output_text,
        "audio_ready": audio_generated,
        "audio_url": "/audio",
        "voice_model_used": voice_model,
        "voice_model_name": VOICE_MODELS[voice_model]["name"]
    })

@app.route('/audio')
def get_audio():
    if os.path.exists('out.mp3'):
        return send_file('out.mp3', mimetype='audio/mp3')
    else:
        return jsonify({'error': 'Audio file not found'}), 404

@app.route('/test-voice/<voice_model>')
def test_voice(voice_model):
    """اختبار صوت معين"""
    if voice_model not in VOICE_MODELS:
        return jsonify({'error': 'Invalid voice model'}), 400
    
    test_text = "مرحباً، هذا اختبار للصوت. كيف يبدو؟"
    
    # تنظيف الملفات السابقة
    for f in ['out.mp3']:
        if os.path.exists(f):
            os.remove(f)
    
    audio_generated = False
    
    if voice_model == "gemini":
        audio_generated = generate_gemini_audio(test_text)
    elif voice_model.startswith("elevenlabs_"):
        voice_config = VOICE_MODELS[voice_model]
        audio_generated = generate_elevenlabs_audio(test_text, voice_config["voice_id"])
    
    if not audio_generated:
        audio_generated = generate_gtts_audio(test_text)
    
    return jsonify({
        "test_text": test_text,
        "audio_ready": audio_generated,
        "audio_url": "/audio",
        "voice_model": voice_model
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5005)
