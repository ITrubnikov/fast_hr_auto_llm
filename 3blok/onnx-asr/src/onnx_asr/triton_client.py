from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import numpy.typing as npt

try:
    import tritonclient.http as httpclient
    from tritonclient.utils import InferenceServerException
except ImportError:
    raise ImportError(
        "tritonclient is required for Triton inference. "
        "Install it with: pip install tritonclient[all]"
    )


class TritonInferenceConfig:
    def __init__(
        self,
        url: str = "localhost:8000",
        model_name: str = "",
        model_version: str = "",
        verbose: bool = False,
        concurrency: int = 1,
        connection_timeout: float = 60.0,
        network_timeout: float = 60.0,
    ):
        self.url = url
        self.model_name = model_name
        self.model_version = model_version
        self.verbose = verbose
        self.concurrency = concurrency
        self.connection_timeout = connection_timeout
        self.network_timeout = network_timeout


class TritonClient:
    def __init__(self, config: TritonInferenceConfig):
        self.config = config
        self._client = httpclient.InferenceServerClient(
            url=config.url,
            verbose=config.verbose,
            concurrency=config.concurrency,
            connection_timeout=config.connection_timeout,
            network_timeout=config.network_timeout,
        )
        
        if not self._client.is_server_ready():
            raise RuntimeError(f"Triton server at {config.url} is not ready")
        
        if config.model_name and not self._client.is_model_ready(
            config.model_name, config.model_version
        ):
            raise RuntimeError(
                f"Model {config.model_name}:{config.model_version} is not ready"
            )
    
    def infer(
        self,
        inputs: Dict[str, npt.NDArray],
        outputs: List[str],
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> Dict[str, npt.NDArray]:
        model_name = model_name or self.config.model_name
        model_version = model_version or self.config.model_version
        
        if not model_name:
            raise ValueError("Model name must be specified")
        
        triton_inputs = []
        for name, data in inputs.items():
            triton_input = httpclient.InferInput(name, data.shape, self._numpy_to_triton_dtype(data.dtype))
            triton_input.set_data_from_numpy(data)
            triton_inputs.append(triton_input)
        
        triton_outputs = [httpclient.InferRequestedOutput(name) for name in outputs]
        
        try:
            results = self._client.infer(
                model_name=model_name,
                model_version=model_version,
                inputs=triton_inputs,
                outputs=triton_outputs,
            )
        except InferenceServerException as e:
            raise RuntimeError(f"Triton inference failed: {e}")
        
        output_dict = {}
        for name in outputs:
            output_dict[name] = results.as_numpy(name)
        
        return output_dict
    
    @staticmethod
    def _numpy_to_triton_dtype(dtype: np.dtype) -> str:
        if dtype == np.float32:
            return "FP32"
        elif dtype == np.float64:
            return "FP64"
        elif dtype == np.int32:
            return "INT32"
        elif dtype == np.int64:
            return "INT64"
        elif dtype == np.uint32:
            return "UINT32"
        elif dtype == np.uint64:
            return "UINT64"
        elif dtype == np.bool_:
            return "BOOL"
        else:
            raise ValueError(f"Unsupported dtype: {dtype}")
    
    def close(self):
        self._client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class TritonSessionOptions:
    def __init__(
        self,
        triton_config: TritonInferenceConfig,
        cpu_preprocessing: bool = True,
    ):
        self.triton_config = triton_config
        self.cpu_preprocessing = cpu_preprocessing
