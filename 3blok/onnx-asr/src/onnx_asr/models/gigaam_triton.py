from pathlib import Path

import numpy as np
import numpy.typing as npt

from onnx_asr.asr import _AsrWithCtcDecoding, _AsrWithDecoding
from onnx_asr.preprocessors import Preprocessor
from onnx_asr.triton_client import TritonClient, TritonSessionOptions
from onnx_asr.utils import is_float32_array


class _GigaamV2Triton(_AsrWithDecoding):
    @staticmethod
    def _get_model_files(quantization: str | None = None) -> dict[str, str]:
        return {"vocab": "v2_vocab.txt"}

    @property
    def _preprocessor_name(self) -> str:
        assert self.config.get("features_size", 64) == 64
        return "gigaam"

    @property
    def _subsampling_factor(self) -> int:
        return self.config.get("subsampling_factor", 4)


class GigaamV2CtcTriton(_AsrWithCtcDecoding, _GigaamV2Triton):
    def __init__(self, model_files: dict[str, Path], triton_options: TritonSessionOptions):
        super().__init__(model_files, triton_options)
        self._triton_client = TritonClient(triton_options.triton_config)

        preprocessor_model_name = f"{self._preprocessor_name}_preprocessor"
        self._preprocessor = Preprocessor(
            model_name=preprocessor_model_name,
            triton_config=triton_options.triton_config,
            cpu_preprocessing=triton_options.cpu_preprocessing
        )

    @staticmethod
    def _get_model_files(quantization: str | None = None) -> dict[str, str]:
        return _GigaamV2Triton._get_model_files(quantization)

    def _encode(
        self, features: npt.NDArray[np.float32], features_lens: npt.NDArray[np.int64]
    ) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.int64]]:
        feature_lengths_reshaped = features_lens.reshape(-1, 1)
        
        inputs = {
            "features": features,
            "feature_lengths": feature_lengths_reshaped,
        }
        outputs = ["log_probs"]
        
        results = self._triton_client.infer(inputs, outputs)
        log_probs = results["log_probs"]
        
        assert is_float32_array(log_probs)
        return log_probs, (features_lens - 1) // self._subsampling_factor + 1
    
    def recognize_batch(
        self, waveforms: npt.NDArray[np.float32], waveforms_len: npt.NDArray[np.int64], language: str | None
    ):
        features, features_lens = self._preprocessor(waveforms, waveforms_len)
        
        encoder_out, encoder_out_lens = self._encode(features, features_lens)
        
        return (
            self._decode_tokens(tokens, (self.window_size * self._subsampling_factor * np.array(timestamps)).tolist())
            for tokens, timestamps in self._decoding(encoder_out, encoder_out_lens)
        )
    
    def __del__(self):
        if hasattr(self, '_triton_client'):
            self._triton_client.close()
        if hasattr(self, '_preprocessor'):
            self._preprocessor.close()
