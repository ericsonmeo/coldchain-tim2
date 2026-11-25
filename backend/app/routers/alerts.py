
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.database import get_db_connection


router = APIRouter(tags=["Alerts"])


# =========================
# AUTHENTICATION
# =========================

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


# =========================
# ALERT MODEL
# =========================

class AlertCreate(BaseModel):
    device_id: str
    alert_type: str
    severity: str
    message: str
    metadata: dict = {}


class AlertAcknowledge(BaseModel):
    acknowledged_by: str


# =========================
# INTERNAL: CREATE ALERT
# =========================

@router.post(
    "/api/v1/internal/alerts",
    dependencies=[Depends(verify_api_key)],
)
def create_alert(alert: AlertCreate):
    if alert.severity not in ["info", "warning", "critical"]:
        raise HTTPException(
            status_code=400,
            detail="Severity tidak valid",
        )

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO alert_events (
                        device_id,
                        alert_type,
                        severity,
                        message,
                        metadata
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        alert.device_id,
                        alert.alert_type,
                        alert.severity,
                        alert.message,
                        __import__("json").dumps(alert.metadata),
                    ),
                )

                result = cur.fetchone()

        return {
            "message": "Alert berhasil disimpan",
            "data": result,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# GET ALL ALERTS
# =========================

@router.get(
    "/api/v1/alerts",
    dependencies=[Depends(verify_api_key)],
)
def get_alerts(status: str = None):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if status:
                    if status not in ["active", "acknowledged", "resolved"]:
                        raise HTTPException(
                            status_code=400,
                            detail="Status tidak valid",
                        )

                    cur.execute(
                        """
                        SELECT * FROM alert_events
                        WHERE status = %s
                        ORDER BY triggered_at DESC
                        """,
                        (status,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM alert_events
                        ORDER BY triggered_at DESC
                        """
                    )

                alerts = cur.fetchall()

        return {
            "count": len(alerts),
            "data": alerts,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# GET ALERT DETAIL
# =========================

@router.get(
    "/api/v1/alerts/{alert_id}",
    dependencies=[Depends(verify_api_key)],
)
def get_alert(alert_id: int):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM alert_events
                    WHERE alert_id = %s
                    """,
                    (alert_id,),
                )

                alert = cur.fetchone()

        if not alert:
            raise HTTPException(
                status_code=404,
                detail="Alert tidak ditemukan",
            )

        return alert

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# ACKNOWLEDGE ALERT
# =========================

@router.post(
    "/api/v1/alerts/{alert_id}/ack",
    dependencies=[Depends(verify_api_key)],
)
def acknowledge_alert(alert_id: int, body: AlertAcknowledge):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE alert_events
                    SET status = 'acknowledged',
                        acknowledged_at = NOW(),
                        acknowledged_by = %s
                    WHERE alert_id = %s
                      AND status = 'active'
                    RETURNING *
                    """,
                    (body.acknowledged_by, alert_id),
                )

                alert = cur.fetchone()

        if not alert:
            raise HTTPException(
                status_code=404,
                detail="Alert aktif tidak ditemukan",
            )

        return {
            "message": "Alert berhasil di-acknowledge",
            "data": alert,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# INTERNAL: AUTO ESCALATION
# =========================

@router.post(
    "/api/v1/internal/alerts/escalate",
    dependencies=[Depends(verify_api_key)],
)
def escalate_alerts():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO alert_events (
                        device_id,
                        alert_type,
                        severity,
                        message,
                        metadata
                    )
                    SELECT
                        a.device_id,
                        'TEMP_ESCALATED',
                        'critical',
                        'Alert belum di-acknowledge selama 5 menit',
                        jsonb_build_object(
                            'original_alert_id', a.alert_id,
                            'original_alert_type', a.alert_type
                        )
                    FROM alert_events a
                    WHERE a.status = 'active'
                      AND a.alert_type = 'TEMP_HIGH'
                      AND a.triggered_at <= NOW() - INTERVAL '5 minutes'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM alert_events e
                          WHERE e.alert_type = 'TEMP_ESCALATED'
                            AND e.metadata->>'original_alert_id' = a.alert_id::text
                      )
                    RETURNING *
                    """
                )

                escalations = cur.fetchall()

        return {
            "message": "Pemeriksaan eskalasi selesai",
            "count": len(escalations),
            "data": escalations,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# RESOLVE ALERT
# =========================

@router.post(
    "/api/v1/alerts/{alert_id}/resolve",
    dependencies=[Depends(verify_api_key)],
)
def resolve_alert(alert_id: int):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE alert_events
                    SET status = 'resolved',
                        resolved_at = NOW()
                    WHERE alert_id = %s
                      AND status IN ('active', 'acknowledged')
                    RETURNING *
                    """,
                    (alert_id,),
                )

                alert = cur.fetchone()

        if not alert:
            raise HTTPException(
                status_code=404,
                detail="Alert tidak ditemukan atau sudah resolved",
            )

        return {
            "message": "Alert berhasil di-resolve",
            "data": alert,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================
# RESOLVE ALL DEVICE ALERTS
# =========================

@router.post(
    "/api/v1/internal/alerts/resolve-device/{device_id}",
    dependencies=[Depends(verify_api_key)],
)
def resolve_device_alerts(device_id: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE alert_events
                    SET status = 'resolved',
                        resolved_at = NOW()
                    WHERE device_id = %s
                      AND alert_type IN (
                          'TEMP_WARN',
                          'TEMP_HIGH',
                          'TEMP_ESCALATED'
                      )
                      AND status IN ('active', 'acknowledged')
                    RETURNING *
                    """,
                    (device_id,),
                )

                alerts = cur.fetchall()

        return {
            "message": "Alert perangkat berhasil di-resolve",
            "device_id": device_id,
            "count": len(alerts),
            "data": alerts,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



