#!/usr/bin/env python3
"""AnySearch probe/extract CLI — stdlib-only with key-pool recovery.

Key pool state lives in the OS user config directory (single source of truth):
  {
    "rr_index": 0,
    "rotation": "fallback",       # fallback | round-robin
    "auto_register": true,        # auto-register when all keys exhausted
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
import json, os, sys, time, random, string, re, urllib.request, urllib.error, urllib.parse

ENDPOINT = "https://api.anysearch.com/mcp"
WEB_API = "https://anysearch.com"

# Error texts that signal a dead key (rotate to next)
_DEAD_SIGNALS = ("invalid_api_key", "quota_exhausted", "rate_limit", "limit_exceeded")


def _skill_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def _config_dir():
    """Cross-platform user config directory for runtime state.

    Override with ANYSEARCH_CONFIG_DIR for tests or unusual deployments.
    """
    override = os.environ.get("ANYSEARCH_CONFIG_DIR", "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(base, "AnySearch")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "anysearch")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "anysearch")


def _state_path():
    return os.path.join(_config_dir(), "keys-state.json")


def _install_state_path():
    """Install-local state path, imported into _state_path() when present."""
    return os.path.join(_skill_dir(), "keys-state.json")


def _install_env_path():
    """Install-local .env path, imported into _state_path() when present."""
    return os.path.join(_skill_dir(), ".env")


# ── key state: single source of truth ─────────────────────────────────────────

def _default_state():
    return {"rr_index": 0, "rotation": "fallback", "auto_register": True, "keys": []}


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


def _normalise_state(state):
    state.setdefault("rr_index", 0)
    state.setdefault("rotation", "fallback")
    state.setdefault("auto_register", True)
    state.setdefault("keys", [])
    return state


def _load_json_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            return _normalise_state(json.load(f))
    except (json.JSONDecodeError, OSError):
        return None


def _load_key_state():
    """Load key pool state from the OS config dir.

    First run imports install-local keys-state.json/.env and env vars.
    Keeping runtime state outside the skill directory lets npx/skills reinstall
    overwrite code without deleting keys.
    """
    path = _state_path()
    state = _load_json_state(path) if os.path.isfile(path) else None
    if state is not None:
        return state

    install_state = _install_state_path()
    state = _load_json_state(install_state) if os.path.isfile(install_state) else None
    if state is not None:
        _save_key_state(state)
        print(f"[migrate] key state moved to {_state_path()}", file=sys.stderr)
        return state

    # First run — migrate from .env or env vars
    state = _default_state()
    seen = set()

    # Install-local .env file
    env_path = _install_env_path()
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
        os.makedirs(_config_dir(), mode=0o700, exist_ok=True)
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        try:
            os.chmod(_state_path(), 0o600)
        except OSError:
            pass
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
        return data, new_key

    if auto_register:
        fresh_key = _auto_register()
        if fresh_key:
            data, err = _raw_call(tool, args, fresh_key)
            if err:
                print(f"[fresh key] {err} — falling back to anonymous…", file=sys.stderr)
            elif not _is_dead_key(data):
                _mark_key_used(fresh_key)
                print(f"[hit] fresh key ({fresh_key[:12]}…)", file=sys.stderr)
                return data, None

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
    return data, None


def _rotate_round_robin(tool, args, pool, auto_register=False):
    """Round-robin: next key in pool; mark dead in state; skip to next alive."""
    if not pool:
        if auto_register:
            fresh_key = _auto_register()
            if fresh_key:
                data, err = _raw_call(tool, args, fresh_key)
                if err:
                    print(f"[fresh key] {err} — falling back to anonymous…", file=sys.stderr)
                elif not _is_dead_key(data):
                    _mark_key_used(fresh_key)
                    print(f"[hit] fresh key ({fresh_key[:12]}…)", file=sys.stderr)
                    return data, None
        data, err = _raw_call(tool, args, "")
        if err:
            sys.exit(err)
        print("[hit] anonymous (no keys)", file=sys.stderr)
        return data, None

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
        return data, new_key

    if auto_register:
        fresh_key = _auto_register()
        if fresh_key:
            data, err = _raw_call(tool, args, fresh_key)
            if err:
                print(f"[fresh key] {err} — falling back to anonymous…", file=sys.stderr)
            elif not _is_dead_key(data):
                _mark_key_used(fresh_key)
                print(f"[hit] fresh key ({fresh_key[:12]}…)", file=sys.stderr)
                return data, None

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
    return data, None


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


# ── payload rendering ─────────────────────────────────────────────────────────

_NOISE_PATTERNS = (
    "menu", "skip to", "sign in", "log in", "subscribe", "cookie",
    "advertis", "javascript", "©", "home", "about", "contact",
    "search", "nav", "button",
)


def _parse_blob(text):
    """Parse one Markdown-ish result blob into title, URL, body, raw."""
    raw = text.strip()
    lines = raw.splitlines()
    title, url, body_start, url_idx = "", "", 0, None

    for i, line in enumerate(lines):
        stripped = line.strip()
        m = re.match(r"^-?\s*\*\*(?:URL|Source)\*\*:\s*(https?://\S+)", stripped)
        if m:
            url = m.group(1).strip()
            body_start, url_idx = i + 1, i
            break
        if re.match(r"^https?://\S+", stripped):
            url = stripped.split()[0]
            body_start, url_idx = i + 1, i
            break

    title_lines = lines[:url_idx] if url_idx is not None else lines
    for i, line in enumerate(title_lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
        else:
            title = re.sub(r"^[-*]\s*", "", stripped)
        if url_idx is None:
            body_start = i + 1
        break

    body = "\n".join(lines[body_start:]).strip()
    body = re.sub(r"^[-*]\s*", "", body, count=1)
    return {"rank": None, "title": title, "url": url, "body": body, "raw": raw}


def _split_result_blobs(text):
    """Split AnySearch's formatted search output into individual result records."""
    matches = list(re.finditer(r"(?m)^###\s+(\d+)\.\s+(.+?)\s*$", text))
    if not matches:
        blob = _parse_blob(text)
        return [blob] if blob["title"] or blob["url"] or blob["body"] else []

    results = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        raw = text[start:end].strip()
        section_after_title = text[m.end():end].strip()
        rec = _parse_blob(section_after_title)
        rec["rank"] = int(m.group(1))
        rec["title"] = m.group(2).strip()
        rec["raw"] = raw
        results.append(rec)
    return results


def _canonical_url(url):
    """Canonical key for dedup only; displayed URL stays unchanged."""
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlsplit(url.strip())
    except Exception:
        return url.strip().lower().rstrip("/")
    scheme = "https"
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path or ""
    if path == "/":
        path = ""
    path = path.rstrip("/")
    query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = urllib.parse.urlencode(sorted(query_pairs))
    return urllib.parse.urlunsplit((scheme, host, path, query, ""))


def _dedup_results(results, enabled=True):
    if not enabled:
        return results, 0
    seen, out, removed = set(), [], 0
    for rec in results:
        key = _canonical_url(rec.get("url", "")) or rec.get("raw", "")[:120]
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        out.append(rec)
    return out, removed


def _skip_lead_noise(body, budget=200):
    if not body:
        return body
    lines = body.lstrip().splitlines()
    consumed, idx = 0, 0
    while idx < len(lines) and consumed < budget:
        stripped = lines[idx].strip()
        lower = stripped.lower()
        is_noise = (not stripped) or stripped in ("---", "--", "___") or (
            len(stripped) < 40 and any(p in lower for p in _NOISE_PATTERNS)
        )
        if not is_noise:
            break
        consumed += len(lines[idx]) + 1
        idx += 1
    trimmed = "\n".join(lines[idx:]).strip()
    return trimmed or body.strip()


# ── extract reader backends ───────────────────────────────────────────────────
_READER_PER_TIMEOUT = 8
_MIN_READER_BODY = 200


def _extract_local(url):
    """Local readability via a detected defuddle executable on PATH — no Python
    import, no pip. Tries a globally-installed `defuddle`, else `npx` which fills
    the npm cache on first run (not a global install). Returns markdown or None;
    the caller degrades to remote readers when neither is present.
    """
    import shutil
    import subprocess

    if shutil.which("defuddle"):
        args = ["defuddle", "parse", url, "--markdown"]
        timeout = _READER_PER_TIMEOUT
    elif shutil.which("npx"):
        args = ["npx", "--yes", "defuddle", "parse", url, "--markdown"]
        timeout = 30  # first npx run populates the npm cache; later runs reuse it
    else:
        return None
    try:
        out = subprocess.run(args, capture_output=True, timeout=timeout, text=True)
        if out.returncode == 0 and out.stdout:
            md = out.stdout.strip()
            if len(md) >= _MIN_READER_BODY:
                return md
    except Exception:
        pass
    return None


def _strip_reader_frontmatter(raw, name):
    """Peel the reader-specific header so _parse_blob sees clean body text."""
    if name == "jina":
        marker = "Markdown Content:"
        idx = raw.find(marker)
        return raw[idx + len(marker):].strip() if idx >= 0 else raw.strip()
    # defuddle ships YAML frontmatter delimited by leading '---'
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end >= 0:
            return raw[end + 4:].strip()
    return raw.strip()


def _fetch_jina(url):
    """Fetch via r.jina.ai. Returns stripped markdown or None."""
    try:
        req = urllib.request.Request(
            f"https://r.jina.ai/{url}",
            headers={"Accept": "text/markdown", "X-No-Cache": "true"})
        with urllib.request.urlopen(req, timeout=_READER_PER_TIMEOUT) as r:
            charset = r.headers.get_content_charset() or "utf-8"
            raw = r.read().decode(charset, "replace")
        md = _strip_reader_frontmatter(raw, "jina")
        return md if md and len(md) >= _MIN_READER_BODY else None
    except Exception:
        return None


def _fetch_defuddle(url):
    """Fetch via defuddle.md. Returns stripped markdown or None."""
    try:
        req = urllib.request.Request(f"https://defuddle.md/{url}")
        with urllib.request.urlopen(req, timeout=_READER_PER_TIMEOUT) as r:
            charset = r.headers.get_content_charset() or "utf-8"
            raw = r.read().decode(charset, "replace")
        md = _strip_reader_frontmatter(raw, "defuddle")
        return md if md and len(md) >= _MIN_READER_BODY else None
    except Exception:
        return None


def _readers_fallback(url):
    """Try remote readers in series: jina first, defuddle on failure.

    Serial rather than parallel so a normal extract consumes only one reader's
    quota — a request that fails fast never triggers the next reader.
    Returns (name, markdown) or (None, None).
    """
    for name, fetcher in (("jina", _fetch_jina), ("defuddle", _fetch_defuddle)):
        md = fetcher(url)
        if md:
            return name, md
    return None, None


def _extract_via_reader(url, reader="auto"):
    """Choose a body backend.

    Returns (source, markdown); markdown is None when the caller should fall
    back to the original AnySearch extract tool.
    """
    if reader == "anysearch":
        return "anysearch", None
    if reader == "local":
        md = _extract_local(url)
        return ("local", md) if md else ("anysearch", None)
    if reader == "remote":
        name, md = _readers_fallback(url)
        return (name, md) if md else ("anysearch", None)
    # auto (default): local first, then remote fallback, then anysearch
    md = _extract_local(url)
    if md:
        return "local", md
    name, md = _readers_fallback(url)
    if md:
        return name, md
    return "anysearch", None


def _clip(text, max_chars):
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def _render_body(results, fmt="compact", max_chars=500, source_url=None):
    chunks = []
    for fallback_rank, rec in enumerate(results, 1):
        rank = rec.get("rank") or fallback_rank
        title = rec.get("title") or "(untitled)"
        url = rec.get("url") or source_url or ""
        if fmt == "full":
            chunks.append(rec.get("raw") or rec.get("body") or title)
            continue
        lines = [f"#{rank}  {title}"]
        if url:
            lines.append(f"    {url}")
        if fmt == "snippet":
            snippet = _clip(_skip_lead_noise(rec.get("body", "")), max_chars)
            if snippet:
                lines.append("    " + snippet.replace("\n", "\n    "))
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks).strip()


def _with_header(label, body, count, deduped, elapsed, fmt):
    size_kb = len(body.encode("utf-8")) / 1024
    dedup = f" ({deduped} deduped)" if deduped else ""
    header = f"## {label} — {count} result{'s' if count != 1 else ''}{dedup}, {elapsed:.1f}s, {fmt}, {size_kb:.2f} KB"
    return header + ("\n\n" + body if body else "")


def _render_search_like(data, label, fmt="compact", max_chars=500, dedup=True, elapsed=0.0, limit=None):
    text = _format_result(data)
    results = _split_result_blobs(text)
    results, deduped = _dedup_results(results, enabled=dedup)
    if limit is not None:
        results = results[:max(0, limit)]
    results = [{**rec, "rank": i} for i, rec in enumerate(results, 1)]
    body = _render_body(results, fmt=fmt, max_chars=max_chars)
    if fmt == "compact" and body:
        body += "\n\n(use --format snippet for content previews, --format full for complete content, or extract <URL> to deep-read one page)"
    elif fmt == "snippet" and body:
        top_url = results[0].get("url", "<URL>") if results else "<URL>"
        body += f"\n\n(use --format full for complete content, or extract {top_url} to deep-read one page)"
    return _with_header(label, body, len(results), deduped, elapsed, fmt)


def _render_extract(data, url, fmt="full", max_chars=500, elapsed=0.0):
    text = _format_result(data)
    rec = _parse_blob(text)
    if not rec.get("url"):
        rec["url"] = url
    body = _render_body([rec], fmt=fmt, max_chars=max_chars, source_url=url)
    if fmt == "compact" and body:
        body += "\n\n(use --format snippet for a content preview, --format full for complete content)"
    elif fmt == "snippet" and body:
        body += f"\n\n(use --format full to read the complete page: {url})"
    return _with_header(f'extract "{url}"', body, 1 if body else 0, 0, elapsed, fmt)


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
            "state_path": _state_path(),
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

    p = argparse.ArgumentParser(
        prog="anysearch",
        description="Probe the web compactly, then extract selected URLs when evidence is needed.",
    )
    p.add_argument("--api_key", default="", help="One-shot key override (bypasses the saved key pool)")
    p.add_argument("--rotation", "-r", choices=["fallback", "round-robin"],
                   default=None, help="Key rotation mode for this call")
    p.add_argument("--auto_register", action="store_true", default=None,
                   help="Create and save a fresh key if all active keys fail")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("search", description="Discover candidate URLs for one query.")
    s.add_argument("query")
    s.add_argument("--domain", "-d", help="Vertical domain, e.g. finance or code")
    s.add_argument("--sub_domain", "-s", help="Sub-domain returned by get_sub_domains")
    s.add_argument("--sdp", "-p", dest="sdp", help="Sub-domain params as key=value pairs or JSON")
    s.add_argument("--max_results", "--max-results", "-m", type=int, default=5,
                   help="Maximum results to request and render (default: 5, max: 10)")
    s.add_argument("--format", choices=["compact", "snippet", "full"], default="compact",
                   help="compact=rank+title+URL (default), snippet=preview, full=complete content")
    s.add_argument("--max-chars", dest="max_chars", type=int, default=500,
                   help="Character budget for snippet mode (default: 500)")
    s.add_argument("--no-dedup", action="store_true",
                   help="Keep duplicate canonical URLs")
    s.add_argument("--rotation", "-r", dest="rotation",
                   choices=["fallback", "round-robin"], default=None)

    g = sub.add_parser("get_sub_domains", description="Fetch live vertical schemas before structured search.")
    g.add_argument("--domain", help="One vertical domain")
    g.add_argument("--domains", help="Comma-separated vertical domains")
    g.add_argument("--rotation", "-r", dest="rotation",
                   choices=["fallback", "round-robin"], default=None)

    b = sub.add_parser("batch_search", description="Discover candidates across several query angles and dedupe URLs.")
    b.add_argument("queries", nargs="?")
    b.add_argument("--query", action="append", dest="q_items")
    b.add_argument("--domain", "-d", help="Default vertical domain for queries")
    b.add_argument("--sub_domain", "-s", help="Default sub-domain returned by get_sub_domains")
    b.add_argument("--sdp", "-p", dest="sdp", help="Default sub-domain params as key=value pairs or JSON")
    b.add_argument("--max_results", "--max-results", "-m", type=int, default=5,
                   help="Maximum results per query (default: 5, max: 10)")
    b.add_argument("--format", choices=["compact", "snippet", "full"], default="compact",
                   help="compact=rank+title+URL (default), snippet=preview, full=complete content")
    b.add_argument("--max-chars", dest="max_chars", type=int, default=500,
                   help="Character budget for snippet mode (default: 500)")
    b.add_argument("--no-dedup", action="store_true",
                   help="Keep duplicate canonical URLs")
    b.add_argument("--rotation", "-r", dest="rotation",
                   choices=["fallback", "round-robin"], default=None)

    e = sub.add_parser("extract", description="Deep-read one selected URL.")
    e.add_argument("url", nargs="?", help="URL selected from a probe")
    e.add_argument("--format", choices=["compact", "snippet", "full"], default="full",
                   help="compact=rank+title+URL, snippet=preview, full=complete content (default)")
    e.add_argument("--max-chars", dest="max_chars", type=int, default=500,
                   help="Character budget for snippet mode (default: 500)")
    e.add_argument("--reader", choices=["auto", "local", "remote", "anysearch"], default="auto",
                   help="Body extraction backend: auto=local defuddle if present else "
                        "remote reader fallback (default); local=defuddle only; "
                        "remote=jina then defuddle; anysearch=original API")
    e.add_argument("--rotation", "-r", dest="rotation",
                   choices=["fallback", "round-robin"], default=None)

    reg = sub.add_parser(
        "register",
        description="Create AnySearch account(s), create API key(s), and save them to the pool.",
    )
    reg.add_argument("--username", "-u", default="", help="Custom username for the first account")
    reg.add_argument("--password", "-p", default="", help="Custom password for the first account")
    reg.add_argument("--key_name", "-k", default="auto-key", help="Name for created API key(s)")
    reg.add_argument("--rate_limit", type=int, default=500, help="Requested key rate limit")
    reg.add_argument("--count", "-n", type=int, default=1, help="Number of account+key pairs to create")
    reg.add_argument("--print_only", action="store_true", help="Print credentials without saving keys to the pool")

    km = sub.add_parser("keys", description="Inspect and configure the saved API key pool.")
    km.add_argument("keys_action", nargs="?", default="list",
                   choices=["list", "prune", "add", "remove", "status", "config"],
                   help="list (default) | status | add | remove | prune | config")
    km.add_argument("--key_value", default="", help="Full key value for add/remove")
    km.add_argument("--key_name", default="", help="Display name for keys add")
    km.add_argument("--rotation", choices=["fallback", "round-robin"], default=None,
                   help="Set rotation mode with keys config")
    km.add_argument("--auto_register", type=lambda x: x.lower() in ("1", "true", "yes", "on"),
                   default=None, help="Set persistent auto-register on/off with keys config")

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

    def _dispatch(tool, args, render=None):
        start = time.perf_counter()
        data, new_key = _call_with_rotation(tool, args, pool, rotation, auto_register=auto_reg)
        elapsed = time.perf_counter() - start
        output = render(data, elapsed) if render else _format_result(data)
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
        limit = min(a.max_results, 10)
        args["max_results"] = limit
        label = f'"{a.query}"'
        _dispatch("search", args, lambda data, elapsed: _render_search_like(
            data, label, fmt=a.format, max_chars=a.max_chars,
            dedup=not a.no_dedup, elapsed=elapsed, limit=limit))

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
        limit = min(a.max_results, 10)
        for q in queries:
            q["max_results"] = limit
        label = f"batch({len(queries)} queries)"
        _dispatch("batch_search", {"queries": queries}, lambda data, elapsed: _render_search_like(
            data, label, fmt=a.format, max_chars=a.max_chars,
            dedup=not a.no_dedup, elapsed=elapsed, limit=limit * len(queries)))

    elif a.cmd == "extract":
        if not a.url: sys.exit("Error: url required")
        start = time.perf_counter()
        source, md = _extract_via_reader(a.url, reader=a.reader)
        elapsed = time.perf_counter() - start
        if md:
            data = {"result": {"content": [{"type": "text", "text": md}]}}
            print(_render_extract(data, a.url, fmt=a.format, max_chars=a.max_chars, elapsed=elapsed))
            print(f"[extract] source={source}  {elapsed:.1f}s", file=sys.stderr)
        else:
            # reader path empty or forced via --reader anysearch → original API
            if a.reader != "anysearch":
                hint = "[extract] readers unavailable — fell back to AnySearch API."
                hint += " Install `defuddle` (npm i -g defuddle, needs node) for cleaner local extraction."
                print(hint, file=sys.stderr)
            _dispatch("extract", {"url": a.url}, lambda data, el: _render_extract(
                data, a.url, fmt=a.format, max_chars=a.max_chars, elapsed=el))


if __name__ == "__main__":
    main()