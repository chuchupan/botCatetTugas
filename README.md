# Bot Pencatat Tugas Kuliah

Bot Telegram untuk mencatat tugas kuliah: deadline, foto/file tugas, pembacaan
otomatis isi foto pakai Gemini AI, dan pengingat custom per tugas.

## Perintah Bot

- `/start` atau `/help` — lihat daftar perintah
- `/newtugas` — mulai tambah tugas baru (bisa kirim beberapa foto/file)
- `/list` — lihat semua tugas yang belum selesai
- `/selesai_tugas <id>` — tandai tugas sebagai selesai
- `/hapus <id>` — hapus tugas
- `/batal` — batalkan proses yang sedang berjalan

## Cara Kerja

1. Ketik `/newtugas`
2. Kirim foto tugas (boleh lebih dari satu). Bot otomatis membaca foto pertama
   pakai Gemini AI dan menampilkan dugaan mata kuliah + ringkasannya.
3. Ketik `/selesai` kalau sudah selesai kirim foto (atau `/skip` kalau tidak
   pakai foto sama sekali).
4. Bot bertanya mata kuliah, deadline (format `DD-MM-YYYY HH:MM`), dan kapan
   mau diingatkan (contoh: `3,1,0` = diingatkan H-3, H-1, dan hari-H).
5. Konfirmasi dengan ketik `ya`, tugas tersimpan.
6. Bot otomatis kirim pesan pengingat sesuai jadwal yang diminta.

## Deploy ke Railway (gratis)

### 1. Siapkan akun & kredensial
- Buat bot Telegram lewat **@BotFather** di Telegram (`/newbot`) → catat **Bot Token**-nya
- Buat API key Gemini gratis di **aistudio.google.com/apikey** → catat **Gemini API Key**-nya
- Buat akun di **railway.app** (bisa login pakai GitHub)

### 2. Upload kode ke GitHub
1. Buat repository baru di GitHub (bisa privat)
2. Upload semua file di folder ini (`bot.py`, `db.py`, `gemini_helper.py`,
   `requirements.txt`, `Procfile`) ke repository tersebut
   - **Jangan** upload folder `storage/` atau file `tugas.db` kalau sudah ada isinya

### 3. Deploy di Railway
1. Di dashboard Railway, klik **New Project** → **Deploy from GitHub repo**
2. Pilih repository yang tadi dibuat
3. Railway akan otomatis mendeteksi `Procfile` dan `requirements.txt`
4. Buka tab **Variables**, tambahkan environment variable:
   - `BOT_TOKEN` = (token dari BotFather)
   - `GEMINI_API_KEY` = (API key dari Google AI Studio)
5. Pastikan service yang jalan menggunakan tipe **Worker** (bukan Web), karena
   bot ini polling terus-menerus, bukan menerima HTTP request

### 4. Tambahkan Volume (PENTING agar data tidak hilang)
Secara default, filesystem di Railway bisa ter-reset saat redeploy. Supaya
database (`tugas.db`) dan foto tugas di folder `storage/` tidak hilang:
1. Di Railway, buka service kamu → tab **Settings** → **Volumes**
2. Klik **New Volume**, mount ke path `/app` (atau folder tempat kode berjalan)
3. Dengan begini, file akan tetap ada meskipun bot di-redeploy atau restart

### 5. Jalankan
Setelah environment variable dan volume terpasang, Railway akan otomatis
menjalankan bot. Cek tab **Deployments** → **Logs**, pastikan muncul log
`Bot mulai berjalan...` tanpa error. Coba chat bot kamu di Telegram dengan
`/start`.

## Catatan
- Reminder dicek setiap 1 menit oleh bot, jadi pengiriman pesan pengingat bisa
  meleset beberapa menit dari waktu H- yang diminta (ini wajar, cukup akurat
  untuk kebutuhan pengingat harian)
- Kalau Gemini gagal membaca foto (misal API key salah/limit habis), bot tetap
  jalan normal — kamu tinggal isi mata kuliah & deadline secara manual
- File foto/dokumen tugas disimpan di folder `storage/task_<id>/` di server
