# ResetX

Optimizador y hub de software para Windows, con interfaz en CustomTkinter.

## Para usuarios (sin instalar Python)

1. Descarga **`ResetX-Setup.exe`** desde [Releases](https://github.com/XiscoVidal/ResetX/releases) (o genera el instalador con `BUILD_INSTALLER.bat`).
2. Ejecuta el instalador y sigue los pasos.
3. Abre **ResetX** desde el menú Inicio o el acceso directo del escritorio.

Windows pedirá permisos de administrador al abrir la app (necesario para la mayoría de optimizaciones).

### Requisitos

- Windows 10/11 (64 bits)
- [Winget](https://apps.microsoft.com/detail/9nblggh4nns1) (opcional, para el Software Hub)

---

## Para desarrolladores

### Desarrollo local

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Para tweaks con permisos elevados: `LAUNCH_ADMIN.bat` o terminal como administrador.

### Generar el instalador (.exe)

Doble clic en **`BUILD_INSTALLER.bat`** o:

```bash
venv\Scripts\activate
pip install -r requirements.txt
pyinstaller resetx.spec --noconfirm --clean
```

- **Portable:** `dist\ResetX\ResetX.exe`
- **Instalador:** instala [Inno Setup 6](https://jrsoftware.org/isinfo.php) y vuelve a ejecutar `BUILD_INSTALLER.bat` → `dist\ResetX-Setup.exe`

## Estructura

- `main.py` — entrada de la aplicación
- `resetx.spec` — configuración PyInstaller
- `installer.iss` — script Inno Setup
- `backend/` — motor de optimización, winget, métricas
- `ui/` — vistas Dashboard, Rendimiento y Software Hub
- `data/` — catálogo de apps
