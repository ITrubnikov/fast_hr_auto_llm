from collections.abc import Iterable, Iterator
from itertools import chain
from pathlib import Path

import numpy as np
import numpy.typing as npt
from scipy.special import softmax

from onnx_asr.triton_client import TritonClient, TritonSessionOptions
from onnx_asr.utils import is_float32_array
from onnx_asr.vad import Vad


class PyAnnoteVadTriton(Vad):

    SEGMENT_DURATION = 10.0
    HOP_DURATION = 1.0
    
    def __init__(self, model_files: dict[str, Path], triton_options: TritonSessionOptions):
        self._triton_client = TritonClient(triton_options.triton_config)

    @staticmethod
    def _get_model_files(quantization: str | None = None) -> dict[str, str]:
        return {}

    def _encode(self, waveforms: npt.NDArray[np.float32]) -> Iterator[npt.NDArray[np.float32]]:

        segment_samples = int(self.SEGMENT_DURATION * self.SAMPLE_RATE)
        hop_samples = int(self.HOP_DURATION * self.SAMPLE_RATE)
        
        for i in range(len(waveforms)):
            waveform = waveforms[i]
            waveform_len = len(waveform)
            
            segments = []
            for start in range(0, waveform_len, hop_samples):
                end = min(start + segment_samples, waveform_len)
                segment = waveform[start:end]
                
                if len(segment) < segment_samples:
                    segment = np.pad(segment, (0, segment_samples - len(segment)), mode='constant')
                
                segments.append(segment)
            
            if not segments:
                yield np.array([0.0], dtype=np.float32)
                continue
            
            max_batch_size = 8
            all_probs = []
            
            for batch_start in range(0, len(segments), max_batch_size):
                batch_end = min(batch_start + max_batch_size, len(segments))
                batch_segments = segments[batch_start:batch_end]
                
                batch_array = np.array(batch_segments, dtype=np.float32)[:, None, :]
                
                inputs = {
                    "input_values": batch_array,
                }
                outputs = ["logits"]
                
                results = self._triton_client.infer(inputs, outputs)
                logits = results["logits"]
                
                assert is_float32_array(logits)
                
                probabilities = softmax(logits, axis=-1)

                if probabilities.shape[-1] > 1:
                    speech_probs = np.mean(probabilities[:, :, 1], axis=1)
                else:
                    speech_probs = np.mean(probabilities[:, :, 0], axis=1)
                
                all_probs.extend(speech_probs)
            
            yield np.array(all_probs, dtype=np.float32)
    
    def _find_segments(
        self, probs: Iterable[np.float32], threshold: float = 0.5, neg_threshold: float | None = None, **kwargs: float
        ) -> Iterator[tuple[int, int]]:
        if neg_threshold is None:
            neg_threshold = threshold - 0.15

        hop_samples = int(self.HOP_DURATION * self.SAMPLE_RATE)
        
        state = 0
        start = 0
        for i, p in enumerate(chain(probs, (np.float32(0),))):
            if state == 0 and p >= threshold:
                state = 1
                start = i * hop_samples
            elif state == 1 and p < neg_threshold:
                state = 0
                yield start, i * hop_samples

    def _merge_segments(
        self,
        segments: Iterator[tuple[int, int]],
        waveform_len: int,
        min_speech_duration_ms: float = 250,
        max_speech_duration_s: float = 20,
        min_silence_duration_ms: float = 100,
        speech_pad_ms: float = 30,
        **kwargs: float,
    ) -> Iterator[tuple[int, int]]:
        INF = 10**15
        
        speech_pad = int(speech_pad_ms * self.SAMPLE_RATE // 1000)
        min_speech_duration = int(min_speech_duration_ms * self.SAMPLE_RATE // 1000) - 2 * speech_pad
        max_speech_duration = int(max_speech_duration_s * self.SAMPLE_RATE) - 2 * speech_pad
        min_silence_duration = int(min_silence_duration_ms * self.SAMPLE_RATE // 1000) + 2 * speech_pad

        cur_start, cur_end = -INF, -INF
        for start, end in chain(segments, ((waveform_len, waveform_len), (INF, INF))):
            if start - cur_end < min_silence_duration and end - cur_start < max_speech_duration:
                cur_end = end
            else:
                if cur_end - cur_start > min_speech_duration:
                    yield max(cur_start - speech_pad, 0), min(cur_end + speech_pad, waveform_len)
                while end - start > max_speech_duration:
                    yield max(start - speech_pad, 0), start + max_speech_duration - speech_pad
                    start += max_speech_duration
                cur_start, cur_end = start, end

    def _segment(self, probs: Iterable[np.float32], waveform_len: np.int64, **kwargs: float) -> Iterator[tuple[int, int]]:
        return self._merge_segments(self._find_segments(probs, **kwargs), int(waveform_len), **kwargs)

    def segment_batch(
        self, waveforms: npt.NDArray[np.float32], waveforms_len: npt.NDArray[np.int64], **kwargs: float
    ) -> Iterator[Iterator[tuple[int, int]]]:

        encoding = self._encode(waveforms)
        if len(waveforms) == 1:
            yield self._segment(encoding.__next__(), waveforms_len[0], **kwargs)
        else:
            yield from (
                self._segment(probs, waveform_len, **kwargs)
                for probs, waveform_len in zip(encoding, waveforms_len, strict=True)
            )
    
    def __del__(self):
        if hasattr(self, '_triton_client'):
            self._triton_client.close()
