import os
import requests
import threading
from PIL import Image
import customtkinter as ctk
from backend.utils import get_data_path, get_resource_path


class IconManager:
    def __init__(self, cache_dir="icons"):
        self.resource_icons = os.path.join(get_resource_path(), "assets", "icons")
        self.cache_dir = os.path.join(get_data_path(), cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)
        self._loaded_images = {}
        self._download_queue = set()

    def _resolve_icon_path(self, app_id: str) -> str:
        cached = os.path.join(self.cache_dir, f"{app_id}.png")
        if os.path.exists(cached):
            return cached
        bundled = os.path.join(self.resource_icons, f"{app_id}.png")
        if os.path.exists(bundled):
            return bundled
        return cached

    def get_icon(self, app_id, domain=None, size=(128, 128), callback=None):
        icon_path = self._resolve_icon_path(app_id)

        if not os.path.exists(icon_path) and domain and app_id not in self._download_queue:
            self._download_queue.add(app_id)
            dest = os.path.join(self.cache_dir, f"{app_id}.png")
            threading.Thread(
                target=self._download_icon,
                args=(app_id, domain, dest, size, callback),
                daemon=True,
            ).start()

        if app_id not in self._loaded_images:
            try:
                if not os.path.exists(icon_path):
                    pil_image = Image.new("RGBA", size, color=(0, 0, 0, 0))
                    ctk_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=size)
                    return ctk_image

                pil_image = Image.open(icon_path)
                ctk_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=size)
                self._loaded_images[app_id] = ctk_image
            except Exception as e:
                print(f"Error cargando icono para {app_id}: {e}")
                return None

        return self._loaded_images[app_id]

    def _download_icon(self, app_id, domain, icon_path, size, callback):
        try:
            url = f"https://icons.duckduckgo.com/ip3/{domain}.ico"
            response = requests.get(url, timeout=5)
            if response.status_code == 200 and len(response.content) > 100:
                with open(icon_path, "wb") as f:
                    f.write(response.content)
                if app_id in self._loaded_images:
                    del self._loaded_images[app_id]
                if callback:
                    callback(app_id)
        except Exception as e:
            print(f"Error descargando icono para {app_id}: {e}")
        finally:
            self._download_queue.discard(app_id)
