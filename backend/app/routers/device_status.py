
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.database import get_db_connection


router = APIRouter(
    prefix="/api/v1/internal",
    tags=["Device Status"],
)


def verify_api_key(x_api_key: str = Header(default="")):
    if not settings.API_KEY:
        raise HTTPException(
            status_code=500,
            detail="API_KEY belum dikonfigurasi",
        )

    if x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=401,
            detail="API Key tidak valid",
        )


class DeviceStatus(BaseModel):
    device_id: str
    status: str
    ts: int | None = None


@router.post(
    "/device-status",
    dependencies=[Depends(verify_api_key)],
)
def update_device_status(payload: DeviceStatus):
    if payload.status not in ("online", "offline"):
        raise HTTPException(
            status_code=400,
            detail="Status harus online atau offline",
        )

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE devices
                    SET status = %s,
                        last_seen = CASE
                            WHEN %s = 'online' THEN %s
                            ELSE last_seen
                        END,
                        updated_at = NOW()
                    WHERE device_id = %s
                      AND domain = 'coldchain'
                    RETURNING device_id, status, last_seen
                    """,
                    (
                        payload.status,
                        payload.status,
                        (
                            datetime.fromtimestamp(
                                payload.ts / 1000,
                                tz=timezone.utc,
                            )
                            if payload.ts is not None
                            else datetime.now(timezone.utc)
                        ),
                        payload.device_id,
                    ),
                )

                device = cur.fetchone()

                if not device:
                    raise HTTPException(
                        status_code=404,
                        detail="Device tidak ditemukan",
                    )

                return {
                    "message": "Status perangkat berhasil diperbarui",
                    "data": device,
                }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
