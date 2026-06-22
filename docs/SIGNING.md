# Firma de código (eliminar aviso SmartScreen)

SmartScreen bloquea ejecutables **sin reputación** y **sin firma Authenticode**. No hay forma de quitarlo solo con código: hace falta un certificado de firma de código.

## Pasos recomendados

1. Comprar certificado **OV** o **EV** de un proveedor reconocido (DigiCert, Sectigo, SSL.com, etc.).
2. Exportar como `.pfx`.
3. Antes de compilar, definir variables de entorno:

```bat
set RESETX_SIGN_PFX=C:\certs\resetx.pfx
set RESETX_SIGN_PASSWORD=tu_contraseña
BUILD_INSTALLER.bat
```

4. El script `scripts\sign_release.bat` firmará `ResetX.exe` y `ResetX-Setup.exe`.

## Certificado EV

Con certificado **EV**, SmartScreen suele dejar de mostrar el aviso en cuanto se publica la primera versión firmada. Con **OV** puede tardar unas descargas hasta ganar reputación.

## Sin certificado

Los usuarios deben usar **Más información → Ejecutar de todas formas**. La app incluye metadatos de versión y publisher en el ejecutable para mayor transparencia, pero no sustituye la firma.
