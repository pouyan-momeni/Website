FROM python:3.11-slim

WORKDIR /app
COPY run.py .

ENV MODEL_STEP=unknown
ENV OUTPUT_DIR=/output
ENV MODEL_NAME=test-model

CMD ["python", "run.py"]
