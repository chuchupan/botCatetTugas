import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "tugas.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            subject TEXT,
            description TEXT,
            deadline TEXT NOT NULL,
            reminder_offsets TEXT NOT NULL,
            is_done INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS task_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sent_reminders (
            task_id INTEGER NOT NULL,
            offset_days INTEGER NOT NULL,
            sent_at TEXT NOT NULL,
            PRIMARY KEY (task_id, offset_days)
        )
    """)
    conn.commit()
    conn.close()


def create_task(chat_id, subject, description, deadline_iso, reminder_offsets_csv):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """INSERT INTO tasks (chat_id, subject, description, deadline, reminder_offsets, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (chat_id, subject, description, deadline_iso, reminder_offsets_csv, datetime.now().isoformat()),
    )
    conn.commit()
    task_id = c.lastrowid
    conn.close()
    return task_id


def add_task_file(task_id, file_path, file_type):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO task_files (task_id, file_path, file_type) VALUES (?, ?, ?)",
        (task_id, file_path, file_type),
    )
    conn.commit()
    conn.close()


def get_task_files(task_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM task_files WHERE task_id = ?", (task_id,))
    rows = c.fetchall()
    conn.close()
    return rows


def list_tasks(chat_id, include_done=False):
    conn = get_conn()
    c = conn.cursor()
    if include_done:
        c.execute("SELECT * FROM tasks WHERE chat_id = ? ORDER BY deadline ASC", (chat_id,))
    else:
        c.execute(
            "SELECT * FROM tasks WHERE chat_id = ? AND is_done = 0 ORDER BY deadline ASC",
            (chat_id,),
        )
    rows = c.fetchall()
    conn.close()
    return rows


def get_task(task_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = c.fetchone()
    conn.close()
    return row


def mark_done(task_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE tasks SET is_done = 1 WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()


def delete_task(task_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    c.execute("DELETE FROM task_files WHERE task_id = ?", (task_id,))
    c.execute("DELETE FROM sent_reminders WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()


def get_all_pending_tasks():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE is_done = 0")
    rows = c.fetchall()
    conn.close()
    return rows


def has_reminder_been_sent(task_id, offset_days):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT 1 FROM sent_reminders WHERE task_id = ? AND offset_days = ?",
        (task_id, offset_days),
    )
    row = c.fetchone()
    conn.close()
    return row is not None


def mark_reminder_sent(task_id, offset_days):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO sent_reminders (task_id, offset_days, sent_at) VALUES (?, ?, ?)",
        (task_id, offset_days, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
