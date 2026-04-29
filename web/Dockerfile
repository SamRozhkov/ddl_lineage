FROM python:3.11-slim

WORKDIR /app

# Copy the entire project
COPY .. .

# Install dependencies
RUN pip install --no-cache-dir -e .
RUN pip install --no-cache-dir -r web/requirements.txt

# Expose port
EXPOSE 5000

# Run the web interface
CMD ["python", "-m", "web.app"]
