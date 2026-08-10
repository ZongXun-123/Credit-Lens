# envtools.py — 環境變數安全讀取
# 防呆重點:.env 若把註解寫在設定值同一行(如 KEY=   # 說明),
# 空值那一行會把整段註解當成值讀進來,再送進 HTTP 標頭就會 UnicodeEncodeError。
import os


def env(key: str, default: str = "") -> str:
    """讀取環境變數並清掉引號、行末註解與前後空白。"""
    raw = os.getenv(key, default) or ""
    v = raw.strip().strip('"').strip("'")
    if v.startswith("#"):          # 整串都是註解 → 視為未設定
        return ""
    if " #" in v:                  # 行末註解
        v = v.split(" #", 1)[0].strip()
    return v


def env_bool(key: str, default: bool) -> bool:
    v = env(key).lower()
    if v in ("true", "1", "yes", "on"):
        return True
    if v in ("false", "0", "no", "off"):
        return False
    return default


def env_ascii(key: str, default: str = "") -> str:
    """僅接受 ASCII 的設定值(HTTP 標頭用);含中文一律視為未設定。"""
    v = env(key, default)
    return v if v.isascii() else ""
