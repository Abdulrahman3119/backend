from flask import Flask, request, jsonify, send_file
from faster_whisper import WhisperModel
import google.generativeai as genai
from google.generativeai.types import GenerateContentConfig, SpeechConfig, VoiceConfig, PrebuiltVoiceConfig
import tempfile
import os
import requests
from flask_cors import CORS
import wave
import base64
import subprocess

# إعداد Flask
app = Flask(__name__)
CORS(app)

# إعداد نموذج Whisper
model = WhisperModel("base")

# إعداد مفتاح Google Generative AI
GOOGLE_API_KEY = "AIzaSyAHGHJG_jsdk97QlqkmAlmN4uCDbSPC0cE"
genai.configure(api_key=GOOGLE_API_KEY)

# المسار المؤقت لحفظ الرد الصوتي
AUDIO_OUTPUT_PATH = "output.mp3"

@app.route('/process', methods=['POST'])
def process_audio():
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file found"}), 400

    audio_file = request.files['audio']
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
        audio_file.save(temp_audio.name)
        temp_audio_path = temp_audio.name

    try:
        segments, _ = model.transcribe(temp_audio_path)
        transcription = ""
        for segment in segments:
            transcription += segment.text + " "

        prompt = transcription.strip()

        # إعداد إعدادات الصوت من Gemini
        config = GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=SpeechConfig(
                voice_config=VoiceConfig(
                    prebuilt_voice_config=PrebuiltVoiceConfig(
                        voice_name='kore'
                    )
                )
            )
        )

        model = genai.GenerativeModel("models/chat-bison-001")
        response = model.generate_content(prompt, generation_config=config)

        # حفظ الرد الصوتي
        audio_binary = response.candidates[0].audio
        with open(AUDIO_OUTPUT_PATH, "wb") as f:
            f.write(audio_binary)

        return send_file(AUDIO_OUTPUT_PATH, mimetype="audio/mpeg")

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        os.remove(temp_audio_path)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
