import csv
import json
import os
import sqlite3
from datetime import datetime, timedelta


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'attendance.db')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')


def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON;')
    return conn


def _attendance_table_has_unique_constraint(conn) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='attendance'")
    row = cur.fetchone()
    if row is None or row[0] is None:
        return True  # table doesn't exist yet — CREATE TABLE below will make it correctly
    return 'UNIQUE(rollno, date)' in row[0].replace(' ', '') or 'UNIQUE(rollno,date)' in row[0].replace(' ', '')


def _migrate_attendance_table_if_needed(conn):
    """If an old attendance table exists without the UNIQUE(rollno, date)
    constraint, rebuild it in place, keeping only one row per
    (rollno, date) pair. This runs automatically on every init_db() call
    so no manual migration step is needed."""
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='attendance'")
    exists = cur.fetchone() is not None
    if not exists:
        return  # nothing to migrate, CREATE TABLE will make the correct version

    if _attendance_table_has_unique_constraint(conn):
        return  # already correct, nothing to do

    # Old table found without the constraint — rebuild it.
    cur.execute("ALTER TABLE attendance RENAME TO attendance_old")

    cur.execute(
        '''
        CREATE TABLE attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rollno TEXT NOT NULL,
            name TEXT,
            class_name TEXT,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            UNIQUE(rollno, date)
        );
        '''
    )

    # Copy rows over, keeping only the earliest time per (rollno, date)
    cur.execute(
        '''
        INSERT OR IGNORE INTO attendance (rollno, name, class_name, date, time)
        SELECT rollno, name, class_name, date, time
        FROM attendance_old
        ORDER BY date ASC, time ASC
        '''
    )

    cur.execute("DROP TABLE attendance_old")
    conn.commit()


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rollno TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            class_name TEXT,
            encoding TEXT,
            created_at TEXT NOT NULL
        );
        '''
    )

    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rollno TEXT NOT NULL,
            name TEXT,
            class_name TEXT,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            UNIQUE(rollno, date)
        );
        '''
    )

    conn.commit()

    # Self-heal: if an OLD attendance table (pre-existing, without the
    # UNIQUE constraint) is sitting on disk, rebuild it automatically.
    _migrate_attendance_table_if_needed(conn)

    cur.execute('CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(date);')
    conn.commit()
    conn.close()
    purge_old_attendance(max_days=15)


def save_student(rollno: str, name: str, encoding, class_name: str = '') -> dict:
    ensure_dirs()
    float_encoding = [float(value) for value in encoding.tolist()]
    payload = json.dumps(float_encoding)
    created_at = datetime.now().isoformat()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        '''
        INSERT INTO students (rollno, name, class_name, encoding, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(rollno)
        DO UPDATE SET
            name = excluded.name,
            class_name = excluded.class_name,
            encoding = excluded.encoding,
            created_at = excluded.created_at
        ''',
        (rollno, name, class_name, payload, created_at),
    )
    conn.commit()
    conn.close()

    return {'rollno': rollno, 'name': name, 'class_name': class_name, 'created_at': created_at}


def get_students():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT rollno, name, class_name, encoding, created_at FROM students ORDER BY created_at ASC')
    rows = cur.fetchall()
    conn.close()

    students = []
    for row in rows:
        encoding = []
        if row['encoding']:
            try:
                encoding = json.loads(row['encoding'])
            except json.JSONDecodeError:
                encoding = []
        students.append({
            'rollno': row['rollno'],
            'name': row['name'],
            'class_name': row['class_name'],
            'encoding': encoding,
            'created_at': row['created_at'],
        })
    return students


def get_student_by_rollno(rollno: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT rollno, name, class_name, encoding, created_at FROM students WHERE rollno = ?', (rollno,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    encoding = json.loads(row['encoding']) if row['encoding'] else []
    return {
        'rollno': row['rollno'],
        'name': row['name'],
        'class_name': row['class_name'],
        'encoding': encoding,
        'created_at': row['created_at'],
    }


def delete_student(rollno: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM students WHERE rollno = ?', (rollno,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def get_attendance_rows(date_str: str = None):
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        'SELECT rollno, name, class_name, date, time FROM attendance WHERE date = ? ORDER BY time ASC',
        (date_str,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            'rollno': row['rollno'],
            'name': row['name'],
            'class': row['class_name'],
            'date': row['date'],
            'time': row['time'],
        }
        for row in rows
    ]


def log_attendance(rollno: str, name: str = None, class_name: str = None):
    now = datetime.now()
    date_value = now.strftime('%Y-%m-%d')
    time_value = now.strftime('%H:%M:%S')

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT OR IGNORE INTO attendance (rollno, name, class_name, date, time) VALUES (?, ?, ?, ?, ?)',
        (rollno, name, class_name, date_value, time_value),
    )
    conn.commit()
    inserted = cur.rowcount > 0
    conn.close()

    if not inserted:
        return False

    try:
        purge_old_attendance(max_days=15)
        export_attendance_csv(date_value)
        rotate_backups(max_days=15)
    except Exception:
        pass
    return True


def export_attendance_csv(date_str: str = None):
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')

    ensure_dirs()
    out_path = os.path.join(BACKUP_DIR, f'{date_str}.csv')
    rows = get_attendance_rows(date_str)

    with open(out_path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['rollno', 'name', 'class', 'date', 'time'])
        for row in rows:
            writer.writerow([row['rollno'], row['name'], row['class'], row['date'], row['time']])
    return out_path


def clear_database():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM attendance')
    cur.execute('DELETE FROM students')
    cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('attendance', 'students')")
    conn.commit()
    conn.close()


def purge_old_attendance(max_days: int = 15):
    cutoff = (datetime.now() - timedelta(days=max_days)).strftime('%Y-%m-%d')
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM attendance WHERE date < ?', (cutoff,))
    conn.commit()
    conn.close()


def rotate_backups(max_days: int = 15):
    ensure_dirs()
    files = []
    for filename in os.listdir(BACKUP_DIR):
        if not filename.endswith('.csv'):
            continue
        full_path = os.path.join(BACKUP_DIR, filename)
        try:
            files.append((full_path, os.path.getmtime(full_path)))
        except OSError:
            continue
    files.sort(key=lambda item: item[1], reverse=True)
    for full_path, _ in files[max_days:]:
        try:
            os.remove(full_path)
        except OSError:
            pass