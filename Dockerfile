# Step 1: Base Image (Lightweight slim version)
FROM python:3.11-slim

# Step 2: Set working directory
WORKDIR /app

# Step 3: Set Environment Variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app.py

# Step 4: Install system dependencies required for ping
RUN apt-get update && apt-get install -y iputils-ping && rm -rf /var/lib/apt/lists/*

# Step 5: Install Python dependencies
COPY requirements.txt .
# Install gunicorn along with requirements
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Step 6: Copy the rest of the application
COPY . .

# Step 7: Expose the port
EXPOSE 3000

# Step 8: Start the application using Gunicorn (1 worker, 4 threads to prevent scheduler duplication)
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--bind", "0.0.0.0:3000", "app:app"]
