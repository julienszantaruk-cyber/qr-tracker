from fastapi import FastAPI, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from starlette.requests import Request
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
        img = qrcode.make(track_url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
        
        rows += f"""<tr>
            <td style="font-weight:bold">{c['label']}</td>
            <td><a href="{c['target_url']}" target="_blank">{c['target_url'][:50]}</a></td>
            <td style="text-align:center;font-size:1.4rem;font-weight:bold">{c['scan_count']}</td>
            <td><img src="data:image/png;base64,{qr_b64}" width="120" height="120"></td>
            <td><a href="data:image/png;base64,{qr_b64}" download="{c['label']}.png" style="background:#238636;color:white;padding:6px 12px;border-radius:6px;text-decoration:none">Telecharger</a></td>
        </tr>"""
    
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <title>QR Tracker</title>
    <style>
        body {{ font-family: system-ui; max-width: 1000px; margin: 2rem auto; padding: 1rem; background: #0d1117; color: #e6edf3; }}
        h1 {{ color: #58a6ff; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
        td, th {{ padding: 12px; border-bottom: 1px solid #30363d; text-align: left; vertical-align: middle; }}
        th {{ color: #8b949e; }}
        a {{ color: #58a6ff; }}
        form {{ background: #161b22; padding: 1rem; border-radius: 8px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
        input {{ padding: 10px; background: #0d1117; color: #e6edf3; border: 1px solid #30363d; border-radius: 6px; font-size: 14px; }}
        button {{ padding: 10px 20px; background: #238636; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 14px; }}
        button:hover {{ background: #2ea043; }}
    </style></head>
    <body>
        <h1>QR Tracker</h1>
        <form method="POST" action="/create">
            <input name="label" placeholder="Nom du QR" required>
            <input name="target_url" placeholder="https://exemple.com" size="40" required>
            <button type="submit">+ Creer un QR</button>
        </form>
        <table>
            <tr><th>Label</th><th>Destination</th><th>Scans</th><th>QR Code</th><th></th></tr>
            {rows if rows else '<tr><td colspan="5" style="text-align:center;color:#8b949e;padding:3rem">Aucun QR code encore. Crees-en un !</td></tr>'}
        </table>
    </body></html>"""

@app.post("/create")
async def create_qr(label: str = Form(...), target_url: str = Form(...)):
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
