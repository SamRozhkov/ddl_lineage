FROM python:3.11-slim

WORKDIR /app

# Copy the entire project
COPY .. .

# Install dependencies
RUN pip install --no-cache-dir -e .
RUN pip install --no-cache-dir -r web/backend/requirements.txt

# Expose port
EXPOSE 5001

# Run the web interface
CMD ["python", "web/backend/app.py"]
