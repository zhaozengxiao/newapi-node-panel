# -*- coding: utf-8 -*-
"""new-api 节点管理 Web 服务入口。

功能: 渠道看板 / 一键启用(含全部 key) / 批量操作 / 定时规则 / 操作日志
部署: http://192.168.50.242:3434
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, render_template, request  # noqa: E402

import logstore  # noqa: E402
import newapi  # noqa: E402
import scheduler  # noqa: E402

app = Flask(__name__)


def ok(data=None, msg=""):
    return jsonify({"success": True, "message": msg, "data": data})


def fail(msg):
    return jsonify({"success": False, "message": msg})


# ---------- 页面 ----------

@app.get("/")
def index():
    return render_template("index.html")


# ---------- 渠道 ----------

@app.get("/api/channels")
def channels():
    return ok(newapi.list_channels())


@app.get("/api/channels/<int:cid>")
def channel_detail(cid):
    d = newapi.get_channel(cid)
    if not d.get("success"):
        return fail(d.get("message", "查询失败"))
    ks = newapi.get_key_status(cid)
    return ok({"channel": d["data"], "keys": ks.get("data", {})})


@app.post("/api/channels/<int:cid>/enable")
def enable(cid):
    d = newapi.set_status(cid, 1)
    logstore.add("手动", "enable", cid, d.get("success"), d.get("message", ""))
    return jsonify(d)


@app.post("/api/channels/<int:cid>/disable")
def disable(cid):
    d = newapi.set_status(cid, 2)
    logstore.add("手动", "disable", cid, d.get("success"), d.get("message", ""))
    return jsonify(d)


@app.post("/api/channels/<int:cid>/enable_keys")
def enable_keys(cid):
    d = newapi.enable_all_keys(cid)
    logstore.add("手动", "enable_keys", cid, d.get("success"), d.get("message", ""))
    return jsonify(d)


@app.post("/api/channels/<int:cid>/enable_full")
def enable_full(cid):
    """一键启用：恢复全部 key + 渠道启用"""
    k = newapi.enable_all_keys(cid)
    s = newapi.set_status(cid, 1)
    ok_all = k.get("success") and s.get("success")
    msg = f"keys: {k.get('message', '')}; status: {s.get('message', '')}"
    logstore.add("手动", "enable_full", cid, ok_all, msg)
    return ok(msg=msg)


@app.post("/api/channels/<int:cid>/test")
def test(cid):
    model = request.get_json(silent=True) or {}
    d = newapi.test_channel(cid, model.get("model", ""))
    logstore.add("手动", "test", cid, d.get("success"),
                 f"time={d.get('time')}s {d.get('message', '')}".strip())
    return jsonify(d)


@app.post("/api/channels/<int:cid>/key/<int:idx>/enable")
def key_enable(cid, idx):
    d = newapi.enable_key(cid, idx)
    logstore.add("手动", f"enable_key[{idx}]", cid, d.get("success"), d.get("message", ""))
    return jsonify(d)


@app.post("/api/channels/<int:cid>/key/<int:idx>/disable")
def key_disable(cid, idx):
    d = newapi.disable_key(cid, idx)
    logstore.add("手动", f"disable_key[{idx}]", cid, d.get("success"), d.get("message", ""))
    return jsonify(d)


@app.post("/api/channels/batch")
def batch():
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    target = body.get("target") or {}
    ids = list(target.get("ids") or [])
    if not ids:
        filt = target.get("filter")
        channels = newapi.list_channels()
        if filt == "auto_disabled":
            ids = [c["id"] for c in channels if c.get("status") == 3]
        elif filt == "disabled":
            ids = [c["id"] for c in channels if c.get("status") in (2, 3)]
        elif filt == "all":
            ids = [c["id"] for c in channels]
    results = []
    for cid in ids:
        if action == "enable":
            d = newapi.set_status(cid, 1)
        elif action == "disable":
            d = newapi.set_status(cid, 2)
        elif action == "enable_keys":
            d = newapi.enable_all_keys(cid)
        elif action == "enable_full":
            newapi.enable_all_keys(cid)
            d = newapi.set_status(cid, 1)
        else:
            continue
        results.append({"channel": cid, "ok": d.get("success"), "msg": d.get("message", "")})
        logstore.add("批量", action, cid, d.get("success"), d.get("message", ""))
    return ok(results)


# ---------- 定时规则 ----------

@app.get("/api/rules")
def rules_list():
    return ok(scheduler.list_rules())


@app.post("/api/rules")
def rules_add():
    b = request.get_json(silent=True) or {}
    try:
        r = scheduler.add_rule(b.get("name", "未命名"),
                               b.get("cron", "0 * * * *"),
                               b.get("action", "enable"),
                               b.get("target", {}),
                               bool(b.get("enabled", True)))
    except ValueError as e:
        return fail(f"cron 无效: {e}")
    return ok(r)


@app.put("/api/rules/<rid>")
def rules_update(rid):
    b = request.get_json(silent=True) or {}
    try:
        scheduler.update_rule(rid, **b)
    except KeyError:
        return fail("规则不存在")
    return ok()


@app.delete("/api/rules/<rid>")
def rules_delete(rid):
    try:
        scheduler.delete_rule(rid)
    except KeyError:
        return fail("规则不存在")
    return ok()


@app.post("/api/rules/<rid>/trigger")
def rules_trigger(rid):
    try:
        msg = scheduler.trigger(rid)
    except KeyError:
        return fail("规则不存在")
    return ok(msg=msg)


# ---------- 日志 ----------

@app.get("/api/logs")
def logs():
    return ok(logstore.recent())


if __name__ == "__main__":
    scheduler.start()
    app.run(host="0.0.0.0", port=3434, debug=False)
