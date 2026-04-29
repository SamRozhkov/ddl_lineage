# 🚀 Installation & Setup Guide

Complete guide for setting up the DDL Lineage Web Interface.

## Prerequisites

- Python 3.10 or higher
- pip (Python package manager)
- (Optional) Docker & Docker Compose for containerized deployment

## ⚡ Quick Start (5 minutes)

### macOS / Linux

```bash
# 1. Navigate to web directory
cd web

# 2. Install Flask
pip install flask

# 3. Start the application
python app.py
```

### Windows (PowerShell)

```powershell
# 1. Navigate to web directory
cd web

# 2. Install Flask
pip install flask

# 3. Start the application
python app.py
```

Then open your browser to: **http://127.0.0.1:5000**

---

## 📦 Full Installation

### Option 1: Manual Setup

```bash
# 1. Navigate to project root
cd /path/to/ddl_lineage

# 2. Install the main package in development mode
pip install -e .

# 3. Navigate to web directory
cd web

# 4. Install web dependencies
pip install -r requirements.txt

# 5. Run the application
python app.py
```

### Option 2: Using Virtual Environment (Recommended)

```bash
# 1. Create virtual environment
python -m venv venv

# 2. Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# 3. Install dependencies
pip install -e ..
pip install -r requirements.txt

# 4. Run the application
python app.py
```

### Option 3: Using the Shell Script

```bash
cd web
bash run.sh
```

The script automatically:
- Checks for Flask installation
- Installs dependencies if needed
- Starts the server

---

## 🐳 Docker Deployment

### Build and Run with Docker

```bash
# Build the image
docker build -t ddl-lineage-web web/

# Run the container
docker run -p 5000:5000 ddl-lineage-web
```

### Using Docker Compose

```bash
# Start the service
docker-compose -f web/docker-compose.yml up

# Stop the service
docker-compose -f web/docker-compose.yml down

# View logs
docker-compose -f web/docker-compose.yml logs -f
```

---

## 🔧 Configuration

### Change the Port

#### From Command Line

```bash
# Use port 8080 instead of 5000
python -c "from app import app; app.run(host='127.0.0.1', port=8080)"
```

#### By Environment Variable

```bash
# macOS/Linux
export FLASK_ENV=production
export FLASK_PORT=8080
python app.py

# Windows
set FLASK_ENV=production
set FLASK_PORT=8080
python app.py
```

### Allow External Access

```bash
# Default: localhost only (127.0.0.1)
# Change to accept external connections

python -c "from app import app; app.run(host='0.0.0.0', port=5000)"
```

**⚠️ Security Warning**: Only do this on trusted networks or with proper firewall rules.

### Configure File Upload Size

Edit `web/app.py`:

```python
# Default: 16MB
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32MB
```

---

## 🆚 Troubleshooting

### Port Already in Use

```bash
# Check what's using port 5000
lsof -i :5000  # macOS/Linux

# Kill the process
kill -9 <PID>

# Or use a different port
python -c "from app import app; app.run(port=5001)"
```

### Module Import Errors

```bash
# Make sure you're in the right directory
cd /path/to/ddl_lineage/web

# Or add parent directory to Python path
export PYTHONPATH="${PYTHONPATH}:$(cd .. && pwd)"
python app.py
```

### Flask Not Found

```bash
# Install Flask
pip install flask

# Or use the requirements file
pip install -r requirements.txt
```

### CDN Resources Not Loading

If Bulma, Mermaid, or Font Awesome icons don't load:

1. Check internet connection (CDN resources are external)
2. Configure proxy if behind corporate firewall:
   ```bash
   export HTTP_PROXY=http://proxy:port
   export HTTPS_PROXY=https://proxy:port
   ```

3. Or use offline mode by downloading CDN resources locally

### Memory Issues with Large SQL Files

```bash
# Increase max upload size
python -c "
from app import app
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024  # 64MB
app.run()
"
```

---

## 🌐 Production Deployment

### Using Gunicorn

```bash
# Install gunicorn
pip install gunicorn

# Run with multiple workers
gunicorn -w 4 -b 0.0.0.0:5000 web.app:app
```

### Using Nginx + Gunicorn

```bash
# Install Nginx and Gunicorn
brew install nginx  # macOS
pip install gunicorn

# Start Gunicorn
gunicorn -w 4 -b 127.0.0.1:8000 web.app:app

# Configure Nginx as reverse proxy (nginx.conf)
upstream gunicorn {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://gunicorn;
    }
}
```

### Using systemd Service

Create `/etc/systemd/system/ddl-lineage.service`:

```ini
[Unit]
Description=DDL Lineage Web Interface
After=network.target

[Service]
Type=notify
User=www-data
WorkingDirectory=/opt/ddl-lineage
Environment="PATH=/opt/ddl-lineage/venv/bin"
ExecStart=/opt/ddl-lineage/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 web.app:app

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl enable ddl-lineage
sudo systemctl start ddl-lineage
```

---

## 📊 Performance Optimization

### Enable Caching

Edit `web/app.py`:

```python
from flask_caching import Cache

cache = Cache(app, config={'CACHE_TYPE': 'simple'})

@app.route('/api/analyze', methods=['POST'])
@cache.cached(timeout=300)
def analyze():
    # ...
```

### Database for Results

For production, consider adding database support:

```bash
pip install sqlalchemy psycopg2-binary
```

### Compression

```python
from flask_compress import Compress

Compress(app)
```

---

## 🔐 Security Checklist

- [ ] Set `FLASK_ENV=production` in production
- [ ] Use strong secret key: `app.secret_key = os.urandom(24)`
- [ ] Enable HTTPS with Let's Encrypt
- [ ] Limit upload file size
- [ ] Validate all user inputs
- [ ] Use environment variables for secrets
- [ ] Run behind a reverse proxy (Nginx)
- [ ] Keep dependencies updated: `pip install -U flask`

---

## 📚 Additional Resources

- [Flask Documentation](https://flask.palletsprojects.com/)
- [Gunicorn Documentation](https://gunicorn.org/)
- [Nginx Configuration](https://nginx.org/en/docs/)
- [Docker Best Practices](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)

---

## 🆘 Getting Help

If you encounter issues:

1. Check the [README.md](README.md)
2. Look at the troubleshooting section above
3. Check Flask logs: `FLASK_DEBUG=1 python app.py`
4. Review browser console for client-side errors (F12)
5. Open an issue on GitHub

---

## ✅ Verification

After installation, verify everything works:

```bash
# 1. Check Flask version
python -c "import flask; print(f'Flask {flask.__version__}')"

# 2. Check parent package
python -c "import ddl_lineage; print(f'ddl_lineage {ddl_lineage.__version__}')"

# 3. Start server and test
python app.py
# Open browser to http://127.0.0.1:5000
# Try "Analyze" with example SQL
```

You should see:
- ✓ Web interface loads
- ✓ Examples are pre-populated
- ✓ "Analyze" button works
- ✓ Diagram displays
- ✓ No console errors
