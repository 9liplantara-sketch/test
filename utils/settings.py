# --- settings primitives (must be defined at top; safe against partial imports) ---
SETTINGS_VERSION = "2026-01-15T14:40:00"

import os

_ST = None
def _get_st():
    global _ST
    if _ST is not None:
        return _ST
    try:
        import streamlit as st
        _ST = st
    except Exception:
        _ST = None
    return _ST

_TRUE = {"1", "true", "yes", "y", "on"}
_FALSE = {"0", "false", "no", "n", "off", ""}

def get_flag(key: str, default: bool = False) -> bool:
    st = _get_st()
    if st is not None:
        try:
            v = st.secrets.get(key, None)
            if v is not None:
                if isinstance(v, bool):
                    return v
                if isinstance(v, int):
                    return v != 0
                s = str(v).strip().lower()
                if s in _TRUE:
                    return True
                if s in _FALSE:
                    return False
        except Exception:
            pass

    v = os.getenv(key)
    if v is not None:
        s = str(v).strip().lower()
        if s in _TRUE:
            return True
        if s in _FALSE:
            return False

    return default

def get_secret_str(key: str, default: str = "") -> str:
    st = _get_st()
    if st is not None:
        try:
            v = st.secrets.get(key, None)
            if v is not None:
                return str(v)
        except Exception:
            pass
    v = os.getenv(key)
    if v is not None:
        return str(v)
    return default
# --- end primitives ---

"""
アプリケーション設定の読み取り（Secrets + 環境変数対応）
循環importに強い最小モジュール（プロジェクト内の他モジュールを一切importしない）

重要: get_flag をファイル最上部で定義し、定義前に落ちないようにする
"""
from pathlib import Path
from typing import Optional


def is_cloud() -> bool:
    """Streamlit Cloud環境かどうかを判定"""
    if os.getenv("STREAMLIT_CLOUD") == "1":
        return True
    if os.getenv("HOSTNAME") and "streamlit" in os.getenv("HOSTNAME", "").lower():
        return True
    if Path("/mount/src").exists():
        return True
    return False


def get_database_url() -> str:
    """データベースURLを取得（優先順位付き）"""
    # st.secretsから取得を試みる
    st = _get_st()
    if st is not None:
        try:
            url = st.secrets.get("connections", {}).get("materialbase_db", {}).get("url")
            if url:
                return str(url)
        except Exception:
            pass
        try:
            url = st.secrets.get("DATABASE_URL")
            if url:
                return str(url)
        except Exception:
            pass
    
    # os.environから取得
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    
    # ローカル環境のみ: SQLiteフォールバック
    if not is_cloud():
        return "sqlite:///./materials.db"
    
    raise RuntimeError(
        "DATABASE_URL is required on Streamlit Cloud. "
        "Please set it in Streamlit Secrets (connections.materialbase_db.url or DATABASE_URL)."
    )


def get_db_dialect(url: str) -> str:
    """データベースURLからdialect（postgresql/sqlite）を判定"""
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return "postgresql"
    elif url.startswith("sqlite:///"):
        return "sqlite"
    else:
        return "postgresql"  # デフォルトはpostgresqlとみなす


def mask_db_url(url: str) -> str:
    """データベースURLをマスク（パスワードを隠す）"""
    if "://" in url and "@" in url:
        parts = url.split("://")
        if len(parts) == 2:
            scheme = parts[0]
            rest = parts[1]
            if "@" in rest:
                auth_part, host_part = rest.split("@", 1)
                if ":" in auth_part:
                    user = auth_part.split(":")[0]
                    masked = f"{scheme}://{user}:***@{host_part}"
                    return masked
    return url




def is_admin_mode() -> bool:
    """管理者モードかどうかを判定（DEBUGとは分離）"""
    return get_flag("ADMIN_MODE", False)


def is_debug() -> bool:
    """DEBUG が有効か（Secrets / 環境変数）。ログや内部診断用。"""
    return get_flag("DEBUG", False)


def is_debug_env() -> bool:
    """DEBUG_ENV が有効か（Secrets / 環境変数）。詳細ログ用。"""
    return get_flag("DEBUG_ENV", False)


def is_admin_authenticated() -> bool:
    """
    管理者パスワード認証済みか。

    - ADMIN_PASSWORD 未設定: ローカル開発のみ True（Cloud では False）
    - ADMIN_PASSWORD 設定済み: session_state.admin_authenticated を見る
    """
    password = get_secret_str("ADMIN_PASSWORD", "").strip()
    if not password:
        return not is_cloud()

    st = _get_st()
    if st is None:
        return False
    try:
        return bool(st.session_state.get("admin_authenticated", False))
    except Exception:
        return False


def show_debug_ui() -> bool:
    """
    画面上にデバッグ表示を出してよいか。

    DEBUG / DEBUG_ENV が有効でも、管理者認証前の学生には出さない。
    サーバーログ用の is_debug() / is_debug_env() とは分離する。
    """
    if not (is_debug() or is_debug_env()):
        return False
    return is_admin_authenticated()


# モジュールの公開APIを明示的に定義
__all__ = [
    "is_cloud",
    "get_database_url",
    "get_db_dialect",
    "mask_db_url",
    "get_secret_str",
    "get_flag",
    "is_admin_mode",
    "is_debug",
    "is_debug_env",
    "is_admin_authenticated",
    "show_debug_ui",
    "SETTINGS_VERSION",
]
