from pathlib import Path
from typing import Literal

from .adapters import TextResultsAsrAdapter
from .models import (
    GigaamV2CtcTriton,
    PyAnnoteVadTriton,
)
from .preprocessors import Resampler
from .triton_client import TritonInferenceConfig, TritonSessionOptions
from .vad import Vad

ModelNames = Literal[
    "gigaam-v2-ctc",
]
ModelTypes = Literal[
    "gigaam-v2-ctc",
]
VadNames = Literal["pyannote"]


class ModelNotSupportedError(ValueError):
    def __init__(self, model: str):
        super().__init__(f"Model '{model}' not supported!")


def load_model(
    model: str | ModelNames | ModelTypes,
    triton_url: str = "localhost:8000",
    triton_model_name: str | None = None,
    triton_model_version: str = "",
    path: str | Path | None = None,
    *,
    cpu_preprocessing: bool = True,
    **triton_kwargs,
) -> TextResultsAsrAdapter:
    model_type: type[GigaamV2CtcTriton]
    match model:
        case "gigaam-v2-ctc":
            model_type = GigaamV2CtcTriton
            if triton_model_name is None:
                triton_model_name = "gigaam-v2-ctc"
        case _:
            raise ModelNotSupportedError(model)

    triton_config = TritonInferenceConfig(
        url=triton_url,
        model_name=triton_model_name,
        model_version=triton_model_version,
        **triton_kwargs,
    )
    
    triton_options = TritonSessionOptions(
        triton_config=triton_config,
        cpu_preprocessing=cpu_preprocessing,
    )

    model_files = {}
    if path:
        path_obj = Path(path)
        if path_obj.is_dir():
            vocab_files = list(path_obj.glob("*vocab*.txt"))
            if vocab_files:
                model_files["vocab"] = vocab_files[0]
            
            config_file = path_obj / "config.json"
            if config_file.exists():
                model_files["config"] = config_file

    return TextResultsAsrAdapter(
        model_type(model_files, triton_options),
        Resampler(),
    )


def load_vad(
    model: VadNames = "pyannote",
    triton_url: str = "localhost:8000",
    triton_model_name: str | None = None,
    triton_model_version: str = "",
    path: str | Path | None = None,
    **triton_kwargs,
) -> Vad:
    model_type: type[PyAnnoteVadTriton]
    match model:
        case "pyannote":
            model_type = PyAnnoteVadTriton
            if triton_model_name is None:
                triton_model_name = "pyannote-vad"
        case _:
            raise ModelNotSupportedError(model)

    triton_config = TritonInferenceConfig(
        url=triton_url,
        model_name=triton_model_name,
        model_version=triton_model_version,
        **triton_kwargs,
    )
    
    triton_options = TritonSessionOptions(
        triton_config=triton_config,
    )

    model_files = {}

    return model_type(model_files, triton_options)
