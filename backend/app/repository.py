"""SQLite persistence: immutable import/run snapshots and append-only audit decisions."""

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4


class Repository:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS imports(id TEXT PRIMARY KEY, created TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS fetches(id TEXT PRIMARY KEY, created TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS webhook_receipts(id TEXT PRIMARY KEY, digest TEXT NOT NULL, event TEXT NOT NULL, created TEXT NOT NULL, outcome TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, created TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY, run_id TEXT NOT NULL, case_id TEXT NOT NULL, created TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS webhooks(id TEXT PRIMARY KEY, created TEXT NOT NULL, outcome TEXT NOT NULL);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    def audit(self, action, actor, payload, db=None):
        if db is not None:
            db.execute(
                "INSERT INTO audit(created,action,actor,payload) VALUES(?,?,?,?)",
                (self.now(), action, actor, json.dumps(payload)),
            )
        else:
            with self.connect() as conn:
                self.audit(action, actor, payload, conn)

    def save(self, kind, payload):
        ident, created = uuid4().hex, self.now()
        with self.connect() as db:
            db.execute(
                f"INSERT INTO {kind}(id,created,payload) VALUES(?,?,?)",
                (ident, created, json.dumps(payload)),
            )
            self.audit(
                kind + "_created",
                "local",
                {
                    "id": ident,
                    "source": payload.get("source"),
                    "provenance": payload.get("provenance"),
                },
                db,
            )
        return {"id": ident, "created": created, **payload}

    def get(self, kind, ident):
        with self.connect() as db:
            row = db.execute(f"SELECT * FROM {kind} WHERE id=?", (ident,)).fetchone()
        if not row:
            raise KeyError(ident)
        return {"id": ident, "created": row["created"], **json.loads(row["payload"])}

    def runs(self):
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM runs ORDER BY created DESC LIMIT 25"
            ).fetchall()
        return [
            {
                "id": r["id"],
                "created": r["created"],
                "metrics": json.loads(r["payload"])["metrics"],
                "provenance": json.loads(r["payload"])["provenance"],
            }
            for r in rows
        ]

    def reviewed(self, run):
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM decisions WHERE run_id=? ORDER BY created", (run["id"],)
            ).fetchall()
        with self.connect() as db:
            investigations = db.execute(
                "SELECT payload FROM audit WHERE action='investigation' ORDER BY id"
            ).fetchall()
        explanations = {}
        for entry in investigations:
            payload = json.loads(entry["payload"])
            if payload.get("run_id") == run["id"]:
                explanations[payload["case_id"]] = payload["result"]
        decisions = {}
        for r in rows:
            decisions[r["case_id"]] = json.loads(r["payload"])
        for c in run["cases"]:
            c["investigation"] = explanations.get(c["id"])
            c["review"] = decisions.get(c["id"])
            c["effective_status"] = (
                c["review"]["new_status"] if c["review"] else c["status"]
            )
        return run

    def decide(self, run_id, case_id, actor, action, note):
        statuses = {
            "confirm": "MATCHED",
            "reject": "UNMATCHED",
            "partial": "PARTIAL",
            "duplicate": "DUPLICATE",
            "unresolved": "REVIEW",
            "note": None,
        }
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            if not row:
                raise KeyError(run_id)
            run = json.loads(row["payload"])
            c = next((c for c in run["cases"] if c["id"] == case_id), None)
            if not c:
                raise KeyError(case_id)
            if action in ("confirm", "partial") and not c["right"]:
                raise ValueError("A candidate allocation is required for this decision")
            latest = db.execute(
                "SELECT payload FROM decisions WHERE run_id=? AND case_id=? ORDER BY created DESC LIMIT 1",
                (run_id, case_id),
            ).fetchone()
            previous = (
                json.loads(latest["payload"])["new_status"] if latest else c["status"]
            )
            payload = {
                "actor": actor,
                "action": action,
                "note": note,
                "previous_status": previous,
                "new_status": statuses[action] or previous,
                "automated_status": c["automated_status"],
                "case_id": case_id,
                "run_id": run_id,
            }
            ident, created = uuid4().hex, self.now()
            db.execute(
                "INSERT INTO decisions VALUES(?,?,?,?,?)",
                (ident, run_id, case_id, created, json.dumps(payload)),
            )
            self.audit("manual_decision", actor, payload, db)
        return {"id": ident, "created": created, **payload}

    def audits(self):
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM audit ORDER BY id DESC LIMIT 10000"
            ).fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    def receive_webhook(self, event_id, digest, event):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT digest FROM webhook_receipts WHERE id=?", (event_id,)
            ).fetchone()
            if previous:
                if previous["digest"] != digest:
                    raise ValueError("Event identifier reused with a different payload")
                return {"event_id": event_id, "outcome": "duplicate_ignored"}
            db.execute(
                "INSERT INTO webhook_receipts VALUES(?,?,?,?,?)",
                (event_id, digest, event, self.now(), "recorded_not_applied"),
            )
            self.audit(
                "webhook_received",
                "razorpay",
                {
                    "event_id": event_id,
                    "event": event,
                    "outcome": "recorded_not_applied",
                },
                db,
            )
        return {"event_id": event_id, "outcome": "recorded_not_applied"}
