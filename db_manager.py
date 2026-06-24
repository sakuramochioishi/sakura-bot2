import sqlite3
from datetime import datetime

DB_NAME = "bot_settings.db"

def init_db():
    """新しいダッシュボード用のテーブルをすべて作成・初期化"""
    conn = sqlite3.connect(DB_NAME, timeout=20)
    cursor = conn.cursor()
    
    # 👥 1. サーバー数・ユーザー数用テーブル
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_stats (
            key TEXT PRIMARY KEY,
            value INTEGER
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO bot_stats (key, value) VALUES ('guild_count', 0)")
    cursor.execute("INSERT OR IGNORE INTO bot_stats (key, value) VALUES ('user_count', 0)")
    
    # 📊 2. コマンド実行回数カウント用テーブル
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS command_counts (
            command_name TEXT PRIMARY KEY,
            count INTEGER DEFAULT 0
        )
    ''')
    # 最初によく使うコマンドを登録しておく
    for cmd in ['help', 'skr_help', 'youtube_check', 'x_check', 'other']:
        cursor.execute("INSERT OR IGNORE INTO command_counts (command_name, count) VALUES (?, 0)", (cmd,))
        
    # 📜 3. 動作ログ保存用テーブル
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            message TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

# --- 👥 サーバー数・ユーザー数の更新・取得 ---
def update_bot_counts(guild_count, user_count):
    conn = sqlite3.connect(DB_NAME, timeout=20)
    cursor = conn.cursor()
    cursor.execute("UPDATE bot_stats SET value = ? WHERE key = 'guild_count'", (guild_count,))
    cursor.execute("UPDATE bot_stats SET value = ? WHERE key = 'user_count'", (user_count,))
    conn.commit()
    conn.close()

def get_bot_counts():
    conn = sqlite3.connect(DB_NAME, timeout=20)
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM bot_stats")
    res = dict(cursor.fetchall())
    conn.close()
    return res.get('guild_count', 0), res.get('user_count', 0)

# --- 📊 コマンド実行回数のカウントアップ・取得 ---
def increment_command(command_name):
    conn = sqlite3.connect(DB_NAME, timeout=20)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO command_counts (command_name, count) VALUES (?, 0)", (command_name,))
    cursor.execute("UPDATE command_counts SET count = count + 1 WHERE command_name = ?", (command_name,))
    conn.commit()
    conn.close()

def get_command_stats():
    conn = sqlite3.connect(DB_NAME, timeout=20)
    cursor = conn.cursor()
    cursor.execute("SELECT command_name, count FROM command_counts")
    rows = cursor.fetchall()
    conn.close()
    labels = [row[0] for row in rows]
    data = [row[1] for row in rows]
    return labels, data

# --- 📜 ログの追加・取得 ---
def add_log(message):
    conn = sqlite3.connect(DB_NAME, timeout=20)
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO bot_logs (timestamp, message) VALUES (?, ?)", (now_str, message))
    # ログは最新の20件だけ残して古いものは削除
    cursor.execute("DELETE FROM bot_logs WHERE id NOT IN (SELECT id FROM bot_logs ORDER BY id DESC LIMIT 20)")
    conn.commit()
    conn.close()

def get_logs():
    conn = sqlite3.connect(DB_NAME, timeout=20)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, message FROM bot_logs ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    return rows

if __name__ == "__main__":
    init_db()