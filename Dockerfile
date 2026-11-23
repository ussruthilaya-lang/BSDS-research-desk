FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY prototype ./prototype
COPY harness ./harness
RUN pip install --no-cache-dir -e .
ENV PYTHONUNBUFFERED=1
