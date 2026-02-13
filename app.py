from fastapi import FastAPI, Response, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import sqlite3
from pathlib import Path

app = FastAPI(title="Resume API", version="1.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://docs.dealapiops.dev"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RESUME_PATH = Path(__file__).parent / "resume.json"
DB_PATH = Path("/var/lib/resume-api/metrics.db")


def load_resume() -> dict:
    if not RESUME_PATH.exists():
        return {"error": "resume.json not found"}
    return json.loads(RESUME_PATH.read_text(encoding="utf-8"))


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=5)
    cur = con.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("CREATE TABLE IF NOT EXISTS counters (key TEXT PRIMARY KEY, value INTEGER NOT NULL)")
    con.commit()
    return con


def inc_counter(key: str, amount: int = 1) -> None:
    con = _connect()
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO counters(key, value) VALUES (?, 0)", (key,))
    cur.execute("UPDATE counters SET value = value + ? WHERE key = ?", (amount, key))
    con.commit()
    con.close()


def get_counter(key: str) -> int:
    con = _connect()
    cur = con.cursor()
    cur.execute("SELECT value FROM counters WHERE key = ?", (key,))
    row = cur.fetchone()
    con.close()
    return int(row[0]) if row else 0


@app.get("/")
def root(request: Request):
    inc_counter("api_calls")
    r = load_resume()
    b = r.get("basics", {})
    return {
        "service": "resume-api",
        "name": b.get("name"),
        "label": b.get("label"),
        "endpoints": ["/resume", "/resume.min", "/resume.txt", "/health", "/metrics", "/visit"],
        "documentation": "https://docs.dealapiops.dev"
    }


@app.get("/health")
def health(request: Request):
    inc_counter("api_calls")
    return {"status": "ok"}


@app.get("/metrics")
def metrics(request: Request):
    inc_counter("api_calls")
    return {
        "site_visits": get_counter("site_visits"),
        "api_calls": get_counter("api_calls")
    }


@app.get("/visit")
def visit(request: Request):
    inc_counter("site_visits")
    inc_counter("api_calls")
    return {"status": "counted"}


@app.get("/resume")
def resume(request: Request):
    inc_counter("api_calls")
    return JSONResponse(content=load_resume())


@app.get("/resume.min")
def resume_min(request: Request):
    inc_counter("api_calls")
    r = load_resume()
    return {
        "basics": r.get("basics", {}),
        "work": r.get("work", []),
        "skills": r.get("skills", []),
        "certificates": r.get("certificates", []),
        "education": r.get("education", [])
    }


@app.get("/resume.txt")
def resume_txt(request: Request):
    inc_counter("api_calls")
    r = load_resume()
    b = r.get("basics", {})

    lines = []
    name = b.get("name", "")
    label = b.get("label", "")
    email = b.get("email", "")

    loc = b.get("location", {}) or {}
    location = ", ".join([x for x in [loc.get("city", ""), loc.get("region", "")] if x])

    if name or label:
        lines.append(" | ".join([x for x in [name, label] if x]))
    if email:
        lines.append(email)
    if location:
        lines.append(location)

    lines.append("")
    lines.append("SUMMARY")
    lines.append(b.get("summary", ""))

    lines.append("")
    lines.append("SKILLS")
    for s in r.get("skills", []):
        sname = s.get("name", "")
        kws = ", ".join(s.get("keywords", []))
        if sname and kws:
            lines.append(f"- {sname}: {kws}")
        elif sname:
            lines.append(f"- {sname}")

    lines.append("")
    lines.append("EXPERIENCE")
    for w in r.get("work", []):
        pos = w.get("position", "")
        comp = w.get("name", "")
        start = w.get("startDate", "")
        end = w.get("endDate", "") or "Present"
        header = " | ".join([x for x in [pos, comp] if x]).strip()
        dates = " - ".join([x for x in [start, end] if x]).strip()
        if header:
            lines.append(header)
        if dates:
            lines.append(dates)
        for h in w.get("highlights", [])[:5]:
            lines.append(f"  - {h}")
        lines.append("")

    text = "\n".join(lines).strip() + "\n"
    return Response(content=text, media_type="text/plain; charset=utf-8")
