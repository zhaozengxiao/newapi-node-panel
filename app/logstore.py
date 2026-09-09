# -*- coding: utf-8 -*-
"""操作日志:内存环形缓冲(最近 200 条)+ JSONL 落盘(data/ops.log);启动时从磁盘回填历史,重启后日志不丢。"""
import json
import os
import time

DATA_DIR = os.environ.get("DATA_DIR", "/data")
LOG_FILE = os.path.join(DATA_DIR, "ops.log")
MAX_RING = 200

_ring = []


def _load():
    """启动时从磁盘 ops.log 回填内存环形缓冲(容错:跳过坏行,超过 200 条只保留最新的)。"""
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                _ring.append(entry)
                if len(_ring) > MAX_RING:
                    _ring.pop(0)
    except OSError:
        pass


_load()


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
