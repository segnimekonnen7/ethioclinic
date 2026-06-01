# Use the official Python 3.11 slim image as the base.
# "slim" means we omit a lot of build tools to keep the image small.
FROM python:3.11-slim

# Set the working directory inside the container.
WORKDIR /app

# Copy the requirements file and install dependencies.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire app directory.
COPY . .

# Expose port 8000 so Docker Compose can map it.
EXPOSE 8000

# Run the FastAPI app with Uvicorn.
# We bind to 0.0.0.0 so it listens on all network interfaces (Docker requirement).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
