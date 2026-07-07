#!/usr/bin/env python3
"""AnySearch probe — stdlib-only CLI with multi-key rotation + state tracking.

Key pool state lives in keys-state.json (single source of truth):
  {
    "rr_index": 0,
    "rotation": "fallback",       # fallback | round-robin
    "auto_register": false,       # auto-register when all keys exhausted
    "keys": [
      {
        "key": "as_sk_xxx",
        "prefix": "as_sk_xxx…",
        "name": "auto-key",
        "source": "manual",        # manual | register | auto_register | migrated
        "status": "active",        # active | exhausted | invalid
        "added_at": "ISO timestamp",
        "call_count": 0,
        "last_used": null,
        "last_error": null,
        "exhausted_at": null
      }
    ]
  }

Rotation modes:
  fallback    (default) key1 until exhausted → key2 → … → anonymous
  round-robin each call uses the next key in the pool, cycling back to start.
              Dead keys are skipped; if all dead, falls back to anonymous.
"""
import json, os, sys, time, random, string, urllib.request, urllib.error

ENDPOINT = "https://api.anysearch.com/mcp"
WEB_API = "https://anysearch.com"

# Error texts that signal a dead key (rotate to next)
_DEAD_SIGNALS = ("invalid_api_key", "quota_exhausted", "rate_limit", "limit_exceeded")


def _skill_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

def _state_path():
    return os.path.join(_skill_dir(), "keys-state.json")

def _old_env_path():
    """Legacy .env path — only used for one-time migration."""
    return os.path.join(_skill_dir(), ".env")


# ── key state: single source of truth ─────────────────────────────────────────

def _default_state():
    return {"rr_index": 0, "rotation": "fallback", "auto_register": False, "keys": []}


def _new_key_entry(key, source="manual", name=None):
    return {
        "key": key,
        "prefix": key[:12] + "…",
        "name": name or "",
        "source": source,
        "status": "active",
        "added_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "call_count": 0,
        "last_used": None,
        "last_error": None,
        "exhausted_at": None,
    }


def _load_key_state():
    """Load key pool state from keys-state.json.

    On first run, migrates from .env (if it exists) or ANYSEARCH_API_KEYS env var.
    """
    path = _state_path()
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                state = json.load(f)
            # Backfill missing fields for forward-compat
            state.setdefault("rr_index", 0)
            state.setdefault("rotation", "fallback")
            state.setdefault("auto_register", False)
            state.setdefault("keys", [])
            return state
        except (json.JSONDecodeError, OSError):
            pass

    # First run — migrate from .env or env vars
    state = _default_state()
    seen = set()

    # Legacy .env file
    env_path = _old_env_path()
    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip("\"'")
                if k == "ANYSEARCH_API_KEYS":
                    for key in v.split(","):
                        key = key.strip()
                        if key and key not in seen:
                            seen.add(key)
                            state["keys"].append(_new_key_entry(key, source="migrated"))
                elif k == "ANYSEARCH_API_KEY" and v and v not in seen:
                    seen.add(v)
                    state["keys"].append(_new_key_entry(v, source="migrated"))
                elif k == "ANYSEARCH_ROTATION":
                    state["rotation"] = v
                elif k == "ANYSEARCH_AUTO_REGISTER":
                    state["auto_register"] = v in ("1", "true", "yes", "on")

    # Env vars (override .env)
    for env_k in ("ANYSEARCH_API_KEYS",):
        v = os.environ.get(env_k, "")
        if v:
            for key in v.split(","):
                key = key.strip()
                if key and key not in seen:
                    seen.add(key)
                    state["keys"].append(_new_key_entry(key, source="migrated"))
    single = os.environ.get("ANYSEARCH_API_KEY", "")
    if single and single not in seen:
        seen.add(single)
        state["keys"].append(_new_key_entry(single, source="migrated"))

    _save_key_state(state)
    return state


def _save_key_state(state):
    try:
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except OSError as e:
        print(f"[warn] Could not save key state: {e}", file=sys.stderr)


def _active_keys(state):
    return [e["key"] for e in state["keys"] if e["status"] == "active"]


def _add_key_to_state(key, source="manual", name=None):
    """Add a key to the pool (idempotent). Reactivates if was dead."""
    state = _load_key_state()
    for entry in state["keys"]:
        if entry["key"] == key:
            if entry["status"] != "active":
                entry["status"] = "active"
                entry["exhausted_at"] = None
                entry["last_error"] = None
                _save_key_state(state)
            return entry
    entry = _new_key_entry(key, source=source, name=name)
    state["keys"].append(entry)
    _save_key_state(state)
    return entry


def _mark_key_used(key):
    """Record a successful call on this key."""
    state = _load_key_state()
    for entry in state["keys"]:
        if entry["key"] == key:
            entry["call_count"] += 1
            entry["last_used"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            break
    _save_key_state(state)


def _mark_key_dead(key, reason="exhausted", error=None):
    """Mark a key as exhausted or invalid."""
    state = _load_key_state()
    for entry in state["keys"]:
        if entry["key"] == key:
            entry["status"] = reason
            entry["exhausted_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            entry["last_error"] = error
            break
    _save_key_state(state)
    print(f"[dead] {key[:12]}… marked {reason}: {error or 'quota/rate exhausted'}", file=sys.stderr)


def _prune_dead_keys():
    """Remove all exhausted/invalid keys. Returns count removed."""
    state = _load_key_state()
    before = len(state["keys"])
    state["keys"] = [e for e in state["keys"] if e["status"] == "active"]
    removed = before - len(state["keys"])
    if state["rr_index"] >= len(state["keys"]):
        state["rr_index"] = 0
    _save_key_state(state)
    return removed


# ── account & key creation ────────────────────────────────────────────────────

def _random_username(prefix="auto"):
    ts = int(time.time())
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{prefix}_{ts}_{rand}"


def _random_password():
    ts = str(int(time.time()))
    suffix = ts[-4:]
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"As{suffix}!{rand}"


def _register_account(username="", password=""):
    username = username or _random_username()
    password = password or _random_password()
    body = json.dumps({
        "username": username, "password": password,
        "confirm_password": password, "agreement": True,
    }).encode()
    req = urllib.request.Request(
        f"{WEB_API}/api/ssuser/auth/register",
        data=body, headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Register failed (HTTP {e.code}): {e.read().decode()[:500]}")
    if resp.get("code") != 0:
        raise RuntimeError(f"Register failed: {resp.get('message')} (code {resp.get('code')})")
    data = resp["data"]
    data["_username"] = username
    data["_password"] = password
    return data


def _create_api_key(access_token, name="auto-key", rate_limit=500,
                     quota_is_unlimited=True, is_active=True):
    body = json.dumps({
        "name": name, "rate_limit": rate_limit,
        "quota_is_unlimited": quota_is_unlimited, "quota_limit": 0,
        "is_active": is_active,
    }).encode()
    req = urllib.request.Request(
        f"{WEB_API}/api/api/user/keys",
        data=body,
        headers={"Content-Type": "application/json",
                  "Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Create key failed (HTTP {e.code}): {e.read().decode()[:500]}")
    if resp.get("code") != 0:
        raise RuntimeError(f"Create key failed: {resp.get('message')} (code {resp.get('code')})")
    return resp["data"]


def _register_and_create_key(key_name="auto-key", rate_limit=500, username="", password=""):
    reg = _register_account(username, password)
    key_data = _create_api_key(reg["access_token"], name=key_name, rate_limit=rate_limit)
    return key_data["key"], reg["_username"], reg["_password"], key_data


# ── API call ──────────────────────────────────────────────────────────────────

def _raw_call(tool, args, key):
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": tool, "arguments": args},
    }).encode()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(ENDPOINT, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:300]}"
    except Exception as e:
        return None, f"Error: {e}"


def _is_dead_key(data):
    if not data:
        return False
    result = data.get("result", {})
    if not result.get("isError"):
        return False
    for item in result.get("content", []):
        text = item.get("text", "").lower()
        if any(sig in text for sig in _DEAD_SIGNALS):
            return True
    return False


def _dead_reason(data):
    if not data:
        return "unknown"
    result = data.get("result", {})
    for item in result.get("content", []):
        text = item.get("text", "").lower()
        for sig in _DEAD_SIGNALS:
            if sig in text:
                return sig
    return "unknown"


def _extract_new_key(data):
    if not data:
        return None
    result = data.get("result", {})
    auto = result.get("auto_registered") or result.get("new_key")
    if isinstance(auto, dict):
        return auto.get("api_key") or auto.get("key")
    if isinstance(auto, str) and auto:
        return auto
    for item in result.get("content", []):
        text = item.get("text", "")
        if "auto_registered" in text.lower():
            try:
                parsed = json.loads(text)
                return parsed.get("api_key") or parsed.get("key")
            except (json.JSONDecodeError, AttributeError):
                pass
    return None


# ── rotation engines ─────────────────────────────────────────────────────────

def _rotate_fallback(tool, args, pool, auto_register=False):
    """Fallback: try keys in order; mark dead in state; fall back to auto-register or anonymous."""
    for i, key in enumerate(pool):
        data, err = _raw_call(tool, args, key)
        if err:
            print(f"[key {i+1}/{len(pool)}] {err} — rotating…", file=sys.stderr)
            continue
        if _is_dead_key(data):
            reason = _dead_reason(data)
            _mark_key_dead(key, reason="exhausted" if "quota" in reason else "invalid", error=reason)
            print(f"[key {i+1}/{len(pool)}] {reason} — rotating…", file=sys.stderr)
            continue
        _mark_key_used(key)
        new_key = _extract_new_key(data)
        if new_key:
            print(f"[auto-registered] New key received: {new_key[:12]}…", file=sys.stderr)
        print(f"[hit] key {i+1}/{len(pool)} ({key[:12]}…) calls+1", file=sys.stderr)
        return _format_result(data), new_key

    if auto_register:
        fresh_key = _auto_register()
        if fresh_key:
            data, err = _raw_call(tool, args, fresh_key)
            if err:
                print(f"[fresh key] {err} — falling back to anonymous…", file=sys.stderr)
            elif not _is_dead_key(data):
                _mark_key_used(fresh_key)
                print(f"[hit] fresh key ({fresh_key[:12]}…)", file=sys.stderr)
                return _format_result(data), None

    if pool:
        print("[fallback] All keys exhausted, trying anonymous…", file=sys.stderr)
    data, err = _raw_call(tool, args, "")
    if err:
        sys.exit(err)
    if _is_dead_key(data):
        result = data.get("result", {})
        for item in result.get("content", []):
            sys.exit(item.get("text", "All keys exhausted and anonymous failed."))
        sys.exit("All keys exhausted.")
    print("[hit] anonymous", file=sys.stderr)
    return _format_result(data), None


def _rotate_round_robin(tool, args, pool, auto_register=False):
    """Round-robin: next key in pool; mark dead in state; skip to next alive."""
    if not pool:
        data, err = _raw_call(tool, args, "")
        if err:
            sys.exit(err)
        print("[hit] anonymous (no keys)", file=sys.stderr)
        return _format_result(data), None

    state = _load_key_state()
    n = len(pool)
    start = state.get("rr_index", 0) % n
    print(f"[rr] pool={n} cursor={start}", file=sys.stderr)

    for offset in range(n):
        idx = (start + offset) % n
        key = pool[idx]
        data, err = _raw_call(tool, args, key)
        if err:
            print(f"[rr key {idx+1}/{n}] {err} — skipping…", file=sys.stderr)
            continue
        if _is_dead_key(data):
            reason = _dead_reason(data)
            _mark_key_dead(key, reason="exhausted" if "quota" in reason else "invalid", error=reason)
            print(f"[rr key {idx+1}/{n}] {reason} — skipping…", file=sys.stderr)
            continue
        next_idx = (idx + 1) % n
        state["rr_index"] = next_idx
        _save_key_state(state)
        _mark_key_used(key)
        new_key = _extract_new_key(data)
        if new_key:
            print(f"[auto-registered] New key received: {new_key[:12]}…", file=sys.stderr)
        print(f"[hit] key {idx+1}/{n} ({key[:12]}…) calls+1 → cursor={next_idx}", file=sys.stderr)
        return _format_result(data), new_key

    if auto_register:
        fresh_key = _auto_register()
        if fresh_key:
            data, err = _raw_call(tool, args, fresh_key)
            if err:
                print(f"[fresh key] {err} — falling back to anonymous…", file=sys.stderr)
            elif not _is_dead_key(data):
                _mark_key_used(fresh_key)
                print(f"[hit] fresh key ({fresh_key[:12]}…)", file=sys.stderr)
                return _format_result(data), None

    if pool:
        print("[rr] All keys exhausted, trying anonymous…", file=sys.stderr)
    data, err = _raw_call(tool, args, "")
    if err:
        sys.exit(err)
    if _is_dead_key(data):
        result = data.get("result", {})
        for item in result.get("content", []):
            sys.exit(item.get("text", "All keys exhausted and anonymous failed."))
        sys.exit("All keys exhausted.")
    print("[hit] anonymous", file=sys.stderr)
    return _format_result(data), None


def _call_with_rotation(tool, args, pool, mode="fallback", auto_register=False):
    if mode == "round-robin":
        return _rotate_round_robin(tool, args, pool, auto_register=auto_register)
    return _rotate_fallback(tool, args, pool, auto_register=auto_register)


def _format_result(data):
    if "error" in data:
        return f"API Error: {data['error'].get('message', data['error'])}"
    result = data.get("result", {})
    parts = []
    for item in result.get("content", []):
        if item.get("type") == "text":
            parts.append(item["text"])
    return "\n".join(parts) if parts else json.dumps(result, indent=2, ensure_ascii=False)


# ── key persistence ───────────────────────────────────────────────────────────

def _persist_new_key(new_key, source="auto_register", name=None):
    if not new_key:
        return
    _add_key_to_state(new_key, source=source, name=name)
    print(f"[persisted] Key {new_key[:12]}… added to pool (source={source})", file=sys.stderr)


def _auto_register():
    print("[auto-register] All keys exhausted — registering a new account…", file=sys.stderr)
    try:
        key, username, password, key_data = _register_and_create_key()
        print(f"[auto-register] Account: {username}  Key: {key[:12]}…", file=sys.stderr)
        _persist_new_key(key, source="auto_register", name=key_data.get("name"))
        return key
    except Exception as e:
        print(f"[auto-register] Failed: {e}", file=sys.stderr)
        return None


def _sdp(v):
    if not v:
        return None
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        pass
    r = {}
    for pair in v.split(","):
        if "=" in pair:
            k, _, val = pair.partition("=")
            r[k.strip()] = val.strip()
    return r or None


# ── keys management subcommand ────────────────────────────────────────────────

def _cmd_keys(args):
    state = _load_key_state()

    if args.keys_action == "list" or args.keys_action is None:
        if not state["keys"]:
            print("Key pool is empty. Run `anysearch register` to create one.")
            return
        print(f"{'#':>2}  {'Status':<10}  {'Calls':>5}  {'Key':<16}  {'Source':<14}  {'Last Used':<21}  {'Name'}")
        print("-" * 90)
        for i, e in enumerate(state["keys"]):
            last = (e["last_used"] or "-")[:19]
            name = e.get("name") or "-"
            print(f"{i+1:>2}  {e['status']:<10}  {e['call_count']:>5}  {e['prefix']:<16}  {e['source']:<14}  {last:<21}  {name}")
        active = sum(1 for e in state["keys"] if e["status"] == "active")
        dead = sum(1 for e in state["keys"] if e["status"] != "active")
        print(f"\n{active} active  {dead} dead  rr_index={state.get('rr_index', 0)}  "
              f"rotation={state.get('rotation', 'fallback')}  "
              f"auto_register={state.get('auto_register', False)}")

    elif args.keys_action == "prune":
        removed = _prune_dead_keys()
        print(f"Pruned {removed} dead key(s).")

    elif args.keys_action == "add":
        if not args.key_value:
            sys.exit("Error: --key_value required for add")
        entry = _add_key_to_state(args.key_value, source="manual", name=args.key_name or None)
        print(f"Added: {entry['prefix']} (source=manual)")

    elif args.keys_action == "remove":
        if not args.key_value:
            sys.exit("Error: --key_value required for remove")
        state = _load_key_state()
        before = len(state["keys"])
        state["keys"] = [e for e in state["keys"] if e["key"] != args.key_value]
        removed = before - len(state["keys"])
        _save_key_state(state)
        print(f"Removed {removed} key(s) matching {args.key_value[:12]}…")

    elif args.keys_action == "status":
        active = [e for e in state["keys"] if e["status"] == "active"]
        dead = [e for e in state["keys"] if e["status"] != "active"]
        total_calls = sum(e["call_count"] for e in state["keys"])
        print(json.dumps({
            "total_keys": len(state["keys"]),
            "active": len(active),
            "dead": len(dead),
            "total_calls": total_calls,
            "rr_index": state.get("rr_index", 0),
            "rotation": state.get("rotation", "fallback"),
            "auto_register": state.get("auto_register", False),
        }, indent=2))

    elif args.keys_action == "config":
        if args.rotation:
            state["rotation"] = args.rotation
        if args.auto_register is not None:
            state["auto_register"] = args.auto_register
        _save_key_state(state)
        print(f"rotation={state['rotation']}  auto_register={state['auto_register']}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse

    p = argparse.ArgumentParser(prog="anysearch", description="AnySearch probe")
    p.add_argument("--api_key", default="", help="One-shot key override (bypasses pool)")
    p.add_argument("--rotation", "-r", choices=["fallback", "round-robin"],
                   default=None, help="Key rotation mode (overrides keys-state.json)")
    p.add_argument("--auto_register", action="store_true", default=None,
                   help="Auto-register when all keys exhausted (overrides keys-state.json)")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--domain", "-d")
    s.add_argument("--sub_domain", "-s")
    s.add_argument("--sdp", "-p", dest="sdp")
    s.add_argument("--max_results", "-m", type=int)
    s.add_argument("--rotation", "-r", dest="rotation",
                   choices=["fallback", "round-robin"], default=None)

    g = sub.add_parser("get_sub_domains")
    g.add_argument("--domain")
    g.add_argument("--domains")
    g.add_argument("--rotation", "-r", dest="rotation",
                   choices=["fallback", "round-robin"], default=None)

    b = sub.add_parser("batch_search")
    b.add_argument("queries", nargs="?")
    b.add_argument("--query", action="append", dest="q_items")
    b.add_argument("--domain", "-d")
    b.add_argument("--sub_domain", "-s")
    b.add_argument("--sdp", "-p", dest="sdp")
    b.add_argument("--rotation", "-r", dest="rotation",
                   choices=["fallback", "round-robin"], default=None)

    e = sub.add_parser("extract")
    e.add_argument("url", nargs="?")
    e.add_argument("--rotation", "-r", dest="rotation",
                   choices=["fallback", "round-robin"], default=None)

    reg = sub.add_parser("register",
                         description="Register a new account, create an API key, add to pool")
    reg.add_argument("--username", "-u", default="", help="Custom username (auto-generated if empty)")
    reg.add_argument("--password", "-p", default="", help="Custom password (auto-generated if empty)")
    reg.add_argument("--key_name", "-k", default="auto-key", help="Name for the API key")
    reg.add_argument("--rate_limit", type=int, default=500, help="Rate limit (req/s)")
    reg.add_argument("--count", "-n", type=int, default=1, help="Number of accounts+keys to create")
    reg.add_argument("--print_only", action="store_true", help="Print keys without adding to pool")

    km = sub.add_parser("keys", description="Manage the API key pool")
    km.add_argument("keys_action", nargs="?", default="list",
                   choices=["list", "prune", "add", "remove", "status", "config"],
                   help="list (default) | prune dead | add --key_value | remove --key_value | status | config")
    km.add_argument("--key_value", default="", help="Key string to add/remove")
    km.add_argument("--key_name", default="", help="Name for add")
    km.add_argument("--rotation", choices=["fallback", "round-robin"], default=None,
                   help="Set rotation mode (config action)")
    km.add_argument("--auto_register", type=lambda x: x.lower() in ("1", "true", "yes", "on"),
                   default=None, help="Set auto_register on/off (config action)")

    a = p.parse_args()
    if not a.cmd:
        p.print_help()
        return

    # ── keys management ──────────────────────────────────────────────────────
    if a.cmd == "keys":
        _cmd_keys(a)
        return

    # ── register subcommand ──────────────────────────────────────────────────
    if a.cmd == "register":
        count = max(1, a.count)
        results = []
        for i in range(count):
            try:
                key, username, password, key_data = _register_and_create_key(
                    key_name=a.key_name, rate_limit=a.rate_limit,
                    username=a.username if i == 0 else "",
                    password=a.password if i == 0 else "",
                )
                if not a.print_only:
                    _persist_new_key(key, source="register", name=key_data.get("name"))
                results.append({
                    "username": username, "password": password,
                    "api_key": key, "key_id": key_data.get("id", ""),
                    "key_name": key_data.get("name", ""),
                })
                print(f"[{i+1}/{count}] {username} → {key}", file=sys.stderr)
            except Exception as e:
                print(f"[{i+1}/{count}] FAILED: {e}", file=sys.stderr)
                results.append({"error": str(e)})
            if i < count - 1:
                time.sleep(2)
        print(json.dumps(results, indent=2))
        return

    # ── search / get_sub_domains / batch_search / extract ─────────────────────
    state = _load_key_state()

    # Resolve rotation: CLI flag > state file
    rotation = a.rotation or state.get("rotation", "fallback")
    # Resolve auto_register: CLI flag > state file
    auto_reg = a.auto_register if a.auto_register is not None else state.get("auto_register", False)

    # Build pool
    if a.api_key:
        pool = [a.api_key]
    else:
        pool = _active_keys(state)

    if pool:
        print(f"[keys] {len(pool)} active  mode={rotation}  auto_register={auto_reg}", file=sys.stderr)
    else:
        print(f"[keys] anonymous (no active keys)  mode={rotation}  auto_register={auto_reg}", file=sys.stderr)

    def _dispatch(tool, args):
        output, new_key = _call_with_rotation(tool, args, pool, rotation, auto_register=auto_reg)
        print(output)
        if new_key:
            _persist_new_key(new_key, source="auto_register")

    if a.cmd == "search":
        args = {"query": a.query}
        if a.domain: args["domain"] = a.domain
        if a.sub_domain: args["sub_domain"] = a.sub_domain
        if a.sdp:
            parsed = _sdp(a.sdp)
            if parsed: args["sub_domain_params"] = parsed
        if a.max_results is not None:
            args["max_results"] = min(a.max_results, 10)
        _dispatch("search", args)

    elif a.cmd == "get_sub_domains":
        if a.domains:
            args = {"domains": [s.strip() for s in a.domains.split(",") if s.strip()]}
        elif a.domain:
            args = {"domain": a.domain}
        else:
            sys.exit("Error: --domain or --domains required")
        _dispatch("get_sub_domains", args)

    elif a.cmd == "batch_search":
        if a.q_items:
            queries = [{"query": q} for q in a.q_items]
        elif a.queries:
            try:
                queries = json.loads(a.queries)
                if not isinstance(queries, list): queries = [queries]
            except json.JSONDecodeError:
                sys.exit("Error: queries must be valid JSON array")
        else:
            sys.exit("Error: provide --query or queries JSON")
        if len(queries) > 5: sys.exit("Error: max 5 queries")
        for q in queries:
            if a.domain and not q.get("domain"): q["domain"] = a.domain
            if a.sub_domain and not q.get("sub_domain"): q["sub_domain"] = a.sub_domain
            if a.sdp and not q.get("sub_domain_params"): q["sub_domain_params"] = _sdp(a.sdp)
        _dispatch("batch_search", {"queries": queries})

    elif a.cmd == "extract":
        if not a.url: sys.exit("Error: url required")
        _dispatch("extract", {"url": a.url})


if __name__ == "__main__":
    main()