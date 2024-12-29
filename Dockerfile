# Use a lightweight base image
FROM python:3.8-slim

# Set environment variables for Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Set the working directory inside the Docker container
WORKDIR /app

# Copy the necessary files into the container
COPY requirements.txt .
COPY app.py .
COPY argoproxy .
COPY run_app.sh .

# Install the required Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Ensure the run script is executable
RUN chmod +x run_app.sh

# Set the entry point to the run_app.sh script
ENTRYPOINT ["./run_app.sh"]