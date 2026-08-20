# -*- coding: utf-8 -*-
"""new-api 管理 API 客户端。

token 不硬编码：每次从 postgres 的 users.access_token 实时读取（带 TTL 缓存），
DB 重建 / token 轮换后无需改任何配置。管理操作全部走 HTTP API，不直写数据库。
"""
import os
import time
from urllib.parse import quote

import psycopg2
import requests

_TOKEN_CACHE = {"val": None, "ts": 0.0}
TOKEN_TTL = 300  # token 缓存秒数

BASE = os.environ.get("NEWAPI_BASE", "http://new-api:3000").rstrip("/")


def _pg_conn():
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "postgres"),
        port=int(os.environ.get("PG_PORT", "5432")),
        user=os.environ.get("PG_USER", "root"),
        password=os.environ.get("PG_PASSWORD", ""),
        dbname=os.environ.get("PG_DB", "new-api"),
        connect_timeout=5,
    )


def get_token():
    now = time.time()
    if _TOKEN_CACHE["val"] and now - _TOKEN_CACHE["ts"] < TOKEN_TTL:
        return _TOKEN_CACHE["val"]
    conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT access_token FROM users WHERE id=1")
        row = cur.fetchone()
        if not row:
            raise RuntimeError("users.access_token not found (user id=1)")
        _TOKEN_CACHE["val"] = row[0]
        _TOKEN_CACHE["ts"] = now
        return row[0]
    finally:
        conn.close()


def _call(method, path, body=None, timeout=60):
    url = BASE + path
    headers = {"Authorization": "Bearer " + get_token(), "New-Api-User": "1"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        resp = requests.request(method, url, headers=headers, json=body,
                                timeout=timeout, allow_redirects=False)
    except requests.RequestException as e:
        return {"success": False, "message": f"请求失败: {e}"}
    # 缺尾斜杠时的 301/307：补斜杠重试并保持方法（new-api 的已知坑）
    if resp.status_code in (301, 302, 307, 308):
        try:
            resp = requests.request(method, url + "/", headers=headers,
                                    json=body, timeout=timeout)
        except requests.RequestException as e:
            return {"success": False, "message": f"重试失败: {e}"}
    try:
        data = resp.json()
    except ValueError:
        return {"success": False,
                "message": f"非JSON响应 HTTP {resp.status_code}: {resp.text[:200]}"}
    if not data.get("success", False):
        data.setdefault("message", f"HTTP {resp.status_code}")
    return data


# ---------- 渠道 ----------

def list_channels():
    """渠道列表（/api/channel/search 主路径；分页参数是 page_size 不是 size）"""
    d = _call("GET", "/api/channel/search?p=1&page_size=200")
    if not d.get("success"):
        return []
    return d.get("data", {}).get("items", [])


def get_channel(cid):
    return _call("GET", f"/api/channel/{cid}")


def set_status(cid, status):
    """渠道状态：1=启用 2=手动禁用（官方安全端点，不碰 key）"""
    return _call("POST", f"/api/channel/{cid}/status", {"status": status})


def test_channel(cid, model=""):
    path = f"/api/channel/test/{cid}"
    if model:
        path += "?model=" + quote(model)
    return _call("GET", path, timeout=120)


# ---------- 多 key 管理（rc.25 官方端点） ----------

def multi_key(cid, action, **kw):
    body = {"channel_id": cid, "action": action}
    body.update(kw)
    return _call("POST", "/api/channel/multi_key/manage", body)


def get_key_status(cid):
    """key 状态列表：index/status/disabled_time/reason/key_preview + 统计"""
    return multi_key(cid, "get_key_status", page=1, page_size=100)


def enable_all_keys(cid):
    """一键恢复渠道全部 key（清空禁用状态）"""
    return multi_key(cid, "enable_all_keys")


def enable_key(cid, idx):
    return multi_key(cid, "enable_key", key_index=idx)


def disable_key(cid, idx):
    return multi_key(cid, "disable_key", key_index=idx)
