# Use a lightweight, secure official Python image
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies needed for potential compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only the requirements file first to leverage Docker layer caching
COPY REQUIREMENTS.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r REQUIREMENTS.txt

# Copy the rest of the application files
COPY . .

# Expose Streamlit's default port
EXPOSE 8501

# Run the Streamlit application on container start
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
