from __future__ import annotations

import hashlib
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

import requests


class UserStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def reset(self, database_path: Path | None = None) -> None:
        if database_path is not None:
            self.database_path = database_path
        if self.database_path.exists():
            self.database_path.unlink()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def login_with_wechat_code(self, code: str, dev_openid: str = "") -> dict[str, Any]:
        openid = self._resolve_openid(code, dev_openid)
        now = time.time()
        with self._connect() as conn:
            row = conn.execute("select id from users where openid = ?", (openid,)).fetchone()
            if row:
                user_id = str(row["id"])
                conn.execute("update users set last_login_at = ? where id = ?", (now, user_id))
            else:
                user_id = uuid.uuid4().hex
                conn.execute(
                    "insert into users (id, openid, created_at, last_login_at) values (?, ?, ?, ?)",
                    (user_id, openid, now, now),
                )
            token = uuid.uuid4().hex
            conn.execute(
                "insert into sessions (token, user_id, created_at) values (?, ?, ?)",
                (token, user_id, now),
            )
        return {"token": token, "user": {"userId": user_id, "openid": openid}}

    def get_user_by_token(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                select users.id, users.openid, users.created_at, users.last_login_at
                from sessions
                join users on users.id = sessions.user_id
                where sessions.token = ?
                """,
                (token,),
            ).fetchone()
        if row is None:
            return None
        return {
            "userId": str(row["id"]),
            "openid": str(row["openid"]),
            "createdAt": float(row["created_at"]),
            "lastLoginAt": float(row["last_login_at"]),
        }

    def record_usage(self, user_id: str | None, event: str, task_id: str = "", metadata: dict[str, Any] | None = None) -> None:
        if not user_id:
            return
        with self._connect() as conn:
            conn.execute(
                "insert into usage_records (id, user_id, task_id, event, metadata, created_at) values (?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, user_id, task_id, event, repr(metadata or {}), time.time()),
            )

    def list_usage(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select task_id, event, metadata, created_at
                from usage_records
                where user_id = ?
                order by created_at desc
                limit ?
                """,
                (user_id, limit),
            ).fetchall()
        return [
            {
                "taskId": str(row["task_id"]),
                "event": str(row["event"]),
                "metadata": str(row["metadata"]),
                "createdAt": float(row["created_at"]),
            }
            for row in rows
        ]

    def _resolve_openid(self, code: str, dev_openid: str = "") -> str:
        appid = os.getenv("WECHAT_APPID", "").strip()
        secret = os.getenv("WECHAT_SECRET", "").strip()
        if not appid or not secret:
            source = dev_openid.strip() or code or "local-dev"
            digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]
            return f"dev_{digest}"
        response = requests.get(
            "https://api.weixin.qq.com/sns/jscode2session",
            params={"appid": appid, "secret": secret, "js_code": code, "grant_type": "authorization_code"},
            timeout=10,
        )
        response.raise_for_status()
        body = response.json()
        openid = str(body.get("openid") or "").strip()
        if not openid:
            raise ValueError(f"WeChat login failed: {body}")
        return openid

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                create table if not exists users (
                    id text primary key,
                    openid text not null unique,
                    created_at real not null,
                    last_login_at real not null
                );
                create table if not exists sessions (
                    token text primary key,
                    user_id text not null,
                    created_at real not null,
                    foreign key(user_id) references users(id)
                );
                create table if not exists usage_records (
                    id text primary key,
                    user_id text not null,
                    task_id text not null,
                    event text not null,
                    metadata text not null,
                    created_at real not null,
                    foreign key(user_id) references users(id)
                );
                """
            )
