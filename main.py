"""ResetX — System Optimizer & Software Hub (UI web con pywebview)."""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import webview

from backend.api import Api
from backend.utils import get_resource_path


def main():
    api = Api()
    index = os.path.join(get_resource_path(), "webui", "index.html")
    window = webview.create_window(
        "ResetX",
        index,
        js_api=api,
        width=1280,
        height=820,
        min_size=(980, 640),
        background_color="#080b10",
        maximized=True,
    )
    api.set_window(window)
    webview.start()


if __name__ == "__main__":
    main()
