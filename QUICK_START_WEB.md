# 🚀 Quick Start Guide - Web Interface

## Installation & Launch (Choose One)

### ⚡ Fastest (30 seconds)
```bash
cd web
pip install flask
python app.py
```

### 🎯 Interactive Choice
```bash
cd web
python launcher.py
# Then choose:
# 1) Basic interface
# 2) Extended (with file upload)
```

### 📦 Full Setup
```bash
cd web
pip install -r requirements.txt
python app.py
```

### 🐳 Docker
```bash
docker-compose -f web/docker-compose.yml up
```

---

## Access the Interface

Open your browser to: **http://127.0.0.1:5000**

You'll see:
- SQL input area with examples
- Analysis button
- Real-time Mermaid diagram
- Statistics and relationships
- Export options

---

## Try It Out

1. **Pre-loaded examples** - Click buttons at bottom left
2. **Enter SQL** - Paste your own DDL
3. **Click Analyze** - Results appear in seconds
4. **Explore tabs** - Objects, Cycles, Topo, etc.
5. **Export** - Download as JSON/Mermaid/Text

---

## What's Included

### Backend APIs
```
POST   /api/analyze              → Analyze SQL
POST   /api/impact/<object>      → Impact analysis
POST   /api/topo                 → Topological sort
POST   /api/upload               → File upload
POST   /api/export               → Export results
GET    /download/<file>          → Download file
GET    /api/health               → Health check
```

### Frontend
- HTML5 interface with Bulma CSS
- Mermaid.js diagrams
- JavaScript client logic
- Responsive design

---

## Documentation

- **[README.md](web/README.md)** - Overview & features
- **[INSTALLATION.md](web/INSTALLATION.md)** - Detailed setup
- **[API.md](web/API.md)** - API reference
- **[SUMMARY.md](web/SUMMARY.md)** - Technical overview

---

## Troubleshooting

**Port already in use?**
```bash
python -c "from web.app import app; app.run(port=5001)"
```

**Flask not installed?**
```bash
pip install flask
```

**Import errors?**
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/.."
python app.py
```

---

## Features

✅ Real-time SQL analysis
✅ Interactive Mermaid diagrams
✅ Impact analysis (upstream/downstream)
✅ Cycle detection
✅ Topological sort
✅ File upload & export
✅ Responsive UI
✅ REST API
✅ Docker ready
✅ Production deployable

---

## Next Steps

1. Run the server
2. Try examples
3. Upload your SQL files
4. Export results
5. Integrate with your tools
6. Deploy to production

---

**Happy analyzing! 📊**

For full details, see [WEB_INTERFACE_COMPLETE.md](WEB_INTERFACE_COMPLETE.md)
