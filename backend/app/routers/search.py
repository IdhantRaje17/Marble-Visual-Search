import time
from io import BytesIO
from fastapi import APIRouter, Depends, File, UploadFile, Query, HTTPException
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.middleware.auth import get_current_account
from app.models.admin import Admin
from app.models.search_log import SearchLog
from app.models.tile import Tile
from app.services.search_service import run_visual_search
from ai.gatekeeper import NOT_TILE, VALIDATION_UNAVAILABLE, VALID_TILE, validate_tile_image

GATEKEEPER_REJECTION_MESSAGE = (
    "Please upload a valid marble, tile, or stone surface image."
)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED_IMAGE_TYPES = {"JPEG", "PNG", "WEBP"}

router = APIRouter(prefix="/api/search", tags=["Visual Search"])

# ── Single-image search (original — unchanged) ────────────
@router.post("/image")
async def search_by_image(
    file: UploadFile = File(...),
    top_k: int = Query(3, ge=1, le=10),
    material_id: Optional[int] = Query(None),
    color_family_id: Optional[int] = Query(None),
    min_confidence: float = Query(0.0, ge=0.0, le=100.0),
    db: Session = Depends(get_db),
    account: Admin = Depends(get_current_account),
):
    try:
        start_time = time.time()

        if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(status_code=415, detail="Upload a JPEG, PNG, or WebP image.")

        image_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
        if not image_bytes:
            raise HTTPException(status_code=400, detail="The uploaded image is empty.")
        if len(image_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Image must be 10 MB or smaller.")

        try:
            with Image.open(BytesIO(image_bytes)) as uploaded_image:
                if uploaded_image.format not in SUPPORTED_IMAGE_TYPES:
                    raise HTTPException(status_code=415, detail="Upload a JPEG, PNG, or WebP image.")
                uploaded_image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="The uploaded file is not a valid image.") from exc

        gatekeeper_result = validate_tile_image(image_bytes)
        validation_status = gatekeeper_result.get("status", VALIDATION_UNAVAILABLE)
        if validation_status == NOT_TILE:
            raise HTTPException(
                status_code=400,
                detail={
                    "status": NOT_TILE,
                    "message": GATEKEEPER_REJECTION_MESSAGE,
                },
            )
        if validation_status not in {VALID_TILE, VALIDATION_UNAVAILABLE}:
            raise HTTPException(
                status_code=503,
                detail={
                    "status": VALIDATION_UNAVAILABLE,
                    "message": "Tile validation unavailable. Search is blocked until validation is available.",
                },
            )

        # Run visual search
        search_response = run_visual_search(
            db=db,
            image_bytes=image_bytes,
            top_k=top_k,
            min_confidence=min_confidence / 100,
            material_id=material_id,
            color_family_id=color_family_id
        )

        # Extract results and validation info
        results = search_response.get("results", [])
        validation = {
            "status": validation_status,
            "is_tile": validation_status == VALID_TILE,
            "score": gatekeeper_result.get("score") if validation_status == VALID_TILE else None,
            "message": (
                "Tile image validated."
                if validation_status == VALID_TILE
                else "Tile validation was unavailable; visual matches are unverified."
            ),
        }
        error_msg = search_response.get("error", None)

        response_time_ms = int((time.time() - start_time) * 1000)

        # Log the search
        top_match = results[0] if results else None
        log = SearchLog(
            account_id       = account.id,
            query_image_url = "uploaded_image",
            matched_tile_id  = top_match["tile_id"] if top_match else None,
            confidence       = top_match["confidence"] / 100 if top_match else None,
            response_time_ms = response_time_ms,
            status           = (
                "matched"        if top_match and top_match["confidence"] >= 75
                else "low_confidence" if top_match
                else "no_match"
            )
        )
        db.add(log)
        db.commit()

        return {
            "results":         results,
            "total_found":     len(results),
            "response_time_ms": response_time_ms,
            "status":          log.status,
            "validation":      validation
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        import sys
        tb = traceback.format_exc()
        print(f"ERROR in search_by_image: {str(e)}", file=sys.stderr)
        print(tb, file=sys.stderr)
        sys.stderr.flush()
        raise HTTPException(status_code=500, detail={
            "message": "search image failed",
            "error": str(e),
            "traceback": tb,
            "hint": "restart backend and run seed_tiles.py if missing embeddings"
        })


@router.get("/history")
def search_history(
    limit: int = Query(50),
    db: Session = Depends(get_db),
    account: Admin = Depends(get_current_account),
):
    rows = db.query(
        SearchLog,
        Tile.sku.label("tile_sku"),
        Tile.name.label("tile_name"),
    ).outerjoin(
        Tile, Tile.id == SearchLog.matched_tile_id
    ).filter(
        SearchLog.account_id == account.id
    ).order_by(
        SearchLog.searched_at.desc()
    ).limit(limit).all()
    return [{
        "id": log.id,
        "account_id": log.account_id,
        "query_image_url": log.query_image_url,
        "matched_tile_id": log.matched_tile_id,
        "confidence": log.confidence,
        "response_time_ms": log.response_time_ms,
        "status": log.status,
        "searched_at": log.searched_at,
        "tile_sku": tile_sku,
        "tile_name": tile_name,
    } for log, tile_sku, tile_name in rows]