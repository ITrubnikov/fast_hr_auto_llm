# Gradio UI for testing ASR (GigaAM via Triton) and TTS (Vosk-TTS API)
import os
import sys
import json
import time
from typing import Optional, Tuple, Dict, Any, List

import requests
import numpy as np
import gradio as gr
import json as _json

# Make onnx_asr available by adding mounted source path
ONNX_ASR_SRC = os.environ.get("ONNX_ASR_SRC", "/app/onnx_asr_src")
if os.path.isdir(ONNX_ASR_SRC):
    if ONNX_ASR_SRC not in sys.path:
        sys.path.insert(0, ONNX_ASR_SRC)

import onnx_asr  # type: ignore

ASR_TRITON_URL = os.environ.get("ASR_TRITON_URL", "asr-triton:8000")
TTS_TRITON_URL = os.environ.get("TTS_TRITON_URL", "localhost:8000")
TTS_API_URL = os.environ.get("TTS_API_URL", "http://tts-api:8080")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Lazy singletons
_asr_model = None
_asr_model_with_vad = None
_voices: List[str] = []


def fetch_status() -> Dict[str, Any]:
    status: Dict[str, Any] = {"services": {}, "models": {}}
    # ASR Triton health
    try:
        r = requests.get(f"http://{ASR_TRITON_URL}/v2/health/ready", timeout=3)
        status["services"]["asr_triton"] = r.status_code
    except Exception as e:
        status["services"]["asr_triton"] = f"error: {e}"
    # TTS API health
    try:
        r = requests.get(f"{TTS_API_URL}/health", timeout=3)
        status["services"]["tts_api"] = r.status_code
        status["tts_health"] = r.json()
    except Exception as e:
        status["services"]["tts_api"] = f"error: {e}"
    # ASR models list
    try:
        r = requests.get(f"http://{ASR_TRITON_URL}/v2/repository/index", timeout=5)
        status["models"]["asr"] = r.json()
    except Exception:
        status["models"]["asr"] = []
    return status


def status_markdown() -> str:
    s = fetch_status()
    lines = ["## Статус сервисов",
             f"- ASR Triton: {s['services'].get('asr_triton')}",
             f"- TTS API: {s['services'].get('tts_api')}"]
    lines.append("\n## Модели")
    asr_models = s.get("models", {}).get("asr", [])
    if isinstance(asr_models, list) and asr_models:
        lines.append("- ASR:")
        for m in asr_models:
            name = m.get('name') if isinstance(m, dict) else str(m)
            state = m.get('state') if isinstance(m, dict) else ''
            lines.append(f"  - {name} {f'({state})' if state else ''}")
    # TTS API health details
    if s.get("tts_health"):
        details = s["tts_health"].get("details", {})
        lines.append("\n## TTS API детали")
        lines.append(f"- initialized: {details.get('initialized')}")
        lines.append(f"- model_loaded: {details.get('model_loaded')}")
        lines.append(f"- synth_ready: {details.get('synth_ready')}")
    return "\n".join(lines)


def ensure_asr(vad: bool = False):
    global _asr_model, _asr_model_with_vad
    if _asr_model is None:
        _asr_model = onnx_asr.load_model(
            model="gigaam-v2-ctc",
            triton_url=ASR_TRITON_URL,
            cpu_preprocessing=True,
            path="/app/onnx_asr_vocab",  # vocab
        )
    if vad and _asr_model_with_vad is None:
        vad_model = onnx_asr.load_vad("pyannote", triton_url=ASR_TRITON_URL)
        _asr_model_with_vad = _asr_model.with_vad(vad_model)


def asr_transcribe(audio: Tuple[int, np.ndarray], use_vad: bool = False) -> str:
    if audio is None:
        return ""
    sr, wav = audio
    if wav is None or len(wav) == 0:
        return ""
    # Приводим к моно и float32
    if hasattr(wav, "ndim") and wav.ndim == 2:
        wav = wav.mean(axis=1)
    if wav.dtype != np.float32:
        wav = wav.astype(np.float32)
    # Минимальная длительность и нормализация уровня
    duration = len(wav) / float(sr)
    if duration < 0.5:
        print(f"[ASR] too short audio: {duration:.2f}s")
    peak = float(np.max(np.abs(wav))) if len(wav) else 0.0
    if peak > 0:
        wav = (wav / peak * 0.95).astype(np.float32)
    # Быстрый пинг ASR Triton
    try:
        r = requests.get(f"http://{ASR_TRITON_URL}/v2/health/ready", timeout=2)
        if r.status_code != 200:
            msg = f"ASR error: Triton not ready ({r.status_code})"
            print(msg)
            return msg
    except Exception as e:
        msg = f"ASR error: Triton unreachable ({e})"
        print(msg)
        return msg
    ensure_asr(vad=use_vad)
    model = _asr_model_with_vad if use_vad and _asr_model_with_vad is not None else _asr_model
    try:
        if model is _asr_model:
            text = model.recognize(wav.astype(np.float32), sample_rate=sr)
            print(f"[ASR] sr={sr} len={len(wav)} -> '{text}'")
            return text or ""
        else:
            segments = list(model.recognize(wav.astype(np.float32), sample_rate=sr))
            text = " ".join((getattr(seg, 'text', '') or '').strip() for seg in segments).strip()
            print(f"[ASR-VAD] segs={len(segments)} -> '{text}'")
            # Fallback без VAD, если пусто
            if not text:
                text = _asr_model.recognize(wav.astype(np.float32), sample_rate=sr)
                print(f"[ASR-FB] -> '{text}'")
            return text or ""
    except Exception as e:
        return f"ASR error: {e}"


def fetch_voices() -> List[str]:
    global _voices
    if _voices:
        return _voices
    try:
        r = requests.get(f"{TTS_API_URL}/voices", timeout=5)
        data = r.json()
        _voices = list(data.keys())
    except Exception:
        _voices = ["irina", "elena", "pavel"]
    return _voices


def tts_synthesize(text: str, voice: str) -> Optional[Tuple[int, np.ndarray]]:
    if not text or not text.strip():
        return None
    try:
        payload = {"text": text, "voice": voice}
        r = requests.post(f"{TTS_API_URL}/synthesize", json=payload, timeout=60)
        r.raise_for_status()
        audio_url = r.json().get("audio_url")
        if not audio_url:
            return None
        au = f"{TTS_API_URL}{audio_url}"
        a = requests.get(au, timeout=60)
        a.raise_for_status()
        import soundfile as sf
        import io
        data, sr = sf.read(io.BytesIO(a.content), dtype="float32")
        if data.ndim == 2:
            data = data.mean(axis=1)
        return sr, data
    except Exception as e:
        gr.Warning(f"TTS error: {e}")
        return None


def build_interface() -> gr.Blocks:
    with gr.Blocks(title="ASR/TTS Test UI") as demo:
        gr.Markdown("# Тест ASR/TTS\nПроверка статусов, микрофон → ASR, текст → TTS")
        with gr.Tab("Статус"):
            status_md = gr.Markdown(value=status_markdown())
            refresh_btn = gr.Button("Обновить статус")
            refresh_btn.click(fn=status_markdown, inputs=None, outputs=status_md)
        with gr.Tab("ASR (Распознавание)"):
            audio_in = gr.Audio(sources=["microphone", "upload"], type="numpy", label="Микрофон/Файл")
            use_vad = gr.Checkbox(value=False, label="Использовать VAD")
            run_asr = gr.Button("Распознать")
            asr_text = gr.Textbox(label="Результат", lines=4)
            run_asr.click(fn=asr_transcribe, inputs=[audio_in, use_vad], outputs=asr_text)
        with gr.Tab("TTS (Синтез)"):
            text_in = gr.Textbox(label="Текст", lines=4)
            voices = fetch_voices()
            voice_dd = gr.Dropdown(choices=voices, value=(voices[0] if voices else None), label="Голос")
            run_tts = gr.Button("Озвучить")
            audio_out = gr.Audio(label="Аудио", autoplay=True)
            run_tts.click(fn=tts_synthesize, inputs=[text_in, voice_dd], outputs=audio_out)

        with gr.Tab("Диалог (ASR → OpenRouter → TTS)"):
            diar_audio = gr.Audio(sources=["microphone", "upload"], type="numpy", label="Микрофон/Файл")
            sys_prompt = gr.Textbox(label="System prompt", value="Вы ассистент.")
            model_id = gr.Dropdown(
                choices=["anthropic/claude-3.7-sonnet", "anthropic/claude-3.5-sonnet", "google/gemini-1.5-pro"],
                value="anthropic/claude-3.5-sonnet",
                label="Модель OpenRouter"
            )
            voice2 = gr.Dropdown(choices=voices, value=(voices[0] if voices else None), label="Голос TTS")
            run_dialog = gr.Button("Сказать и получить ответ")
            asr_text_box = gr.Textbox(label="ASR текст", lines=3)
            llm_text_box = gr.Textbox(label="Ответ модели", lines=5)
            tts_audio_box = gr.Audio(label="Озвучка", autoplay=True)

            def dialog_pipeline(audio: tuple[int, np.ndarray], system: str, model: str, voice: str):
                # 1) ASR
                text = asr_transcribe(audio, use_vad=False)
                if text.startswith("ASR error"):
                    return text, "", None
                # 2) OpenRouter
                if not OPENROUTER_API_KEY:
                    return text, "Ошибка: нет OPENROUTER_API_KEY", None
                headers = {
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system or "Вы ассистент."},
                        {"role": "user", "content": text},
                    ],
                }
                try:
                    rr = requests.post(OPENROUTER_URL, headers=headers, data=_json.dumps(payload), timeout=60)
                    rr.raise_for_status()
                    data = rr.json()
                    reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                except Exception as e:
                    reply = f"LLM error: {e}"
                # 3) TTS
                audio_t = tts_synthesize(reply, voice)
                return text, reply, audio_t

            # Запуск по кнопке
            run_dialog.click(fn=dialog_pipeline, inputs=[diar_audio, sys_prompt, model_id, voice2], outputs=[asr_text_box, llm_text_box, tts_audio_box])
    return demo


def main():
    demo = build_interface()
    demo.queue(max_size=16)
    demo.launch(server_name="0.0.0.0", server_port=7860, show_api=False, share=False)


if __name__ == "__main__":
    main()
