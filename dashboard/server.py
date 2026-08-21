"""
ATIG Command & Control Dashboard Server
Flask + SocketIO backend serving the tactical dashboard.
Accepts alerts via both MQTT and direct HTTP ingestion from nodes.
"""

import sys
import os
import time

# Ensure dashboard directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO
from mqtt_client import ATIGMQTTClient

app = Flask(__name__)
app.config['SECRET_KEY'] = 'atig-tactical-grid'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Initialize MQTT Client with SocketIO for real-time push
mqtt_client = ATIGMQTTClient(socketio=socketio)
mqtt_client.start()

# ─── Page Routes ─────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

# ─── API Endpoints ───────────────────────────────────────────────────

@app.route('/api/alerts')
def api_alerts():
    """Get recent alerts and active threat count."""
    recent_alerts = mqtt_client.get_recent_alerts(50)
    recent_threats_count = sum(
        1 for alert in recent_alerts
        if time.time() - alert.get('timestamp', 0) < 30
    )
    return jsonify({
        'active_threats': recent_threats_count,
        'alerts': recent_alerts[:15]
    })


@app.route('/api/stats')
def api_stats():
    """Get threat statistics for the Analysis tab."""
    return jsonify(mqtt_client.get_threat_stats())


@app.route('/api/nodes')
def api_nodes():
    """Get active node statuses."""
    return jsonify({'nodes': mqtt_client.get_active_nodes()})


@app.route('/api/system')
def api_system():
    """Get system-wide metrics."""
    return jsonify(mqtt_client.get_system_info())


@app.route('/api/rover/status')
def api_rover_status():
    """Get current rover state."""
    return jsonify(mqtt_client.get_rover_status())


@app.route('/api/rover/command', methods=['POST'])
def api_rover_command():
    """Send a command to the rover."""
    data = request.get_json()
    command = data.get('command', '')
    valid_commands = ['deploy', 'patrol', 'return', 'stop', 'forward', 'back', 'left', 'right']
    if command not in valid_commands:
        return jsonify({'error': f'Invalid command. Valid: {valid_commands}'}), 400
    result = mqtt_client.send_rover_command(command)
    return jsonify(result)


# ─── Direct HTTP Ingest (bypasses MQTT for local nodes) ──────────────

@app.route('/api/ingest/alert', methods=['POST'])
def ingest_alert():
    """Receive an alert directly from a surveillance node via HTTP.
    This bypasses MQTT entirely for local deployments."""
    payload = request.get_json()
    if not payload:
        return jsonify({'error': 'No payload'}), 400

    # Use the same handler as MQTT
    mqtt_client._handle_alert(payload)
    mqtt_client.message_count += 1
    return jsonify({'status': 'ok'})


@app.route('/api/ingest/heartbeat', methods=['POST'])
def ingest_heartbeat():
    """Receive a heartbeat directly from a surveillance node via HTTP."""
    payload = request.get_json()
    if not payload:
        return jsonify({'error': 'No payload'}), 400

    mqtt_client._handle_heartbeat(payload)
    mqtt_client.message_count += 1
    return jsonify({'status': 'ok'})


# ─── SocketIO Events ─────────────────────────────────────────────────

@socketio.on('connect')
def handle_connect():
    print("[Server] Dashboard client connected via SocketIO.")


@socketio.on('disconnect')
def handle_disconnect():
    print("[Server] Dashboard client disconnected.")


# ─── Entry Point ─────────────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 60)
    print("  ATIG — Autonomous Tactical Intelligence Grid")
    print("  Command & Control Dashboard")
    print("=" * 60)
    print(f"  Dashboard:  http://localhost:8502")
    print(f"  Ingest:     http://localhost:8502/api/ingest/alert")
    print(f"  MQTT:       {mqtt_client.connected and 'Connected' or 'Optional (HTTP ingest active)'}")
    print("=" * 60)

    try:
        socketio.run(
            app,
            host='0.0.0.0',
            port=8502,
            debug=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True
        )
    except KeyboardInterrupt:
        print("\n[Server] Shutting down...")
    finally:
        mqtt_client.stop()
