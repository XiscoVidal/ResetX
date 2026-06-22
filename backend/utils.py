import os
import sys

APP_NAME = "ResetX"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def get_resource_path() -> str:
    """Ruta de solo lectura (recursos empaquetados o raíz del proyecto en desarrollo)."""
    if is_frozen():
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_data_path() -> str:
    """Ruta escribible para estado local (AppData en exe, data/ en desarrollo)."""
    if is_frozen():
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        path = os.path.join(base, APP_NAME)
    else:
        path = os.path.join(get_resource_path(), "data")
    os.makedirs(path, exist_ok=True)
    return path


def get_base_path() -> str:
    """Alias de compatibilidad → recursos empaquetados."""
    return get_resource_path()


def apply_window_icon(window) -> None:
    """Icono de ventana y barra de tareas (ICO preferido en Windows)."""
    import tkinter as tk

    base = get_resource_path()
    ico = os.path.join(base, "assets", "resetx.ico")
    png = os.path.join(base, "assets", "resetx.png")
    try:
        if os.path.exists(ico):
            window.iconbitmap(default=ico)
            return
        if os.path.exists(png):
            img = tk.PhotoImage(file=png)
            window.iconphoto(True, img)
            window._icon_image_ref = img
    except Exception:
        pass


def request_admin_restart() -> bool:
    """Reinicia la app con elevación UAC. True si ya se ejecuta como administrador."""
    import ctypes

    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return True
    except Exception:
        pass

    try:
        if is_frozen():
            executable = sys.executable
            params = " ".join(f'"{arg}"' for arg in sys.argv[1:])
        else:
            executable = sys.executable
            params = f'"{os.path.abspath(sys.argv[0])}"'

        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params or None, None, 1)
        if ret > 32:
            sys.exit(0)
    except Exception:
        pass
    return False
