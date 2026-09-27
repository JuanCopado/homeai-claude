# Imagen para un Hugging Face Space (SDK "docker") o cualquier servicio de contenedores.
# El servicio solo hace de proxy hacia la Inference API: no necesita GPU.
FROM python:3.11-slim
RUN useradd -m -u 1000 app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
USER app
ENV PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
