import sys
import threading
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

# importing metrics starts the /metrics server before streamlit gets its first visitor
import metrics  # noqa
import captioner

threading.Thread(target=captioner.get_shared, daemon=True).start()

from streamlit.web import cli

# file watcher off, otherwise it spams torchvision import errors from transformers
sys.argv = ["streamlit", "run", str(APP_DIR / "streamlit_app.py"), "--server.headless", "true", "--server.fileWatcherType", "none", *sys.argv[1:]]
sys.exit(cli.main())
