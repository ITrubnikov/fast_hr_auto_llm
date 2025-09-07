FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# onnx_asr src and vocab will be mounted at runtime
COPY app.py ./app.py
EXPOSE 7860
CMD ["python", "app.py"]
