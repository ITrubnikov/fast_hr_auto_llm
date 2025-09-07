import argparse
import pathlib
from importlib.metadata import version
from typing import get_args

import onnx_asr
from onnx_asr.loader import ModelNames, ModelTypes, VadNames


def run() -> None:
    parser = argparse.ArgumentParser(prog="onnx_asr", description="Automatic Speech Recognition in Python using Triton Inference Server.")
    parser.add_argument(
        "model",
        help=f"Model name or type {(*get_args(ModelNames), *get_args(ModelTypes))}",
    )
    parser.add_argument(
        "filename",
        help="Path to wav file (only PCM_U8, PCM_16, PCM_24 and PCM_32 formats are supported).",
        nargs="+",
    )
    parser.add_argument("-p", "--model_path", type=pathlib.Path, help="Path to directory with model files")
    parser.add_argument("--vad", help="Use VAD model", choices=get_args(VadNames))
    parser.add_argument("--triton_url", default="localhost:8000", help="Triton server URL")
    parser.add_argument("--triton_model_name", help="Model name in Triton repository")
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('onnx_asr')}")
    args = parser.parse_args()

    model = onnx_asr.load_model(
        args.model,
        triton_url=args.triton_url,
        triton_model_name=args.triton_model_name,
        path=args.model_path,
    )
    if args.vad:
        vad = onnx_asr.load_vad(args.vad, triton_url=args.triton_url)
        for segment in model.with_vad(vad, batch_size=1).recognize(args.filename):
            for res in segment:
                print(f"[{res.start:5.1f}, {res.end:5.1f}]: {res.text}")
            print()
    else:
        for text in model.recognize(args.filename):
            print(text)
