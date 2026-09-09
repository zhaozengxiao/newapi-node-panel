# -*- coding: utf-8 -*-
"""定时规则管理：规则 JSON 持久化 + APScheduler 调度。

规则结构: {
  "id": "8位hex", "name": "规则名", "cron": "5 8 * * *",
  "action": "enable|disable|test|checkup|enable_keys|enable_full",
  "target": {"ids": [76]} 或 {"filter": "all|auto_disabled|disabled"},
  "enabled": true
}
动作语义:
  enable      渠道启用 (status=1)
  disable     渠道禁用 (status=2)
  enable_keys 恢复该渠道全部 key
  enable_full 一键启用:恢复全部 key + 渠道启用(与前端/手动 API 一致)
  test        测试渠道(首个模型)
  checkup     巡检:恢复全部 key → 测试 → 通过则启用渠道
"""
import json
import os
import threading
import uuid

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import logstore
import newapi

DATA_DIR = os.environ.get("DATA_DIR", "/data")
RULES_FILE = os.path.join(DATA_DIR, "rules.json")

sched = BackgroundScheduler(timezone="Asia/Shanghai")
_lock = threading.Lock()


def _load_rules():
    try:
        with open(RULES_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_rules(rules):
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)


def _target_channels(target):
    """按 target 解析渠道 id 列表"""
    target = target or {}
    ids = target.get("ids") or []
    if ids:
        return list(ids)
    channels = newapi.list_channels()
    filt = target.get("filter")
    if filt == "auto_disabled":
        return [c["id"] for c in channels if c.get("status") == 3]
    if filt == "disabled":
        return [c["id"] for c in channels if c.get("status") in (2, 3)]
    if filt == "all":
        return [c["id"] for c in channels]
    return []


def _run_action(action, cid):
    """对单个渠道执行动作，返回 (ok, msg)"""
    if action == "enable":
        d = newapi.set_status(cid, 1)
        return d.get("success"), d.get("message", "")
    if action == "disable":
        d = newapi.set_status(cid, 2)
        return d.get("success"), d.get("message", "")
    if action == "enable_keys":
        d = newapi.enable_all_keys(cid)
        return d.get("success"), d.get("message", "")
    if action == "enable_full":
        k = newapi.enable_all_keys(cid)
        s = newapi.set_status(cid, 1)
        ok_all = k.get("success") and s.get("success")
        return ok_all, f"keys: {k.get('message', '')}; status: {s.get('message', '')}"
    if action == "test":
        d = newapi.test_channel(cid)
        return d.get("success"), f"time={d.get('time')}s {d.get('message', '')}".strip()
    if action == "checkup":
        newapi.enable_all_keys(cid)
        t = newapi.test_channel(cid)
        if t.get("success"):
            s = newapi.set_status(cid, 1)
            return True, f"测试通过({t.get('time')}s)，渠道已启用"
        return False, f"测试失败: {t.get('message', '')}"
    return False, f"未知动作 {action}"


def execute_rule(rule):
    """执行一条规则的全部目标渠道，返回汇总字符串"""
    action = rule.get("action")
    targets = _target_channels(rule.get("target"))
    if not targets:
        return "目标渠道为空，跳过"
    results = []
    for cid in targets:
        try:
            ok, msg = _run_action(action, cid)
        except Exception as e:  # noqa: BLE001
            ok, msg = False, f"异常: {e}"
        results.append(f"渠道{cid}: {'✓' if ok else '✗'} {msg}")
        logstore.add(rule.get("name", ""), action, cid, ok, msg)
    return "; ".join(results)


def _job(rule_id):
    rules = {r["id"]: r for r in _load_rules()}
    rule = rules.get(rule_id)
    if not rule or not rule.get("enabled"):
        return
    try:
        execute_rule(rule)
    except Exception as e:  # noqa: BLE001
        logstore.add(rule.get("name", ""), rule.get("action"), None, False, f"规则异常: {e}")


def _schedule(rule):
    job_id = f"rule_{rule['id']}"
    existing = sched.get_job(job_id)
    if existing:
        existing.remove()
    if rule.get("enabled"):
        sched.add_job(_job, CronTrigger.from_crontab(rule.get("cron", "0 * * * *")),
                      args=[rule["id"]], id=job_id, replace_existing=True)


def reload_rules():
    for r in _load_rules():
        try:
            _schedule(r)
        except ValueError:
            pass


def list_rules():
    return _load_rules()


def add_rule(name, cron, action, target, enabled=True):
    with _lock:
        rules = _load_rules()
        rule = {"id": uuid.uuid4().hex[:8], "name": name, "cron": cron,
                "action": action, "target": target, "enabled": enabled}
        _schedule(rule)  # 校验 cron，无效会抛 ValueError
        rules.append(rule)
        _save_rules(rules)
        return rule


def update_rule(rid, **fields):
    with _lock:
        rules = _load_rules()
        for r in rules:
            if r["id"] == rid:
                r.update(fields)
                _schedule(r)
                break
        else:
            raise KeyError(rid)
        _save_rules(rules)


def delete_rule(rid):
    with _lock:
        rules = _load_rules()
        rules = [r for r in rules if r["id"] != rid]
        _save_rules(rules)
        job = sched.get_job(f"rule_{rid}")
        if job:
            job.remove()


def trigger(rid):
    with _lock:
        for r in _load_rules():
            if r["id"] == rid:
                return execute_rule(r)
        raise KeyError(rid)


def start():
    if not sched.running:
        sched.start()
        reload_rules()
