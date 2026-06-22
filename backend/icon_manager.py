import os
import requests
import threading
from PIL import Image
import customtkinter as ctk
from backend.utils import get_base_path

class IconManager:
    def __init__(self, cache_dir="assets/icons"):
        base_dir = get_base_path()
        self.cache_dir = os.path.join(base_dir, cache_dir.replace("/", os.sep))
        os.makedirs(self.cache_dir, exist_ok=True)
        # Diccionario para mantener las imágenes cargadas en memoria (evitar garbage collection)
        self._loaded_images = {}
        self._download_queue = set()

    def get_icon(self, app_id, domain=None, size=(128, 128), callback=None):
        # Retorna un CTkImage listo para usar
        
        # 1. Comprobar caché local
        icon_path = os.path.join(self.cache_dir, f"{app_id}.png")
            
        # 2. Descargar si no existe y tenemos dominio
        if not os.path.exists(icon_path) and domain and app_id not in self._download_queue:
            self._download_queue.add(app_id)
            threading.Thread(target=self._download_icon, args=(app_id, domain, icon_path, size, callback), daemon=True).start()
            
        # 3. Cargar y retornar
        if app_id not in self._loaded_images:
            try:
                if not os.path.exists(icon_path):
                    # Fallback silencioso mientras descarga
                    pil_image = Image.new('RGBA', size, color=(0,0,0,0))
                    ctk_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=size)
                    return ctk_image
                else:
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
                with open(icon_path, 'wb') as f:
                    f.write(response.content)
                # Forzar recarga en memoria
                if app_id in self._loaded_images:
                    del self._loaded_images[app_id]
                
                if callback:
                    callback(app_id)
        except Exception as e:
            print(f"Error descargando icono para {app_id}: {e}")
        finally:
            if app_id in self._download_queue:
                self._download_queue.remove(app_id)
