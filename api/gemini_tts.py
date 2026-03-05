import base64
import requests
from pathlib import Path


TTS_URL = "https://texttospeech.googleapis.com/v1beta1/text:synthesize"

VOICES = [
    "Kore", "Charon", "Callirrhoe", "Aoede", "Puck", "Fenrir", "Leda",
    "Orus", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat", "Erinome",
    "Laomedeia", "Algenib", "Rasalgethi", "Algieba", "Despina", "Umbriel",
    "Alathfar", "Achernar", "Alnilam", "Iapetus",
]


class GeminiTTSClient:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-tts"):
        self.api_key = api_key
        self.model = model

    def synthesize(self, text: str, voice: str, output_path: str, language_code: str = "th-TH") -> str:
        """
        Call Google TTS API and save MP3 to output_path.
        Returns the output_path on success.
        Raises on failure.
        """
        payload = {
            "model": self.model,
            "input": {"text": text},
            "voice": {
                "languageCode": language_code,
                "name": voice,
            },
            "audioConfig": {
                "audioEncoding": "MP3",
            },
        }
        resp = requests.post(
            TTS_URL,
            params={"key": self.api_key},
            json=payload,
            timeout=60,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"TTS API error {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        audio_b64 = data.get("audioContent", "")
        if not audio_b64:
            raise RuntimeError("TTS API returned empty audioContent")

        audio_bytes = base64.b64decode(audio_b64)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(audio_bytes)

        return output_path
