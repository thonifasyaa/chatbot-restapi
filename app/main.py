import json
import os
import re
import shutil
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

from app import database as db
from app.auth import create_token, current_admin, hash_password, verify_password
from app.extractor import ALLOWED, chunk_text, extract
from app.rag import answer

app = FastAPI(title="Chatbot RAG Berbasis Role", version="1.0.0")
STATIC = Path(__file__).resolve().parent.parent / "static"
UPLOADS = Path(os.getenv("UPLOAD_DIR", "./uploads"))
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
def startup():
    db.init_db()
    if not db.one("SELECT id FROM admins LIMIT 1"):
        db.execute("INSERT INTO admins(username,password_hash) VALUES (?,?)", (os.getenv("ADMIN_USERNAME", "admin"), hash_password(os.getenv("ADMIN_PASSWORD", "admin123"))))
    for role in ("mahasiswa", "dosen"):
        db.execute("INSERT OR IGNORE INTO roles(name) VALUES (?)", (role,))
    # Seed dokumen yang disertakan dengan praktikum ke role mahasiswa dan dosen.
    for source in sorted((Path(__file__).resolve().parent.parent / "dataset").glob("*")):
        if source.is_file() and source.suffix.lower() in ALLOWED and not db.one("SELECT id FROM documents WHERE filename=?", (source.name,)):
            _store_document(source.name, source, [r["id"] for r in db.rows("SELECT id FROM roles")], copy_file=True)


def _store_document(filename, path, role_ids, copy_file=False):
    UPLOADS.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w. -]", "_", filename).strip() or "document"
    stored = UPLOADS / f"{os.urandom(6).hex()}_{safe}"
    if copy_file:
        shutil.copyfile(path, stored)
    else:
        shutil.move(str(path), stored)
    doc_id = db.execute("INSERT INTO documents(filename,stored_path) VALUES (?,?)", (filename, str(stored.resolve())))
    content = extract(stored)
    with db.connect() as conn:
        conn.executemany("INSERT INTO chunks(document_id,ordinal,content) VALUES (?,?,?)", [(doc_id, i, c) for i, c in enumerate(chunk_text(content))])
    db.set_document_roles(doc_id, role_ids)
    return doc_id


class ChatInput(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    role: str = Field(min_length=1, max_length=50)


@app.get("/", response_class=HTMLResponse)
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return FileResponse(STATIC / "admin.html")


@app.post("/api/auth/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    admin = db.one("SELECT * FROM admins WHERE username=?", (username,))
    if not admin or not verify_password(password, admin["password_hash"]):
        raise HTTPException(status_code=401, detail="Username atau password salah.")
    response = JSONResponse({"ok": True})
    response.set_cookie("access_token", create_token(username), httponly=True, samesite="lax", secure=request.url.scheme == "https", max_age=43200)
    return response


@app.post("/api/auth/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("access_token")
    return response


@app.get("/api/admin/me")
def me(_: str = Depends(current_admin)):
    return {"ok": True}


@app.get("/api/roles")
def list_roles():
    return db.rows("SELECT id,name FROM roles ORDER BY name")


@app.post("/api/admin/roles")
def add_role(name: str = Form(...), _: str = Depends(current_admin)):
    name = re.sub(r"[^a-zA-Z0-9_-]", "", name.strip().lower())
    if not name:
        raise HTTPException(400, "Nama role tidak valid.")
    try:
        role_id = db.execute("INSERT INTO roles(name) VALUES (?)", (name,))
    except Exception:
        raise HTTPException(409, "Role sudah ada.")
    return {"id": role_id, "name": name}


@app.delete("/api/admin/roles/{role_id}")
def delete_role(role_id: int, _: str = Depends(current_admin)):
    role = db.one("SELECT name FROM roles WHERE id=?", (role_id,))
    if not role:
        raise HTTPException(404, "Role tidak ditemukan.")
    if role["name"] in {"mahasiswa", "dosen"}:
        raise HTTPException(400, "Role bawaan tidak dapat dihapus.")
    db.execute("DELETE FROM roles WHERE id=?", (role_id,))
    return {"ok": True}


@app.get("/api/admin/documents")
def documents(_: str = Depends(current_admin)):
    docs = db.rows("SELECT * FROM documents ORDER BY id DESC")
    for item in docs:
        item["roles"] = [r["name"] for r in db.rows("SELECT r.name FROM roles r JOIN document_roles dr ON r.id=dr.role_id WHERE dr.document_id=?", (item["id"],))]
        item["chunks"] = db.one("SELECT COUNT(*) AS n FROM chunks WHERE document_id=?", (item["id"],))["n"]
    return docs


@app.post("/api/admin/documents")
async def upload_document(file: UploadFile = File(...), role_ids: str = Form(...), _: str = Depends(current_admin)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(400, "Format yang didukung: PDF, DOCX, XLSX, CSV, TXT, MD.")
    try:
        ids = json.loads(role_ids)
        valid = {r["id"] for r in db.rows("SELECT id FROM roles")}
        ids = [int(i) for i in ids if int(i) in valid]
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(400, "Role dokumen tidak valid.")
    if not ids:
        raise HTTPException(400, "Pilih setidaknya satu role.")
    max_bytes = int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024
    UPLOADS.mkdir(parents=True, exist_ok=True)
    temp = UPLOADS / f"incoming_{os.urandom(8).hex()}{suffix}"
    size = 0
    with temp.open("wb") as out:
        while data := await file.read(1024 * 1024):
            size += len(data)
            if size > max_bytes:
                temp.unlink(missing_ok=True)
                raise HTTPException(413, "Ukuran file melewati batas.")
            out.write(data)
    try:
        doc_id = _store_document(Path(file.filename or "dokumen").name, temp, ids)
    except Exception as exc:
        temp.unlink(missing_ok=True)
        raise HTTPException(400, f"Gagal membaca dokumen: {exc}")
    return {"id": doc_id, "ok": True}


@app.patch("/api/admin/documents/{doc_id}")
def set_active(doc_id: int, active: bool = Form(...), _: str = Depends(current_admin)):
    if not db.one("SELECT id FROM documents WHERE id=?", (doc_id,)):
        raise HTTPException(404, "Dokumen tidak ditemukan.")
    db.execute("UPDATE documents SET active=? WHERE id=?", (int(active), doc_id))
    return {"ok": True}


@app.put("/api/admin/documents/{doc_id}/roles")
def update_doc_roles(doc_id: int, role_ids: str = Form(...), _: str = Depends(current_admin)):
    if not db.one("SELECT id FROM documents WHERE id=?", (doc_id,)):
        raise HTTPException(404, "Dokumen tidak ditemukan.")
    try:
        ids = [int(i) for i in json.loads(role_ids)]
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(400, "Role dokumen tidak valid.")
    valid = {r["id"] for r in db.rows("SELECT id FROM roles")}
    if not ids or any(i not in valid for i in ids):
        raise HTTPException(400, "Pilih role yang valid.")
    db.set_document_roles(doc_id, ids)
    return {"ok": True}


@app.get("/api/admin/documents/{doc_id}/chunks")
def document_chunks(doc_id: int, _: str = Depends(current_admin)):
    return db.rows("SELECT ordinal,content FROM chunks WHERE document_id=? ORDER BY ordinal", (doc_id,))


@app.delete("/api/admin/documents/{doc_id}")
def delete_document(doc_id: int, _: str = Depends(current_admin)):
    item = db.one("SELECT stored_path FROM documents WHERE id=?", (doc_id,))
    if not item:
        raise HTTPException(404, "Dokumen tidak ditemukan.")
    db.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    Path(item["stored_path"]).unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/documents/{doc_id}/download")
def download_document(doc_id: int, role: str):
    item = db.one("""SELECT d.* FROM documents d JOIN document_roles dr ON dr.document_id=d.id JOIN roles r ON r.id=dr.role_id
        WHERE d.id=? AND d.active=1 AND r.name=?""", (doc_id, role))
    if not item:
        raise HTTPException(404, "Dokumen tidak tersedia untuk role ini.")
    return FileResponse(item["stored_path"], filename=item["filename"])


@app.post("/api/chat")
def chat(payload: ChatInput):
    if not db.one("SELECT id FROM roles WHERE name=?", (payload.role,)):
        raise HTTPException(400, "Role tidak dikenal.")
    return answer(payload.question.strip(), payload.role)


@app.get("/api/admin/groq-quota")
def quota(_: str = Depends(current_admin)):
    totals = db.one("SELECT COUNT(*) AS requests,COALESCE(SUM(prompt_tokens),0) AS prompt_tokens,COALESCE(SUM(completion_tokens),0) AS completion_tokens FROM quota_logs")
    return {**totals, "has_api_key": bool(os.getenv("GROQ_API_KEY", "").strip()), "model": os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")}
