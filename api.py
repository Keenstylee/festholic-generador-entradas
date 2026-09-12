from __future__ import annotations

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import cv2
import numpy as np

from src.pipeline import process_image
from src.reconstruction import encode_png

app = FastAPI(title="Festholic QR Reconstruction API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.post("/reconstruir-qr")
async def reconstruct_qr(file: UploadFile = File(...)):
    data = await file.read()
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return {"success": False, "message": "El archivo no es una imagen válida."}

    result = process_image(image)
    if not result.success or not result.validated or result.clean is None:
        return {"success": False, "message": result.message}

    return Response(
        content=encode_png(result.clean),
        media_type="image/png",
        headers={"X-QR-Content": result.validation_text},
    )

