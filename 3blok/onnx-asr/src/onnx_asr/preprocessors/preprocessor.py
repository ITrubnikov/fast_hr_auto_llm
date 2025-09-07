from typing import Optional

import numpy as np
import numpy.typing as npt

from onnx_asr.triton_client import TritonClient, TritonInferenceConfig
from onnx_asr.utils import is_float32_array, is_int64_array


class Preprocessor:
    def __init__(
        self, 
        model_name: str,
        triton_config: TritonInferenceConfig,
        cpu_preprocessing: bool = True
    ):
        self.model_name = model_name
        self.cpu_preprocessing = cpu_preprocessing
        preprocessor_config = TritonInferenceConfig(
            url=triton_config.url,
            model_name=model_name,
            model_version=triton_config.model_version,
            verbose=triton_config.verbose,
            concurrency=triton_config.concurrency,
            connection_timeout=triton_config.connection_timeout,
            network_timeout=triton_config.network_timeout,
        )
        
        self._triton_client = TritonClient(preprocessor_config)

    def __call__(
        self, waveforms: npt.NDArray[np.float32], waveforms_lens: npt.NDArray[np.int64]
    ) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.int64]]:
        # Triton с max_batch_size > 0 требует правильных размерностей
        # waveforms_lens должен быть [batch_size, 1] вместо [batch_size]
        waveforms_lens_reshaped = waveforms_lens.reshape(-1, 1)
        
        inputs = {
            "waveforms": waveforms,
            "waveforms_lens": waveforms_lens_reshaped
        }
        outputs = ["features", "features_lens"]
        
        results = self._triton_client.infer(inputs, outputs, model_name=self.model_name)
        
        features = results["features"]
        features_lens = results["features_lens"]
        
        # Возвращаем features_lens в оригинальной форме [batch_size]
        if features_lens.ndim > 1:
            features_lens = features_lens.flatten()
        
        assert is_float32_array(features) and is_int64_array(features_lens)
        return features, features_lens
    
    def close(self):
        if hasattr(self, '_triton_client'):
            self._triton_client.close()
    
    def __del__(self):
        self.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
