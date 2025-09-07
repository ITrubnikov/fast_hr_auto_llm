import wave
from typing import Literal, TypeGuard, get_args

import numpy as np
import numpy.typing as npt

SampleRates = Literal[8_000, 16_000, 22_050, 24_000, 32_000, 44_100, 48_000]


def is_supported_sample_rate(sample_rate: int) -> TypeGuard[SampleRates]:
    return sample_rate in get_args(SampleRates)


def is_float32_array(x: object) -> TypeGuard[npt.NDArray[np.float32]]:
    return isinstance(x, np.ndarray) and x.dtype == np.float32


def is_int32_array(x: object) -> TypeGuard[npt.NDArray[np.int32]]:
    return isinstance(x, np.ndarray) and x.dtype == np.int32


def is_int64_array(x: object) -> TypeGuard[npt.NDArray[np.int64]]:
    return isinstance(x, np.ndarray) and x.dtype == np.int64


class SupportedOnlyMonoAudioError(ValueError):
    def __init__(self) -> None:
        super().__init__("Supported only mono audio.")


class WrongSampleRateError(ValueError):
    def __init__(self) -> None:
        super().__init__(f"Supported only {get_args(SampleRates)} sample rates.")


class DifferentSampleRatesError(ValueError):
    def __init__(self) -> None:
        super().__init__("All sample rates in a batch must be the same.")


def read_wav(filename: str) -> tuple[npt.NDArray[np.float32], int]:
    with wave.open(filename, mode="rb") as f:
        data = f.readframes(f.getnframes())
        zero_value = 0
        if f.getsampwidth() == 1:
            buffer = np.frombuffer(data, dtype="u1")
            zero_value = 1
        elif f.getsampwidth() == 3:
            buffer = np.zeros((len(data) // 3, 4), dtype="V1")
            buffer[:, -3:] = np.frombuffer(data, dtype="V1").reshape(-1, f.getsampwidth())
            buffer = buffer.view(dtype="<i4")
        else:
            buffer = np.frombuffer(data, dtype=f"<i{f.getsampwidth()}")

        max_value = 2 ** (8 * buffer.itemsize - 1)
        return buffer.reshape(f.getnframes(), f.getnchannels()).astype(np.float32) / max_value - zero_value, f.getframerate()


def read_wav_files(
    waveforms: list[npt.NDArray[np.float32] | str], numpy_sample_rate: SampleRates
) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.int64], SampleRates]:
    results = []
    sample_rates = []
    for x in waveforms:
        if isinstance(x, str):
            waveform, sample_rate = read_wav(x)
            if waveform.ndim == 2 and waveform.shape[1] != 1:
                waveform = waveform.mean(axis=1, keepdims=True)
            results.append(waveform[:, 0])
            sample_rates.append(sample_rate)
        else:
            if x.ndim != 1:
                raise SupportedOnlyMonoAudioError()
            results.append(x)
            sample_rates.append(numpy_sample_rate)

    if len(set(sample_rates)) > 1:
        raise DifferentSampleRatesError()

    if is_supported_sample_rate(sample_rates[0]):
        return *pad_list(results), sample_rates[0]
    raise WrongSampleRateError()


def pad_list(arrays: list[npt.NDArray[np.float32]]) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.int64]]:
    lens = np.array([array.shape[0] for array in arrays], dtype=np.int64)

    result = np.zeros((len(arrays), lens.max()), dtype=np.float32)
    for i, x in enumerate(arrays):
        result[i, : x.shape[0]] = x[: min(x.shape[0], result.shape[1])]

    return result, lens
