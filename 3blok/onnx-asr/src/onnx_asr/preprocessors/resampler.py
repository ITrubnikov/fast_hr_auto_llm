import numpy as np
import numpy.typing as npt
from scipy import signal

from onnx_asr.utils import SampleRates


class Resampler:
    def __init__(self, target_sample_rate: int = 16_000, **kwargs):
        self.target_sample_rate = target_sample_rate
    
    def __call__(
        self, waveforms: npt.NDArray[np.float32], waveforms_lens: npt.NDArray[np.int64], sample_rate: SampleRates
    ) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.int64]]:
        if sample_rate == self.target_sample_rate:
            return waveforms, waveforms_lens
        
        batch_size, max_length = waveforms.shape
        
        ratio = self.target_sample_rate / sample_rate
        
        new_lens = np.round(waveforms_lens * ratio).astype(np.int64)
        new_max_length = int(np.ceil(max_length * ratio))
        
        resampled_waveforms = np.zeros((batch_size, new_max_length), dtype=np.float32)
        
        for i in range(batch_size):
            original_length = int(waveforms_lens[i])
            if original_length == 0:
                continue
                
            audio = waveforms[i, :original_length]
            
            resampled_audio = self._resample_audio(audio, sample_rate, self.target_sample_rate)
            
            actual_new_length = len(resampled_audio)
            new_lens[i] = actual_new_length
            resampled_waveforms[i, :actual_new_length] = resampled_audio
        
        return resampled_waveforms, new_lens
    
    def _resample_audio(
        self, audio: npt.NDArray[np.float32], orig_sr: int, target_sr: int
    ) -> npt.NDArray[np.float32]:
        if len(audio) == 0:
            return audio
            
        from math import gcd
        
        common_divisor = gcd(orig_sr, target_sr)
        up_factor = target_sr // common_divisor
        down_factor = orig_sr // common_divisor
        
        try:
            resampled = signal.resample_poly(audio, up_factor, down_factor, axis=0)
            return resampled.astype(np.float32)
        except Exception as e:
            print(f"Warning: resample_poly failed ({e}), using fallback method")
            return self._resample_fallback(audio, orig_sr, target_sr)
    
    def _resample_fallback(
        self, audio: npt.NDArray[np.float32], orig_sr: int, target_sr: int
    ) -> npt.NDArray[np.float32]:
        if len(audio) == 0:
            return audio
            
        new_length = int(len(audio) * target_sr / orig_sr)
        
        resampled = signal.resample(audio, new_length)
        return np.array(resampled, dtype=np.float32)
