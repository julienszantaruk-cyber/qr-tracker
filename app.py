from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
import sqlite3, qrcode, io, base64, uuid, hashlib, secrets
from datetime import datetime

app = FastAPI()

# ========== CONFIG ==========
ADMIN_USER = "admin"
ADMIN_PASS_HASH = hashlib.sha256("MonMotDePasse123".encode()).hexdigest()  # Change ce mot de passe !
SESSION_TOKENS = set()

# ========== DB ==========
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

# ========== AUTH ==========
def is_logged(request: Request) -> bool:
    token = request.cookies.get("session")
    return token in SESSION_TOKENS

def require_login(request: Request):
    if not is_logged(request):
        return RedirectResponse("/login", status_code=303)
    return None

# ========== LOGIN ==========
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if is_logged(request):
        return RedirectResponse("/", status_code=303)
    return """<!DOCTYPE html><html><head><meta charset="utf-8">
    <title>QR Tracker - Connexion</title>
    <style>
        body { font-family: system-ui; background: #0d1117; color: #e6edf3; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .card { background: #161b22; padding: 2.5rem; border-radius: 12px; border: 1px solid #30363d; width: 340px; }
        h1 { text-align: center; color: #58a6ff; margin-bottom: 0.3rem; }
        .sub { text-align: center; color: #8b949e; margin-bottom: 1.5rem; font-size: 0.9rem; }
        label { display: block; margin-bottom: 4px; color: #8b949e; font-size: 0.85rem; }
        input { width: 100%; padding: 10px; background: #0d1117; color: #e6edf3; border: 1px solid #30363d; border-radius: 6px; margin-bottom: 1rem; box-sizing: border-box; font-size: 14px; }
        input:focus { border-color: #58a6ff; outline: none; }
        button { width: 100%; padding: 12px; background: #238636; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 15px; }
        button:hover { background: #2ea043; }
        .error { background: #da363340; color: #f85149; padding: 10px; border-radius: 6px; text-align: center; margin-bottom: 1rem; display: none; }
    </style></head>
    <body>
        <div class="card">
            <h1>🔐 QR Tracker</h1>
            <p class="sub">Connecte-toi pour acceder au dashboard</p>
            <div class="error" id="err">Identifiants incorrects</div>
            <form method="POST" action="/login">
                <label>Identifiant</label>
                <input name="username" placeholder="admin" required autofocus>
                <label>Mot de passe</label>
                <input name="password" type="password" placeholder="••••••••" required>
                <button type="submit">Se connecter</button>
            </form>
        </div>
    </body></html>"""

@app.post("/login")
async def do_login(username: str = Form(...), password: str = Form(...)):
    pass_hash = hashlib.sha256(password.encode()).hexdigest()
    if username == ADMIN_USER and pass_hash == ADMIN_PASS_HASH:
        token = secrets.token_hex(32)
        SESSION_TOKENS.add(token)
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie("session", token, httponly=True, max_age=86400)
        return resp
    return HTMLResponse("""<!DOCTYPE html><html><head><meta charset="utf-8">
    <title>QR Tracker - Connexion</title>
    <style>
        body { font-family: system-ui; background: #0d1117; color: #e6edf3; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .card { background: #161b22; padding: 2.5rem; border-radius: 12px; border: 1px solid #30363d; width: 340px; }
        h1 { text-align: center; color: #58a6ff; margin-bottom: 0.3rem; }
        .sub { text-align: center; color: #8b949e; margin-bottom: 1.5rem; font-size: 0.9rem; }
        label { display: block; margin-bottom: 4px; color: #8b949e; font-size: 0.85rem; }
        input { width: 100%; padding: 10px; background: #0d1117; color: #e6edf3; border: 1px solid #30363d; border-radius: 6px; margin-bottom: 1rem; box-sizing: border-box; font-size: 14px; }
        button { width: 100%; padding: 12px; background: #238636; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 15px; }
        button:hover { background: #2ea043; }
        .error { background: #da363340; color: #f85149; padding: 10px; border-radius: 6px; text-align: center; margin-bottom: 1rem; }
    </style></head>
    <body>
        <div class="card">
            <h1>🔐 QR Tracker</h1>
            <p class="sub">Connecte-toi pour acceder au dashboard</p>
            <div class="error">Identifiants incorrects</div>
            <form method="POST" action="/login">
                <label>Identifiant</label>
                <input name="username" placeholder="admin" required autofocus>
                <label>Mot de passe</label>
                <input name="password" type="password" placeholder="••••••••" required>
                <button type="submit">Se connecter</button>
            </form>
        </div>
    </body></html>""", status_code=401)

@app.get("/logout")
def logout(request: Request):
    token = request.cookies.get("session")
    SESSION_TOKENS.discard(token)
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("session")
    return resp

# ========== API JSON (pour auto-refresh) ==========
@app.get("/api/stats")
def api_stats(request: Request):
    if not is_logged(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    db = get_db()
    codes = db.execute("""
        SELECT qr_codes.*, COUNT(scans.id) as scan_count 
        FROM qr_codes LEFT JOIN scans ON qr_codes.id = scans.qr_id 
        GROUP BY qr_codes.id ORDER BY created_at DESC
    """).fetchall()
    return [{"id": c["id"], "label": c["label"], "target_url": c["target_url"], "scan_count": c["scan_count"]} for c in codes]

# ========== DASHBOARD ==========
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect
    
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
        
        rows += f"""<tr id="row-{c['id']}">
            <td style="font-weight:bold">{c['label']}</td>
            <td><a href="{c['target_url']}" target="_blank">{c['target_url'][:50]}</a></td>
            <td class="scan-count" data-id="{c['id']}" style="text-align:center;font-size:1.4rem;font-weight:bold">{c['scan_count']}</td>
            <td><img src="data:image/png;base64,{qr_b64}" width="120" height="120"></td>
            <td>
                <a href="data:image/png;base64,{qr_b64}" download="{c['label']}.png" style="background:#238636;color:white;padding:6px 12px;border-radius:6px;text-decoration:none;display:inline-block;margin-bottom:4px">Telecharger</a>
                <button onclick="deleteQR('{c['id']}')" style="background:#da3633;color:white;padding:6px 12px;border-radius:6px;border:none;cursor:pointer;font-size:13px">Supprimer</button>
            </td>
        </tr>"""
    
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <title>QR Tracker</title>
    <style>
        body {{ font-family: system-ui; max-width: 1000px; margin: 2rem auto; padding: 1rem; background: #0d1117; color: #e6edf3; }}
        h1 {{ color: #58a6ff; display: inline-block; }}
        .topbar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }}
        .logout {{ color: #f85149; text-decoration: none; font-size: 0.9rem; padding: 6px 14px; border: 1px solid #f8514930; border-radius: 6px; }}
        .logout:hover {{ background: #f8514920; }}
        .live {{ display: inline-block; width: 8px; height: 8px; background: #3fb950; border-radius: 50%; margin-left: 8px; animation: pulse 2s infinite; }}
        @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.3; }} }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
        td, th {{ padding: 12px; border-bottom: 1px solid #30363d; text-align: left; vertical-align: middle; }}
        th {{ color: #8b949e; }}
        a {{ color: #58a6ff; }}
        form {{ background: #161b22; padding: 1rem; border-radius: 8px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
        input {{ padding: 10px; background: #0d1117; color: #e6edf3; border: 1px solid #30363d; border-radius: 6px; font-size: 14px; }}
        input:focus {{ border-color: #58a6ff; outline: none; }}
        button, .btn {{ padding: 10px 20px; background: #238636; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 14px; }}
        button:hover {{ opacity: 0.9; }}
        .updated {{ animation: flash 0.5s; }}
        @keyframes flash {{ 0% {{ background: #238636; }} 100% {{ background: transparent; }} }}
    </style></head>
    <body>
        <div class="topbar">
            <div><h1>QR Tracker</h1><span class="live" title="Auto-refresh actif"></span></div>
            <a href="/logout" class="logout">Deconnexion</a>
        </div>
        <form method="POST" action="/create">
            <input name="label" placeholder="Nom du QR" required>
            <input name="target_url" placeholder="https://exemple.com" size="40" required>
            <button type="submit">+ Creer un QR</button>
        </form>
        <table>
            <tr><th>Label</th><th>Destination</th><th>Scans</th><th>QR Code</th><th>Actions</th></tr>
            <tbody id="tbody">
            {rows if rows else '<tr id="empty"><td colspan="5" style="text-align:center;color:#8b949e;padding:3rem">Aucun QR code encore !</td></tr>'}
            </tbody>
        </table>

        <script>
            // Auto-refresh des compteurs toutes les 5 secondes
            setInterval(async () => {{
                try {{
                    const resp = await fetch('/api/stats');
                    if (!resp.ok) return;
                    const data = await resp.json();
                    data.forEach(qr => {{
                        const el = document.querySelector(`.scan-count[data-id="${{qr.id}}"]`);
                        if (el && el.textContent !== String(qr.scan_count)) {{
                            el.textContent = qr.scan_count;
                            el.classList.add('updated');
                            setTimeout(() => el.classList.remove('updated'), 600);
                        }}
                    }});
                }} catch(e) {{}}
            }}, 5000);

            // Suppression
            async function deleteQR(id) {{
                if (!confirm('Supprimer ce QR code et tous ses scans ?')) return;
                const resp = await fetch('/delete/' + id, {{ method: 'DELETE' }});
                if (resp.ok) {{
                    const row = document.getElementById('row-' + id);
                    if (row) row.remove();
                    if (document.querySelectorAll('[id^="row-"]').length === 0) {{
                        document.getElementById('tbody').innerHTML = '<tr><td colspan="5" style="text-align:center;color:#8b949e;padding:3rem">Aucun QR code encore !</td></tr>';
                    }}
                }}
            }}
        </script>
    </body></html>"""

# ========== ACTIONS ==========
@app.post("/create")
async def create_qr(request: Request, label: str = Form(...), target_url: str = Form(...)):
    redirect = require_login(request)
    if redirect:
        return redirect
    qr_id = uuid.uuid4().hex[:8]
    db = get_db()
    db.execute("INSERT INTO qr_codes VALUES (?,?,?,?)",
        (qr_id, label, target_url, datetime.now().isoformat()))
    db.commit()
    return RedirectResponse("/", status_code=303)

@app.delete("/delete/{qr_id}")
def delete_qr(qr_id: str, request: Request):
    if not is_logged(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    db = get_db()
    db.execute("DELETE FROM scans WHERE qr_id=?", (qr_id,))
    db.execute("DELETE FROM qr_codes WHERE id=?", (qr_id,))
    db.commit()
    return JSONResponse({"ok": True})

# ========== SCAN (public) ==========
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
