from flask import Flask, render_template
import sqlite3
import os

app = Flask(__name__)
DB_NAME = "intruder_logs.db"

def get_logs():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row # Allows accessing columns by name
    cursor = conn.cursor()
    # Get logs sorted by newest first
    cursor.execute("SELECT * FROM logs ORDER BY id DESC")
    data = cursor.fetchall()
    conn.close()
    return data

@app.route('/')
def index():
    logs = get_logs()
    return render_template('index.html', logs=logs)

if __name__ == '__main__':
    # Run on http://127.0.0.1:5000
    app.run(debug=True, port=5000)