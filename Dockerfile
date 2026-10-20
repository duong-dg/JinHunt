FROM python:3.12-slim
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY requirements-moderation.txt .
ARG INSTALL_IMAGE_SCANNER=1
RUN if [ "$INSTALL_IMAGE_SCANNER" = "1" ]; then pip install --no-cache-dir -r requirements-moderation.txt; fi
COPY app app
RUN mkdir -p /data/uploads
ENV UPLOAD_DIR=/data/uploads
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
