from flask import Flask, render_template_string
import db_manager

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Sakura Bot 2 総合ダッシュボード</title>
    <meta http-equiv="refresh" content="5"> <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: 'Helvetica Neue', Arial, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 40px; }
        .container { max-width: 900px; margin: 0 auto; }
        h1 { color: #38bdf8; text-align: center; margin-bottom: 30px; font-size: 28px; }
        
        /* 👥 ステータスカードの並び */
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px; }
        .card { background: #1e293b; padding: 20px; border-radius: 12px; border: 1px solid #334155; text-align: center; }
        .card h2 { margin: 0; font-size: 14px; color: #94a3b8; text-transform: uppercase; }
        .card .stat { font-size: 36px; font-weight: bold; color: #f43f5e; margin-top: 10px; }
        .card .stat.user { color: #10b981; }

        /* 📊 グラフとログのエリア */
        .main-content { background: #1e293b; padding: 25px; border-radius: 12px; border: 1px solid #334155; margin-bottom: 30px; }
        .main-content h3 { margin-top: 0; color: #38bdf8; border-bottom: 1px solid #334155; padding-bottom: 10px; }
        
        .chart-box { max-width: 400px; margin: 0 auto 30px auto; }

        /* 📜 ログのタイムライン */
        .log-table { width: 100%; border-collapse: collapse; text-align: left; font-size: 14px; }
        .log-table th { color: #94a3b8; padding: 10px; border-bottom: 2px solid #334155; }
        .log-table td { padding: 10px; border-bottom: 1px solid #334155; font-family: monospace; }
        .log-time { color: #64748b; width: 160px; }
        .log-msg { color: #38bdf8; }
        
        .footer { text-align: center; font-size: 12px; color: #475569; margin-top: 20px; }
    </style>
</head>
<body>
<div class="container">
    <h1>🌸 Sakura Bot 2 総合運用ダッシュボード</h1>
    
    <div class="grid">
        <div class="card">
            <h2>🌐 参加サーバー数</h2>
            <div class="stat">{{ guild_count }}</div>
        </div>
        <div class="card">
            <h2>👥 合計所属ユーザー数</h2>
            <div class="stat user">{{ user_count }}</div>
        </div>
    </div>

    <div class="main-content">
        <h3>📊 コマンド実行の割合</h3>
        <div class="chart-box">
            <canvas id="cmdChart"></canvas>
        </div>
    </div>

    <div class="main-content">
        <h3>📜 最新のBot動作ログ (直近10件)</h3>
        <table class="log-table">
            <thead>
                <tr>
                    <th>発生時刻</th>
                    <th>ログ内容</th>
                </tr>
            </thead>
            <tbody>
                {% for timestamp, message in logs %}
                <tr>
                    <td class="log-time">{{ timestamp }}</td>
                    <td class="log-msg">{{ message }}</td>
                </tr>
                {% endfor %}
                {% if not logs %}
                <tr>
                    <td colspan="2" style="text-align: center; color: #475569;">ログはまだありません</td>
                </tr>
                {% endif %}
            </tbody>
        </table>
    </div>

    <div class="footer">
        🔄 5秒ごとに自動更新中
    </div>
</div>

<script>
    const labels = {{ chart_labels | tojson }};
    const data = {{ chart_data | tojson }};

    const ctx = document.getElementById('cmdChart').getContext('2d');
    new Chart(ctx, {
        type: 'bar', // 📊 棒グラフで見やすく表示
        data: {
            labels: labels,
            datasets: [{
                label: '実行回数',
                data: data,
                backgroundColor: '#38bdf8',
                borderRadius: 5
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: { beginAtZero: true, grid: { color: '#334155' }, ticks: { color: '#94a3b8' } },
                x: { grid: { color: '#334155' }, ticks: { color: '#94a3b8' } }
            },
            plugins: { legend: { display: false } }
        }
    });
</script>
</body>
</html>
"""

@app.route('/')
def index():
    guild_count, user_count = db_manager.get_bot_counts()
    chart_labels, chart_data = db_manager.get_command_stats()
    logs = db_manager.get_logs()
    
    return render_template_string(
        HTML_TEMPLATE,
        guild_count=guild_count,
        user_count=user_count,
        chart_labels=chart_labels,
        chart_data=chart_data,
        logs=logs
    )

if __name__ == '__main__':
    db_manager.init_db()
    app.run(debug=True, port=5000)