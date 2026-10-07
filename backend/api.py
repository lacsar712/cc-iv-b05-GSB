import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from jose import JWTError, jwt
from litestar import Litestar, Request, get, post
from litestar.exceptions import HTTPException
from litestar.response import Response
from litestar.status_codes import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND
from passlib.context import CryptContext
from psycopg.types.json import Jsonb
from psycopg import IsolationLevel

from db import SCHEMA, connect
from rules import judge

SECRET = os.environ.get("JWT_SECRET", "pvivscan-dev-secret")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
USERS = {
    "scanner": {"role": "writer", "password_hash": pwd.hash("scan123456")},
    "watcher": {"role": "reader", "password_hash": pwd.hash("watch123456")},
}


def dump(row):
    out = dict(row)
    for key, val in list(out.items()):
        if hasattr(val, "isoformat"):
            out[key] = val.isoformat()
    return out


def seed():
    with connect() as conn:
        conn.execute(SCHEMA)
        n = conn.execute("SELECT COUNT(*) AS n FROM iv_scans").fetchone()["n"]
        if n == 0:
            now = datetime.now(timezone.utc)
            samples = [
                ("阵列A-串03", 41.2, 9.1, 0.78, "合格"),
                ("阵列B-串11", 38.0, 8.4, 0.61, "衰减"),
            ]
            for code, voc, isc, ff, expect in samples:
                verdict, reason = judge(ff)
                assert verdict == expect
                conn.execute(
                    """INSERT INTO iv_scans
                       (string_code, voc_v, isc_a, fill_factor, status, verdict, reason,
                        created_by, created_at, processed_at)
                       VALUES (%s,%s,%s,%s,'done',%s,%s,'scanner',%s,%s)""",
                    (code, voc, isc, ff, verdict, reason, now, now),
                )
        conn.commit()


seed()


def user_from(request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    try:
        payload = jwt.decode(auth.split(" ", 1)[1].strip(), SECRET, algorithms=["HS256"])
    except JWTError:
        return None
    sub = payload.get("sub")
    if sub not in USERS:
        return None
    return {"username": sub, "role": payload.get("role")}


def need_login(request: Request):
    user = user_from(request)
    if user is None:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="未登录")
    return user


def need_writer(request: Request, detail: str = "仅扫描员可执行此操作"):
    user = need_login(request)
    if user["role"] != "writer":
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail=detail)
    return user


@get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "pv-string-iv-scan"}


@post("/api/auth/login")
async def login(request: Request) -> dict:
    data = await request.json()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    user = USERS.get(username)
    if not user or not pwd.verify(password, user["password_hash"]):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode(
        {"sub": username, "role": user["role"], "exp": exp}, SECRET, algorithm="HS256"
    )
    return {"access_token": token, "username": username, "role": user["role"]}


@get("/api/logs")
async def list_logs(request: Request) -> list:
    need_login(request)
    with connect() as conn:
        rows = conn.execute(
            """SELECT id, string_code, voc_v, isc_a, fill_factor, status, verdict, reason,
                      created_by, created_at, processed_at
               FROM iv_scans ORDER BY id DESC"""
        ).fetchall()
        return [dump(r) for r in rows]


@post("/api/logs", status_code=201)
async def create_log(request: Request) -> dict:
    user = need_writer(request)
    data = await request.json()
    code = (data.get("string_code") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="组串编号不能为空")
    try:
        voc = float(data.get("voc_v"))
        isc = float(data.get("isc_a"))
        ff = float(data.get("fill_factor"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="电压电流与填充因子必须是数字")
    now = datetime.now(timezone.utc)
    with connect() as conn:
        row = conn.execute(
            """INSERT INTO iv_scans
               (string_code, voc_v, isc_a, fill_factor, status, created_by, created_at)
               VALUES (%s,%s,%s,%s,'pending',%s,%s)
               RETURNING id, string_code, voc_v, isc_a, fill_factor, status, verdict, reason,
                         created_by, created_at, processed_at""",
            (code, voc, isc, ff, user["username"], now),
        ).fetchone()
        conn.commit()
        return dump(row)


def render_book_body(stamped_at, stamped_by, counts, scans):
    lines = [
        "交班本",
        f"盖章时间：{stamped_at:%Y-%m-%d %H:%M:%S} UTC",
        f"交班人：{stamped_by}",
        "",
        "盖章瞬间三张计数：",
        f"  在线单据总数：{counts['total']}",
        f"  合格：{counts['pass']}",
        f"  衰减：{counts['decay']}",
        "",
        "盖章瞬间在线单据明细：",
    ]
    if not scans:
        lines.append("  （一张单据都没有）")
    else:
        for r in scans:
            verdict = r["verdict"] or "—"
            lines.append(
                f"  #{r['id']} {r['string_code']} Voc={r['voc_v']} Isc={r['isc_a']} "
                f"FF={r['fill_factor']} 状态={r['status']} 结论={verdict}"
            )
    return "\n".join(lines)


@get("/api/handover-books")
async def list_handover_books(request: Request) -> list:
    need_login(request)
    with connect() as conn:
        rows = conn.execute(
            """SELECT id, stamped_at, stamped_by, total_count, pass_count,
                      decay_count, pending_count
               FROM shift_handover_books ORDER BY id DESC"""
        ).fetchall()
        return [dump(r) for r in rows]


@get("/api/handover-books/{book_id:int}")
async def get_handover_book(book_id: int, request: Request) -> dict:
    need_login(request)
    with connect() as conn:
        row = conn.execute(
            """SELECT id, stamped_at, stamped_by, total_count, pass_count,
                      decay_count, pending_count, body, snapshot
               FROM shift_handover_books WHERE id = %s""",
            (book_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="这本交班本不存在")
        return dump(row)


@post("/api/handover-books", status_code=201)
async def stamp_handover_book(request: Request) -> dict:
    user = need_writer(request, detail="仅扫描员可盖交班章，观察员只能翻看已盖的本")
    stamped_at = datetime.now(timezone.utc)
    with connect() as conn:
        # REPEATABLE READ：计数与明细共用同一快照，全部取自按下盖章这一瞬
        conn.isolation_level = IsolationLevel.REPEATABLE_READ
        with conn.transaction():
            counts_row = conn.execute(
                """SELECT
                     COUNT(*) AS total,
                     COUNT(*) FILTER (WHERE verdict = '合格') AS pass,
                     COUNT(*) FILTER (WHERE verdict = '衰减') AS decay,
                     COUNT(*) FILTER (WHERE status = 'pending') AS pending
                   FROM iv_scans"""
            ).fetchone()
            scans = conn.execute(
                """SELECT id, string_code, voc_v, isc_a, fill_factor, status, verdict, reason,
                          created_by, created_at, processed_at
                   FROM iv_scans ORDER BY id DESC"""
            ).fetchall()
            counts = {
                "total": counts_row["total"],
                "pass": counts_row["pass"],
                "decay": counts_row["decay"],
                "pending": counts_row["pending"],
            }
            snapshot = [dump(r) for r in scans]
            body = render_book_body(
                stamped_at, user["username"], counts, [dict(r) for r in scans]
            )
            book = conn.execute(
                """INSERT INTO shift_handover_books
                   (stamped_at, stamped_by, total_count, pass_count, decay_count,
                    pending_count, body, snapshot)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id, stamped_at, stamped_by, total_count, pass_count,
                             decay_count, pending_count, body, snapshot""",
                (
                    stamped_at,
                    user["username"],
                    counts["total"],
                    counts["pass"],
                    counts["decay"],
                    counts["pending"],
                    body,
                    Jsonb(snapshot),
                ),
            ).fetchone()
        conn.commit()
        return dump(book)


app = Litestar(
    route_handlers=[
        health,
        login,
        list_logs,
        create_log,
        list_handover_books,
        get_handover_book,
        stamp_handover_book,
    ]
)
