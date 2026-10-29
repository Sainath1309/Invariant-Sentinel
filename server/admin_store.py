"""Small SQLite store for service administration and durable drift incidents."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AdminStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    @contextmanager
    def db(self):
        con = self.connect()
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def init_db(self):
        with self.db() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS clients (
              id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
              contact_email TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
              notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS incidents (
              id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER,
              dataset TEXT NOT NULL, run_id TEXT NOT NULL, batch_index INTEGER NOT NULL,
              verdict TEXT NOT NULL, title TEXT NOT NULL, headline TEXT NOT NULL,
              suspect TEXT, confidence TEXT, evidence_json TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL,
              UNIQUE(run_id, batch_index), FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS recommendations (
              id INTEGER PRIMARY KEY AUTOINCREMENT, incident_id INTEGER NOT NULL,
              recommended_method TEXT NOT NULL, payload_json TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending_review', created_at TEXT NOT NULL,
              FOREIGN KEY(incident_id) REFERENCES incidents(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS audit_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL,
              action TEXT NOT NULL, details_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_incidents_created ON incidents(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
            """)

    def audit(self, actor, action, details=None):
        with self.db() as c:
            c.execute("INSERT INTO audit_log(actor,action,details_json,created_at) VALUES(?,?,?,?)",
                      (actor, action, json.dumps(details or {}), now_iso()))

    def add_client(self, name, email="", status="active", notes=""):
        name = (name or "").strip()
        if not name:
            raise ValueError("Client name is required.")
        if status not in ("active", "paused"):
            raise ValueError("Status must be active or paused.")
        with self.db() as c:
            cur = c.execute("INSERT INTO clients(name,contact_email,status,notes,created_at) VALUES(?,?,?,?,?)",
                            (name, (email or "").strip(), status, (notes or "").strip(), now_iso()))
            row = c.execute("SELECT * FROM clients WHERE id=?", (cur.lastrowid,)).fetchone()
            return dict(row)

    def clients(self):
        with self.db() as c:
            return [dict(r) for r in c.execute("""SELECT c.*,
              (SELECT COUNT(*) FROM incidents i WHERE i.client_id=c.id) incident_count
              FROM clients c ORDER BY c.created_at DESC""")]

    def update_client(self, client_id, fields):
        allowed = {k: fields[k] for k in ("name", "contact_email", "status", "notes") if k in fields}
        if "name" in allowed and not str(allowed["name"]).strip():
            raise ValueError("Client name is required.")
        if "status" in allowed and allowed["status"] not in ("active", "paused"):
            raise ValueError("Status must be active or paused.")
        if not allowed:
            raise ValueError("No editable client fields were supplied.")
        with self.db() as c:
            cur = c.execute("UPDATE clients SET " + ",".join(f"{k}=?" for k in allowed) + " WHERE id=?",
                             [str(v).strip() for v in allowed.values()] + [client_id])
            if not cur.rowcount:
                return None
            return dict(c.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone())

    def add_incident(self, run_id, dataset, batch_index, result):
        evidence = {"issues": result.get("issues", []), "masked": result.get("masked", []),
                    "candidates": result.get("candidates", []), "baseline": result.get("baseline", {}),
                    "mae": result.get("mae"), "mae_ref": result.get("mae_ref")}
        with self.db() as c:
            c.execute("""INSERT OR IGNORE INTO incidents
              (dataset,run_id,batch_index,verdict,title,headline,suspect,confidence,evidence_json,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?)""", (dataset, run_id, batch_index, result.get("verdict", "unclear"),
              result.get("title", "Drift incident"), result.get("headline", ""), result.get("suspect"),
              result.get("confidence"), json.dumps(evidence), now_iso()))
            row = c.execute("SELECT * FROM incidents WHERE run_id=? AND batch_index=?", (run_id, batch_index)).fetchone()
            return dict(row) if row else None

    def incidents(self, status=None):
        with self.db() as c:
            if status and status != "all":
                rows = c.execute("SELECT i.*, c.name AS client_name FROM incidents i LEFT JOIN clients c ON c.id=i.client_id WHERE i.status=? ORDER BY i.created_at DESC LIMIT 500", (status,))
            else:
                rows = c.execute("SELECT i.*, c.name AS client_name FROM incidents i LEFT JOIN clients c ON c.id=i.client_id ORDER BY i.created_at DESC LIMIT 500")
            out = []
            for r in rows:
                item = dict(r)
                item["evidence"] = json.loads(item.pop("evidence_json") or "{}")
                rec = c.execute("SELECT id,payload_json,status FROM recommendations WHERE incident_id=? ORDER BY id DESC LIMIT 1", (item["id"],)).fetchone()
                item["recommendation"] = ({"id": rec["id"], "payload": json.loads(rec["payload_json"]), "status": rec["status"]} if rec else None)
                out.append(item)
            return out

    def get_incident(self, incident_id):
        with self.db() as c:
            r = c.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone()
            if not r: return None
            item = dict(r); item["evidence"] = json.loads(item.pop("evidence_json") or "{}")
            return item

    def save_recommendation(self, incident_id, payload):
        with self.db() as c:
            c.execute("INSERT INTO recommendations(incident_id,recommended_method,payload_json,status,created_at) VALUES(?,?,?,?,?)",
                      (incident_id, payload["recommended_method"], json.dumps(payload), payload.get("status", "pending_review"), now_iso()))
            c.execute("UPDATE incidents SET status='in_review' WHERE id=? AND status='open'", (incident_id,))
            return c.execute("SELECT last_insert_rowid()").fetchone()[0]

    def update_incident_status(self, incident_id, status):
        if status not in ("open", "in_review", "resolved", "dismissed"):
            raise ValueError("Status must be open, in_review, resolved, or dismissed.")
        with self.db() as c:
            cur = c.execute("UPDATE incidents SET status=? WHERE id=?", (status, incident_id))
            return bool(cur.rowcount)


    def update_incident_client(self, incident_id, client_id):
        with self.db() as c:
            if client_id is not None and not c.execute("SELECT 1 FROM clients WHERE id=?", (client_id,)).fetchone():
                raise ValueError("Choose an existing client.")
            cur = c.execute("UPDATE incidents SET client_id=? WHERE id=?", (client_id, incident_id))
            return bool(cur.rowcount)

    def overview(self, dataset_count, run_count):
        with self.db() as c:
            scalar = lambda q: c.execute(q).fetchone()[0]
            return {"clients": scalar("SELECT COUNT(*) FROM clients"),
                    "active_clients": scalar("SELECT COUNT(*) FROM clients WHERE status='active'"),
                    "datasets": dataset_count, "runs_this_session": run_count,
                    "incidents": scalar("SELECT COUNT(*) FROM incidents"),
                    "open_incidents": scalar("SELECT COUNT(*) FROM incidents WHERE status IN ('open','in_review')"),
                    "recommendations": scalar("SELECT COUNT(*) FROM recommendations"),
                    "recent_incidents": [dict(r) for r in c.execute("SELECT id,dataset,verdict,title,headline,status,created_at FROM incidents ORDER BY created_at DESC LIMIT 6")],
                    "audit": [dict(r) for r in c.execute("SELECT actor,action,details_json,created_at FROM audit_log ORDER BY id DESC LIMIT 8")]}
