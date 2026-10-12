FROM python:3.12-slim

WORKDIR /app
COPY . .

ENV AGRI_VISION_HOST=0.0.0.0
ENV AGRI_VISION_PORT=8765
ENV AGRI_VISION_DATABASE=/data/agri_vision.sqlite3
ENV AGRI_VISION_MEDIA_DIR=/data/media
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Set AGRI_VISION_API_KEY in the deployment secret store.

RUN addgroup --system agri && adduser --system --ingroup agri agri \
    && mkdir -p /data/media \
    && chown -R agri:agri /app /data
USER agri
EXPOSE 8765
CMD ["python", "run.py"]
