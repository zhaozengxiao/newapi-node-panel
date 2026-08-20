# -*- coding: utf-8 -*-
"""操作日志：内存环形缓冲（最近 200 条）+ JSONL 落盘（data/ops.log）"""
import json
import os
import time

DATA_DIR = os.environ.get("DATA_DIR", "/data")
LOG_FILE = os.path.join(DATA_DIR, "ops.log")
MAX_RING = 200

_ring = []


def add(rule_name, action, cid, ok, msg):
    entry = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "rule": rule_name,
        "action": action,
        "channel": cid,
        "ok": bool(ok),
        "msg": str(msg)[:300],
    }
    _ring.append(entry)
    if len(_ring) > MAX_RING:
        _ring.pop(0)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def recent(n=100):
    return _ring[-n:][::-1]
