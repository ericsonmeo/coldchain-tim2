from fastapi import FastAPI, Depends, HTTPException, Header
from app.config import settings
from app.database import get_db_connection
from app.influx import query_influx
from app.routers.coldchain import router as coldchain_router
from app.routers.device_status import router as device_status_router
from app.routers.alerts import router as alerts_router



app = FastAPI(
    title="Cold-Chain IoT API",
    description="API untuk monitoring sistem cold-chain",
    version="1.0.0",
)

app.include_router(coldchain_router)
app.include_router(device_status_router)
app.include_router(alerts_router)


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
# HEALTH CHECK
# =========================

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "coldchain-api",
    }


# =========================
# DEVICE ENDPOINTS
# =========================

@app.get(
    "/api/v1/devices",
    dependencies=[Depends(verify_api_key)],
)
def get_devices():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT device_id, domain, gedung, ruang,
                           status, last_seen
                    FROM devices
                    ORDER BY device_id
                """)
                return cur.fetchall()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/api/v1/devices/{device_id}",
    dependencies=[Depends(verify_api_key)],
)
def get_device(device_id: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT device_id, domain, gedung, ruang,
                           status, last_seen
                    FROM devices
                    WHERE device_id = %s
                    """,
                    (device_id,),
                )
                device = cur.fetchone()

                if not device:
                    raise HTTPException(
                        status_code=404,
                        detail="Device tidak ditemukan",
                    )

                return device

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get(
    "/api/v1/devices/{device_id}/status",
    dependencies=[Depends(verify_api_key)],
)
def get_device_status(device_id: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT device_id, status, last_seen
                    FROM devices
                    WHERE device_id = %s
                    """,
                    (device_id,),
                )

                device = cur.fetchone()

                if not device:
                    raise HTTPException(
                        status_code=404,
                        detail="Device tidak ditemukan",
                    )

                return device

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================
# TELEMETRY ENDPOINT
# =========================

@app.get(
    "/api/v1/telemetry/latest",
    dependencies=[Depends(verify_api_key)],
)
def get_latest_telemetry(device_id: str = None):
    try:
        if device_id and not all(
            c.isalnum() or c in "-_" for c in device_id
        ):
            raise HTTPException(
                status_code=400,
                detail="Device ID tidak valid",
            )

        device_filter = ""

        if device_id:
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

        return {
            "count": len(records),
            "data": records,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))