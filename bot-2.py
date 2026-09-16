import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
from threading import Thread

from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

import db
import gemini_helper

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
STORAGE_DIR = Path(__file__).parent / "storage"
STORAGE_DIR.mkdir(exist_ok=True)

# Conversation states
COLLECTING_FILES, ASK_SUBJECT, ASK_DEADLINE, ASK_REMINDER, CONFIRM = range(5)

DATE_FORMATS = ["%d-%m-%Y %H:%M", "%d-%m-%Y"]


# ---------- Helper functions ----------

def parse_deadline(text: str):
    text = text.strip()
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            return dt
        except ValueError:
            continue
    return None


def parse_reminder_offsets(text: str):
    text = text.strip()
    try:
        parts = [int(p.strip()) for p in text.split(",") if p.strip() != ""]
        parts = sorted(set(p for p in parts if p >= 0), reverse=True)
        return parts if parts else None
    except ValueError:
        return None


def format_task_summary(task_row, files_count=0):
    deadline = datetime.fromisoformat(task_row["deadline"])
    status = "Selesai" if task_row["is_done"] else "Belum selesai"
    return (
        f"#{task_row['id']} — {task_row['subject'] or '(tanpa mata kuliah)'}\n"
        f"Deadline: {deadline.strftime('%d-%m-%Y %H:%M')}\n"
        f"Status: {status}\n"
        f"Deskripsi: {task_row['description'] or '-'}\n"
        f"File terlampir: {files_count}"
    )


# ---------- Command: /start & /help ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Halo! Aku bot pencatat tugas kuliah.\n\n"
        "Perintah yang tersedia:\n"
        "/newtugas - tambah tugas baru (bisa lampirkan foto)\n"
        "/list - lihat tugas yang belum selesai\n"
        "/selesai_tugas <id> - tandai tugas selesai\n"
        "/hapus <id> - hapus tugas\n"
        "/batal - batalkan proses yang sedang berjalan"
    )


# ---------- Conversation: /newtugas ----------

async def newtugas_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["files"] = []  # list of (path, type)
    context.user_data["gemini_hint"] = None
    await update.message.reply_text(
        "Oke, mari catat tugas baru.\n\n"
        "Kirim foto tugasnya sekarang (boleh lebih dari satu foto/file).\n"
        "Kalau sudah selesai kirim foto, ketik /selesai.\n"
        "Kalau tidak ada foto sama sekali, ketik /skip."
    )
    return COLLECTING_FILES


async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_tmp_dir = STORAGE_DIR / f"tmp_{update.effective_chat.id}_{update.effective_user.id}"
    task_tmp_dir.mkdir(exist_ok=True)

    file_obj = None
    file_type = None
    mime_type = "image/jpeg"

    if update.message.photo:
        file_obj = await update.message.photo[-1].get_file()
        file_type = "photo"
    elif update.message.document:
        file_obj = await update.message.document.get_file()
        file_type = "document"
        mime_type = update.message.document.mime_type or "application/octet-stream"

    if file_obj is None:
        await update.message.reply_text("Format file belum didukung, coba kirim foto ya.")
        return COLLECTING_FILES

    ext = ".jpg" if file_type == "photo" else Path(update.message.document.file_name or "file").suffix
    local_path = task_tmp_dir / f"{len(context.user_data['files'])}{ext}"
    await file_obj.download_to_drive(custom_path=str(local_path))
    context.user_data["files"].append((str(local_path), file_type))

    # Analisis foto pertama dengan Gemini sebagai bantuan
    if file_type == "photo" and context.user_data.get("gemini_hint") is None:
        with open(local_path, "rb") as f:
            image_bytes = f.read()
        hint = gemini_helper.analyze_image(image_bytes, mime_type="image/jpeg")
        context.user_data["gemini_hint"] = hint
        await update.message.reply_text(
            f"File diterima ({len(context.user_data['files'])} file).\n\n"
            f"Hasil baca otomatis:\n{hint}\n\n"
            "Kirim file lagi kalau ada, atau ketik /selesai untuk lanjut."
        )
    else:
        await update.message.reply_text(
            f"File diterima ({len(context.user_data['files'])} file). "
            "Kirim lagi atau ketik /selesai untuk lanjut."
        )

    return COLLECTING_FILES


async def skip_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Oke, tanpa foto. Ini tugas mata kuliah apa?")
    return ASK_SUBJECT


async def finish_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("files"):
        await update.message.reply_text(
            "Belum ada file yang dikirim. Kirim foto dulu, atau ketik /skip kalau memang tanpa foto."
        )
        return COLLECTING_FILES

    hint = context.user_data.get("gemini_hint")
    suggestion = ""
    if hint and "Mata kuliah:" in hint:
        try:
            guessed = hint.split("Mata kuliah:")[1].split("\n")[0].strip()
            suggestion = f" (dugaan: {guessed})"
        except IndexError:
            pass

    await update.message.reply_text(f"Ini tugas mata kuliah apa?{suggestion}")
    return ASK_SUBJECT


async def receive_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["subject"] = update.message.text.strip()
    await update.message.reply_text(
        "Deadline-nya kapan? Format: DD-MM-YYYY HH:MM (contoh: 20-09-2026 23:59)\n"
        "Boleh juga tanpa jam, contoh: 20-09-2026"
    )
    return ASK_DEADLINE


async def receive_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dt = parse_deadline(update.message.text)
    if dt is None:
        await update.message.reply_text(
            "Format tanggal tidak dikenali. Coba lagi, contoh: 20-09-2026 23:59 atau 20-09-2026"
        )
        return ASK_DEADLINE
    if dt < datetime.now():
        await update.message.reply_text(
            "Tanggal itu sudah lewat. Masukkan deadline yang belum lewat ya."
        )
        return ASK_DEADLINE

    context.user_data["deadline"] = dt
    await update.message.reply_text(
        "Mau diingatkan berapa hari sebelum deadline? Pisahkan dengan koma.\n"
        "Contoh: 3,1,0 (artinya diingatkan H-3, H-1, dan hari-H)\n"
        "Atau ketik 'default' untuk pakai H-1 dan H-0."
    )
    return ASK_REMINDER


async def receive_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if text == "default":
        offsets = [1, 0]
    else:
        offsets = parse_reminder_offsets(text)
        if offsets is None:
            await update.message.reply_text(
                "Format tidak dikenali. Contoh yang benar: 3,1,0 atau ketik 'default'."
            )
            return ASK_REMINDER

    context.user_data["reminder_offsets"] = offsets

    subject = context.user_data.get("subject", "(tanpa mata kuliah)")
    deadline = context.user_data["deadline"]
    n_files = len(context.user_data.get("files", []))
    desc = context.user_data.get("gemini_hint") or "-"

    await update.message.reply_text(
        f"Konfirmasi tugas:\n\n"
        f"Mata kuliah: {subject}\n"
        f"Deadline: {deadline.strftime('%d-%m-%Y %H:%M')}\n"
        f"Reminder: H-{', H-'.join(str(o) for o in offsets)}\n"
        f"Jumlah file: {n_files}\n\n"
        f"Ketik 'ya' untuk simpan, atau /batal untuk batalkan."
    )
    return CONFIRM


async def confirm_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip().lower() not in ("ya", "y", "yes", "ok", "oke"):
        await update.message.reply_text("Oke, ketik /batal untuk membatalkan atau 'ya' untuk simpan.")
        return CONFIRM

    chat_id = update.effective_chat.id
    subject = context.user_data.get("subject")
    deadline = context.user_data["deadline"]
    offsets = context.user_data["reminder_offsets"]
    description = context.user_data.get("gemini_hint")

    task_id = db.create_task(
        chat_id=chat_id,
        subject=subject,
        description=description,
        deadline_iso=deadline.isoformat(),
        reminder_offsets_csv=",".join(str(o) for o in offsets),
    )

    # Pindahkan file dari folder sementara ke folder permanen per tugas
    final_dir = STORAGE_DIR / f"task_{task_id}"
    final_dir.mkdir(exist_ok=True)
    for idx, (path, ftype) in enumerate(context.user_data.get("files", [])):
        src = Path(path)
        dest = final_dir / src.name
        src.replace(dest)
        db.add_task_file(task_id, str(dest), ftype)

    await update.message.reply_text(f"Tugas tersimpan dengan ID #{task_id}. Semangat mengerjakan!")
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Dibatalkan.")
    return ConversationHandler.END


# ---------- Command: /list, /selesai_tugas, /hapus ----------

async def list_tasks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    tasks = db.list_tasks(chat_id)
    if not tasks:
        await update.message.reply_text("Tidak ada tugas yang belum selesai. Mantap!")
        return
    messages = []
    for t in tasks:
        files = db.get_task_files(t["id"])
        messages.append(format_task_summary(t, len(files)))
    await update.message.reply_text("\n\n".join(messages))


async def mark_done_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Pakai format: /selesai_tugas <id>")
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID harus berupa angka.")
        return
    task = db.get_task(task_id)
    if not task or task["chat_id"] != update.effective_chat.id:
        await update.message.reply_text("Tugas tidak ditemukan.")
        return
    db.mark_done(task_id)
    await update.message.reply_text(f"Tugas #{task_id} ditandai selesai.")


async def delete_task_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Pakai format: /hapus <id>")
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID harus berupa angka.")
        return
    task = db.get_task(task_id)
    if not task or task["chat_id"] != update.effective_chat.id:
        await update.message.reply_text("Tugas tidak ditemukan.")
        return
    db.delete_task(task_id)
    await update.message.reply_text(f"Tugas #{task_id} dihapus.")


# ---------- Reminder job ----------

async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    tasks = db.get_all_pending_tasks()
    now = datetime.now()
    for t in tasks:
        deadline = datetime.fromisoformat(t["deadline"])
        offsets = [int(o) for o in t["reminder_offsets"].split(",") if o != ""]
        days_left = (deadline.date() - now.date()).days
        for offset in offsets:
            if days_left == offset and not db.has_reminder_been_sent(t["id"], offset):
                label = "HARI INI deadline-nya!" if offset == 0 else f"{offset} hari lagi deadline-nya."
                text = (
                    f"Pengingat tugas!\n\n{format_task_summary(t, len(db.get_task_files(t['id'])))}\n\n"
                    f"{label}"
                )
                try:
                    await context.bot.send_message(chat_id=t["chat_id"], text=text)
                    db.mark_reminder_sent(t["id"], offset)
                except Exception as e:
                    logger.error(f"Gagal kirim reminder task {t['id']}: {e}")


# ---------- Health check server (dibutuhkan Render Web Service) ----------
# Render mengecek apakah service merespons HTTP di port yang diberikan.
# Bot ini polling terus-menerus (bukan server HTTP), jadi kita jalankan
# server Flask kecil di thread terpisah hanya supaya Render menganggap
# service ini "sehat" dan tidak me-restart-nya berulang kali.

web_app = Flask(__name__)


@web_app.route("/")
def health_check():
    return "Bot jalan"


def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)


# ---------- Main ----------

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN belum diset di environment variable.")

    db.init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("newtugas", newtugas_start)],
        states={
            COLLECTING_FILES: [
                CommandHandler("selesai", finish_files),
                CommandHandler("skip", skip_files),
                MessageHandler(filters.PHOTO | filters.Document.ALL, receive_file),
            ],
            ASK_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_subject)],
            ASK_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_deadline)],
            ASK_REMINDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reminder)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_save)],
        },
        fallbacks=[CommandHandler("batal", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("list", list_tasks_cmd))
    app.add_handler(CommandHandler("selesai_tugas", mark_done_cmd))
    app.add_handler(CommandHandler("hapus", delete_task_cmd))

    app.job_queue.run_repeating(check_reminders, interval=60, first=10)

    Thread(target=run_web_server, daemon=True).start()

    logger.info("Bot mulai berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()
