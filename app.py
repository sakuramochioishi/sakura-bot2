from flask import Flask, render_template_string, jsonify
import db_manager

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Bot リアルタイムグラフモニター</title>
    <meta http-equiv="refresh" content="10"> <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: 'Helvetica Neue', Arial, sans-serif; background: #0e1626; color: #fff; margin: 40px; text-align: center; }
        .monitor-card { max-width: 600px; margin: 0 auto; background: #1b263b; padding: 30px; border-radius: 15px; box-shadow: 0 8px 20px rgba(0,0,0,0.5); border: 1px solid #00b4d8; }
        h1 { color: #00b4d8; font-size: 24px; margin-bottom: 25px; }
        .stat-box { margin: 20px 0; padding: 10px; background: #0d1b2a; border-radius: 10px; font-size: 16px; }
        .chart-container { background: #0d1b2a; padding: 20px; border-radius: 10px; margin-top: 20px; }
        .footer { font-size: 12px; color: #64ffda; margin-top: 20px; }
    </style>
</head>
<body>
<div class="monitor-card">
    <h1>📊 Bot リアルタイム回線モニター</h1>
    
    <div class="stat-box">
        🎭 ステータス: <strong>{{ status_text }}</strong>
    </div>

    <div class="chart-container">
        <canvas id="pingChart"></canvas>
    </div>

    <div class="footer">
        🔄 最終更新: {{ last_update }} (10秒ごとに自動更新)
    </div>
</div>

<script>
    // Python側から渡されたデータをJavaScriptに変換
    const labels = {{ labels | tojson }};
    const data = {{ data | tojson }};

    const ctx = document.getElementById('pingChart').getContext('2d');
    const pingChart = new Chart(ctx, {
        type: 'line', // 折れ線グラフ
        data: {
            labels: labels,
            datasets: [{
                label: 'Ping値 (ms)',
                data: data,
                borderColor: '#52b788',
                backgroundColor: 'rgba(82, 183, 136, 0.2)',
                borderWidth: 3,
                tension: 0.3, // 線のなめらかさ
                fill: true
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(255, 255, 255, 0.1)' },
                    ticks: { color: '#8892b0' }
                },
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.1)' },
                    ticks: { color: '#8892b0' }
                }
            },
            plugins: {
                legend: { labels: { color: '#fff' } }
            }
        }
    });
</script>
</body>
</html>
"""

@app.route('/')
def index():
    status_text, last_update = db_manager.get_status_text()
    labels, data = db_manager.get_ping_history()
    
    return render_template_string(
        HTML_TEMPLATE,
        status_text=status_text,
        last_update=last_update,
        labels=labels,
        data=data
    )

if __name__ == '__main__':
    db_manager.init_db()
    app.run(debug=True, port=5000)