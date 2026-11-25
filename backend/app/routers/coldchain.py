
from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import settings
from app.database import get_db_connection
from app.influx import query_influx


router = APIRouter(
    prefix="/api/v1/coldchain",
    tags=["Cold-Chain"],
)


# =========================
# API KEY AUTHENTICATION
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
# HELPER: LATEST TELEMETRY
# =========================

def get_latest_telemetry(device_id: str = None):
    device_filter = ""

    if device_id:
        if not all(c.isalnum() or c in "-_" for c in device_id):
            raise HTTPException(
                status_code=400,
                detail="Device ID tidak valid",
            )

        device_filter = f'''
            |> filter(fn: (r) => r.device_id == "{device_id}")
        '''

    flux_query = f'''
        from(bucket: "{settings.INFLUXDB_BUCKET}")
            |> range(start: -24h)
            |> filter(fn: (r) =>
                r._measurement == "coldchain_telemetry"
            )
            |> filter(fn: (r) =>
                r._field == "temp_c" or
                r._field == "humidity_pct" or
                r._field == "door_open"
            )
            {device_filter}
            |> pivot(
                rowKey: ["_time"],
                columnKey: ["_field"],
                valueColumn: "_value"
            )
            |> group(columns: ["device_id"])
            |> sort(columns: ["_time"], desc: true)
            |> limit(n: 1)
    '''

    records = query_influx(flux_query)

    telemetry = {}

    for record in records:
        device = record.get("device_id")

        if device:
            telemetry[device] = {
                "timestamp": record.get("_time"),
                "temp_c": record.get("temp_c"),
                "humidity_pct": record.get("humidity_pct"),
                "door_open": record.get("door_open"),
            }

    return telemetry


# =========================
# GET ALL CHAMBERS
# =========================

@router.get(
    "/chambers",
    dependencies=[Depends(verify_api_key)],
)
def get_chambers():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT device_id, domain, gedung, ruang,
                           status, last_seen
                    FROM devices
                    WHERE domain = 'coldchain'
                    ORDER BY device_id
                """)

                devices = cur.fetchall()

        telemetry = get_latest_telemetry()

        chambers = []

        for device in devices:
            device_data = dict(device)
            device_id = device_data["device_id"]

            device_data["telemetry"] = telemetry.get(device_id)

            chambers.append(device_data)

        return {
            "count": len(chambers),
            "data": chambers,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# GET CHAMBER DETAIL
# =========================

@router.get(
    "/chambers/{device_id}",
    dependencies=[Depends(verify_api_key)],
)
def get_chamber(device_id: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT device_id, domain, gedung, ruang,
                           status, last_seen
                    FROM devices
                    WHERE device_id = %s
                      AND domain = 'coldchain'
                    """,
                    (device_id,),
                )

                device = cur.fetchone()

                if not device:
                    raise HTTPException(
                        status_code=404,
                        detail="Chamber tidak ditemukan",
                    )

        device_data = dict(device)
        telemetry = get_latest_telemetry(device_id)

        device_data["telemetry"] = telemetry.get(device_id)

        return device_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# GET COLD-CHAIN ESCALATIONS
# =========================

@router.get(
    "/escalations",
    dependencies=[Depends(verify_api_key)],
)
def get_escalations():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        alert_id,
                        device_id,
                        alert_type,
                        severity,
                        message,
                        status,
                        triggered_at,
                        acknowledged_at,
                        acknowledged_by,
                        resolved_at,
                        metadata
                    FROM alert_events
                    WHERE alert_type = 'TEMP_ESCALATED'
                    ORDER BY triggered_at DESC
                """)

                alerts = cur.fetchall()

                return {
                    "count": len(alerts),
                    "data": alerts,
                }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
