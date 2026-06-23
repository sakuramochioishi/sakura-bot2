import sqlite3
from datetime import datetime

DB_NAME = "bot_settings.db"

def init_db():
    """BotのステータスとPing履歴を保存するテーブルを作る"""
    # 💡 timeout=20 を追加
    conn = sqlite3.connect(DB_NAME, timeout=20)
    cursor = conn.cursor()
    
    # 状態の基本情報用テーブル
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_status (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # 📈 Pingの履歴を保存するテーブル
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ping_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            ping_value REAL
        )
    ''')
    
    # 初期値をセット
    default_stats = [
        ("status_text", "起動準備中..."),
        ("last_update", "未同期")
    ]
    for key, value in default_stats:
        cursor.execute("INSERT OR IGNORE INTO bot_status (key, value) VALUES (?, ?)", (key, value))
        
    conn.commit()
    conn.close()

def update_status_text(status_text, last_update):
    """ステータステキストを更新"""
    # 💡 timeout=20 を追加
    conn = sqlite3.connect(DB_NAME, timeout=20)
    cursor = conn.cursor()
    cursor.execute("UPDATE bot_status SET value = ? WHERE key = 'status_text'", (status_text,))
    cursor.execute("UPDATE bot_status SET value = ? WHERE key = 'last_update'", (last_update,))
    conn.commit()
    conn.close()

def add_ping_record(ping_value):
    """最新のPing値を履歴に追加し、最大10件に維持する"""
    # 💡 timeout=20 を追加
    conn = sqlite3.connect(DB_NAME, timeout=20)
    cursor = conn.cursor()
    
    now_str = datetime.now().strftime("%H:%M:%S")
    cursor.execute("INSERT INTO ping_history (timestamp, ping_value) VALUES (?, ?)", (now_str, ping_value))
    
    # 10件を超えた古いデータを自動削除
    cursor.execute('''
        DELETE FROM ping_history WHERE id NOT IN (
            SELECT id FROM ping_history ORDER BY id DESC LIMIT 10
        )
    ''')
    
    conn.commit()
    conn.close()

def get_status_text():
    """現在のステータステキスト等を取得"""
    # 💡 timeout=20 を追加
    conn = sqlite3.connect(DB_NAME, timeout=20)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM bot_status WHERE key = 'status_text'")
    status_text = cursor.fetchone()[0]
    cursor.execute("SELECT value FROM bot_status WHERE key = 'last_update'")
    last_update = cursor.fetchone()[0]
    conn.close()
    return status_text, last_update

def get_ping_history():
    """グラフ用に直近10件の履歴を取得"""
    # 💡 timeout=20 を追加
    conn = sqlite3.connect(DB_NAME, timeout=20)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, ping_value FROM (SELECT * FROM ping_history ORDER BY id DESC LIMIT 10) ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    
    labels = [row[0] for row in rows]
    data = [row[1] for row in rows]
    return labels, data

if __name__ == "__main__":
    init_db()