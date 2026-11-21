# Custom AI Chatbot RAG Berbasis Role (RBAC)

Aplikasi praktikum FastAPI, SQLite, JWT, dan Groq. Dokumen yang aktif hanya dapat dicari oleh role yang ditautkan ke dokumen itu. Tanpa `GROQ_API_KEY`, aplikasi tetap dapat mengambil potongan dokumen dan mengembalikannya sebagai jawaban lokal.

## Menjalankan di Windows

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Buka `http://127.0.0.1:8000` untuk chatbot, `/admin` untuk panel admin, dan `/docs` untuk dokumentasi API. Login awal: `admin` / `admin123`; ubah `ADMIN_PASSWORD` serta `SECRET_KEY` di `.env` sebelum deployment atau pemakaian bersama. Isikan `GROQ_API_KEY` untuk jawaban generatif Groq.

Pada startup, dataset praktikum dimasukkan ke SQLite dan dikaitkan dengan role `mahasiswa` dan `dosen`. Unggahan baru menerima PDF, DOCX, XLSX, CSV, TXT, dan MD. Admin dapat membuat role tambahan, menetapkan role dokumen, menonaktifkan dokumen, dan melihat chunk.

## Deploy Railway

Deployment yang dipilih: **Metode B - GitHub Repository** sesuai modul.

1. Pastikan `.env` tidak masuk repository. `.gitignore` sudah mengecualikan `.env`, database, virtual environment, dan file unggahan.
2. Buat repository GitHub, lalu push project ini dari terminal. Jangan masukkan API key ke kode atau README.
3. Di Railway pilih **New Project -> GitHub Repository**, lalu pilih repository project ini.
4. Pada service Railway, isi Variables berikut. Masukkan nilai rahasia langsung di dashboard Railway, jangan ke chat atau berkas repository.

   | Variable | Nilai |
   | --- | --- |
   | `GROQ_API_KEY` | API key Groq Anda |
   | `GROQ_MODEL` | `qwen/qwen3.8-27b` |
   | `JWT_SECRET` | String acak yang panjang |
   | `DB_PATH` | `/data/modul2ai.db` |
   | `UPLOAD_DIR` | `/data/uploads` |

5. Tambahkan Railway Volume ke service dengan **Mount Path** `/data`, lalu deploy perubahan. Konfigurasi `railpack.json`, `railway.json`, dan `Procfile` memberi tahu Railway cara menjalankan Uvicorn pada `$PORT`.
6. Generate public domain pada **Settings -> Networking -> Public Networking**. Jika Railway meminta target port, isi port yang terlihat pada log Uvicorn service.
7. Buka domain untuk chatbot dan `/admin` untuk panel admin, lalu uji role serta unggahan dokumen.

**Bukti untuk dikumpulkan:** tangkapan layar admin login/dashboard, pengaturan role dokumen dosen, hasil chatbot mahasiswa tanpa dokumen khusus dosen, hasil chatbot dosen dengan sumber dokumen, deployment Railway Online dan domain publik, serta chatbot live. Pastikan nilai rahasia pada dashboard tidak terlihat di tangkapan layar.

## Pengujian pemisahan akses

1. Login admin, tambahkan dokumen uji yang hanya berisi fakta penanda khusus, misalnya `INFORMASI KHUSUS DOSEN: kode akses TAK adalah ALFA-739`.
2. Atur dokumen tersebut agar hanya memiliki role `dosen`.
3. Tanyakan kode penanda melalui `/` dengan role `mahasiswa`, lalu dengan role `dosen`.
4. Pastikan mahasiswa tidak mendapat sumber dokumen itu dan dosen mendapat sumber serta isinya.

## Struktur

```text
app/       API, autentikasi, SQLite, ekstraksi, pencarian RAG
dataset/   materi praktikum yang disediakan
static/    chatbot dan panel admin
uploads/   file yang diunggah
```
