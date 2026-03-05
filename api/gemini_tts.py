import base64
import struct
import requests
from pathlib import Path


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

VOICES = [
    "Kore", "Charon", "Callirrhoe", "Aoede", "Puck", "Fenrir", "Leda",
    "Orus", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat", "Erinome",
    "Laomedeia", "Algenib", "Rasalgethi", "Algieba", "Despina", "Umbriel",
    "Alathfar", "Achernar", "Alnilam", "Iapetus",
]

# Actual model IDs on generativelanguage.googleapis.com
MODELS = [
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
]

# Remap legacy / shorthand model names to actual API model IDs
_MODEL_ALIASES = {
    "gemini-2.5-flash-tts": "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-tts": "gemini-2.5-pro-preview-tts",
    "gemini-2.5-flash-lite-preview-tts": "gemini-2.5-flash-preview-tts",
}


class GeminiTTSClient:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-preview-tts"):
        self.api_key = api_key
        self.model = _MODEL_ALIASES.get(model, model)

    def synthesize(self, text: str, voice: str, output_path: str,
                   retries: int = 3) -> str:
        """
        Call Gemini TTS via generativelanguage.googleapis.com and save audio to output_path.
        Returns output_path on success. Raises on failure.
        Retries up to `retries` times on timeout or 5xx errors.
        """
        import time
        url = GEMINI_API_URL.format(model=self.model)
        payload = {
            "contents": [
                {"parts": [{"text": text}]}
            ],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice,
                        }
                    }
                },
            },
        }
        last_err = None
        for attempt in range(1, retries + 1):
            try:
                resp = requests.post(
                    url,
                    params={"key": self.api_key},
                    json=payload,
                    timeout=300,  # 5 minutes — long scripts can take a while
                )
                if resp.status_code == 200:
                    break
                # Retry on server errors, raise immediately on client errors
                if resp.status_code < 500:
                    raise RuntimeError(f"TTS API error {resp.status_code}: {resp.text[:400]}")
                last_err = RuntimeError(f"TTS API error {resp.status_code}: {resp.text[:400]}")
            except requests.exceptions.Timeout as e:
                last_err = RuntimeError(f"TTS timeout (attempt {attempt}/{retries}): {e}")
            except requests.exceptions.RequestException as e:
                last_err = RuntimeError(f"TTS request failed (attempt {attempt}/{retries}): {e}")

            if attempt < retries:
                time.sleep(5 * attempt)  # wait 5s, 10s before retrying
        else:
            raise last_err

        data = resp.json()
        try:
            inline = data["candidates"][0]["content"]["parts"][0]["inlineData"]
            audio_b64 = inline["data"]
            mime_type = inline.get("mimeType", "audio/wav")
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Unexpected TTS response shape: {e}\n{data}")

        audio_bytes = base64.b64decode(audio_b64)

        # Gemini TTS returns raw PCM (audio/pcm or audio/L16) without WAV headers.
        # Wrap it in a proper WAV container so ffprobe/ffmpeg can read it.
        if "pcm" in mime_type.lower() or "l16" in mime_type.lower() or mime_type == "audio/wav":
            # Parse sample rate from mime (e.g. audio/pcm;rate=24000), default 24000
            sample_rate = 24000
            for part in mime_type.split(";"):
                part = part.strip()
                if part.startswith("rate="):
                    try:
                        sample_rate = int(part.split("=")[1])
                    except ValueError:
                        pass
            audio_bytes = _pcm_to_wav(audio_bytes, sample_rate=sample_rate)
            out_path = Path(output_path).with_suffix(".wav")
        elif "mp3" in mime_type.lower():
            out_path = Path(output_path).with_suffix(".mp3")
        else:
            out_path = Path(output_path).with_suffix(".wav")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(audio_bytes)
        return str(out_path)


def _pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000, channels: int = 1, bit_depth: int = 16) -> bytes:
    """Wrap raw PCM bytes in a RIFF WAV container."""
    byte_rate = sample_rate * channels * bit_depth // 8
    block_align = channels * bit_depth // 8
    data_size = len(pcm_data)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,           # PCM chunk size
        1,            # PCM format
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bit_depth,
        b"data",
        data_size,
    )
    return header + pcm_data
