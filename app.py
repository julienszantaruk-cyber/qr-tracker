from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse
import sqlite3, qrcode, io, base64, uuid
from datetime import datetime

app = FastAPI()

def get_db():
    db = sqlite3.connect("qr.db")
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.execute("""CREATE TABLE IF NOT EXISTS qr_codes (
        id TEXT PRIMARY KEY, label TEXT, target_url TEXT, created_at TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT, qr_id TEXT, scanned_at TEXT)""")
    db.commit()

init_db()

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    db = get_db()
    codes = db.execute("""
        SELECT qr_codes.*, COUNT(scans.id) as scan_count 
        FROM qr_codes LEFT JOIN scans ON qr_codes.id = scans.qr_id 
        GROUP BY qr_codes.id ORDER BY created_at DESC
    """).fetchall()
    
    base = str(request.base_url).rstrip("/")
    rows = ""
    for c in codes:
        track_url = f"{base}/s/{c['id']}"
        # Générer QR en base64
        img = qrcode.make(track_url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
        
        rows += f"""<tr>
            <td>{c['label']}</td>
            <td><a href="{c['target_url']}" target="_blank">{c['target_url'][:40]}...</a></td>
            <td style="font-size:2em;text-align:center">{c['scan_count']}</td>
            <td><img src="data:image/png;base64,{qr_b64}" width="120"></td>
        </tr>"""
    
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <title>QR Tracker</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: system-ui; max-width: 900px; margin: 2rem auto; padding: 1rem; background: #0d1117; color: #e6edf3; }}
        h1 {{ color: #58a6ff; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
        td, th {{ padding: 10px; border-bottom: 1px solid #30363d; text-align: left; }}
        th {{ color: #8b949e; }}
        a {{ color: #58a6ff; }}
        form {{ background: #161b22; padding: 1rem; border-radius: 8px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
        input {{ padding: 10px; background: #0d1117; color: #e6edf3; border: 1px solid #30363d; border-radius: 6px; }}
        button {{ padding: 10px 20px; background: #238636; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; }}
        button:hover {{ background: #2ea043; }}
        .empty {{ text-align: center; color: #8b949e; padding: 3rem; }}
    </style></head>
    <body>
        <h1>📊 QR Tracker</h1>
        <form method="POST" action="/create">
            <input name="label" placeholder="Nom du QR" required>
            <input name="target_url" placeholder="https://exemple.com" size="40" required>
            <button type="submit">+ Créer un QR</button>
        </form>
        <table>
            <tr><th>Label</th><th>Destination</th><th>Scans</th><th>QR Code</th></tr>
            {rows if rows else '<tr><td colspan="4" class="empty">Aucun QR code encore. Crées-en un !</td></tr>'}
        </table>
    </body></html>"""

@app.post("/create")
def create_qr(request: Request, label: str = "", target_url: str = ""):
    from fastapi import Form
    return RedirectResponse("/", status_code=303)

@app.post("/create")
async def create_qr(label: str = "", target_url: str = ""):
    qr_id = uuid.uuid4().hex[:8]
    db = get_db()
    db.execute("INSERT INTO qr_codes VALUES (?,?,?,?)",
        (qr_id, label, target_url, datetime.now().isoformat()))
    db.commit()
    return RedirectResponse("/", status_code=303)

from fastapi import Form

@app.api_route("/create", methods=["POST"])
async def create_qr_form(label: str = Form(...), target_url: str = Form(...)):
    qr_id = uuid.uuid4().hex[:8]
    db = get_db()
    db.execute("INSERT INTO qr_codes VALUES (?,?,?,?)",
        (qr_id, label, target_url, datetime.now().isoformat()))
    db.commit()
    return RedirectResponse("/", status_code=303)

@app.get("/s/{qr_id}")
def scan(qr_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM qr_codes WHERE id=?", (qr_id,)).fetchone()
    if not row:
        return HTMLResponse("<h1>QR introuvable</h1>", status_code=404)
    db.execute("INSERT INTO scans (qr_id, scanned_at) VALUES (?,?)",
        (qr_id, datetime.now().isoformat()))
    db.commit()
    return RedirectResponse(row["target_url"], status_code=302)
