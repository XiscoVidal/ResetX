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
