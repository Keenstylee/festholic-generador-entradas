# Reconstrucción inteligente de códigos QR físicos

MVP universitario que recibe una fotografía, busca el código QR con varias
estrategias de preprocesamiento, corrige su perspectiva, reconstruye una imagen
binaria limpia y verifica que el resultado siga siendo legible.

## Instalación en Windows CMD

```bat
python -m venv .venv
.venv\Scripts\activate.bat
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Ejecución

```bat
.venv\Scripts\python.exe -m streamlit run app.py
```

## Instalación en PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## API para Festholic

La misma lógica puede exponerse para que el frontend JavaScript envíe la
fotografía y reciba el PNG procesado por Python:

```powershell
python -m uvicorn api:app --host 0.0.0.0 --port 8000
```

Endpoint: `POST /reconstruir-qr`, campo multipart `file`. La respuesta es
`image/png`; si la reconstrucción no se valida, responde JSON con `success`
igual a `false`.

## Pruebas

```bat
.venv\Scripts\python.exe -m pytest
```

## Criterio de fidelidad

El sistema no crea un QR nuevo a partir del texto. Limpia la matriz obtenida de
la imagen rectificada por el detector. Una salida se marca como validada solo si
el lector puede decodificarla y su contenido coincide con el detectado en la
entrada.

La recuperación no es garantizable cuando la fotografía perdió más información
que la admitida por el nivel de corrección de errores del QR.
