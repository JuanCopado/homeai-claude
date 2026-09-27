# Imagen para un Hugging Face Space (SDK "docker") o cualquier servicio de contenedores.
# La generación va a la Inference API (sin GPU); la segmentación por zonas
# (SegFormer-b4) corre en la CPU del propio contenedor.
FROM python:3.11-slim
RUN useradd -m -u 1000 app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ENV HF_HOME=/app/.cache/huggingface
COPY segmentation.py style.py ./
# Descarga los modelos (segmentación y estilo) al construir, no en la primera petición.
RUN python -c "import segmentation as s, style as st; s.load_segmenter(); st.load_classifier()" && chown -R app /app/.cache
COPY app.py .
USER app
ENV PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
