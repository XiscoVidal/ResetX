# ResetX

Optimizador y hub de software para Windows, con interfaz en CustomTkinter.

## Requisitos

- Windows 10/11
- Python 3.11+
- [Winget](https://apps.microsoft.com/detail/9nblggh4nns1) (para el Software Hub)

## Instalación

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

```bash
python main.py
```

Para tweaks que requieren administrador, ejecuta `LAUNCH_ADMIN.bat` o abre la terminal como admin.

## Estructura

- `main.py` — entrada de la aplicación
- `backend/` — motor de optimización, winget, métricas
- `ui/` — vistas Dashboard, Rendimiento y Software Hub
- `data/` — catálogo de apps y datos locales
