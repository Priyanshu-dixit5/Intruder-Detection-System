IntruderSystem

Minimal Flask-based intruder detection dashboard skeleton.

Quickstart

1. Create a virtualenv and activate it:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

2. Install Flask:

```powershell
pip install flask
```

3. Run the app:

```powershell
python main.py
```

Files
- main.py: Flask backend and DB init
- static/: `style.css`, `script.js`
- templates/: `index.html`, `login.html`, `register.html`
- known_faces/: folder to store authorized face images
- database.db: SQLite DB (created/initialized on first run)
