# Start from a small ready-made Python image
FROM python:3.12-slim
# Work inside /app in the container
WORKDIR /app
# Install the libraries listed in requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copy the app code in
COPY . .
# The app listens on port 8080
EXPOSE 8080
# Start the web server (1 worker keeps the database simple and safe)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "app:app"]
