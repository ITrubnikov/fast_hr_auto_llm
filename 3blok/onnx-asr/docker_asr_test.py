import sys
import time
import requests

# Подключаем локальный модуль onnx_asr из папки src
sys.path.insert(0, '/work/src')

import onnx_asr


def main():
    triton_http = 'http://host.docker.internal:18000'

    print('Checking Triton readiness...')
    r = requests.get(f'{triton_http}/v2/health/ready', timeout=5)
    print('health:', r.status_code)

    for model in ['gigaam-v2-ctc', 'gigaam_preprocessor', 'pyannote-vad']:
        try:
            rr = requests.get(f'{triton_http}/v2/models/{model}/ready', timeout=5)
            print(f'{model}:', rr.status_code)
        except Exception as e:
            print(f'{model}: error {e}')

    print('\nLoading ASR model...')
    asr = onnx_asr.load_model(
        model='gigaam-v2-ctc',
        triton_url='host.docker.internal:18000',
        cpu_preprocessing=True,
        path='/work',
    )

    print('Recognizing /work/test.wav ...')
    t0 = time.time()
    text = asr.recognize('/work/test.wav', sample_rate=16000)
    dt = time.time() - t0
    print('Result:', repr(text))
    print(f'Time: {dt:.3f}s')


if __name__ == '__main__':
    main()


