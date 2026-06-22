# ResetX

Optimizador y hub de software para Windows, con interfaz en CustomTkinter.

## Para usuarios

1. Descarga **`ResetX-Setup.exe`** desde [Releases](https://github.com/XiscoVidal/ResetX/releases).
2. Ejecuta el instalador.
3. Abre **ResetX** desde el menú Inicio.

La app comprueba actualizaciones al iniciar y puede instalarlas automáticamente.

### Aviso de SmartScreen

Si Windows muestra *"SmartScreen impidió el inicio de una aplicación desconocida"*, es normal en apps sin certificado de firma de código. Opciones:

- Clic en **Más información** → **Ejecutar de todas formas**
- El desarrollador puede eliminar el aviso firmando el `.exe` con un certificado **OV/EV** (ver `docs/SIGNING.md`)

### Requisitos

- Windows 10/11 (64 bits)
- [Winget](https://apps.microsoft.com/detail/9nblggh4nns1) (opcional, para el Software Hub)

---

## Para desarrolladores

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Generar instalador

Doble clic en **`BUILD_INSTALLER.bat`** → `dist\ResetX-Setup.exe`

Incluye generación de iconos (`assets/resetx.svg` → `.ico`/`.png`), metadatos de versión y empaquetado PyInstaller + Inno Setup.

### Publicar release

1. Actualiza `version.py`
2. Ejecuta `BUILD_INSTALLER.bat`
3. Sube `dist\ResetX-Setup.exe` a GitHub Releases con el tag `vX.Y.Z`

La app instalada detectará la nueva release y ofrecerá actualizar.
