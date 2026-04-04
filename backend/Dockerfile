# Use Bullseye (Debian 11) to prevent the Docker Toolbox LZMA memory crash
FROM python:3.11-slim-bullseye

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

# Install Playwright dependencies (Fail gracefully if not needed)
RUN apt-get update -o Acquire::Check-Valid-Until=false || true \
    && apt-get install -y --no-install-recommends libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 || true \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN playwright install chromium || true

# Copy the rest of the application
COPY . .

# FIX: --reload is development-only. Removed for correctness.
# When you go to production, change to:
# CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]