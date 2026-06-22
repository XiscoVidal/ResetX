import sys
import os

def get_base_path():
    """
    Returns the base path of the application.
    Works for both development and PyInstaller bundled environments.
    """
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
