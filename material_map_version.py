"""
Material Map のバージョン情報
Git SHAを使用してキャッシュバスターとして利用
"""
import subprocess

def get_app_version() -> str:
    """Gitの短縮SHAを取得（失敗時は'no-git'を返す）"""
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        return sha
    except (subprocess.CalledProcessError, FileNotFoundError, Exception):
        return "no-git"

# グローバル変数として使用（初回呼び出し時に取得）
APP_VERSION = get_app_version()
