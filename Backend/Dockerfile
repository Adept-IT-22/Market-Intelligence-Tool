# Use a slim Python image
FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# Install system dependencies needed for building wheels and git
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt first for build cache efficiency
COPY requirements.txt .

# --- Install PyTorch and all other dependencies ---
# This command installs PyTorch libraries for CPU, then the rest from requirements.txt
RUN pip install --no-cache-dir torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0 \
    --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose app port
EXPOSE 8000

# Run the app
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "main:app", "--reload", "--timeout", "300"]