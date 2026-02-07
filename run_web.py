"""
AI Crawler Web UI - Startup Script
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from web.app import app, socketio

if __name__ == '__main__':
    print("=" * 50)
    print("  AI Crawler Web UI")
    print("=" * 50)
    print()
    print("  启动中...")
    print()
    print("  访问地址: http://localhost:5000")
    print()
    print("  按 Ctrl+C 停止服务")
    print("=" * 50)
    
    # Flask-SocketIO blocks running on Werkzeug by default (newer versions).
    # This project uses it for local development, so explicitly allow it here.
    socketio.run(
        app,
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
    )
