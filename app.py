"""
StreamlitベースのWebアプリケーション
マテリアル感のあるリッチなUI
"""
import streamlit as st
# ページ設定は最初の st.* 呼び出しでなければならない（Streamlitの制約）
from utils.ui_shell import setup_page_config
setup_page_config()

import os
import subprocess

def get_build_sha() -> str:
    # Streamlit Cloudではgitコマンドが使えることが多い
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        return sha
    except Exception:
        return "unknown"


def get_running_sha() -> str:
    """
    現在実行中のコミットSHAを取得（常時表示用）
    
    Returns:
        short SHA文字列、取得失敗時は"unknown"
    """
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def is_debug() -> bool:
    """
    DEBUGモードが有効かどうかを判定（os.environ + st.secrets の両方をチェック）
    
    Returns:
        DEBUGが有効ならTrue、それ以外はFalse
    """
    # os.environ をチェック
    if os.getenv("DEBUG") == "1":
        return True
    
    # st.secrets をチェック（例外時はFalse）
    try:
        return str(st.secrets.get("DEBUG", "0")) == "1"
    except Exception:
        return False


def show_debug_ui() -> bool:
    """画面デバッグ表示用。未認証の学生には出さない（fallback実装）。"""
    return False


# is_debug_flag / show_debug_ui: settings を優先、失敗時は fallback
try:
    from utils.settings import is_debug as is_debug_flag, show_debug_ui as show_debug_ui
except Exception:
    # utils.settings が壊れている場合の fallback
    is_debug_flag = is_debug


# 実行順序の安全策: is_debug_flag が callable であることを確認
if not callable(is_debug_flag):
    # 万が一 callable でない場合は fallback
    is_debug_flag = is_debug
if not callable(show_debug_ui):
    def show_debug_ui() -> bool:
        return False


from pathlib import Path
from typing import Any, Dict, List, Optional
from PIL import Image as PILImage
import qrcode
from io import BytesIO
import base64
import pandas as pd
import plotly.express as px
from urllib.parse import urlsplit, urlunsplit, quote
from streamlit_option_menu import option_menu

# グローバル変数の初期化（NameErrorを防ぐ）
_card_generator_import_error = None
_card_generator_import_traceback = None
import plotly.graph_objects as go
from datetime import datetime, timedelta
from collections import Counter
import json
import uuid
import logging
import textwrap

from database import Material, Property, Image, MaterialMetadata, ReferenceURL, UseExample, ProcessExampleImage, MaterialSubmission, init_db

# ロガーを設定（Cloudで確実に追えるように）
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('[%(name)s] %(levelname)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
from material_form_detailed import _normalize_required
from sqlalchemy.orm import selectinload
from sqlalchemy import select, func, or_
from utils.logo import render_site_header, render_logo_mark, show_logo_debug_info, get_logo_debug_info, get_project_root

# デプロイバージョン（Streamlit Cloudのデプロイ確認用）
DEPLOY_VERSION = "2026-01-15T15:05:00"

# card_generatorとschemasのimportは削除（起動時クラッシュを避けるため）
# これらのモジュールは使用する関数内でlazy importする

# エントリーポイント関数（本文の最初に必ず出るマーカー、main呼び出しの強制、例外の可視化）
import traceback
import sys

def render_startup_import_error(error_type, error_description, hints, debug_payload=None):
    """
    起動時の import エラーを表示する（統一フォーマット）
    
    Args:
        error_type: エラー種別（例: "ModuleNotFoundError", "ImportError", "想定外の例外"）
        error_description: エラーの説明文
        hints: 考えられる原因のリスト（文字列のリスト）
        debug_payload: 管理者向けデバッグ詳細（show_debug_ui時のみ表示）
    """
    st.error("❌ **アプリケーション起動エラー**")
    st.error("必須モジュールの import に失敗しました。")
    st.error("")
    st.error("**これは運用側で修正が必要な問題です。**")
    st.error("")
    st.error(f"**エラー種別:** {error_type}")
    if error_description:
        st.error(error_description)
    st.error("")
    
    if hints:
        st.error("考えられる原因:")
        for hint in hints:
            st.error(f"- {hint}")
        st.error("")
    
    # 起動不能時は認証UIに到達できないため、DEBUG有効時のみ詳細を出す
    if is_debug_flag() and debug_payload:
        st.error("**DEBUG 情報 (DEBUG=1):**")
        st.code(debug_payload.strip(), language="text")
    
    # 必ず停止する（後段での例外連鎖を防ぐ）
    st.stop()

# 必須モジュールの import 保険チェック（本番環境での import エラーを早期検出）
# services.materials_service と utils.db.DBUnavailableError の両方をチェック
# どちらかが失敗したら、UIにエラーを表示して必ず st.stop() で停止する

# 1. services.materials_service の import チェック
try:
    import services.materials_service
except ModuleNotFoundError as e:
    debug_payload = None
    if os.getenv("DEBUG_ENV") == "1":
        debug_payload = f"""
エラー詳細: {e}
例外タイプ: {type(e).__name__}
__file__: {__file__}
現在の作業ディレクトリ: {os.getcwd()}
sys.path:
{chr(10).join(f'  [{i}] {p}' for i, p in enumerate(sys.path))}

Traceback:
{traceback.format_exc()}
        """.strip()
    
    render_startup_import_error(
        error_type="ModuleNotFoundError",
        error_description="`services` パッケージやモジュールが見つかりません。",
        hints=[
            "`services/` がデプロイに含まれていない",
            "リポジトリルートから `streamlit run app.py` が実行されていない",
            "作業ディレクトリが正しく設定されていない",
            "Python の `sys.path` にリポジトリルートが含まれていない"
        ],
        debug_payload=debug_payload
    )
except ImportError as e:
    debug_payload = None
    if os.getenv("DEBUG_ENV") == "1":
        debug_payload = f"""
エラー詳細: {e}
例外タイプ: {type(e).__name__}
__file__: {__file__}
現在の作業ディレクトリ: {os.getcwd()}
sys.path:
{chr(10).join(f'  [{i}] {p}' for i, p in enumerate(sys.path))}

Traceback:
{traceback.format_exc()}
        """.strip()
    
    render_startup_import_error(
        error_type="ImportError",
        error_description="`services` モジュールは見つかりましたが、import に失敗しました。",
        hints=[
            "循環 import が発生している",
            "`services.materials_service` 内で依存モジュールの import に失敗している"
        ],
        debug_payload=debug_payload
    )
except Exception as e:
    debug_payload = None
    if os.getenv("DEBUG_ENV") == "1":
        debug_payload = f"""
エラー詳細: {e}
例外タイプ: {type(e).__name__}
__file__: {__file__}
現在の作業ディレクトリ: {os.getcwd()}
sys.path:
{chr(10).join(f'  [{i}] {p}' for i, p in enumerate(sys.path))}

Traceback:
{traceback.format_exc()}
        """.strip()
    
    render_startup_import_error(
        error_type="想定外の例外",
        error_description="",
        hints=[],
        debug_payload=debug_payload
    )

# 2. utils.db.DBUnavailableError の import チェック
try:
    from utils.db import DBUnavailableError
except ModuleNotFoundError as e:
    debug_payload = None
    if os.getenv("DEBUG_ENV") == "1":
        debug_payload = f"""
エラー詳細: {e}
例外タイプ: {type(e).__name__}
__file__: {__file__}
現在の作業ディレクトリ: {os.getcwd()}
sys.path:
{chr(10).join(f'  [{i}] {p}' for i, p in enumerate(sys.path))}

Traceback:
{traceback.format_exc()}
        """.strip()
    
    render_startup_import_error(
        error_type="ModuleNotFoundError",
        error_description="`utils.db` モジュールが見つかりません。",
        hints=[
            "`utils/` がデプロイに含まれていない",
            "リポジトリルートから `streamlit run app.py` が実行されていない",
            "作業ディレクトリが正しく設定されていない",
            "Python の `sys.path` にリポジトリルートが含まれていない"
        ],
        debug_payload=debug_payload
    )
except ImportError as e:
    debug_payload = None
    if os.getenv("DEBUG_ENV") == "1":
        debug_payload = f"""
エラー詳細: {e}
例外タイプ: {type(e).__name__}
__file__: {__file__}
現在の作業ディレクトリ: {os.getcwd()}
sys.path:
{chr(10).join(f'  [{i}] {p}' for i, p in enumerate(sys.path))}

Traceback:
{traceback.format_exc()}
        """.strip()
    
    render_startup_import_error(
        error_type="ImportError",
        error_description="`utils.db` モジュールは見つかりましたが、`DBUnavailableError` が import できません。",
        hints=[
            "`utils.db` 内で `DBUnavailableError` が定義されていない",
            "`utils.db` 内で循環 import が発生している",
            "`utils.db` 内で依存モジュールの import に失敗している"
        ],
        debug_payload=debug_payload
    )
except Exception as e:
    debug_payload = None
    if os.getenv("DEBUG_ENV") == "1":
        debug_payload = f"""
エラー詳細: {e}
例外タイプ: {type(e).__name__}
__file__: {__file__}
現在の作業ディレクトリ: {os.getcwd()}
sys.path:
{chr(10).join(f'  [{i}] {p}' for i, p in enumerate(sys.path))}

Traceback:
{traceback.format_exc()}
        """.strip()
    
    render_startup_import_error(
        error_type="想定外の例外",
        error_description="",
        hints=[],
        debug_payload=debug_payload
    )

def _panic_screen(where: str, e: Exception):
    """例外を可視化するパニック画面"""
    st.error(f"💥 PANIC at: {where}")
    st.code("".join(traceback.format_exception(type(e), e, e.__traceback__)))

def run_app_entrypoint():
    """
    アプリのエントリーポイント
    - 本文の最初に必ず出るマーカー
    - main呼び出しの強制
    - 例外の可視化
    """
    # 1) 起動確認マーカー（管理者向けデバッグ時のみ。学生画面には出さない）
    if show_debug_ui():
        st.write("✅ app.py is running (entrypoint reached)")

    # 2) 先にサイドバーDebugを描画（既存関数がある想定）
    # 同一run内で1回だけ描画する（二重表示を防ぐ）
    if "debug_sidebar_rendered" not in st.session_state:
        try:
            if "render_debug_sidebar_early" in globals():
                render_debug_sidebar_early()
                st.session_state["debug_sidebar_rendered"] = True
            elif show_debug_ui():
                st.sidebar.info("render_debug_sidebar_early() not found")
        except Exception as e:
            _panic_screen("render_debug_sidebar_early", e)
            # st.stop()は呼ばない（本文を表示するため）

    # 3) DB初期化（落ちても本文に出す）
    try:
        from database import init_db
        init_db()
        if show_debug_ui():
            st.write("✅ init_db() done")
    except Exception as e:
        _panic_screen("init_db", e)
        # st.stop()は呼ばない（本文を表示するため）

    # 4) ここから本来のUI（main）を"必ず"呼ぶ
    # 最後の砦: DBUnavailableError の捕捉漏れを防ぐ（落ちない設計の維持）
    from utils.db import DBUnavailableError
    try:
        if "main" not in globals():
            raise RuntimeError("main() function is not defined in app.py")
        main()
    except DBUnavailableError as e:
        # 既存の個別捕捉（9箇所）で捕捉できなかった場合の統一UX
        handle_db_unavailable(context="main-top", operation="main()実行")
    except Exception as e:
        _panic_screen("main()", e)
        # st.stop()は呼ばない（本文を表示するため）

from material_form_detailed import show_detailed_material_form
from periodic_table_ui import show_periodic_table
from material_detail_tabs import show_material_detail_tabs

# Git SHA取得関数（ビルド情報表示用）
import subprocess

def get_git_sha() -> str:
    """Gitの短縮SHAを取得（失敗時は'no-git'を返す）"""
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        return sha
    except (subprocess.CalledProcessError, FileNotFoundError, Exception):
        return "no-git"

# クラウド環境でのポート設定
if 'PORT' in os.environ:
    port = int(os.environ.get("PORT", 8501))

# 画像パスの取得（複数のパスを試す）
def safe_url(url: str) -> str:
    """
    URLのpath部分をエンコード（日本語ファイル名対応）
    
    Args:
        url: 元のURL
    
    Returns:
        エンコードされたURL
    """
    if not url:
        return url
    try:
        p = urlsplit(url)
        # path部分をエンコード（/と%はそのまま）
        encoded_path = quote(p.path, safe="/%")
        return urlunsplit((p.scheme, p.netloc, encoded_path, p.query, p.fragment))
    except Exception:
        # エンコードに失敗した場合は元のURLを返す
        return url


@st.cache_data(ttl=600)  # 画像URL: 600秒（10分）TTL（Network transfer削減のため）
def get_material_image_url_cached(db_url: str, material_id: int, updated_at_str: str = None) -> Optional[str]:
    """
    材料の画像URLを取得（キャッシュ付き、primaryのみ）
    
    Args:
        db_url: データベースURL（キャッシュキー用、DB切替時にキャッシュが混ざらないようにする）
        material_id: 材料ID
        updated_at_str: 更新日時文字列（キャッシュキー用、Noneの場合は無視）
    
    Returns:
        primary画像URL（見つからない場合はNone）
    
    Note:
        - 画像URLが無い場合もキャッシュ（Noneをキャッシュ）して無駄なDB問い合わせを抑える
        - updated_at_strが変更されると自動的にキャッシュが無効化される
        - db_urlをキャッシュキーに含めることで、DB切替時にキャッシュが混ざらないようにする
    """
    if not material_id:
        return None
    
    # imagesテーブルから取得（primaryのみ）
    from utils.db import get_session, DBUnavailableError
    try:
        with get_session() as db:
            from database import Image
            from sqlalchemy import select
            stmt = select(Image).filter(
                Image.material_id == material_id,
                Image.kind == 'primary'
            )
            result = db.execute(stmt)
            primary_img = result.scalar_one_or_none()
            if primary_img and primary_img.public_url:
                return primary_img.public_url
    except DBUnavailableError:
        # DB接続エラー時はNoneを返す（UI崩壊を防ぐ）
        logger.warning(f"[get_material_image_url_cached] DB unavailable for material_id={material_id}")
        return None
    
    return None


def get_material_image_url(material_id: int, updated_at_str: str | None = None, db_url: str | None = None) -> Optional[str]:
    """
    materialsテーブルから画像URLを取得（primaryのみ）
    
    一覧/HOMEのトップ画像はprimaryのみを使用。
    space/productは用途タブ専用のため、ここでは返さない。
    
    Args:
        material_id: 材料ID
        updated_at_str: 更新日時文字列（キャッシュキー用、Noneの場合は無視）
        db_url: データベースURL（キャッシュキー用、Noneの場合は内部で取得）
    
    Returns:
        primary画像URL（見つからない場合はNone）
    
    Note:
        - キャッシュ付き関数でDBから取得
        - db_urlがNoneの場合は内部でget_database_url()を呼ぶ
        - updated_at_strが変更されると自動的にキャッシュが無効化される
    """
    if not material_id:
        return None
    
    # db_urlをキャッシュキーに含める（DB切替時にキャッシュが混ざらないようにする）
    # 呼び出し元がdb_urlを持っている場合はそれを使用、なければ内部で取得
    if db_url is None:
        from utils.settings import get_database_url
        db_url = get_database_url()
    return get_material_image_url_cached(db_url, material_id, updated_at_str)


def resolve_material_image_url(material, db_url: str) -> Optional[str]:
    # primary_image_url があれば即return（DBアクセスなし）
    # updated_at が無くても DB取得は試みる（updated_at_str=None OK）
    # dict / object 両対応（材料一覧で dict が渡される場合があるため）
    if isinstance(material, dict):
        primary_image_url = (
            material.get("primary_image_url")
            or material.get("image_url")
            or material.get("primary_image")
            or material.get("primary_image_src")
            or material.get("image_primary_url")
        )
        material_id = material.get("id")
        updated_at = material.get("updated_at")
    else:
        primary_image_url = getattr(material, "primary_image_url", None)
        material_id = getattr(material, "id", None)
        updated_at = getattr(material, "updated_at", None)

    if primary_image_url and str(primary_image_url).strip() and str(primary_image_url).startswith(("http://", "https://")):
        return str(primary_image_url)

    if not material_id:
        return None

    updated_at_str = None
    if updated_at:
        if hasattr(updated_at, "isoformat"):
            updated_at_str = updated_at.isoformat()
        else:
            updated_at_str = str(updated_at)

    return get_material_image_url(int(material_id), updated_at_str, db_url=db_url)


def get_image_path(filename):
    """画像パスを取得"""
    possible_paths = [
        Path("static/images") / filename,
        Path("写真") / filename,
        Path(filename)
    ]
    
    for path in possible_paths:
        if path.exists():
            return str(path)
    return None

def get_base64_image(image_path):
    """画像をBase64エンコード"""
    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as img_file:
                return base64.b64encode(img_file.read()).decode()
        except Exception as e:
            logger.warning(f"画像読み込みエラー: {e}")
            return None
    return None

# 背景画像の読み込み（メイン.webpのみ）
main_bg_path = get_image_path("メイン.webp")
main_bg_base64 = get_base64_image(main_bg_path) if main_bg_path else None

# アイコンファイルの読み込み（iconmonstr風のシンプルなSVGアイコン）
def get_icon_path(icon_name: str) -> Optional[str]:
    """アイコンファイルのパスを取得"""
    icon_path = Path("static/icons") / f"{icon_name}.svg"
    if icon_path.exists():
        return str(icon_path)
    return None

def get_icon_base64(icon_name: str) -> Optional[str]:
    """アイコンをBase64エンコードして返す"""
    icon_path = get_icon_path(icon_name)
    if icon_path:
        try:
            with open(icon_path, "rb") as f:
                return base64.b64encode(f.read()).decode()
        except Exception:
            return None
    return None

def get_icon_svg_inline(icon_name: str, size: int = 48, color: str = "#999999") -> str:
    """アイコンをインラインSVGとして返す（色とサイズを調整）"""
    icon_path = get_icon_path(icon_name)
    if icon_path:
        try:
            with open(icon_path, "r", encoding="utf-8") as f:
                svg_content = f.read()
                # 色とサイズを置換
                svg_content = svg_content.replace('stroke="#999999"', f'stroke="{color}"')
                svg_content = svg_content.replace('width="48"', f'width="{size}"')
                svg_content = svg_content.replace('height="48"', f'height="{size}"')
                return base64.b64encode(svg_content.encode()).decode()
        except Exception:
            pass
    return ""

# デバッグスイッチ（サイドバーでCSSを無効化可能）
# 注意: この変数はmain()関数内で設定されるため、ここでは定義のみ
debug_no_css = False

# WOTA風シンプルなカスタムCSS（視認性重視・コントラスト確保）
def get_custom_css():
    """カスタムCSSを生成（WOTA風シンプルデザイン・コントラスト確保）"""
    return f"""
<style>
    /* CSS変数（コントラスト確保のための共通ルール） */
    :root {{
        --bg: #ffffff;
        --text: #111111;
        --muted: #666666;
        --surface: #f7f7f7;
        --border: #e5e5e5;
        --primary: #1a1a1a;
        --on-primary: #ffffff;
    }}
    
    /* ベースフォント - シンプルなサンセリフ（WOTA風） */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    
    * {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif !important;
    }}
    
    /* ベース文字色を確保（視認性向上） */
    html, body, [class*="st-"], p, span, div, h1, h2, h3, h4, h5, h6 {{
        color: var(--text) !important;
    }}
    
    /* メイン背景 - WOTA風シンプル（白背景） */
    .stApp {{
        background: #ffffff;
        position: relative;
        min-height: 100vh;
    }}
    
    .stApp::before {{
        display: none;
    }}
    
    .main .block-container {{
        padding-top: 2rem;
        padding-bottom: 2rem;
        position: relative;
        z-index: 10;
        background: transparent;
        max-width: 1200px;
    }}
    
    /* ヘッダー - WOTA風シンプルデザイン */
    .main-header {{
        font-size: 2.5rem;
        font-weight: 600;
        color: #1a1a1a;
        text-align: left;
        margin-bottom: 0.5rem;
        letter-spacing: -0.02em;
        position: relative;
        z-index: 2;
        line-height: 1.3;
        margin-top: 0;
    }}
    
    .main-header::after {{
        display: none;
    }}
    
    /* サブ背景画像を装飾として使用（非表示に変更 - 白飛び防止） */
    .material-decoration {{
        display: none;
        position: absolute;
        opacity: 0.05;
        z-index: -1;
        pointer-events: none;
    }}
    
    .decoration-1 {{
        display: none;
    }}
    
    .decoration-2 {{
        display: none;
    }}
    
    /* カードスタイル - WOTA風シンプル */
    .material-card-container {{
        background: #ffffff;
        border-radius: 0;
        padding: 32px;
        margin: 24px 0;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        transition: all 0.2s ease;
        border: 1px solid rgba(0, 0, 0, 0.08);
        position: relative;
        overflow: hidden;
    }}
    
    .material-card-container::before {{
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 2px;
        background: #1a1a1a;
        opacity: 1;
    }}
    
    .material-card-container:hover {{
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
        border-color: rgba(0, 0, 0, 0.15);
    }}
    
    /* カテゴリバッジ - 読みやすく、タグとして表示 */
    .category-badge {{
        display: inline-block;
        background: #f0f0f0;
        color: #1a1a1a;
        padding: 4px 12px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 500;
        margin: 4px 4px 0 0;
        box-shadow: none;
        text-transform: none;
        letter-spacing: 0;
        border: 1px solid #ddd;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        line-height: 1.4;
        max-width: 100%;
        word-wrap: break-word;
        overflow-wrap: break-word;
        white-space: normal;
    }}
    
    /* 素材画像のヒーロー領域 */
    .material-hero-image {{
        width: 100%;
        aspect-ratio: 16 / 9;
        object-fit: cover;
        background: #f5f5f5;
        border-radius: 0;
        margin-bottom: 16px;
    }}
    
    /* 統計カード - WOTA風シンプル */
    .stat-card {{
        background: #ffffff;
        border-radius: 0;
        padding: 32px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        transition: all 0.2s ease;
        border: 1px solid rgba(0, 0, 0, 0.08);
        border-top: 2px solid #1a1a1a;
        position: relative;
        overflow: hidden;
    }}
    
    .stat-card:hover {{
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
    }}
    
    .stat-value {{
        font-size: 2.5rem;
        font-weight: 600;
        color: #1a1a1a;
        margin: 15px 0;
        position: relative;
        z-index: 1;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }}
    
    .stat-label {{
        color: #666666;
        font-size: 14px;
        font-weight: 400;
        text-transform: none;
        letter-spacing: 0;
        position: relative;
        z-index: 1;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }}
    
    /* ボタンスタイル - WOTA風シンプル（コントラスト確保・白文字強制） */
    .stButton>button,
    button[data-baseweb="button"],
    [data-testid="baseButton-secondary"],
    [data-testid="baseButton-primary"],
    [data-testid="baseButton-secondary"] button,
    [data-testid="baseButton-primary"] button,
    button[type="button"] {{
        background: #1a1a1a !important;
        color: #ffffff !important;
        border: 1px solid #1a1a1a !important;
        border-radius: 4px;
        padding: 0.75rem 2rem;
        font-weight: 500;
        transition: all 0.2s ease;
        box-shadow: none;
        text-transform: none;
        letter-spacing: 0;
        font-size: 15px;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }}
    
    .stButton>button *,
    button[data-baseweb="button"] *,
    [data-testid="baseButton-secondary"] *,
    [data-testid="baseButton-primary"] *,
    button[type="button"] *,
    .stButton>button span,
    button[data-baseweb="button"] span {{
        color: #ffffff !important;
    }}
    
    .stButton>button:hover,
    button[data-baseweb="button"]:hover,
    [data-testid="baseButton-secondary"]:hover button,
    [data-testid="baseButton-primary"]:hover button,
    button[type="button"]:hover {{
        background: #333333 !important;
        border-color: #333333 !important;
        color: #ffffff !important;
        transform: none;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    }}
    
    .stButton>button:hover *,
    button[data-baseweb="button"]:hover *,
    button[type="button"]:hover * {{
        color: #ffffff !important;
    }}
    
    /* 黒背景のヘッダー/バー部分の文字色を白に統一 */
    [style*="background: #1a1a1a"],
    [style*="background:#1a1a1a"],
    [style*="background-color: #1a1a1a"],
    [style*="background-color:#1a1a1a"],
    .black-bar,
    .dark-header {{
        color: #ffffff !important;
    }}
    
    .black-bar *,
    .dark-header * {{
        color: #ffffff !important;
    }}
    
    /* Streamlitのヘッダーバーの文字色を白に */
    [data-testid="stHeader"],
    header[data-testid="stHeader"],
    [data-testid="stHeader"] *,
    header[data-testid="stHeader"] *,
    [data-testid="stHeader"] p,
    [data-testid="stHeader"] span,
    [data-testid="stHeader"] div,
    [data-testid="stHeader"] a {{
        color: #ffffff !important;
    }}
    
    /* Streamlitのメニューボタン（ハンバーガーメニュー）の色 */
    [data-testid="stHeader"] button,
    [data-testid="stHeader"] button *,
    header[data-testid="stHeader"] button,
    header[data-testid="stHeader"] button * {{
        color: #ffffff !important;
        fill: #ffffff !important;
        stroke: #ffffff !important;
    }}
    
    /* Streamlitのツールバー（右上のメニュー） */
    [data-testid="stToolbar"],
    [data-testid="stToolbar"] *,
    [data-testid="stToolbar"] button,
    [data-testid="stToolbar"] button * {{
        color: #ffffff !important;
    }}
    
    /* 黒背景の任意の要素 */
    div[style*="background: #1a1a1a"],
    div[style*="background:#1a1a1a"],
    div[style*="background-color: #1a1a1a"],
    div[style*="background-color:#1a1a1a"],
    section[style*="background: #1a1a1a"],
    section[style*="background:#1a1a1a"] {{
        color: #ffffff !important;
    }}
    
    div[style*="background: #1a1a1a"] *,
    div[style*="background:#1a1a1a"] *,
    div[style*="background-color: #1a1a1a"] *,
    div[style*="background-color:#1a1a1a"] *,
    section[style*="background: #1a1a1a"] *,
    section[style*="background:#1a1a1a"] * {{
        color: #ffffff !important;
    }}
    
    /* サイドバー - WOTA風シンプル */
    [data-testid="stSidebar"] {{
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        border-right: 1px solid rgba(0, 0, 0, 0.08);
    }}
    
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {{
        color: #1a1a1a;
        font-weight: 400;
    }}
    
    /* ラジオボタン - シンプルなメニュー */
    [data-testid="stRadio"] label {{
        font-size: 15px;
        font-weight: 400;
        color: #1a1a1a;
        padding: 8px 12px;
        border-radius: 4px;
        transition: background 0.2s ease;
    }}
    
    [data-testid="stRadio"] label:hover {{
        background: rgba(0, 0, 0, 0.04);
    }}
    
    [data-testid="stRadio"] input[type="radio"]:checked + label {{
        background: rgba(0, 0, 0, 0.08);
        font-weight: 500;
    }}
    
    /* 入力フィールド - WOTA風シンプル */
    .stTextInput>div>div>input,
    .stTextArea>div>div>textarea,
    .stSelectbox>div>div>select {{
        border-radius: 4px;
        border: 1px solid rgba(0, 0, 0, 0.15);
        background: #ffffff;
        transition: all 0.2s ease;
        box-shadow: none;
        font-size: 15px;
        padding: 0.5rem 0.75rem;
    }}
    
    .stTextInput>div>div>input:focus,
    .stTextArea>div>div>textarea:focus,
    .stSelectbox>div>div>select:focus {{
        border-color: #1a1a1a;
        box-shadow: 0 0 0 2px rgba(26, 26, 26, 0.1);
        background: #ffffff;
        outline: none;
    }}
    
    /* メトリクス - WOTA風 */
    [data-testid="stMetricValue"] {{
        font-size: 2rem;
        font-weight: 600;
        color: #1a1a1a;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }}
    
    [data-testid="stMetricLabel"] {{
        font-size: 14px;
        font-weight: 400;
        color: #666666;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }}
    
    /* グラデーションテキスト - WOTA風シンプル（削除） */
    
    /* マテリアル装飾要素 */
    .material-texture {{
        position: relative;
        overflow: hidden;
    }}
    
    .material-texture::after {{
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: none;
        background-size: 200%;
        background-position: center;
        opacity: 0.03;
        pointer-events: none;
        mix-blend-mode: multiply;
    }}
    
    /* カードグリッド */
    .card-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
        gap: 25px;
        margin: 30px 0;
    }}
    
    /* ヒーローセクション - WOTA風シンプル */
    .hero-section {{
        background: #ffffff;
        border-radius: 0;
        padding: 40px 0;
        text-align: left;
        margin: 40px 0;
        box-shadow: none;
        border: none;
        border-bottom: 1px solid rgba(0, 0, 0, 0.08);
        position: relative;
        overflow: hidden;
    }}
    
    .hero-section::before {{
        display: none;
    }}
    
    /* セクションタイトル - WOTA風 */
    .section-title {{
        font-size: 2rem;
        font-weight: 600;
        color: #1a1a1a;
        margin: 40px 0 24px 0;
        text-align: left;
        position: relative;
        padding-bottom: 16px;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        letter-spacing: -0.01em;
    }}
    
    .section-title::after {{
        content: '';
        display: block;
        width: 40px;
        height: 2px;
        background: #1a1a1a;
        margin: 16px 0 0;
        border-radius: 0;
    }}
    
    /* 見出しの視認性向上 */
    h1, h2, h3, h4, h5, h6 {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
        font-weight: 600 !important;
        color: #1a1a1a !important;
        letter-spacing: -0.01em;
    }}
    
    /* 本文の視認性向上 */
    p, span, div, li {{
        font-size: 15px;
        line-height: 1.6;
        color: #1a1a1a;
    }}
    
    /* 統計情報を左下に固定表示 */
    .stats-fixed {{
        position: fixed;
        bottom: 20px;
        left: 20px;
        background: rgba(255, 255, 255, 0.95);
        padding: 12px 20px;
        border: 1px solid rgba(0, 0, 0, 0.08);
        font-size: 11px;
        color: #666;
        z-index: 1000;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }}
    
    .stats-fixed div {{
        margin: 2px 0;
    }}
    
    .stats-fixed strong {{
        color: #1a1a1a;
        font-weight: 600;
    }}
    
    /* サイトヘッダー（ロゴ表示用） */
    .site-header {{
        display: flex;
        align-items: flex-start;
        gap: 12px;
        margin-top: 4px;
        margin-bottom: 12px;
    }}
    
    .site-title-block {{
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        gap: 0;
    }}
    
    .site-logo svg {{
        height: 36px;
        width: auto;
        vertical-align: middle;
    }}
    
    .site-mark {{
        /* サイズは render_logo_mark(height_px=72) の inline style で指定 */
        /* ここでは余白や整列のみ */
    }}
    
    .site-logo-fallback {{
        font-size: 36px;
        font-weight: 600;
        color: #1a1a1a;
    }}
    
    .site-subtitle {{
        font-size: 14px;
        color: #666;
        margin-top: 8px;
    }}
    
    /* モバイル対応（画面幅が小さい場合） */
    @media (max-width: 768px) {{
        .site-header {{
            flex-direction: column;
            align-items: flex-start;
            gap: 8px;
        }}
        
        .site-logo svg {{
            height: 28px;
        }}
        
        /* ロゴマークのサイズは render_logo_mark(height_px=72) の inline style で指定 */
        
        .site-subtitle {{
            margin-top: 8px;
            line-height: 1.4;
        }}
    }}
</style>
"""

# データベース初期化
# DB初期化（常に実行：既存DBでも不足カラムを自動追加）
init_db()

def get_material_count_sqlite(db_path: Path) -> int:
    """
    sqlite3で直接materials件数を取得（ORMを使わない安全な方法）
    
    Args:
        db_path: データベースファイルのパス
    
    Returns:
        materials件数（エラー時は0）
    """
    if not db_path.exists():
        return 0
    
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path.absolute()))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM materials")
            count = cursor.fetchone()[0]
            return count if count is not None else 0
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"get_material_count_sqlite failed: {e}")
        return 0


def should_init_sample_data() -> bool:
    """
    サンプルデータを初期化すべきか判定
    
    Returns:
        True: 初期化すべき（INIT_SAMPLE_DATA=1 かつ DBが空）
        False: 初期化しない
    """
    # 環境変数フラグが設定されていない場合は実行しない
    if os.getenv("INIT_SAMPLE_DATA") != "1":
        return False
    
    # DBが空の場合のみ実行
    db_path = Path("materials.db")
    count = get_material_count_sqlite(db_path)
    return count == 0


def maybe_init_sample_data():
    """
    サンプルデータを初期化する（環境変数がONのときだけ）
    
    注意:
    - 起動時（トップレベル）では import しない
    - 環境変数 INIT_SAMPLE_DATA=1 が設定されている場合のみ実行
    - セッション内で1回だけ実行（st.session_stateでガード）
    - 例外が出てもアプリ起動を殺さない（ログのみ）
    """
    if os.getenv("INIT_SAMPLE_DATA") != "1":
        return
    
    # セッション内で1回だけ実行（Streamlitの再実行特性に対応）
    if st.session_state.get("_seed_done", False):
        return
    
    try:
        # Lazy import: 起動時にimportしない（SyntaxErrorがあっても起動できる）
        from init_sample_data import init_sample_data
        init_sample_data()
        logger.info("Sample data initialized successfully")
    except Exception as e:
        # 落とさない（DEBUG時だけ表示でもOK）
        import traceback
        logger.warning(f"init_sample_data failed: {e}")
        if os.getenv("DEBUG", "0") == "1":
            logger.debug(traceback.format_exc())
    finally:
        # 成功/失敗問わず、セッション内で1回だけ実行するフラグを立てる
        st.session_state["_seed_done"] = True

# Phase 2: get_db() を削除し、統一APIを使用
# 旧: def get_db(): return SessionLocal()
# 新: from utils.db import get_session, session_scope
# 
# 読み取り専用: with get_session() as db: ...
# 書き込み: with session_scope() as db: ...


@st.cache_data(ttl=300)  # 件数/統計: 300秒（5分）TTL（起床頻度を下げる）
def get_material_count_cached(db_url: str, include_unpublished: bool = False, include_deleted: bool = False) -> int:
    """
    材料件数を取得（キャッシュ付き、300秒TTL）
    
    Args:
        db_url: データベースURL（キャッシュキー用）
        include_unpublished: Trueの場合、非公開（is_published=0）も含める
        include_deleted: Trueの場合、論理削除済み（is_deleted=1）も含める
    
    Returns:
        材料件数
    """
    from services.materials_service import get_material_count
    bump_db_call_counter("count")
    return get_material_count(include_unpublished=include_unpublished, include_deleted=include_deleted)


@st.cache_data(ttl=120)  # 一覧: 120秒（2分）TTL
def fetch_materials_page_cached(
    db_url: str,
    include_unpublished: bool = False,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
    search_query: str = None
) -> List[Dict[str, Any]]:
    """
    材料一覧をページングで取得（キャッシュ付き、120秒TTL、dict化して返す）
    
    Args:
        db_url: データベースURL（キャッシュキー用）
        include_unpublished: Trueの場合、非公開（is_published=0）も含める
        include_deleted: Trueの場合、論理削除済み（is_deleted=1）も含める
        limit: 取得件数
        offset: オフセット
        search_query: 検索クエリ（材料名で部分一致）
    
    Returns:
        材料データのdictリスト（表示用）
    
    Note:
        - サービス層経由でDBアクセス
    """
    from services.materials_service import get_materials_page
    bump_db_call_counter("page")
    return get_materials_page(
        include_unpublished=include_unpublished,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
        search_query=search_query
    )


@st.cache_data(ttl=120)  # 全材料: 120秒（2分）TTL
def get_all_materials(db_url: str, include_unpublished: bool = False, include_deleted: bool = False):
    """
    全材料を取得（Eager Loadでリレーションも先読み・全リレーション網羅）
    重複を除去して返す（DB由来のデータに一本化）
    
    Args:
        db_url: データベースURL（キャッシュキー用、DB切替時にキャッシュが混ざらないようにする）
        include_unpublished: Trueの場合、非公開（is_published=0）も含める
        include_deleted: Trueの場合、論理削除済み（is_deleted=1）も含める
    
    Note:
        - NeonのCU-hours節約のため、ttl=120秒でキャッシュ
        - サービス層経由でDBアクセス
        - db_urlをキャッシュキーに含めることで、DB切替時にキャッシュが混ざらないようにする
    """
    from services.materials_service import get_all_materials as _get_all_materials
    bump_db_call_counter("list")
    return _get_all_materials(include_unpublished=include_unpublished, include_deleted=include_deleted)

def get_material_by_id(material_id: int):
    """
    IDで材料を取得（サービス層経由）
    
    Args:
        material_id: 材料ID
    
    Returns:
        Materialオブジェクト（見つからない場合はNone）
    
    Note:
        - サービス層経由でDBアクセス
    """
    from services.materials_service import get_material_by_id as _get_material_by_id
    bump_db_call_counter("detail")
    return _get_material_by_id(material_id)

def create_material(name, category, description, properties_data):
    """材料を作成"""
    # Phase 2: 統一APIを使用（書き込み、自動commit/rollback）
    from utils.db import session_scope
    with session_scope() as db:
        material = Material(
            name=name,
            category=category,
            description=description
        )
        db.add(material)
        db.flush()
        
        for prop in properties_data:
            if prop.get('name') and prop.get('value'):
                db_property = Property(
                    material_id=material.id,
                    property_name=prop['name'],
                    value=float(prop['value']) if prop['value'] else None,
                    unit=prop.get('unit', '')
                )
                db.add(db_property)
        
        # session_scopeが自動commit（例外時は自動rollback）
        return material

def generate_qr_code(material_id: int):
    """QRコードを生成（後方互換性のため残すが、新しいコードではgenerate_qr_png_bytesを使用）"""
    from utils.qr import generate_qr_png_bytes
    qr_bytes = generate_qr_png_bytes(f"Material ID: {material_id}")
    if qr_bytes:
        from PIL import Image as PILImage
        from io import BytesIO
        return PILImage.open(BytesIO(qr_bytes))
    return None

def create_category_chart(materials):
    """カテゴリ別の円グラフを作成"""
    if not materials:
        return None
    
    categories = [m.category or "未分類" for m in materials]
    category_counts = Counter(categories)
    
    fig = px.pie(
        values=list(category_counts.values()),
        names=list(category_counts.keys()),
        title="カテゴリ別分布",
        color_discrete_sequence=px.colors.qualitative.Set3
    )
    fig.update_traces(
        textposition='inside',
        textinfo='percent+label',
        hovertemplate='<b>%{label}</b><br>数量: %{value}<br>割合: %{percent}<extra></extra>'
    )
    fig.update_layout(
        font=dict(size=14),
        showlegend=True,
        height=400,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    return fig

def create_timeline_chart(materials):
    """登録タイムラインを作成"""
    if not materials:
        return None
    
    dates = [m.created_at.date() if m.created_at else datetime.now().date() for m in materials]
    date_counts = Counter(dates)
    sorted_dates = sorted(date_counts.items())
    
    df = pd.DataFrame(sorted_dates, columns=['日付', '登録数'])
    df['累計'] = df['登録数'].cumsum()
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['日付'],
        y=df['累計'],
        mode='lines+markers',
        name='累計登録数',
        line=dict(color='#667eea', width=3),
        marker=dict(size=8, color='#764ba2')
    ))
    fig.update_layout(
        title="登録数の推移",
        xaxis_title="日付",
        yaxis_title="累計登録数",
        height=300,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(size=12)
    )
    return fig

def show_materials_duplicate_diagnostics():
    """材料重複診断UIを表示"""
    st.markdown("# 🔍 材料重複診断")
    st.markdown("材料の重複状況を診断します")
    st.markdown("---")
    
    # Phase 2: 統一APIを使用（読み取り専用）
    from utils.db import get_session
    with get_session() as db:
        # DB materials count
        db_count = db.execute(select(func.count(Material.id))).scalar() or 0
        
        # UI materials count（高速化のためget_material_count_cachedを使用、DEBUG=0の時はスキップ）
        debug_enabled = show_debug_ui()
        if debug_enabled:
            from utils.settings import get_database_url
            db_url = get_database_url()
            ui_count = get_material_count_cached(db_url, include_unpublished=False, include_deleted=False)
            # Unique names count（DEBUG時のみ、軽量クエリで取得）
            unique_names_stmt = select(func.count(func.distinct(Material.name_official))).filter(Material.is_deleted == 0, Material.is_published == 1)
            unique_names_count = db.execute(unique_names_stmt).scalar() or 0
        else:
            ui_count = db_count
            unique_names_count = 0
        
        # Duplicate name list（同名の材料を検出、DEBUG=0の時はスキップ）
        duplicate_list = []
        if debug_enabled:
            from collections import Counter
            # DEBUG時のみ重複チェック（軽量クエリで取得）
            name_stmt = select(Material.name_official, func.count(Material.id)).filter(
                Material.is_deleted == 0,
                Material.is_published == 1
            ).group_by(Material.name_official).having(func.count(Material.id) > 1).limit(20)
            name_results = db.execute(name_stmt).all()
            duplicate_list = [(name, count) for name, count in name_results if name]
        
        # 統計表示
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("DB materials count", db_count)
        with col2:
            st.metric("UI materials count", ui_count, delta=f"{ui_count - db_count}" if ui_count != db_count else None)
        with col3:
            st.metric("Unique names count", unique_names_count)
        with col4:
            st.metric("Duplicate names", len(duplicate_list))
        
        # 重複チェック結果（DEBUG=0の時はスキップ）
        if debug_enabled:
            if ui_count == unique_names_count:
                st.success("✅ 重複なし: UI materials count == Unique names count")
            else:
                st.warning(f"⚠️ 重複あり: UI materials count ({ui_count}) != Unique names count ({unique_names_count})")
            
            # 重複リスト表示
            if duplicate_list:
                st.markdown("### 重複材料名（上位20件）")
                for name, count in duplicate_list:
                    st.markdown(f"- **{name}**: {count}件")
                    
                    # 重複している材料のIDを表示（軽量クエリで取得）
                    duplicate_ids_stmt = select(Material.id).filter(
                        Material.name_official == name,
                        Material.is_deleted == 0,
                        Material.is_published == 1
                    ).limit(10)
                    duplicate_ids = db.execute(duplicate_ids_stmt).scalars().all()
                    ids = [str(mid) for mid in duplicate_ids]
                st.caption(f"  ID: {', '.join(ids)}")
        else:
            st.info("重複している材料名はありません。")
        
        # 詳細情報
        with st.expander("詳細情報"):
            st.markdown("#### 全材料名リスト")
            # 全材料名を取得（軽量クエリ）
            all_names_stmt = select(Material.name_official).filter(
                Material.is_deleted == 0,
                Material.is_published == 1
            ).order_by(Material.name_official).limit(100)
            all_names = [row[0] for row in db.execute(all_names_stmt).all() if row[0]]
            for name in all_names:
                st.text(f"- {name}")


def show_asset_diagnostics(asset_stats: dict):
    """Asset診断UIを表示"""
    st.markdown("# 🔍 Asset診断モード")
    st.markdown("生成物（元素画像など）の存在状況を診断します")
    st.markdown("---")
    
    from utils.paths import get_generated_dir, resolve_path
    from PIL import Image as PILImage
    
    # 元素画像の診断
    if "elements" in asset_stats:
        st.markdown("## 元素画像")
        elem_stats = asset_stats["elements"]
        
        if "error" in elem_stats:
            st.error(f"エラー: {elem_stats['error']}")
        else:
            total = elem_stats.get("total", 0)
            existing = elem_stats.get("existing", 0)
            generated = elem_stats.get("generated", 0)
            failed = elem_stats.get("failed", 0)
            missing = elem_stats.get("missing_files", [])
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("総数", total)
            with col2:
                st.metric("存在", existing, delta=f"{existing/total*100:.1f}%" if total > 0 else "0%")
            with col3:
                st.metric("生成", generated)
            with col4:
                st.metric("欠損", failed, delta=f"-{failed}" if failed > 0 else None, delta_color="inverse")
            
            if missing:
                with st.expander(f"欠損ファイル一覧 ({len(missing)}件)", expanded=False):
                    for filename in missing[:20]:  # 最大20件表示
                        st.text(f"  • {filename}")
                    if len(missing) > 20:
                        st.text(f"  ... 他 {len(missing) - 20} 件")
            
            # 代表的な画像のプレビュー
            if existing > 0:
                st.markdown("#### プレビュー（代表例）")
                elem_dir = get_generated_dir("elements")
                preview_files = list(elem_dir.glob("element_*.png"))[:6]  # 最大6件
                
                if preview_files:
                    cols = st.columns(min(3, len(preview_files)))
                    for idx, filepath in enumerate(preview_files):
                        with cols[idx % 3]:
                            try:
                                from utils.image_display import display_image_unified
                                display_image_unified(filepath, caption=filepath.name, width=150)
                            except Exception as e:
                                st.caption(f"{filepath.name} (読み込みエラー)")
    
    # 加工例画像の診断
    if "process_examples" in asset_stats:
        st.markdown("---")
        st.markdown("## 加工例画像")
        proc_stats = asset_stats["process_examples"]
        
        if "error" in proc_stats:
            st.error(f"エラー: {proc_stats['error']}")
        else:
            total = proc_stats.get("total", 0)
            existing = proc_stats.get("existing", 0)
            generated = proc_stats.get("generated", 0)
            failed = proc_stats.get("failed", 0)
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("総数", total)
            with col2:
                st.metric("存在", existing)
            with col3:
                st.metric("生成", generated)
            with col4:
                st.metric("欠損", failed, delta_color="inverse" if failed > 0 else "normal")
    
    # カテゴリ画像の診断
    if "categories" in asset_stats:
        st.markdown("---")
        st.markdown("## カテゴリ画像")
        cat_stats = asset_stats["categories"]
        
        if "error" in cat_stats:
            st.error(f"エラー: {cat_stats['error']}")
        else:
            total = cat_stats.get("total", 0)
            existing = cat_stats.get("existing", 0)
            st.metric("総数", total)
            st.metric("存在", existing)
    
    st.markdown("---")
    st.info("💡 ヒント: 欠損がある場合は、アプリを再起動すると自動生成されます。")

# メインアプリケーション
def get_assets_mode_stats():
    """
    Assets Mode診断: URLを持つ画像数をカウント
    
    Returns:
        (mode, url_count, total_count) のタプル
    """
    # Phase 2: 統一APIを使用（読み取り専用）
    from utils.db import get_session
    with get_session() as db:
        # Imageテーブル
        total_images = db.query(func.count(Image.id)).scalar() or 0
        url_images = db.query(func.count(Image.id)).filter(
            Image.url != None,
            Image.url != ""
        ).scalar() or 0
        
        # Material.texture_image_url
        total_textures = db.query(func.count(Material.id)).filter(
            Material.texture_image_path != None,
            Material.texture_image_path != ""
        ).scalar() or 0
        url_textures = db.query(func.count(Material.id)).filter(
            Material.texture_image_url != None,
            Material.texture_image_url != ""
        ).scalar() or 0
        
        # UseExample.image_url
        total_use_cases = db.query(func.count(UseExample.id)).filter(
            UseExample.image_path != None,
            UseExample.image_path != ""
        ).scalar() or 0
        url_use_cases = db.query(func.count(UseExample.id)).filter(
            UseExample.image_url != None,
            UseExample.image_url != ""
        ).scalar() or 0
        
        # ProcessExampleImage.image_url
        total_process = db.query(func.count(ProcessExampleImage.id)).filter(
            ProcessExampleImage.image_path != None,
            ProcessExampleImage.image_path != ""
        ).scalar() or 0
        url_process = db.query(func.count(ProcessExampleImage.id)).filter(
            ProcessExampleImage.image_url != None,
            ProcessExampleImage.image_url != ""
        ).scalar() or 0
        
        total_count = total_images + total_textures + total_use_cases + total_process
        url_count = url_images + url_textures + url_use_cases + url_process
        
        if url_count > 0:
            mode = "url" if url_count == total_count else "mixed"
        else:
            mode = "local"
        
        return mode, url_count, total_count


def bump_db_call_counter(kind: str):
    """
    DB呼び出しカウンタをインクリメント（DEBUG_ENV=1時のみ）
    
    Args:
        kind: DB呼び出し種別（count/page/list/detail/statistics）
    """
    if os.getenv("DEBUG_ENV", "0") == "1":
        if "_db_call_counts" not in st.session_state:
            st.session_state["_db_call_counts"] = {
                "count": 0,
                "page": 0,
                "list": 0,
                "detail": 0,
                "statistics": 0,
            }
        if kind in st.session_state["_db_call_counts"]:
            st.session_state["_db_call_counts"][kind] += 1


def handle_db_unavailable(context: str, retry_fn=None, operation: str = None):
    """
    DBUnavailableError時の共通処理（ウォームアップUX + 統一メッセージ）
    
    Args:
        context: エラー発生コンテキスト（ログ用、「どの画面で」「どの操作で」）
        retry_fn: 再試行する関数（Noneの場合は自動リトライなし）
        operation: 操作名（例: "材料一覧取得"、"統計情報取得"）
    
    Note:
        - 最大2回の軽量リトライを試行
        - それでもダメなら統一メッセージ + st.stop()
        - 無限リトライ禁止（CU節約のため）
        - DEBUG_ENV=1では例外種別もloggerに出力（UIには出しすぎない）
    """
    from utils.db import DBUnavailableError
    from services.db_retry import db_retry
    import traceback
    import sys
    
    # 例外情報を取得（例外ハンドラから呼ばれる前提）
    exc_type, exc_value, exc_tb = sys.exc_info()
    
    # 常にログに出力（context と例外メッセージを含める）
    if exc_type and exc_value:
        exception_msg = str(exc_value)
        logger.warning(f"[DB_UNAVAILABLE] context={context} operation={operation} exception={exc_type.__name__}: {exception_msg}")
        
        # DEBUG_ENV=1 のときだけ traceback を logger に出す（UI表示ではなくログ）
        if os.getenv("DEBUG_ENV", "0") == "1":
            logger.warning(f"[DB_UNAVAILABLE] traceback:\n{traceback.format_exc()}")
    else:
        # 例外情報が取得できない場合（通常は発生しない）
        logger.warning(f"[DB_UNAVAILABLE] context={context} operation={operation} (例外情報が取得できませんでした)")
    
    # ウォームアップ表示
    st.info("🔄 データベースを起こしています...")
    
    # 自動リトライ（最大2回）
    if retry_fn is not None:
        try:
            result = db_retry(retry_fn, operation_name=f"{context} (自動リトライ)")
            # リトライ成功時はrerunして続行
            st.success("✅ データベース接続が復帰しました")
            st.rerun()
            return
        except DBUnavailableError:
            # リトライ失敗時は統一メッセージへ
            pass
    
    # 統一メッセージ + 再試行ボタン
    st.warning("⚠️ データベースがスリープ中の可能性があります。数秒後に再試行してください。")
    if st.button("🔄 再試行", key=f"retry_{context}"):
        st.rerun()
    st.stop()


def render_debug_sidebar_early():
    """
    Debugを先に描画（UIが出る前に死ぬ問題を回避）
    DBのpath/sha/columns/件数を表示
    例外が起きても最後まで描く（st.stop()は絶対に呼ばない）
    学生向けには何も出さない（show_debug_ui のみ）。
    """
    if not show_debug_ui():
        return

    import traceback
    import hashlib
    from pathlib import Path
    import sqlite3
    
    with st.sidebar:
        try:
            st.caption(f"build: {get_git_sha()}")
            st.caption(f"time: {datetime.now().isoformat(timespec='seconds')}")
        except Exception as e:
            # sidebarで例外が起きたら警告を出して続行（本体描画を止めない）
            st.sidebar.warning("Sidebar: build/time debug failed")
            with st.sidebar.expander("詳細", expanded=False):
                st.sidebar.exception(e)
        
        # DB呼び出し回数表示
        if "_db_call_counts" in st.session_state:
            counts = st.session_state["_db_call_counts"]
            total = sum(counts.values())
            if total > 0:
                st.sidebar.markdown("---")
                st.sidebar.markdown("### 📊 DB呼び出し回数")
                st.sidebar.write(f"**合計:** {total} 回")
                for kind, count in counts.items():
                    if count > 0:
                        st.sidebar.write(f"- {kind}: {count} 回")
        
        # デバッグ詳細
        with st.expander("🔧 Debug", expanded=False):
                # 環境情報（例外が起きても続行）
                try:
                    st.write("**環境情報:**")
                    st.write(f"- **cwd:** {str(Path.cwd())}")
                    st.write(f"- **__file__:** {__file__}")
                except Exception as e:
                    # sidebarで例外が起きたら警告を出して続行（本体描画を止めない）
                    st.sidebar.warning("Sidebar: env debug failed")
                    with st.sidebar.expander("詳細", expanded=False):
                        st.sidebar.exception(e)
                
                st.write("---")
                
                # DB fingerprint（ここで落ちてもアプリは止めない）
                try:
                    # 絶対パス固定（相対パス事故を潰す）
                    db_path = Path(__file__).parent / "materials.db"
                    st.write("**materials.db fingerprint:**")
                    
                    if not db_path.exists():
                        st.error(f"missing: {db_path}")
                    else:
                        b = db_path.read_bytes()
                        st.write(f"- **abs path:** {str(db_path.resolve())}")
                        st.write(f"- **size:** {db_path.stat().st_size:,} bytes")
                        st.write(f"- **mtime:** {datetime.fromtimestamp(db_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
                        st.write(f"- **sha256:** {hashlib.sha256(b).hexdigest()[:16]}")
                        
                        con = sqlite3.connect(str(db_path))
                        try:
                            cnt = con.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
                            st.write(f"- **count(materials):** {cnt} 件")
                            
                            cols = [r[1] for r in con.execute("PRAGMA table_info(materials)")]
                            if len(cols) > 50:
                                st.write(f"- **cols (先頭50件):** {', '.join(cols[:50])} ...")
                                st.write(f"  (他 {len(cols) - 50} 列)")
                            else:
                                st.write(f"- **cols (全{len(cols)}件):** {', '.join(cols)}")
                            
                            if cnt > 0:
                                first = con.execute("SELECT name_official, name FROM materials LIMIT 1").fetchone()
                                if first:
                                    first_name = first[0] or first[1] or "N/A"
                                    st.write(f"- **first material name:** {first_name}")
                        finally:
                            con.close()
                except Exception as e:
                    # sidebarで例外が起きたら警告を出して続行（本体描画を止めない）
                    st.sidebar.warning("Sidebar: DB fingerprint failed")
                    with st.sidebar.expander("詳細", expanded=False):
                        st.sidebar.exception(e)
                
                st.write("---")
                
                # card_generator/schemasのimportエラー情報（防御的に参照）
                try:
                    err = globals().get("_card_generator_import_error")
                    tb = globals().get("_card_generator_import_traceback")
                    if err:
                        st.write("**card_generator/schemas import エラー:**")
                        st.write(f"- **エラー:** {err}")
                        if tb:
                            with st.expander("詳細なトレースバック", expanded=False):
                                st.code(tb, language="python")
                    else:
                        st.write("**card_generator/schemas import:** ✅ 成功")
                except Exception as e:
                    # sidebarで例外が起きたら警告を出して続行（本体描画を止めない）
                    st.sidebar.warning("Sidebar: import error debug failed")
                    with st.sidebar.expander("詳細", expanded=False):
                        st.sidebar.exception(e)
                
                st.write("---")
                
                # 画像探索の詳細情報（Cloud上で実際のフォルダ・画像を確認）
                try:
                    from utils.image_display import get_material_image_ref
                    import re
                    
                    base = Path(__file__).parent / "static" / "images" / "materials"
                    # Cloud Secretsの前提を明記
                    image_base_url = os.getenv("IMAGE_BASE_URL")
                    image_version = os.getenv("IMAGE_VERSION")
                    st.write("**Cloud Secrets:**")
                    st.write(f"- **IMAGE_BASE_URL:** {'設定済み' if image_base_url else '未設定'}")
                    if image_base_url:
                        # 伏字で表示（最初の10文字のみ）
                        masked = image_base_url[:10] + "..." if len(image_base_url) > 10 else image_base_url
                        st.write(f"  - 値: {masked}")
                    st.write(f"- **IMAGE_VERSION:** {'設定済み' if image_version else '未設定'}")
                    if image_version:
                        st.write(f"  - 値: {image_version[:10]}...")
                    
                    st.write("**画像探索情報:**")
                    st.write(f"- **base dir:** {str(base)}")
                    
                    if base.exists():
                        dirs = [p.name for p in base.iterdir() if p.is_dir()]
                        primaries = list(base.glob("*/primary.jpg"))
                        st.write(f"- **dir count:** {len(dirs)}")
                        st.write(f"- **dirs (sample, 先頭30):** {dirs[:30]}")
                        st.write(f"- **primary.jpg count:** {len(primaries)}")
                    else:
                        st.warning(f"base dir not exists: {base}")
                        dirs = []
                    
                    # show_debug_ui() 通過済みのため詳細探索を表示
                    try:
                        from utils.settings import get_database_url
                        db_url = get_database_url()
                        material_count = get_material_count_cached(db_url, include_unpublished=False, include_deleted=False)
                        st.write(f"- **materials count:** {material_count}")
                        bump_db_call_counter("list")
                        materials = get_all_materials(db_url)
                        if materials:
                            st.write("**素材ごとの探索結果（先頭30件）:**")
                            
                            for m in materials[:30]:  # 先頭30件のみ
                                try:
                                    # get_material_image_refを使用して画像参照を取得
                                    # project_rootはbaseの親の親の親（static/images/materials -> static/images -> static -> プロジェクトルート）
                                    project_root = base.parent.parent.parent
                                    primary_src, primary_debug = get_material_image_ref(m, "primary", project_root)
                                    space_src, space_debug = get_material_image_ref(m, "space", project_root)
                                    product_src, product_debug = get_material_image_ref(m, "product", project_root)
                                    
                                    material_display_name = getattr(m, 'name_official', None) or getattr(m, 'name', None) or "N/A"
                                    
                                    with st.expander(f"📦 {material_display_name}", expanded=False):
                                        # safe_slugとbase_dir_sampleを表示
                                        safe_slug = primary_debug.get('safe_slug', 'N/A')
                                        base_dir_sample = primary_debug.get('base_dir_sample', [])
                                        chosen_branch = primary_debug.get('chosen_branch', 'unknown')
                                        final_src_type = primary_debug.get('final_src_type', 'unknown')
                                        final_path_exists = primary_debug.get('final_path_exists', False)
                                        
                                        st.write(f"**safe_slug:** {safe_slug}")
                                        st.write(f"**base_dir_sample:** {', '.join(base_dir_sample[:10])}..." if len(base_dir_sample) > 10 else f"**base_dir_sample:** {', '.join(base_dir_sample)}")
                                        st.write(f"**chosen_branch:** {chosen_branch}")
                                        st.write(f"**final_src_type:** {final_src_type}")
                                        st.write(f"**final_path_exists:** {final_path_exists}")
                                        
                                        if primary_src:
                                            if isinstance(primary_src, str):
                                                st.write(f"**final_url:** {primary_src[:80]}..." if len(primary_src) > 80 else f"**final_url:** {primary_src}")
                                            elif isinstance(primary_src, Path):
                                                st.write(f"**final_path:** {primary_src.resolve()}")
                                        else:
                                            st.warning("⚠️ primary.jpg not found")
                                        
                                        # candidate_pathsとfailed_pathsを表示
                                        candidate_paths = primary_debug.get('candidate_paths', [])
                                        failed_paths = primary_debug.get('failed_paths', [])
                                        if candidate_paths:
                                            st.write(f"**candidate_paths:** {len(candidate_paths)}件")
                                        if failed_paths:
                                            st.write(f"**failed_paths:** {len(failed_paths)}件")
                                        
                                        # 詳細情報はexpanderへ
                                        with st.expander("🔍 詳細デバッグ情報", expanded=False):
                                            st.json(primary_debug)
                                except Exception as e:
                                    st.write(f"❌ {getattr(m, 'name_official', None) or 'N/A'}: {e}")
                                    with st.expander("詳細", expanded=False):
                                        st.code(traceback.format_exc())
                        else:
                            st.write("- **materials:** 0件（DBが空）")
                    except Exception as e:
                        st.warning("materials取得失敗（DB debugだけ表示）")
                except Exception as e:
                    # sidebarで例外が起きたら警告を出して続行（本体描画を止めない）
                    st.sidebar.warning("Sidebar: 画像探索情報の取得に失敗")
                    with st.sidebar.expander("詳細", expanded=False):
                        st.sidebar.exception(e)


def _handle_material_registration():
    """
    材料登録ページのハンドラー（後方互換性のため残す）
    
    編集対象IDは st.session_state.get("edit_material_id") から取得し、
    show_detailed_material_form(material_id=その値) を呼ぶ。Noneなら新規登録。
    
    注意: この関数は後方互換性のため残していますが、
    新しいコードでは pages.registration_page.render() を使用してください。
    """
    # 関数内importで循環を避ける（import は関数内に維持）
    import streamlit as st
    from material_form_detailed import show_detailed_material_form
    
    # 編集対象IDを取得（Noneなら新規登録）
    edit_material_id = st.session_state.get("edit_material_id")
    
    # 材料フォームを表示
    show_detailed_material_form(material_id=edit_material_id)


def _handle_approval_queue(is_admin: bool = False):
    """
    承認待ち一覧ページのハンドラー（後方互換性のため残す）
    
    注意: この関数は後方互換性のため残していますが、
    新しいコードでは pages.approval_page.render() を使用してください。
    """
    from features.approval import show_approval_queue
    return show_approval_queue()


def main():
    # ===== DBアクセス禁止ゾーン（初期表示時） =====
    # 運用ルール: 初期表示ではDBを叩かない（Neon節約 / Scale-to-zero前提）
    # - DBアクセスは「ユーザー操作（ボタン/確定）」または「管理者限定」に寄せる
    # - ここで get_*_cached() / services.* を呼ぶな（将来の事故防止）
    # - 件数表示や統計情報はボタンクリック時のみ取得する設計
    # - スキーマチェックも管理者モード時のみ自動実行、それ以外はボタンで実行
    # - 例外: DEBUG/診断モードのみ（必要な場合）
    # ============================================
    
    # 実行順序の安全策: is_debug_flag が存在することを確認
    if "is_debug_flag" not in globals() or not callable(globals().get("is_debug_flag")):
        # 万が一 is_debug_flag が存在しない場合は警告を出して続行
        st.warning("⚠️ is_debug_flag is not available. Using fallback.")
        # fallback を定義
        globals()["is_debug_flag"] = is_debug
    
    # セッション状態のデフォルト値を設定（最初に実行）
    try:
        from core.state import ensure_state_defaults
        ensure_state_defaults()
    except Exception as e:
        # 初期化失敗時も続行（後でエラーが表示される）
        if show_debug_ui():
            st.warning(f"ensure_state_defaults() failed: {e}")
    
    # パフォーマンス計測（DEBUG=1のみ）
    import time
    t0_main = time.perf_counter() if is_debug_flag() else None
    
    # 起動順序を固定：Debug表示 → init_db() → その後に通常処理
    
    # 実行中バージョンは一言だけ（長い JSON / 起動マーカーは出さない）
    if show_debug_ui():
        from features.approval_actions import APPROVAL_ACTIONS_VERSION
        st.caption(
            f"RUNNING_SHA: {get_running_sha()} | "
            f"DEPLOY: {DEPLOY_VERSION} | "
            f"APPROVAL: {APPROVAL_ACTIONS_VERSION}"
        )
    print("[BOOT] body reached")  # runtime logsで見える
    
    # 1. Debugを先に描画（UIが出る前に死ぬ問題を回避）
    # 例外が起きても最後まで描く（st.stop()は呼ばない）
    # 同一run内で1回だけ描画する（二重表示を防ぐ）
    if "debug_sidebar_rendered" not in st.session_state:
        try:
            render_debug_sidebar_early()
            # ロゴファイルのデバッグ情報を表示（管理者デバッグ時のみ）
            try:
                show_logo_debug_info()
            except Exception as e:
                if show_debug_ui():
                    st.sidebar.warning(f"ロゴデバッグ情報の表示に失敗: {e}")
            st.session_state["debug_sidebar_rendered"] = True
        except Exception as e:
            _panic_screen("render_debug_sidebar_early in main()", e)
            # st.stop()は呼ばない（本文を表示するため）
    
    # 2. init_db()を呼ぶ（常に）
    # 例外が起きても本文を表示する（st.stop()は呼ばない）
    try:
        init_db()
        print("[BOOT] init_db() done")
    except Exception as e:
        # 例外を可視化（本文に出す）
        st.error("DB初期化エラー")
        st.exception(e)
        st.code("".join(traceback.format_exception(type(e), e, e.__traceback__)), language="python")
        # st.stop()は呼ばない（本文を表示するため）
    
    # 3. スキーマドリフト検知（Neon節約のため、ボタンクリック時のみDBアクセス）
    # 初期表示ではDBを叩かない（毎rerunでのDBアクセスを削減）
    if "check_schema_drift" not in st.session_state:
        st.session_state.check_schema_drift = False
    
    # 管理者モード時は自動チェック、それ以外はボタンでチェック
    # スキーマ整合性チェック（管理者のみ表示）
    from utils.settings import is_admin_mode
    is_admin_for_schema = is_admin_mode()
    if is_admin_for_schema:
        # 管理者モード時は自動チェック（運用上の問題を早期発見）
        st.session_state.check_schema_drift = True
    # 非管理者にはボタンを表示しない（重要でなければ隠す）
    
    if st.session_state.check_schema_drift:
        try:
            from database import get_schema_drift_status
            from utils.settings import get_database_url
            # TTL=60秒のキャッシュを使用（database.pyで定義済み）
            schema_status = get_schema_drift_status(get_database_url())
            
            # スキーマチェックが成功した場合のみ、スキーマ不整合の警告を表示
            if schema_status.get("ok", False):
                # スキーマ不整合がある場合は警告を表示
                images_ok = schema_status.get("images_ok", False)
                # 後方互換: images_kind_exists も確認
                if not images_ok and not schema_status.get("images_kind_exists", False):
                    missing_columns = schema_status.get("images_missing_columns", [])
                    if missing_columns:
                        missing_cols_str = ", ".join(missing_columns)
                        st.warning(f"""
                        ⚠️ **DB Schema Mismatch Detected**
                        
                        The `images` table is missing required columns: **{missing_cols_str}**
                        
                        This may cause errors when loading materials.
                        
                        **To fix:**
                        1. Set `MIGRATE_ON_START=1` in Streamlit Secrets
                        2. Reboot the application
                        3. The migration will run automatically and add the missing columns
                        
                        **Current status:** Running in safe mode (images are not loaded to prevent crashes)
                        """)
                    else:
                        st.warning("""
                        ⚠️ **DB Schema Mismatch Detected**
                        
                        The `images` table is missing required columns. This may cause errors when loading materials.
                        
                        **To fix:**
                        1. Set `MIGRATE_ON_START=1` in Streamlit Secrets
                        2. Reboot the application
                        3. The migration will run automatically and add the missing columns
                        
                        **Current status:** Running in safe mode (images are not loaded to prevent crashes)
                        """)
                    
                    # 管理者向けに詳細情報を表示
                    from utils.settings import is_admin_mode
                    if is_admin_mode():
                        with st.expander("🔍 Schema Status Details", expanded=False):
                            st.json(schema_status)
                
                # エラーがある場合は表示（ok==True の場合でも）
                if schema_status.get("errors"):
                    for error in schema_status["errors"]:
                        st.warning(f"Schema check warning: {error}")
            else:
                # スキーマチェックが失敗した場合（ok==False）
                st.warning("""
                ⚠️ **DB Schema Check Failed**
                
                Unable to verify database schema. Running in safe mode to prevent crashes.
                
                **Details:**
                """)
                if schema_status.get("errors"):
                    for error in schema_status["errors"]:
                        st.error(f"Schema check error: {error}")
                
                # 管理者向けに詳細情報を表示
                from utils.settings import is_admin_mode
                if is_admin_mode():
                    with st.expander("🔍 Schema Status Details", expanded=False):
                        st.json(schema_status)
        except Exception as e:
            # スキーマチェック失敗時は警告を表示して続行（PANICしない）
            st.warning(f"⚠️ DB Schema check failed: {e}. Running in safe mode.")
            if os.getenv("DEBUG", "0") == "1":
                print(f"[SCHEMA] schema check exception: {e}")
                import traceback
                traceback.print_exc()
    
    # 4. その後に通常処理（Debugは既にrender_debug_sidebar_early()で表示済み）
    
    # アセット確保（生成物の自動生成）
    try:
        from utils.ensure_assets import ensure_all_assets
        asset_stats = ensure_all_assets()
    except Exception as e:
        # 例外を可視化（管理者デバッグ時のみ本文に出す）
        if show_debug_ui():
            st.warning(f"アセット確保エラー: {e}")
            st.code("".join(traceback.format_exception(type(e), e, e.__traceback__)), language="python")
        asset_stats = {}
    
    # サンプルデータの自動投入（INIT_SAMPLE_DATA=1 かつ DBが空の時だけ実行）
    # init_db()の後に実行（スキーマ補完完了後）
    # 例外が出てもアプリ起動を殺さない
    try:
        maybe_init_sample_data()
    except Exception as e:
        # 例外はログのみ（起動時クラッシュを防ぐため、画面には出さない）
        import traceback
        print(f"[WARN] maybe_init_sample_data() failed: {e}")
        if show_debug_ui():
            st.warning(f"maybe_init_sample_data() failed: {e}")
            st.code("".join(traceback.format_exception(type(e), e, e.__traceback__)), language="python")
        # アプリ起動は続行
    
    # 画像の自動修復（INIT_SAMPLE_DATA=1 の時だけ）
    # init_db()の後に実行（スキーマ補完完了後）
    if os.getenv("INIT_SAMPLE_DATA") == "1":
        try:
            from utils.ensure_images import ensure_images
            ensure_images(Path.cwd())
        except Exception as e:
            # 例外を可視化（管理者デバッグ時のみ本文に出す）
            if show_debug_ui():
                st.warning(f"画像自動修復エラー: {e}")
                st.code("".join(traceback.format_exception(type(e), e, e.__traceback__)), language="python")
            # アプリ起動は続行
    
    # デバッグスイッチ（管理者認証後のみ。学生には出さない）
    if show_debug_ui():
        debug_no_css = st.sidebar.checkbox("Debug: CSSを無効化", value=False, help="白飛びが発生している場合、このチェックをONにするとCSSを無効化して表示を確認できます")
        debug_images = st.sidebar.checkbox("🔍 画像診断モード", value=False, help="画像の健康状態を診断します（原因切り分け用）")
        debug_assets = st.sidebar.checkbox("🔍 Asset診断モード", value=False, help="生成物（元素画像など）の存在状況を診断します")
        debug_materials_duplicate = st.sidebar.checkbox("🔍 材料重複診断", value=False, help="材料の重複状況を診断します")
    else:
        debug_no_css = False
        debug_images = False
        debug_assets = False
        debug_materials_duplicate = False
    
    # CSS適用（デバッグモードでない場合のみ）
    if not debug_no_css:
        st.markdown(get_custom_css(), unsafe_allow_html=True)
    else:
        # デバッグモード: 最小限のCSSのみ（可読性確保）
        st.markdown("""
        <style>
            /* デバッグモード: 最小限のスタイル */
            body, html {
                color: #111 !important;
                background: #f5f5f5 !important;
            }
            .stApp {
                background: #f5f5f5 !important;
            }
            .stApp::before {
                display: none !important;
            }
            [class*="st-"] {
                color: #111 !important;
            }
        </style>
        """, unsafe_allow_html=True)
        st.warning("デバッグモード: CSS（<style>注入）が無効化されています。ロゴ/画像描画は正常に実行されます。")
    
    # ヘッダー - WOTA風シンプル
    # 本文UIの開始（Debug sidebarはrun_app_entrypointで先に描画済み）
    # タイトルは各ページでロゴとして表示（show_home()など）
    
    # 素材件数の表示（デフォルトON、Neon節約のためTTLキャッシュを使用）
    # 初期表示ではDBを叩かない（毎rerunでのDBアクセスを削減）
    if "show_material_count" not in st.session_state:
        st.session_state.show_material_count = True  # デフォルトON
    
    if st.session_state.show_material_count:
        try:
            from utils.settings import get_database_url
            db_url = get_database_url()
            # TTL=300秒（5分）のキャッシュを使用（Neon節約のため）
            material_count = get_material_count_cached(db_url, include_unpublished=False, include_deleted=False)
            st.write(f"素材件数: {material_count} 件")
        except Exception as e:
            st.error("❌ 素材件数の取得に失敗しました")
            import traceback
            st.code("".join(traceback.format_exception(type(e), e, e.__traceback__)), language="python")
    
    # ページ状態の初期化
    if 'page' not in st.session_state:
        st.session_state.page = "ホーム"
    if 'selected_material_id' not in st.session_state:
        st.session_state.selected_material_id = None
    if 'last_material_id_param' not in st.session_state:
        st.session_state.last_material_id_param = None
    
    # クエリパラメータからページ遷移を処理（カードクリック対応）
    allowed_pages = {"ホーム", "材料登録", "材料一覧", "検索", "素材カード"}
    page_param = st.query_params.get("page")
    if page_param and page_param in allowed_pages:
        st.session_state.page = page_param
    
    # 材料IDのクエリパラメータを処理（カード全体クリック対応）
    # 一回だけ処理するガード（query param routing 安定化のため）
    material_id_param = st.query_params.get("material_id")
    if not material_id_param:
        # クエリパラメータに material_id がない場合は last_material_id_param をリセット
        st.session_state.last_material_id_param = None
    if material_id_param:
        # 既に処理済みの場合はスキップ（無限ループ防止）
        last_processed = st.session_state.get("last_material_id_param")
        if last_processed != material_id_param:
            try:
                material_id = int(material_id_param)
                st.session_state.selected_material_id = material_id
                st.session_state.page = "材料一覧"  # 一覧ページの詳細表示モード
                st.session_state.last_material_id_param = material_id_param
            except (ValueError, TypeError):
                # 数値でない場合は無視（例外で落とさない）
                pass
    
    # 詳細ページへの遷移がリクエストされた場合
    if st.session_state.selected_material_id and st.session_state.page != "detail":
        # 詳細ページに遷移する場合は、ページを"材料一覧"に設定（詳細表示モード）
        st.session_state.page = "材料一覧"
    
    # 編集権限者判定（ADMIN_MODE=1 のときのみ、DEBUGとは分離）
    from utils.settings import is_admin_mode
    is_admin = is_admin_mode()
    
    # サイドバー - PCでは表示、スマホではCSSで非表示
    with st.sidebar:
        # ロゴマークをサイドバー最上部に表示（全ページ共通）
        from utils.logo import render_logo_mark
        is_debug = show_debug_ui()
        
        # ロゴマークを中央寄せで大きく表示
        st.markdown("""
        <style>
            /* サイドバーのロゴマークを中央寄せ */
            .sidebar-logo {
                display: flex !important;
                justify-content: center !important;
                align-items: center !important;
                margin: 8px 0 12px !important;
            }
        </style>
        <div class="sidebar-logo">
        """, unsafe_allow_html=True)
        render_logo_mark(height_px=60, debug=is_debug, use_component=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("---")
        
        # ページ選択（詳細ページ表示中は選択を変更しない）
        if st.session_state.selected_material_id:
            # 詳細ページ表示中は、ページ選択を一時的に無効化
            st.session_state.page = "材料一覧"
            page = "材料一覧"
        else:
            # 基本メニュー項目（通常ユーザー向け）
            menu_items = ["ホーム", "材料一覧", "材料登録", "検索", "素材カード"]
            menu_icons = ["house", "grid", "pencil", "search", "file-earmark"]
            
            # 管理者の場合は追加項目を表示
            if is_admin:
                menu_items.extend(["ダッシュボード", "元素周期表"])
                menu_icons.extend(["bar-chart", "table"])
                menu_items.append("承認待ち一覧")
                menu_icons.append("clipboard-check")
                menu_items.append("一括登録")
                menu_icons.append("upload")
            
            # 現在のページのインデックスを取得
            current_index = 0
            if st.session_state.page in menu_items:
                current_index = menu_items.index(st.session_state.page)
            
            # option_menuでメニューを表示
            page = option_menu(
                None,
                menu_items,
                icons=menu_icons,
                default_index=current_index,
                styles={
                    "container": {"padding": "0.25rem", "background-color": "transparent"},
                    "nav-link": {
                        "font-size": "14px",
                        "padding": "8px 10px",
                        "border-radius": "10px",
                        "margin-bottom": "4px",
                    },
                    "nav-link-selected": {
                        "background-color": "#111",
                        "color": "white",
                    },
                }
            )
            st.session_state.page = page
            # ホーム遷移時は selected_material_id と last_material_id_param をリセット
            if page == "ホーム":
                st.session_state.selected_material_id = None
                st.session_state.last_material_id_param = None
        
        # hover効果のCSSを追加 + チェックボックス/ラジオボタンを非表示 + スマホでサイドバー非表示
        st.markdown("""
            <style>
            /* streamlit-option-menuのhover効果 */
            div[data-testid="stOptionMenu"] .nav-link:hover {
                background-color: #f0f0f0 !important;
                border-radius: 10px;
            }
            div[data-testid="stOptionMenu"] .nav-link-selected {
                background-color: #111 !important;
                color: white !important;
            }
            /* サイドバーの旧ナビ（radio/checkbox）を非表示（option_menuのみでページ選択） */
            /* stRadio と stCheckbox のみを対象（stToggle は除外） */
            section[data-testid="stSidebar"] [data-testid="stRadio"] input[type="radio"],
            section[data-testid="stSidebar"] [data-testid="stCheckbox"] input[type="checkbox"],
            .stSidebar [data-testid="stRadio"] input[type="radio"],
            .stSidebar [data-testid="stCheckbox"] input[type="checkbox"] {
                display: none !important;
                visibility: hidden !important;
                opacity: 0 !important;
                position: absolute !important;
                width: 0 !important;
                height: 0 !important;
            }
            /* 旧ナビのラジオボタン/チェックボックスのラベルも非表示 */
            section[data-testid="stSidebar"] [data-testid="stRadio"] label,
            section[data-testid="stSidebar"] [data-testid="stCheckbox"] label,
            .stSidebar [data-testid="stRadio"] label,
            .stSidebar [data-testid="stCheckbox"] label {
                display: none !important;
            }
            /* スマホでサイドバーを非表示（画面幅768px以下） */
            @media (max-width: 768px) {
                section[data-testid="stSidebar"] {
                    display: none !important;
                }
            }
            </style>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # 管理者認証（ADMIN_PASSWORD: Secrets / 環境変数）
        # デバッグUIもこの認証後のみ表示される（show_debug_ui）
        try:
            from utils.settings import get_secret_str
            admin_password = get_secret_str("ADMIN_PASSWORD", "").strip()
        except Exception:
            admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
        if admin_password:
            # セッション状態で認証状態を管理
            if "admin_authenticated" not in st.session_state:
                st.session_state["admin_authenticated"] = False
            
            if not st.session_state["admin_authenticated"]:
                st.markdown("---")
                st.markdown("### 🔐 管理者認証")
                password_input = st.text_input(
                    "管理者パスワード",
                    type="password",
                    key="admin_password_input"
                )
                if st.button("認証", key="admin_auth_button"):
                    if password_input == admin_password:
                        st.session_state["admin_authenticated"] = True
                        st.success("✅ 認証成功")
                        st.rerun()
                    else:
                        st.error("❌ パスワードが正しくありません")
                # 認証されていない場合は管理者機能を無効化
                is_admin = False
            else:
                if st.button("🔓 ログアウト", key="admin_logout"):
                    st.session_state["admin_authenticated"] = False
                    st.rerun()
                if show_debug_ui():
                    st.caption("🛠 デバッグ表示: ON（管理者のみ）")
        
        # 管理者表示チェック（管理者のみ）
        if is_admin:
            include_unpublished = st.checkbox(
                "管理者表示（非公開も表示）",
                value=st.session_state.get("include_unpublished", False),
                key="admin_include_unpublished"
            )
            st.session_state["include_unpublished"] = include_unpublished
            
            # DB起床ボタン（管理者のみ）
            st.markdown("---")
            st.markdown("### 🔌 DB管理")
            if st.button("🔌 DBを起こす", key="wake_db_btn"):
                from services.db_health import ping_db
                from utils.db import DBUnavailableError
                try:
                    ping_db()
                    st.success("✅ DB接続成功")
                    # DB起床直後は重い処理を自動実行しない（直近3秒はガード）
                    st.session_state.db_warmed_recently = True
                    st.session_state.db_warmed_at = time.time()
                except DBUnavailableError:
                    handle_db_unavailable("DB起床", retry_fn=ping_db, operation="DB起床")
        else:
            include_unpublished = False
        
        # 統計情報（画面左下に小さく表示）- 遅延取得（ボタン押下時のみ）
        # 初期表示ではDBアクセスしない（起床頻度を下げる）
        # 編集権限者（ADMIN_MODE）のみに表示
        stats_key = "show_statistics"
        if stats_key not in st.session_state:
            st.session_state[stats_key] = False
        
        # 変数を初期化（エラー回避）
        materials = []
        categories = 0
        total_properties = 0
        avg_properties = 0.0
        material_count = 0
        
        include_deleted = st.session_state.get("include_deleted", False) if is_admin else False
        
        # 統計情報表示ボタン（サイドバーに配置、管理者のみ）
        if is_admin:
            if not st.session_state[stats_key]:
                if st.sidebar.button("📊 統計情報を表示", key="show_stats_btn"):
                    st.session_state[stats_key] = True
                    st.rerun()
            else:
                # 統計情報を取得（try/exceptで囲み、失敗時はデフォルト値のまま進む）
                try:
                    from utils.settings import get_database_url
                    from services.materials_service import get_statistics
                    from services.db_retry import db_retry
                    from utils.db import DBUnavailableError
                    
                    db_url = get_database_url()
                    
                    # DB起床直後の自動実行ガード（直近3秒は重い処理を自動実行しない）
                    db_warmed_recently = st.session_state.get("db_warmed_recently", False)
                    db_warmed_at = st.session_state.get("db_warmed_at", 0)
                    if db_warmed_recently and (time.time() - db_warmed_at) < 3.0:
                        # 起床直後は自動実行をスキップ（ボタン押下の明示操作は許可）
                        # None にして表示ブロックをスキップ（0をセットすると「材料ゼロ」に見えるリスクを避ける）
                        material_count = None
                        categories = None
                        total_properties = None
                        avg_properties = None
                    else:
                        try:
                            bump_db_call_counter("statistics")
                            stats = db_retry(
                                lambda: get_statistics(
                                    include_unpublished=include_unpublished,
                                    include_deleted=include_deleted
                                ),
                                operation_name="統計情報取得"
                            )
                            material_count = stats["material_count"]
                            categories = stats["categories"]
                            total_properties = stats["total_properties"]
                            avg_properties = stats["avg_properties"]
                        except DBUnavailableError:
                            handle_db_unavailable(
                                "統計情報取得",
                                retry_fn=lambda: get_statistics(
                                    include_unpublished=include_unpublished,
                                    include_deleted=include_deleted
                                )
                            )
                except Exception as e:
                    # 統計情報取得失敗時はデフォルト値のまま進む（PANICさせない）
                    material_count = 0
                    if show_debug_ui():
                        st.caption(f"統計情報取得エラー（表示は続行）: {e}")
                
                # 材料数はmaterial_countを使用（materialsが空でも表示できる）
                # DB起床直後ガード中（material_count=None）の場合は表示をスキップ
                if material_count is not None:
                    material_display_count = material_count if material_count > 0 else (len(materials) if materials else 0)
                    
                    # 左下に小さく配置（統計情報が取得済みの場合のみ表示）
                    if st.session_state[stats_key]:
                        st.markdown("""
                        <div class="stats-fixed">
                            <div>材料数: <strong>{}</strong></div>
                            <div>カテゴリ: <strong>{}</strong></div>
                            <div>物性データ: <strong>{}</strong></div>
                        </div>
                        """.format(material_display_count, categories, total_properties), unsafe_allow_html=True)
        
        st.markdown("""
        <div style="text-align: center; padding: 20px 0; color: #666;">
            <small>Material Map v1.0</small>
        </div>
        """, unsafe_allow_html=True)
    
    # page変数を設定（サイドバーで設定されていない場合のフォールバック）
    if 'page' not in locals():
        page = st.session_state.page
    
    # Asset診断モード（デバッグ時のみ表示）
    if debug_assets:
        show_asset_diagnostics(asset_stats)
        return  # 診断モード時は他のページを表示しない
    
    # 画像診断モード（デバッグ時のみ表示、DEBUG=0の時はスキップ）
    debug_enabled = show_debug_ui()
    if debug_images and debug_enabled:
        from utils.image_diagnostics import show_image_diagnostics
        from utils.db import DBUnavailableError
        from utils.settings import get_database_url
        try:
            db_url = get_database_url()
            materials = get_all_materials(db_url)
            show_image_diagnostics(materials, Path.cwd())
            return  # 診断モード時は他のページを表示しない
        except DBUnavailableError:
            db_url = get_database_url()
            handle_db_unavailable(
                "画像診断",
                retry_fn=lambda: get_all_materials(db_url)
            )
    
    # 管理者表示フラグを取得（サイドバーで設定されていない場合のフォールバック）
    if 'include_unpublished' not in locals():
        include_unpublished = st.session_state.get("include_unpublished", False) if is_admin else False
    if 'include_deleted' not in locals():
        include_deleted = st.session_state.get("include_deleted", False) if is_admin else False
    
    # page変数を設定（サイドバーで設定されていない場合のフォールバック）
    if 'page' not in locals():
        page = st.session_state.page
    
    # ページルーティング
    # まず、routesから取得を試みる（pages配下のページ）
    try:
        from core.router import get_routes
        routes = get_routes()
        
        # routesに存在する場合は、そのhandlerを実行
        if page in routes:
            try:
                routes[page]()
                return
            except Exception as e:
                # ページレンダリング時の例外を捕捉
                st.error(f"❌ ページ '{page}' のレンダリング中にエラーが発生しました")
                st.exception(e)
                import traceback
                with st.expander("🔍 エラー詳細", expanded=False):
                    st.code("".join(traceback.format_exception(type(e), e, e.__traceback__)), language="python")
                return
    except Exception as e:
        # routes取得失敗時は従来のルーティングにフォールバック
        if show_debug_ui():
            st.warning(f"get_routes() failed, using fallback routing: {e}")
    
    # ホーム以外のページには「← ホーム」リンク風ボタンを表示
    if page != "ホーム":
        st.markdown("""
        <style>
            /* 「← ホーム」ボタンをリンク風にする */
            div[data-testid="stButton"]:has(button[key="go_home"]) button {
                background-color: transparent !important;
                border: none !important;
                color: #666 !important;
                font-size: 13px !important;
                padding: 4px 8px !important;
                text-align: left !important;
                box-shadow: none !important;
            }
            div[data-testid="stButton"]:has(button[key="go_home"]) button:hover {
                color: #1a1a1a !important;
                text-decoration: underline !important;
            }
        </style>
        """, unsafe_allow_html=True)
        if st.button("← ホーム", key="go_home", use_container_width=False):
            st.session_state.page = "ホーム"
            st.session_state.selected_material_id = None
            st.session_state.last_material_id_param = None
            st.rerun()
        st.markdown("---")
    
    # 従来のルーティング（後方互換性のため残す）
    if page == "ホーム":
        show_home()
    elif page == "材料一覧":
        show_materials_list(include_unpublished=include_unpublished, include_deleted=include_deleted)
    elif page == "材料登録":
        _handle_material_registration()
    elif page == "ダッシュボード":
        show_dashboard()
    elif page == "検索":
        show_search()
    elif page == "素材カード":
        show_material_cards()
    elif page == "元素周期表":
        show_periodic_table()
    elif page == "投稿ステータス確認":
        show_submission_status()
    elif page == "承認待ち一覧":
        _handle_approval_queue(is_admin)
    elif page == "一括登録":
        _handle_bulk_import(is_admin)
    else:
        st.error(f"❌ ページ '{page}' が見つかりません")

def resolve_home_main_visual(project_root: Optional[Path] = None) -> tuple[Optional[Path], Optional[bytes]]:
    """
    ホームのメインビジュアル画像のパスと画像データを解決
    static/images/メイン.jpg を優先し、WebPが読めない環境ではjpg/pngにフォールバック
    PILで開けるかを検証して、開けない候補はスキップ
    
    Args:
        project_root: プロジェクトルート（Noneの場合は自動解決）
    
    Returns:
        (見つかった画像のPath, 画像データのbytes) のタプル、見つからなければ (None, None)
    """
    if project_root is None:
        # Path解決は Path(__file__).resolve().parent を project_root として開始
        project_root = Path(__file__).resolve().parent
        
        # 念のため static/ が存在する上位ディレクトリまで最大3階層だけ辿って見つける（Cloudのcwdズレ対策）
        current = project_root
        for _ in range(3):
            static_dir = current / "static"
            if static_dir.exists() and static_dir.is_dir():
                project_root = current
                break
            if current == current.parent:
                break
            current = current.parent
    
    # WebPサポートチェック
    webp_supported = False
    try:
        from PIL import features
        webp_supported = features.check("webp")
    except Exception:
        pass
    
    # 候補の優先順（まず static/images を正とする）
    candidate_paths = [
        project_root / "static" / "images" / "メイン.jpg",
        project_root / "static" / "images" / "メイン.png",
    ]
    
    if webp_supported:
        # WebP対応時のみWebP候補を追加
        candidate_paths.append(project_root / "static" / "images" / "メイン.webp")
    
    candidate_paths.extend([
        project_root / "写真" / "メイン.jpg",
        project_root / "写真" / "メイン.png",
    ])
    
    if webp_supported:
        candidate_paths.append(project_root / "写真" / "メイン.webp")
    
    # 必要なら static/メイン.* も最後尾
    candidate_paths.extend([
        project_root / "static" / "メイン.jpg",
        project_root / "static" / "メイン.png",
    ])
    
    if webp_supported:
        candidate_paths.append(project_root / "static" / "メイン.webp")
    
    # 各候補を「存在する & 実際に読み込める」順に選ぶ
    for path in candidate_paths:
        if not path.exists() or not path.is_file():
            continue
        
        # PILで開けるかを検証
        try:
            from PIL import Image
            with Image.open(path) as img:
                # 画像を開いて検証（実際に読み込めるか確認）
                img.verify()
            
            # 検証後、再度開いてbytesに変換
            # verify()で検証した後は画像が閉じられるので、再度開く必要がある
            img = Image.open(path)
            try:
                # RGBに変換（RGBAやPモードなどに対応）
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # BytesIOに保存してbytesを取得
                from io import BytesIO
                buffer = BytesIO()
                img.save(buffer, format='JPEG', quality=95)
                image_bytes = buffer.getvalue()
                
                return (path, image_bytes)
            finally:
                img.close()
        except Exception as e:
            # 開けない候補はスキップして次へ（エラーはデバッグ情報に含める）
            continue
    
    return (None, None)


def get_main_visual_debug_info() -> Dict[str, Any]:
    """
    メインビジュアル画像のデバッグ情報を辞書形式で返す（DEBUG表示用）
    
    Returns:
        デバッグ情報の辞書
    """
    # Path解決は Path(__file__).resolve().parent を project_root として開始
    project_root = Path(__file__).resolve().parent
    
    # 念のため static/ が存在する上位ディレクトリまで最大3階層だけ辿って見つける
    current = project_root
    for _ in range(3):
        static_dir = current / "static"
        if static_dir.exists() and static_dir.is_dir():
            project_root = current
            break
        if current == current.parent:
            break
        current = current.parent
    
    # WebPサポートチェック
    webp_supported = False
    try:
        from PIL import features
        webp_supported = features.check("webp")
    except Exception:
        pass
    
    # 候補の優先順（まず static/images を正とする）
    candidate_paths = [
        project_root / "static" / "images" / "メイン.jpg",
        project_root / "static" / "images" / "メイン.png",
    ]
    
    if webp_supported:
        candidate_paths.append(project_root / "static" / "images" / "メイン.webp")
    
    candidate_paths.extend([
        project_root / "写真" / "メイン.jpg",
        project_root / "写真" / "メイン.png",
    ])
    
    if webp_supported:
        candidate_paths.append(project_root / "写真" / "メイン.webp")
    
    candidate_paths.extend([
        project_root / "static" / "メイン.jpg",
        project_root / "static" / "メイン.png",
    ])
    
    if webp_supported:
        candidate_paths.append(project_root / "static" / "メイン.webp")
    
    # 各候補の存在確認とPILで開けるか検証
    candidates = []
    for path in candidate_paths:
        exists = path.exists() and path.is_file()
        open_ok = False
        error = None
        
        if exists:
            try:
                from PIL import Image
                with Image.open(path) as img:
                    img.verify()
                open_ok = True
            except Exception as e:
                error = str(e)
        
        candidates.append({
            "path": str(path),
            "exists": exists,
            "size": path.stat().st_size if exists else 0,
            "mtime": path.stat().st_mtime if exists else 0,
            "open_ok": open_ok,
            "error": error,
        })
    
    # 最終的に選ばれたパスと画像データ
    selected_path, selected_bytes = resolve_home_main_visual(project_root)
    
    return {
        "project_root": str(project_root),
        "pil_webp_supported": webp_supported,
        "candidates": candidates,
        "selected_path": str(selected_path) if selected_path else None,
        "selected_exists": selected_path.exists() if selected_path else False,
        "selected_size": selected_path.stat().st_size if selected_path and selected_path.exists() else 0,
        "selected_mtime": selected_path.stat().st_mtime if selected_path and selected_path.exists() else 0,
        "selected_bytes_size": len(selected_bytes) if selected_bytes else 0,
    }


def show_home():
    """ホームページ"""
    # 実行順序の安全策: is_debug_flag が存在することを確認
    if not callable(is_debug_flag):
        # 万が一 is_debug_flag が存在しない場合は fallback
        debug_enabled = show_debug_ui()
    else:
        debug_enabled = show_debug_ui()
    
    # パフォーマンス計測（DEBUG=1のみ）
    import time
    t0 = time.perf_counter() if debug_enabled else None
    
    # DEBUGタグ（反映確認用）
    if debug_enabled:
        st.caption("BUILD_TAG: APPROVAL_IMG_EDIT_FIX_V1")
    
    # デバッグモードかどうか（ローカル変数名を debug_enabled に統一）
    # is_debug は debug_enabled のエイリアスとして定義（後方互換）
    is_debug = debug_enabled
    
    # タイプロゴをホーム画面の上部に表示
    from utils.logo import render_site_header
    render_site_header(subtitle="素材の可能性を探索するデータベース", debug=is_debug, use_component=True)
    st.markdown("---")
    
    # 修正2: components描画スモークテスト（DEBUG=1時のみ）
    if is_debug:
        import streamlit.components.v1 as components
        components.html(
            "<div style='padding:6px;border:1px solid #f00;background:#fff;'>components ok</div>",
            height=40,
            scrolling=False
        )
    
    # 修正3,4: DEBUG=1のときは診断情報をst.jsonで表示（CSS無効でも読める）
    if debug_enabled:
        st.markdown("---")
        st.markdown("### 🔍 デバッグ情報（CSS無効でも表示）")
        
        # ロゴデバッグ情報
        logo_debug = get_logo_debug_info()
        
        # メインビジュアルデバッグ情報
        main_visual_debug = get_main_visual_debug_info()
        
        st.json({
            "logo_debug": logo_debug,
            "main_visual_debug": main_visual_debug,
        })
        
        st.markdown("---")
    
    # メイン画像をメインビジュアルとして表示
    # st.image(bytes)で直接表示（Streamlit Cloudでも安定）
    main_image_path, main_image_bytes = resolve_home_main_visual()
    
    if main_image_path and main_image_bytes:
        try:
            # CSSはDEBUG=1のときだけ無効化（<style>挿入だけ止める）
            if not is_debug:
                st.markdown("""
                <style>
                    .main-visual {
                        border-radius: 12px;
                        margin-top: 12px;
                        margin-bottom: 24px;
                        overflow: hidden;
                    }
                </style>
                """, unsafe_allow_html=True)
            
            # main-visual div を開く（閉じタグは st.image の後に統合）
            main_visual_html_raw = f"""
            <div class="main-visual">
            """
            main_visual_html = textwrap.dedent(main_visual_html_raw).strip()
            st.markdown(main_visual_html, unsafe_allow_html=True)
            # st.imageにbytesを渡して直接表示（相対パス/CWD依存を避ける）
            st.image(main_image_bytes, use_container_width=True)
            # main-visual div を閉じる
            st.markdown('</div>', unsafe_allow_html=True)
        except Exception as e:
            if is_debug:
                st.warning(f"メイン画像の表示に失敗: {e}")
    elif is_debug:
        # 選べなければ通常は何も出さず、DEBUG=1時だけwarningを出す（ユーザー体験を壊さない）
        st.warning("⚠️ メイン画像が見つかりませんでした")
    
    # 管理者表示フラグを取得
    include_unpublished = st.session_state.get("include_unpublished", False)
    
    # 初期表示ではDBアクセスしない（起床頻度を下げる）
    # ユーザーが明示的に「一覧を表示」ボタンを押した時だけ取得
    show_materials_key = "show_materials_on_home"
    if show_materials_key not in st.session_state:
        st.session_state[show_materials_key] = False
    
    # 一覧表示ボタン
    st.markdown("---")
    col_btn1, col_btn2 = st.columns([1, 3])
    with col_btn1:
        if st.button("📋 材料一覧を表示", type="primary", key="show_materials_btn"):
            st.session_state[show_materials_key] = True
            st.rerun()
    
    # 一覧表示が有効な場合のみDBアクセス
    materials_dicts = []
    if st.session_state[show_materials_key]:
        from utils.settings import get_database_url
        from utils.db import DBUnavailableError
        from services.db_retry import db_retry
        
        db_url = get_database_url()
        
        # DBアクセス計測
        t1 = time.perf_counter() if t0 is not None else None
        try:
            # 軽量リトライ付きで取得
            materials_dicts = db_retry(
                lambda: fetch_materials_page_cached(
                    db_url=db_url,
                    include_unpublished=include_unpublished,
                    include_deleted=False,
                    limit=50,
                    offset=0
                ),
                operation_name="材料一覧取得"
            )
        except DBUnavailableError as e:
            handle_db_unavailable(
                "材料一覧取得",
                retry_fn=lambda: fetch_materials_page_cached(
                    db_url=db_url,
                    include_unpublished=include_unpublished,
                    include_deleted=False,
                    limit=50,
                    offset=0
                )
            )
        if t1 is not None:
            print(f"[PERF] show_home() fetch_materials_page_cached: {time.perf_counter() - t1:.3f}s")
    
    # dict から Material 風のオブジェクトを作成（後方互換のため）
    class MaterialProxy:
        def __init__(self, d):
            self.id = d.get("id")
            self.uuid = d.get("uuid")
            self.name_official = d.get("name_official")
            self.name = d.get("name")
            self.category_main = d.get("category_main")
            self.category = d.get("category")
            self.description = d.get("description")  # 説明（後方互換）
            self.is_published = d.get("is_published", 1)
            self.is_deleted = d.get("is_deleted", 0)
            self.created_at = d.get("created_at")
            self.updated_at = d.get("updated_at")
            self.properties = d.get("properties", [])  # 一覧では一括取得したpropertiesを使用
            self.images = []  # 一覧ではロードしない
            self.primary_image_url = d.get("primary_image_url")  # imagesテーブルから取得したpublic_url
    
    # 一覧表示が有効な場合のみ表示
    materials = []
    if st.session_state[show_materials_key]:
        materials = [MaterialProxy(d) for d in materials_dicts]
        
        if not materials:
            st.info("📭 材料が登録されていません。")
        else:
            # 材料カード表示（既存のコード）
            st.markdown('<h3 class="section-title">材料一覧</h3>', unsafe_allow_html=True)
            
            # 画像表示トグル（Network transfer削減のため）
            if "show_images_in_list" not in st.session_state:
                st.session_state.show_images_in_list = True
            show_images = st.toggle("🖼️ 画像を表示", value=st.session_state.show_images_in_list, key="toggle_images_home")
            st.session_state.show_images_in_list = show_images
    
    # ヒーローセクション
    st.markdown("""
    <div class="hero-section">
        <h2 style="color: #2c3e50; margin-bottom: 20px; font-size: 2.5rem; font-weight: 800;">✨ ようこそ！</h2>
        <p style="font-size: 1.2rem; color: #555; line-height: 1.8; max-width: 800px; margin: 0 auto; font-weight: 500;">
            素材を、カードのように集めて、眺めて、比べ、このデータベースは、材料について理解するための万華鏡のような道具です。<br>
            歴史や加工法などこれまで分断されてきた材料の活用法を記録することで意外な発見を共有します。
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # 機能紹介カード（クリック可能なリンクカード）
    st.markdown('<h3 class="section-title">主な機能</h3>', unsafe_allow_html=True)
    # カードクリック用のCSSを追加
    st.markdown("""
    <style>
    .nav-card {
        display: block;
        text-decoration: none;
        color: inherit;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .nav-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15) !important;
    }
    .nav-card .stat-card {
        cursor: pointer;
    }
    </style>
    """, unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    
    icon1 = get_icon_svg_inline("icon-register", 40, "#999999")
    icon2 = get_icon_svg_inline("icon-chart", 40, "#999999")
    icon3 = get_icon_svg_inline("icon-search", 40, "#999999")
    icon4 = get_icon_svg_inline("icon-card", 40, "#999999")
    
    with col1:
        st.markdown(f"""
        <a href="?page=材料登録" class="nav-card">
            <div class="stat-card">
                <div style="margin-bottom: 15px; text-align: center;">
                    <img src="data:image/svg+xml;base64,{icon1}" style="width: 40px; height: 40px; opacity: 0.6;" />
                </div>
                <h3 style="color: #1a1a1a; margin: 15px 0; font-weight: 600; font-size: 1.1rem;">材料登録</h3>
                <p style="color: #666; margin: 0; font-size: 14px;">簡単に材料情報を登録・管理</p>
            </div>
        </a>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <a href="?page=材料一覧" class="nav-card">
            <div class="stat-card">
                <div style="margin-bottom: 15px; text-align: center;">
                    <img src="data:image/svg+xml;base64,{icon2}" style="width: 40px; height: 40px; opacity: 0.6;" />
                </div>
                <h3 style="color: #1a1a1a; margin: 15px 0; font-weight: 600; font-size: 1.1rem;">材料一覧</h3>
                <p style="color: #666; margin: 0; font-size: 14px;">登録された材料を一覧表示</p>
            </div>
        </a>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <a href="?page=検索" class="nav-card">
            <div class="stat-card">
                <div style="margin-bottom: 15px; text-align: center;">
                    <img src="data:image/svg+xml;base64,{icon3}" style="width: 40px; height: 40px; opacity: 0.6;" />
                </div>
                <h3 style="color: #1a1a1a; margin: 15px 0; font-weight: 600; font-size: 1.1rem;">検索（自然言語検索）</h3>
                <p style="color: #666; margin: 0; font-size: 14px;">「高強度で軽量な材料」など、自然な言葉で検索</p>
            </div>
        </a>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <a href="?page=素材カード" class="nav-card">
            <div class="stat-card">
                <div style="margin-bottom: 15px; text-align: center;">
                    <img src="data:image/svg+xml;base64,{icon4}" style="width: 40px; height: 40px; opacity: 0.6;" />
                </div>
                <h3 style="color: #1a1a1a; margin: 15px 0; font-weight: 600; font-size: 1.1rem;">素材カード</h3>
                <p style="color: #666; margin: 0; font-size: 14px;">素材カードを自動生成</p>
            </div>
        </a>
        """, unsafe_allow_html=True)
    
    # 強制画像テスト（診断用：DEBUG=1時のみ、かつチェックボックスONのときだけ表示）
    if show_debug_ui() and materials:
        if st.checkbox("🔍 診断: 強制画像テストを表示", value=False, key="dbg_force_img_test"):
            st.markdown("---")
            st.markdown("### 🔍 強制画像テスト（診断用）")
            test_material = materials[0]
            from utils.image_display import get_material_image_ref
            from utils.logo import get_project_root
            test_src, test_debug = get_material_image_ref(test_material, "primary", get_project_root())
            
            st.write(f"**テスト対象:** {test_material.name_official or test_material.name}")
            st.write(f"**chosen_branch:** {test_debug.get('chosen_branch', 'N/A')}")
            st.write(f"**final_src_type:** {test_debug.get('final_src_type', 'N/A')}")
            
            if test_src:
                if isinstance(test_src, Path):
                    st.write(f"**Path:** {test_src.resolve()}")
                    st.write(f"**exists:** {test_src.exists()}")
                    st.write(f"**is_file:** {test_src.is_file()}")
                    if test_src.exists() and test_src.is_file():
                        st.image(test_src, width=200, caption="Path直接表示テスト")
                elif isinstance(test_src, str):
                    st.write(f"**URL:** {test_src}")
                    st.image(test_src, width=200, caption="URL直接表示テスト")
            else:
                st.warning("画像が見つかりませんでした")
            
            with st.expander("🔍 詳細デバッグ情報", expanded=True):
                st.json(test_debug)
    
    # パフォーマンス計測ログ（DEBUG=1のみ）
    if t0 is not None:
        elapsed = time.perf_counter() - t0
        print(f"[PERF] show_home() total: {elapsed:.3f}s")
    
    # 最近登録された材料
    if materials:
        st.markdown('<h3 class="section-title">最近登録された材料</h3>', unsafe_allow_html=True)
        recent_materials = sorted(materials, key=lambda x: x.created_at if x.created_at else datetime.min, reverse=True)[:6]
        
        # 2カラムレイアウト（左: サムネ、右: 情報）
        for material in recent_materials:
            with st.container():
                col_img, col_info = st.columns([1, 3])
                
                with col_img:
                    # サムネ画像を表示（高速化: imagesテーブルのpublic_urlを直接使用、base64化やローカル探索をしない）
                    # primaryのみを使用（space/productは用途タブ専用）
                    # 画像表示トグルがOFFの場合は画像URL取得をスキップ（Network transfer削減）
                    # Neon節約: primary_image_urlが無い場合はDB取得を試みない（一覧ではDBアクセスを避ける）
                    image_url = None
                    if st.session_state.get("show_images_in_list", False):
                        # primary_image_urlを確認（DBアクセス不要）
                        primary_image_url = getattr(material, "primary_image_url", None)
                        if primary_image_url and str(primary_image_url).strip() and str(primary_image_url).startswith(("http://", "https://")):
                            image_url = str(primary_image_url)
                        elif primary_image_url:
                            # primary_image_urlが有効な場合はresolve_material_image_url()を呼ぶ（内部でprimaryを優先するためDBアクセスなし）
                            image_url = resolve_material_image_url(material, db_url)
                        # primary_image_urlが無い場合はresolve_material_image_url()を呼ばない（DBアクセスを避ける）
                    
                    # サムネサイズで表示（プレースホルダー付き）
                    if image_url and image_url.strip() and image_url.startswith(('http://', 'https://')):
                        # R2の公開URLを直接使用（キャッシュバスター追加）
                        try:
                            from material_map_version import APP_VERSION
                        except ImportError:
                            APP_VERSION = get_git_sha()
                        separator = "&" if "?" in image_url else "?"
                        image_url_with_cache = f"{image_url}{separator}v={APP_VERSION}"
                        # URLエンコード（日本語ファイル名対応）
                        safe_image_url = safe_url(image_url_with_cache)
                        if safe_image_url and safe_image_url.strip():
                            st.image(safe_image_url, width=120)
                        else:
                            # 画像なしの場合はスペーサーを表示（文字は出さない）
                            st.markdown("<div style='width:120px;height:120px;'></div>", unsafe_allow_html=True)
                    else:
                        # 画像なしの場合はスペーサーを表示（文字は出さない）
                        st.markdown("<div style='width:120px;height:120px;'></div>", unsafe_allow_html=True)
                
                with col_info:
                    # 材料名
                    st.markdown(f"### {material.name_official or material.name}")
                    
                    # カテゴリバッジ
                    category_name = material.category_main or material.category or '未分類'
                    if len(category_name) > 20:
                        category_display = category_name[:17] + "..."
                        category_title = category_name
                    else:
                        category_display = category_name
                        category_title = ""
                    st.markdown(f'<span class="category-badge" title="{category_title}">{category_display}</span>', unsafe_allow_html=True)
                    
                    # 説明
                    material_desc = getattr(material, "description", "") or ""
                    if material_desc:
                        st.markdown(f"<p style='color: #666; margin-top: 8px; font-size: 0.9rem;'>{material_desc[:100]}{'...' if len(material_desc) > 100 else ''}</p>", unsafe_allow_html=True)
                    
                    # 主要物性（1〜2個）
                    if material.properties:
                        props = material.properties[:2]
                        prop_text = " / ".join([
                            f"{p.get('property_name', '')}: {p.get('value', '')} {p.get('unit', '') or ''}"
                            for p in props if isinstance(p, dict)
                        ])
                        if prop_text:
                            st.markdown(f"<small style='color: #999;'>{prop_text}</small>", unsafe_allow_html=True)
                    
                    # 登録日（安全化: created_at が str/datetime/None に対応）
                    created_at = getattr(material, "created_at", None)
                    if created_at:
                        if hasattr(created_at, "strftime"):
                            # datetime オブジェクトの場合
                            date_str = created_at.strftime('%Y/%m/%d')
                        elif isinstance(created_at, str):
                            # 文字列の場合（先頭10文字を表示）
                            date_str = created_at[:10] if len(created_at) >= 10 else created_at
                        else:
                            date_str = str(created_at)[:10] if created_at else ""
                        if date_str:
                            st.markdown(f"<small style='color: #999;'>登録日: {date_str}</small>", unsafe_allow_html=True)
                
                st.markdown("---")
    
    # 将来の機能（iconmonstr風のアイコンを使用）
    st.markdown("---")
    st.markdown('<h3 class="section-title">将来の機能（LLM統合予定）</h3>', unsafe_allow_html=True)
    
    future_features = [
        ("icon-recommend", "材料推奨", "要件に基づいて最適な材料を自動推奨"),
        ("icon-predict", "物性予測", "AIによる物性データの予測"),
        ("icon-similarity", "類似度分析", "材料間の類似性を分析")
    ]
    
    cols = st.columns(3)
    for idx, (icon_name, title, desc) in enumerate(future_features):
        icon = get_icon_svg_inline(icon_name, 48, "#999999")
        with cols[idx]:
            st.markdown(f"""
            <div class="material-card-container" style="padding: 25px; text-align: center;">
                <div style="margin-bottom: 15px; text-align: center;">
                    <img src="data:image/svg+xml;base64,{icon}" style="width: 48px; height: 48px; opacity: 0.6;" />
                </div>
                <h4 style="color: #1a1a1a; margin: 15px 0; font-weight: 600; font-size: 1rem;">{title}</h4>
                <p style="color: #666; font-size: 13px; margin: 0; line-height: 1.6;">{desc}</p>
            </div>
            """, unsafe_allow_html=True)
    
    # バグ報告フォーム（Googleフォーム埋め込み）
    st.markdown("---")
    st.markdown('<h3 class="section-title">バグ報告・フィードバック</h3>', unsafe_allow_html=True)
    st.markdown("不具合の報告やご意見・ご要望をお寄せください。")
    
    import streamlit.components.v1 as components
    components.iframe(
        src="https://docs.google.com/forms/d/e/1FAIpQLSeXFOtD4HJSc6Cu2KF6kd1TXnUKRiNXrWO9V_gFhi5UfiAxGQ/viewform?embedded=true",
        height=520,
        scrolling=True
    )


def clear_material_cache():
    """
    材料関連のキャッシュをクリア（保存/承認/編集/削除後に呼ぶ）
    
    クリア対象:
    - get_all_materials: 全材料一覧
    - fetch_materials_page_cached: ページング一覧
    - get_material_count_cached: 材料件数
    
    理由: 反映遅延による再読み込み連打（=DB起床増加）を防ぐ
    """
    try:
        # 関数単位でキャッシュをクリア（全キャッシュクリアを避ける）
        get_all_materials.clear()
        fetch_materials_page_cached.clear()
        get_material_count_cached.clear()
        get_material_image_url_cached.clear()
        logger.info("[CACHE] Material cache cleared (get_all_materials, fetch_materials_page_cached, get_material_count_cached, get_material_image_url_cached)")
    except Exception as e:
        logger.warning(f"[CACHE] Failed to clear cache: {e}")
    
    # サービス層のキャッシュもクリア（サービス層が独自にキャッシュを持っている場合）
    try:
        # サービス層はキャッシュを持たないが、念のため
        pass
    except Exception:
        pass


def show_materials_list(include_unpublished: bool = False, include_deleted: bool = False):
    """材料一覧ページ（ページング対応、軽量クエリ、エラーハンドリング強化）"""
    try:
        # パフォーマンス計測（DEBUG=1のみ）
        import time
        # is_debug 関数を呼ぶ前に、ローカル変数名を debug_enabled に変更（シャドーイング回避）
        debug_enabled = show_debug_ui()
        t0 = time.perf_counter() if debug_enabled else None
        
        debug_enabled = show_debug_ui()
        st.markdown(render_site_header(debug=debug_enabled), unsafe_allow_html=True)
        st.markdown('<h2 class="section-title">材料一覧</h2>', unsafe_allow_html=True)
        
        # 管理者用の設定エリア（本文側に表示）
        from utils.settings import is_admin_mode
        is_admin = is_admin_mode()
        is_debug = show_debug_ui()
        
        if is_admin or is_debug:
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                # セッションステートの初期化
                if "include_unpublished" not in st.session_state:
                    st.session_state.include_unpublished = include_unpublished
                if "include_deleted" not in st.session_state:
                    st.session_state.include_deleted = include_deleted
                
                # トグルでセッションステートを更新
                st.session_state.include_unpublished = st.toggle(
                    "非公開も表示",
                    value=st.session_state.include_unpublished,
                    key="include_unpublished_toggle"
                )
            with col2:
                st.session_state.include_deleted = st.toggle(
                    "削除済みも表示",
                    value=st.session_state.include_deleted,
                    key="include_deleted_toggle"
                )
            
            # セッションステートの値を優先的に使用（引数より優先）
            include_unpublished = st.session_state.include_unpublished
            include_deleted = st.session_state.include_deleted
        
        # 詳細表示モードのチェック
        if st.session_state.selected_material_id:
            material_id = st.session_state.selected_material_id
            from utils.db import DBUnavailableError
            try:
                material = get_material_by_id(material_id)
            except DBUnavailableError:
                handle_db_unavailable(
                    "材料詳細取得",
                    retry_fn=lambda: get_material_by_id(material_id)
                )
            
            if material:
                # 戻るボタン
                if st.button("← 一覧に戻る", key="back_to_list"):
                    st.session_state.selected_material_id = None
                    st.rerun()
                
                st.markdown("---")
                st.markdown(f"# {material.name_official or material.name}")
                
                # 用途画像（space/product）を表示（材料名の直下）
                from database import Image
                from utils.db import get_session
                
                # imagesテーブルから用途画像を取得
                images = []
                if hasattr(material, 'images') and material.images:
                    images = list(material.images)
                else:
                    # データベースから直接取得（kind/image_typeの両方に対応）
                    from utils.db import DBUnavailableError
                    try:
                        with get_session() as db_images:
                            # kind列またはimage_type列でspace/productを検索
                            try:
                                images = db_images.query(Image).filter(
                                    Image.material_id == material.id,
                                    or_(
                                        Image.kind.in_(['space', 'product']),
                                        Image.image_type.in_(['space', 'product'])
                                    )
                                ).all()
                            except DBUnavailableError:
                                handle_db_unavailable("画像取得（space/product）")
                            except Exception:
                                # image_type列が存在しない場合はkind列のみで検索
                                try:
                                    images = db_images.query(Image).filter(
                                        Image.material_id == material.id,
                                        Image.kind.in_(['space', 'product'])
                                    ).all()
                                except DBUnavailableError:
                                    handle_db_unavailable("画像取得（kind列のみ）")
                                except Exception:
                                    # どちらも失敗した場合は全画像を取得して後でフィルタ
                                    all_images = db_images.query(Image).filter(
                                        Image.material_id == material.id
                                    ).all()
                                    images = []
                                    for img in all_images:
                                        k = getattr(img, "kind", None) or getattr(img, "image_type", None)
                                        if k in ('space', 'product'):
                                            images.append(img)
                    except DBUnavailableError:
                        handle_db_unavailable("画像取得")
                
                # images を {kind: public_url} にする（kind名やurl列名の揺れを吸収）
                images_by_kind: dict[str, str] = {}
                
                for img in images:  # material.images でも DBクエリ結果でもOK
                    k = getattr(img, "kind", None) or getattr(img, "image_type", None) or getattr(img, "type", None)
                    u = getattr(img, "public_url", None) or getattr(img, "url", None)
                    if k and u:
                        images_by_kind[str(k)] = str(u)
                
                space_url = images_by_kind.get("space")
                product_url = images_by_kind.get("product")
                
                # 用途画像を2カラムで表示（画像がある場合のみ）
                if space_url or product_url:
                    c1, c2 = st.columns(2)
                    with c1:
                        if space_url:
                            st.image(safe_url(space_url), use_container_width=True)
                    with c2:
                        if product_url:
                            st.image(safe_url(product_url), use_container_width=True)
                st.markdown("---")
                
                # 管理者モードの場合は編集・削除ボタンを表示
                from utils.settings import is_admin_mode
                is_admin = is_admin_mode()
                if is_admin:
                    col1, col2, col3 = st.columns([1, 1, 8])
                    with col1:
                        if st.button("✏️ 編集", key=f"edit_{material.id}"):
                            st.session_state.edit_material_id = material.id
                            st.session_state.page = "材料登録"
                            st.rerun()
                    with col2:
                        if st.button("🗑️ 削除", key=f"delete_{material.id}"):
                            st.session_state.delete_material_id = material.id
                            st.rerun()
                    with col3:
                        pass  # スペーサー
            
                # 削除確認（2段階確認）
                if st.session_state.get("delete_material_id") == material.id:
                    st.warning("⚠️ この材料を削除しますか？")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("✅ 削除を実行", key=f"confirm_delete_{material.id}", type="primary"):
                            # 論理削除を実行
                            from utils.db import session_scope
                            with session_scope() as db:
                                db_material = db.query(Material).filter(Material.id == material.id).first()
                                if db_material:
                                    db_material.is_deleted = 1
                                    db_material.deleted_at = datetime.utcnow()
                                    # commitはsession_scopeが自動実行
                                    clear_material_cache()  # キャッシュをクリア
                                    st.success("✅ 材料を削除しました")
                                    st.session_state.delete_material_id = None
                                    st.session_state.selected_material_id = None
                                    st.rerun()
                            # 例外時はsession_scopeが自動rollback
                    with col2:
                        if st.button("❌ キャンセル", key=f"cancel_delete_{material.id}"):
                            st.session_state.delete_material_id = None
                            st.rerun()
                    return
                
                # 復活確認（is_deleted=1 の場合のみ表示）
                if material.is_deleted == 1 and st.session_state.get("restore_material_id") == material.id:
                    # 復活前に active同名がいないかチェック
                    from utils.db import get_session
                    from sqlalchemy import select
                    with get_session() as db_check:
                        active_check_stmt = (
                            select(Material.id)
                            .where(Material.name_official == material.name_official)
                            .where(Material.is_deleted == 0)
                            .limit(1)
                        )
                        active_existing = db_check.execute(active_check_stmt).scalar_one_or_none()
                        
                        if active_existing is not None:
                            st.error(f"❌ 同名の材料が既に存在します（ID: {active_existing}）。復活するには材料名を変更してください。")
                            new_name = st.text_input("新しい材料名（正式）", key=f"restore_rename_{material.id}", value=material.name_official)
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button("✅ リネームして復活", key=f"confirm_restore_rename_{material.id}", type="primary"):
                                    if new_name and new_name.strip() and new_name.strip() != material.name_official:
                                        from utils.db import session_scope
                                        with session_scope() as db_restore:
                                            db_material_restore = db_restore.query(Material).filter(Material.id == material.id).first()
                                            if db_material_restore:
                                                db_material_restore.is_deleted = 0
                                                db_material_restore.deleted_at = None
                                                db_material_restore.name_official = new_name.strip()
                                                # commitはsession_scopeが自動実行
                                                st.success(f"✅ 材料を復活しました（名称変更: {material.name_official} → {new_name.strip()}）")
                                                st.session_state.restore_material_id = None
                                                st.session_state.selected_material_id = None
                                                st.rerun()
                                        # 例外時はsession_scopeが自動rollback
                                    else:
                                        st.warning("⚠️ 新しい材料名を入力してください（現在の名前と異なる必要があります）")
                            with col2:
                                if st.button("❌ キャンセル", key=f"cancel_restore_{material.id}"):
                                    st.session_state.restore_material_id = None
                                    st.rerun()
                        else:
                            # 同名が存在しない場合はそのまま復活
                            st.warning("⚠️ この材料を復活しますか？")
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button("✅ 復活を実行", key=f"confirm_restore_{material.id}", type="primary"):
                                    from utils.db import session_scope
                                    with session_scope() as db_restore:
                                        db_material_restore = db_restore.query(Material).filter(Material.id == material.id).first()
                                        if db_material_restore:
                                            db_material_restore.is_deleted = 0
                                            db_material_restore.deleted_at = None
                                            # commitはsession_scopeが自動実行
                                            st.success("✅ 材料を復活しました")
                                            st.session_state.restore_material_id = None
                                            st.session_state.selected_material_id = None
                                            st.rerun()
                                    # 例外時はsession_scopeが自動rollback
                            with col2:
                                if st.button("❌ キャンセル", key=f"cancel_restore_{material.id}"):
                                    st.session_state.restore_material_id = None
                                    st.rerun()
                    return
                
                # 削除済み材料の場合は復活ボタンを表示
                if material.is_deleted == 1:
                    if st.button("🔄 復活", key=f"restore_{material.id}"):
                        st.session_state.restore_material_id = material.id
                        st.rerun()
                
                # 3タブ構造で詳細表示（eager load済みのmaterialを渡す）
                # 念のため、再度取得してeager loadを保証
                material = get_material_by_id(material.id)
                if material:
                    show_material_detail_tabs(material)
                    return
                else:
                    st.error("材料が見つかりませんでした。")
                    st.session_state.selected_material_id = None
        
        # ページングで材料を取得（軽量クエリ、limit=50）
        from utils.settings import get_database_url
        db_url = get_database_url()
        
        # ページ番号を管理
        if "materials_list_page" not in st.session_state:
            st.session_state.materials_list_page = 0
        page_num = st.session_state.materials_list_page
        limit = 50
        offset = page_num * limit
        
        # DB起床直後の自動実行ガード（直近3秒は重い処理を自動実行しない）
        db_warmed_recently = st.session_state.get("db_warmed_recently", False)
        db_warmed_at = st.session_state.get("db_warmed_at", 0)
        if db_warmed_recently and (time.time() - db_warmed_at) < 3.0:
            # 起床直後は自動実行をスキップ（ボタン押下の明示操作は許可）
            # None にして表示ブロックをスキップ（[]をセットすると「材料ゼロ」に見えるリスクを避ける）
            materials_dicts = None
        else:
            materials_dicts = fetch_materials_page_cached(
                db_url=db_url,
                include_unpublished=include_unpublished,
                include_deleted=include_deleted,
                limit=limit,
                offset=offset
            )
        
        # DB起床直後ガード中（materials_dicts=None）の場合は表示をスキップ
        if materials_dicts is None:
            return
        
        if not materials_dicts:
            if page_num == 0:
                st.info("まだ材料が登録されていません。「材料登録」から材料を追加してください。")
            else:
                st.info("これ以上材料がありません。")
            return
        
        # dict から Material 風のオブジェクトを作成（後方互換のため）
        class MaterialProxy:
            def __init__(self, d):
                self.id = d.get("id")
                self.uuid = d.get("uuid")
                self.name_official = d.get("name_official")
                self.name = d.get("name")
                self.category_main = d.get("category_main")
                self.category = d.get("category")
                self.description = d.get("description")  # 説明（後方互換）
                self.is_published = d.get("is_published", 1)
                self.is_deleted = d.get("is_deleted", 0)
                self.created_at = d.get("created_at")
                self.updated_at = d.get("updated_at")
                self.properties = d.get("properties", [])  # 一覧では一括取得したpropertiesを使用
                self.images = []  # 一覧ではロードしない
                self.primary_image_url = d.get("primary_image_url")  # imagesテーブルから取得したpublic_url
        
        materials = [MaterialProxy(d) for d in materials_dicts]
        
        # ページネーションUI
        col_prev, col_info, col_next = st.columns([1, 3, 1])
        with col_prev:
            if st.button("◀ 前のページ", disabled=(page_num == 0)):
                st.session_state.materials_list_page = max(0, page_num - 1)
                st.rerun()
        with col_info:
            st.caption(f"ページ {page_num + 1} (表示中: {len(materials)} 件)")
        with col_next:
            if st.button("次のページ ▶", disabled=(len(materials) < limit)):
                st.session_state.materials_list_page = page_num + 1
                st.rerun()
        
        # フィルタリング
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            categories = ["すべて"] + list(set([m.category_main or m.category for m in materials if m.category_main or m.category]))
            selected_category = st.selectbox("カテゴリでフィルタ", categories)
        with col2:
            search_term = st.text_input("材料名で検索", placeholder="材料名を入力...")
        with col3:
            st.write("")  # スペーサー
            st.write("")  # スペーサー
        
        # フィルタリング適用
        filtered_materials = materials
        if selected_category and selected_category != "すべて":
            filtered_materials = [m for m in filtered_materials if (m.category_main or m.category) == selected_category]
        if search_term:
            filtered_materials = [m for m in filtered_materials if search_term.lower() in (m.name_official or m.name or "").lower()]
        
        st.markdown(f"### **{len(filtered_materials)}件**の材料が見つかりました")
        
        # 画像表示トグル（Network transfer削減のため）
        if "show_images_in_list" not in st.session_state:
            st.session_state.show_images_in_list = True
        show_images = st.toggle("🖼️ 画像を表示", value=st.session_state.show_images_in_list, key="toggle_images_list")
        st.session_state.show_images_in_list = show_images
        
        # 材料カード表示（グリッドレイアウト）
        # カード全体クリック用のCSS（グローバル）
        st.markdown("""
        <style>
            /* カード全体クリック可能にするためのスタイル */
            .material-card-link {
                text-decoration: none !important;
                color: inherit !important;
                display: block !important;
            }
            .material-card-link .material-card-container {
                cursor: pointer !important;
                transition: transform 0.2s, box-shadow 0.2s !important;
            }
            .material-card-link:hover .material-card-container {
                transform: translateY(-2px) !important;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15) !important;
            }
        </style>
        """, unsafe_allow_html=True)
        
        cols = st.columns(3)
        for idx, material in enumerate(filtered_materials):
            with cols[idx % 3]:
                try:
                    with st.container():
                        properties_text = ""
                        if material.properties:
                            props = material.properties[:3]
                            properties_text = "<br>".join([
                                f"<small style='color: #666;'>• {p.get('property_name', '')}: <strong style='color: #667eea;'>{p.get('value', '')} {p.get('unit', '') or ''}</strong></small>"
                                for p in props if isinstance(p, dict)
                            ])
                        
                        material_name = material.name_official or material.name or "名称不明"
                        material_desc = getattr(material, "description", "") or ""
                        
                        # 素材画像を取得（高速化: imagesテーブルのpublic_urlを直接使用、base64化やローカル探索をしない）
                        # primaryのみを使用（space/productは用途タブ専用）
                        # 画像表示トグルがOFFの場合は画像URL取得をスキップ（Network transfer削減）
                        # Neon節約: primary_image_urlが無い場合はDB取得を試みない（一覧ではDBアクセスを避ける）
                        image_url = None
                        if st.session_state.get("show_images_in_list", False):
                            # primary_image_urlを確認（DBアクセス不要）
                            primary_image_url = getattr(material, "primary_image_url", None)
                            if primary_image_url and str(primary_image_url).strip() and str(primary_image_url).startswith(("http://", "https://")):
                                image_url = str(primary_image_url)
                            elif primary_image_url:
                                # primary_image_urlが有効な場合はresolve_material_image_url()を呼ぶ（内部でprimaryを優先するためDBアクセスなし）
                                image_url = resolve_material_image_url(material, db_url)
                            # primary_image_urlが無い場合はresolve_material_image_url()を呼ばない（DBアクセスを避ける）
                        
                        # 画像HTML（public_urlがある場合は直接使用、なければプレースホルダー）
                        if image_url and image_url.strip() and image_url.startswith(('http://', 'https://')):
                            # R2の公開URLを直接使用（キャッシュバスター追加）
                            try:
                                from material_map_version import APP_VERSION
                            except ImportError:
                                APP_VERSION = get_git_sha()
                            separator = "&" if "?" in image_url else "?"
                            image_url_with_cache = f"{image_url}{separator}v={APP_VERSION}"
                            # URLエンコード（日本語ファイル名対応）
                            safe_image_url = safe_url(image_url_with_cache)
                            img_html = f'<img src="{safe_image_url}" class="material-hero-image" alt="{material_name}" />'
                        else:
                            # 画像なし（プレースホルダー）
                            img_html = f'<div class="material-hero-image" style="display: flex; align-items: center; justify-content: center; color: #999; font-size: 14px;">画像なし</div>'
                        
                        # カテゴリ名（長い場合は省略）
                        category_name = material.category_main or material.category or '未分類'
                        if len(category_name) > 20:
                            category_display = category_name[:17] + "..."
                            category_title = category_name
                        else:
                            category_display = category_name
                            category_title = ""
                        
                        # HTMLカードを生成（行頭スペースを強制除去してMarkdownのコードブロック扱いを防ぐ）
                        # カード全体をクリック可能にするため、<a>タグで囲む
                        card_html_raw = f"""<a href="?page=材料一覧&material_id={material.id}" class="material-card-link">
<div class="material-card-container material-texture" id="mat-card-{material.id}">
{img_html}
<div style="display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 12px; margin-top: 16px;">
<h3 style="color: #1a1a1a; margin: 0; font-size: 1.4rem; font-weight: 700; flex: 1;">{material_name}</h3>
</div>
<div style="margin-bottom: 12px;">
<span class="category-badge" title="{category_title}">{category_display}</span>
</div>
<p style="color: #666; margin: 0; font-size: 0.95rem; line-height: 1.6;">
{material_desc[:80] if material_desc else '説明なし'}...
</p>
<div style="margin: 20px 0;">
{properties_text}
</div>
<div style="margin-top: 20px; display: flex; justify-content: space-between; align-items: center;">
<small style="color: #999;">ID: {material.id}</small>
{f'<small style="color: #999;">{"✅ 公開" if getattr(material, "is_published", 1) == 1 else "🔒 非公開"}</small>' if include_unpublished else ''}
</div>
</div>
</a>"""
                        # 行頭スペースを強制除去（Markdownのコードブロック扱いを防ぐ）
                        card_html = "\n".join(line.lstrip() for line in card_html_raw.splitlines()).strip()
                        # st.markdown でHTMLをレンダリング（unsafe_allow_html=True を必ず指定、st.writeは禁止）
                        st.markdown(card_html, unsafe_allow_html=True)
                        
                        # 管理者表示時は公開/非公開切り替えスイッチを表示
                        if include_unpublished:
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                pass  # スペーサー
                            with col2:
                                current_status = getattr(material, "is_published", 1)
                                new_status = st.toggle(
                                    "公開" if current_status == 1 else "非公開",
                                    value=current_status == 1,
                                    key=f"toggle_publish_{material.id}"
                                )
                                if new_status != (current_status == 1):
                                    # ステータス変更
                                    from utils.db import session_scope
                                    from database import Material
                                    with session_scope() as db:
                                        # データベースから再取得して更新
                                        db_material = db.query(Material).filter(Material.id == material.id).first()
                                        if db_material:
                                            db_material.is_published = 1 if new_status else 0
                                            # commitはsession_scopeが自動実行
                                            st.rerun()
                                    # 例外時はsession_scopeが自動rollback
                        
                        # 管理者モードの場合は編集・削除ボタンを表示
                        is_admin = os.getenv("DEBUG", "0") == "1" or os.getenv("ADMIN", "0") == "1"
                        admin_buttons_html = ""
                        if is_admin:
                            admin_buttons_html = f"""
                            <div style="display: flex; gap: 8px; margin-bottom: 8px;">
                                <button onclick="window.streamlitEdit_{material.id}()" style="background: #4a90e2; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 0.9rem;">✏️ 編集</button>
                                <button onclick="window.streamlitDelete_{material.id}()" style="background: #e74c3c; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 0.9rem;">🗑️ 削除</button>
                            </div>
                            """
                        
                        # 管理者モードの場合は編集・削除ボタンを表示
                        if is_admin:
                            col1, col2, col3 = st.columns([1, 1, 8])
                            with col1:
                                if st.button("✏️ 編集", key=f"edit_list_{material.id}"):
                                    st.session_state.edit_material_id = material.id
                                    st.session_state.page = "材料登録"
                                    st.rerun()
                            with col2:
                                if st.button("🗑️ 削除", key=f"delete_list_{material.id}"):
                                    st.session_state.delete_material_id = material.id
                                    st.rerun()
                            with col3:
                                pass
                        
                        # 削除確認（2段階確認）
                        if st.session_state.get("delete_material_id") == material.id:
                            st.warning("⚠️ この材料を削除しますか？")
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button("✅ 削除を実行", key=f"confirm_delete_list_{material.id}", type="primary"):
                                    # 論理削除を実行
                                    from utils.db import session_scope
                                    from database import Material
                                    with session_scope() as db:
                                        db_material = db.query(Material).filter(Material.id == material.id).first()
                                        if db_material:
                                            db_material.is_deleted = 1
                                            db_material.deleted_at = datetime.utcnow()
                                            # commitはsession_scopeが自動実行
                                            clear_material_cache()  # キャッシュをクリア
                                            st.success("✅ 材料を削除しました")
                                            st.session_state.delete_material_id = None
                                            st.rerun()
                                    # 例外時はsession_scopeが自動rollback
                            with col2:
                                if st.button("❌ キャンセル", key=f"cancel_delete_list_{material.id}"):
                                    st.session_state.delete_material_id = None
                                    st.rerun()
                        
                        # 復活確認（is_deleted=1 の場合のみ表示）
                        if material.is_deleted == 1 and st.session_state.get("restore_material_id") == material.id:
                            # 復活前に active同名がいないかチェック
                            from utils.db import get_session, session_scope
                            from sqlalchemy import select
                            with get_session() as db_check:
                                active_check_stmt = (
                                    select(Material.id)
                                    .where(Material.name_official == material.name_official)
                                    .where(Material.is_deleted == 0)
                                    .limit(1)
                                )
                                active_existing = db_check.execute(active_check_stmt).scalar_one_or_none()
                                
                                if active_existing is not None:
                                    st.error(f"❌ 同名の材料が既に存在します（ID: {active_existing}）。復活するには材料名を変更してください。")
                                    new_name = st.text_input("新しい材料名（正式）", key=f"restore_rename_list_{material.id}", value=material.name_official)
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        if st.button("✅ リネームして復活", key=f"confirm_restore_rename_list_{material.id}", type="primary"):
                                            if new_name and new_name.strip() and new_name.strip() != material.name_official:
                                                with session_scope() as db_restore:
                                                    db_material_restore = db_restore.query(Material).filter(Material.id == material.id).first()
                                                    if db_material_restore:
                                                        db_material_restore.is_deleted = 0
                                                        db_material_restore.deleted_at = None
                                                        db_material_restore.name_official = new_name.strip()
                                                        # commitはsession_scopeが自動実行
                                                        st.success(f"✅ 材料を復活しました（名称変更: {material.name_official} → {new_name.strip()}）")
                                                        st.session_state.restore_material_id = None
                                                        st.rerun()
                                                # 例外時はsession_scopeが自動rollback
                                            else:
                                                st.warning("⚠️ 新しい材料名を入力してください（現在の名前と異なる必要があります）")
                                    with col2:
                                        if st.button("❌ キャンセル", key=f"cancel_restore_list_{material.id}"):
                                            st.session_state.restore_material_id = None
                                            st.rerun()
                                else:
                                    # 同名が存在しない場合はそのまま復活
                                    st.warning("⚠️ この材料を復活しますか？")
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        if st.button("✅ 復活を実行", key=f"confirm_restore_list_{material.id}", type="primary"):
                                            with session_scope() as db_restore:
                                                db_material_restore = db_restore.query(Material).filter(Material.id == material.id).first()
                                                if db_material_restore:
                                                    db_material_restore.is_deleted = 0
                                                    db_material_restore.deleted_at = None
                                                    # commitはsession_scopeが自動実行
                                                    st.success("✅ 材料を復活しました")
                                                    st.session_state.restore_material_id = None
                                                    st.rerun()
                                            # 例外時はsession_scopeが自動rollback
                                    with col2:
                                        if st.button("❌ キャンセル", key=f"cancel_restore_list_{material.id}"):
                                            st.session_state.restore_material_id = None
                                            st.rerun()
                        
                        # 削除済み材料の場合は復活ボタンを表示
                        if material.is_deleted == 1:
                            if st.button("🔄 復活", key=f"restore_list_{material.id}"):
                                st.session_state.restore_material_id = material.id
                                st.rerun()
                except Exception as e:
                    logger.exception(f"[LIST] card render failed: id={getattr(material,'id',None)} err={e}")
                    st.warning("⚠️ このカードは表示できませんでした（スキップ）")
        
        # パフォーマンス計測（DEBUG=1のみ）
        if debug_enabled and t0 is not None:
            t1 = time.perf_counter()
            logger.info(f"[PERF] show_materials_list: {(t1 - t0) * 1000:.1f}ms")
    except Exception as e:
        logger.exception(f"[MATERIALS LIST] Error: {e}")
        st.error(f"❌ 材料一覧の表示中にエラーが発生しました: {e}")
        if show_debug_ui():
            import traceback
            st.code("".join(traceback.format_exception(type(e), e, e.__traceback__)), language="python")

def show_dashboard():
    """ダッシュボードページ（管理者限定、全件取得）"""
    is_debug = show_debug_ui()
    st.markdown(render_site_header(debug=is_debug), unsafe_allow_html=True)
    st.markdown('<h2 class="section-title">ダッシュボード</h2>', unsafe_allow_html=True)
    
    # 管理者限定（重い操作のため）
    from utils.settings import is_admin_mode
    is_admin = is_admin_mode()
    if not is_admin:
        st.warning("⚠️ ダッシュボードは管理者のみ利用可能です。")
        return
    
    # 管理者表示フラグを取得
    include_unpublished = st.session_state.get("include_unpublished", False)
    
    from utils.db import DBUnavailableError
    try:
        # ダッシュボードは全件取得が必要（統計・グラフ表示のため）
        # MAX_LIST_LIMIT=200がサービス層で適用される
        from utils.settings import get_database_url
        db_url = get_database_url()
        materials = get_all_materials(db_url, include_unpublished=include_unpublished)
    except DBUnavailableError:
        handle_db_unavailable(
            "ダッシュボード（管理者）",
            retry_fn=lambda: get_all_materials(db_url, include_unpublished=include_unpublished),
            operation="ダッシュボード全件取得"
        )
    
    if not materials:
        st.info("ダッシュボードを表示するには、まず材料を登録してください。")
        return
    
    # 統計カード
    st.markdown("### 統計情報")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-value">{len(materials)}</div>
            <div class="stat-label">登録材料数</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        categories = len(set([m.category for m in materials if m.category]))
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-value">{categories}</div>
            <div class="stat-label">カテゴリ数</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        # SQLで直接カウント（DetachedInstanceError回避）
        # Phase 2: 統一APIを使用（読み取り専用）
        from utils.db import get_session
        with get_session() as db:
            total_properties = db.execute(select(func.count(Property.id))).scalar() or 0
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-value">{total_properties}</div>
            <div class="stat-label">物性データ数</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        avg_properties = total_properties / len(materials) if materials else 0
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-value">{avg_properties:.1f}</div>
            <div class="stat-label">平均物性数</div>
        </div>
        """, unsafe_allow_html=True)
    
    # グラフ
    col1, col2 = st.columns(2)
    
    with col1:
        fig = create_category_chart(materials)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = create_timeline_chart(materials)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
    
    # カテゴリ別詳細
    st.markdown("### カテゴリ別詳細")
    category_data = {}
    for material in materials:
        cat = material.category or "未分類"
        if cat not in category_data:
            category_data[cat] = []
        category_data[cat].append(material)
    
    for category, mats in category_data.items():
        with st.expander(f"📁 {category} ({len(mats)}件)", expanded=False):
            for mat in mats:
                # SQLで直接カウント（DetachedInstanceError回避）
                # Phase 2: 統一APIを使用（読み取り専用）
                from utils.db import get_session
                with get_session() as db:
                    prop_count = db.execute(
                        select(func.count(Property.id))
                        .where(Property.material_id == mat.id)
                    ).scalar() or 0
                st.write(f"• **{mat.name}** - {prop_count}個の物性データ")

def show_search():
    """検索ページ（万華鏡体験：フィルタ + 全文検索）"""
    is_debug = show_debug_ui()
    st.markdown(render_site_header(debug=is_debug), unsafe_allow_html=True)
    st.markdown('<h2 class="section-title">材料検索</h2>', unsafe_allow_html=True)
    
    # DEBUG=1のときだけ関数到達確認とページ状態を表示
    if is_debug:
        st.info("DEBUG: entered show_search()")
        page_state = {
            "page": st.session_state.get("page"),
            "selected_material_id": st.session_state.get("selected_material_id"),
        }
        st.code(f"Page state: {page_state}")
    
    # 自然言語検索バー（上）- 確定ボタン化（DB起床削減のため）
    col_search, col_btn = st.columns([4, 1])
    with col_search:
        search_query_input = st.text_input(
            "🔍 自然言語検索", 
            placeholder="例: 透明 屋外 工房（自然言語で検索できます）", 
            key="search_input_raw"
        )
    with col_btn:
        st.write("")  # スペーサー
        st.write("")  # スペーサー
        search_button_clicked = st.button("🔍 検索", type="primary", key="search_execute_btn")
    
    # 検索実行フラグを管理（確定ボタン押下時のみ検索実行）
    if "search_executed" not in st.session_state:
        st.session_state.search_executed = False
    
    if search_button_clicked:
        st.session_state.search_executed = True
        st.session_state.search_query_executed = search_query_input
        st.rerun()
    
    # 実行された検索クエリを使用（入力中のクエリは無視）
    search_query = st.session_state.get("search_query_executed", "") if st.session_state.get("search_executed", False) else ""
    
    st.markdown("---")
    
    # フィルタ（下）
    st.markdown("### フィルタ")
    
    # フィルタオプションをインポート
    from material_form_detailed import (
        USE_CATEGORIES, TRANSPARENCY_OPTIONS, WEATHER_RESISTANCE_OPTIONS,
        # USE_ENVIRONMENT_OPTIONS,  # 一時的にコメントアウト（DBにカラムが存在しない）
        WATER_RESISTANCE_OPTIONS, EQUIPMENT_LEVELS, COST_LEVELS
    )
    
    # フィルタを2列で配置
    col1, col2 = st.columns(2)
    
    with col1:
        # 使用環境（複数選択）- 一時的にコメントアウト（DBにカラムが存在しない）
        # selected_environments = st.multiselect(
        #     "使用環境",
        #     options=USE_ENVIRONMENT_OPTIONS,
        #     key="filter_use_environment"
        # )
        
        # 用途カテゴリ（複数選択）
        selected_uses = st.multiselect(
            "用途カテゴリ",
            options=USE_CATEGORIES,
            key="filter_use_categories"
        )
        
        # 透明性
        selected_transparency = st.selectbox(
            "透明性",
            options=["すべて"] + TRANSPARENCY_OPTIONS,
            key="filter_transparency"
        )
        
        # 耐候性
        selected_weather = st.selectbox(
            "耐候性",
            options=["すべて"] + WEATHER_RESISTANCE_OPTIONS,
            key="filter_weather"
        )
    
    with col2:
        # 耐水性
        selected_water = st.selectbox(
            "耐水性",
            options=["すべて"] + WATER_RESISTANCE_OPTIONS,
            key="filter_water"
        )
        
        # 設備レベル
        selected_equipment = st.selectbox(
            "設備レベル",
            options=["すべて"] + EQUIPMENT_LEVELS,
            key="filter_equipment"
        )
        
        # コスト帯
        selected_cost = st.selectbox(
            "コスト帯",
            options=["すべて"] + COST_LEVELS,
            key="filter_cost"
        )
    
    # フィルタ辞書を構築（正規化済み）
    filters = {}
    
    # プレースホルダー文字列のリスト（無視すべき値）
    placeholder_values = ["すべて", "", None, "Choose options", "選択してください"]
    
    # 使用環境（multiselect）- 一時的にコメントアウト（DBにカラムが存在しない）
    # if selected_environments and isinstance(selected_environments, list):
    #     # 空でない、有効な値のみをフィルタ
    #     valid_envs = [e for e in selected_environments if e and str(e).strip() and str(e) not in placeholder_values]
    #     if valid_envs:
    #         filters['use_environment'] = valid_envs
    
    # 用途カテゴリ（multiselect）
    if selected_uses and isinstance(selected_uses, list):
        # 空でない、有効な値のみをフィルタ
        valid_uses = [u for u in selected_uses if u and str(u).strip() and str(u) not in placeholder_values]
        if valid_uses:
            filters['use_categories'] = valid_uses
    
    # 単一値フィルタ（selectbox）
    if selected_transparency and str(selected_transparency) not in placeholder_values:
        filters['transparency'] = selected_transparency
    if selected_weather and str(selected_weather) not in placeholder_values:
        filters['weather_resistance'] = selected_weather
    if selected_water and str(selected_water) not in placeholder_values:
        filters['water_resistance'] = selected_water
    if selected_equipment and str(selected_equipment) not in placeholder_values:
        filters['equipment_level'] = selected_equipment
    if selected_cost and str(selected_cost) not in placeholder_values:
        filters['cost_level'] = selected_cost
    
    # 管理者表示フラグを取得
    include_unpublished = st.session_state.get("include_unpublished", False)
    
    # DEBUG=1のときだけ検索実行前の情報を表示
    if is_debug:
        search_query_short = (search_query[:50] + "...") if search_query and len(search_query) > 50 else (search_query or "")
        filters_summary = {
            "use_categories": filters.get("use_categories"),
            "category_main": filters.get("category_main"),
            "include_unpublished": include_unpublished,
            "other_keys": [k for k in filters.keys() if k not in ["use_categories", "category_main"]]
        }
        st.code(f"DEBUG: Before search\n  query: {search_query_short}\n  filters: {filters_summary}")
    
    # 検索実行（確定ボタン押下時のみ、クエリまたはフィルタがある場合）
    # フィルタ変更時も検索を実行（selectbox/multiselectは確定操作）
    filters_changed = any([
        selected_uses,
        selected_transparency != "すべて",
        selected_weather != "すべて",
        selected_water != "すべて",
        selected_equipment != "すべて",
        selected_cost != "すべて"
    ])
    
    if (st.session_state.get("search_executed", False) and (search_query and search_query.strip())) or filters_changed:
        from utils.db import get_session
        
        # ハイブリッド検索を無効化できるフラグ（ENABLE_VECTOR_SEARCH=0で無効化）
        enable_vector_search = os.getenv("ENABLE_VECTOR_SEARCH", "0") == "1"
        
        with get_session() as db:
            if enable_vector_search:
                # ハイブリッド検索（全文検索 + ベクトル検索、フィルタ対応）を使用
                from utils.search import search_materials_hybrid
                try:
                    results, search_info = search_materials_hybrid(
                        db=db,
                        query=search_query.strip() if search_query else "",
                        filters=filters,
                        limit=20,
                        include_unpublished=include_unpublished,
                        include_deleted=False,
                        text_weight=0.5,
                        vector_weight=0.5
                    )
                except Exception as e:
                    # トランザクションエラーを防ぐため、必ずrollbackする
                    db.rollback()
                    
                    # 検索が失敗した場合は全文検索にフォールバック（PANICを防ぐ）
                    if is_debug:
                        st.warning(f"ハイブリッド検索エラー、全文検索にフォールバック: {e}")
                    
                    try:
                        from utils.search import search_materials_fulltext
                        results, search_info = search_materials_fulltext(
                            db=db,
                            query=search_query.strip() if search_query else "",
                            filters=filters,
                            limit=20,
                            include_unpublished=include_unpublished,
                            include_deleted=False
                        )
                        search_info['method'] = 'fulltext_fallback'
                        search_info['fallback_reason'] = str(e)
                    except Exception as e2:
                        # 全文検索も失敗した場合は空結果を返す（get_sessionは読み取り専用なのでrollback不要）
                        if is_debug:
                            st.error(f"全文検索も失敗: {e2}")
                        results = []
                        search_info = {
                            'query': search_query.strip() if search_query else "",
                            'filters': filters,
                            'count': 0,
                            'method': 'error',
                            'error': str(e2)
                        }
            else:
                # ハイブリッド検索が無効化されている場合は全文検索のみ実行
                from utils.search import search_materials_fulltext
                try:
                    results, search_info = search_materials_fulltext(
                        db=db,
                        query=search_query.strip() if search_query else "",
                        filters=filters,
                        limit=20,
                        include_unpublished=include_unpublished,
                        include_deleted=False
                    )
                    search_info['method'] = 'fulltext_only'
                except Exception as e:
                    # get_sessionは読み取り専用なのでrollback不要
                    if is_debug:
                        st.error(f"全文検索が失敗: {e}")
                    results = []
                    search_info = {
                        'query': search_query.strip() if search_query else "",
                        'filters': filters,
                        'count': 0,
                        'method': 'error',
                        'error': str(e)
                    }
        # 例外時はget_sessionが自動close（rollbackは不要、読み取り専用）
        
        # DEBUG=1のときだけ検索実行後の情報を表示
        if is_debug:
            results_count = len(results) if results else 0
            search_query_short = (search_query[:50] + "...") if search_query and len(search_query) > 50 else (search_query or "")
            filters_summary = {
                "use_categories": filters.get("use_categories"),
                "category_main": filters.get("category_main"),
                "include_unpublished": include_unpublished,
                "other_keys": [k for k in filters.keys() if k not in ["use_categories", "category_main"]]
            }
            st.code(f"DEBUG: After search\n  query: {search_query_short}\n  filters: {filters_summary}\n  results_count: {results_count}")
            if results_count == 0:
                st.warning("DEBUG: results=0; no cards will be rendered")
        
        # DEBUG=1のときだけ検索の詳細情報を表示
        if is_debug:
            with st.expander("🔍 検索詳細情報（DEBUG）", expanded=False):
                st.write(f"**検索クエリ**: {search_info.get('query', 'なし')}")
                st.write(f"**フィルタ**: {search_info.get('filters', {})}")
                st.write(f"**検索方法**: {search_info.get('method', 'unknown')}")
                if search_info.get('method') == 'hybrid':
                    st.write(f"**テキスト重み**: {search_info.get('text_weight', 0.5)}")
                    st.write(f"**ベクトル重み**: {search_info.get('vector_weight', 0.5)}")
                st.write(f"**結果件数**: {search_info.get('count', 0)}件")
        
        if results:
            st.success(f"**{len(results)}件**の結果が見つかりました")
            
            # material_idsを使ってprimary画像を一括取得
            from database import Image
            material_ids = [m.id for m in results]
            primary_images_dict = {}  # {material_id: public_url}
            
            if material_ids:
                from utils.db import get_session
                with get_session() as db_images:
                    images_stmt = select(Image).filter(
                        Image.material_id.in_(material_ids),
                        Image.kind == "primary"
                    )
                    images_result = db_images.execute(images_stmt)
                    images = images_result.scalars().all()
                    for img in images:
                        if img.public_url:
                            primary_images_dict[img.material_id] = img.public_url
            
            # DEBUG=1のときだけ1件目の要約を表示
            if is_debug and results:
                first_material = results[0]
                first_summary = {
                    "id": first_material.id,
                    "name_official": getattr(first_material, "name_official", None),
                    "name": getattr(first_material, "name", None),
                    "category_main": getattr(first_material, "category_main", None),
                    "is_published": getattr(first_material, "is_published", None),
                    "image_url": primary_images_dict.get(first_material.id)
                }
                st.code(f"DEBUG: First result summary\n{first_summary}")
            
            # 検索結果をカード形式で表示
            for idx, material in enumerate(results):
                # DEBUG=1のときだけ各カードの開始時に情報を表示
                if is_debug:
                    st.caption(f"DEBUG: rendering card idx={idx} id={material.id}")
                try:
                    with st.container():
                        # 材料カードを表示（画像URLを渡す）
                        image_url = primary_images_dict.get(material.id)
                        _render_material_search_card(material, idx, search_query, image_url=image_url)
                except Exception as e:
                    # カード描画で例外が発生した場合はログに記録し、そのカードだけスキップ
                    logger.exception(f"検索結果カードの描画でエラーが発生しました (material_id={material.id if material else 'unknown'}, idx={idx}): {e}")
                    st.warning(f"⚠️ 材料ID {material.id if material else 'unknown'} のカードを表示できませんでした。")
        
        else:
            st.info("検索結果が見つかりませんでした。検索キーワードやフィルタを変更してみてください。")
    else:
        # 検索クエリもフィルタも空の場合は説明を表示
        st.info("💡 自然言語で材料を検索できます。例：「透明 屋外 工房」「硬い 金属」「軽い プラスチック」など")
        st.info("💡 フィルタを使って材料を絞り込むこともできます。")


def _render_material_search_card(material, idx: int, search_query: str, image_url: str = None):
    """
    検索結果の材料カードをレンダリング

    Args:
        material: Materialオブジェクト
        idx: インデックス
        search_query: 検索クエリ（ハイライト用）
        image_url: primary画像URL（一括取得済み、Noneの場合は個別取得を試みる）
    """
    # DEBUG=1のときだけ関数冒頭でmaterial情報を表示
    is_debug = show_debug_ui()
    if is_debug:
        material_name = getattr(material, "name_official", None) or getattr(material, "name", None) or "名称不明"
        st.caption(f"DEBUG: _render_material_search_card() material.id={material.id} material_name={material_name}")
    
    # フォールバック用の変数を初期化
    material_name = None
    category_name = None
    description_text = None
    
    try:
        # SQLで直接カウント（DetachedInstanceError回避）
        # Phase 2: 統一APIを使用（get_db generatorは使用禁止）
        from sqlalchemy import select, func
        from database import Property
        from utils.db import get_session
        
        prop_count = 0
        try:
            with get_session() as db_sess:
                prop_count = db_sess.execute(
                    select(func.count(Property.id)).where(Property.material_id == material.id)
                ).scalar() or 0
        except Exception as e:
            # prop_count取得失敗は警告のみ（カード描画は継続）
            from utils.settings import is_debug
            if is_debug():
                logger.exception(f"[search_card] prop_count failed material_id={material.id}: {e}")
            prop_count = 0

        # 素材画像を取得（image_urlが渡されている場合はそれを使用）
        image_src = None
        if image_url:
            # キャッシュバスターを追加
            from utils.logo import get_git_sha
            try:
                from material_map_version import APP_VERSION
            except ImportError:
                APP_VERSION = get_git_sha()
            separator = "&" if "?" in image_url else "?"
            image_url_with_cache = f"{image_url}{separator}v={APP_VERSION}"
            # safe_url()で日本語ファイル名をエンコード
            image_src = safe_url(image_url_with_cache)
        # カテゴリ名
        category_name = material.category_main or material.category or '未分類'
        
        # 説明文を生成（1〜2行）
        description_parts = []
        if material.description:
            description_parts.append(material.description)
        elif material.development_background_short:
            description_parts.append(material.development_background_short)
        
        # 加工方法や用途を追加
        if material.processing_methods:
            try:
                methods = json.loads(material.processing_methods)
                if isinstance(methods, list) and methods:
                    description_parts.append(f"加工: {', '.join(methods[:2])}")
            except (json.JSONDecodeError, TypeError):
                pass
        
        if material.use_categories:
            try:
                uses = json.loads(material.use_categories)
                if isinstance(uses, list) and uses:
                    description_parts.append(f"用途: {', '.join(uses[:2])}")
            except (json.JSONDecodeError, TypeError):
                pass
        
        description_text = " | ".join(description_parts[:2]) if description_parts else "説明なし"
        # 長すぎる場合は省略
        if len(description_text) > 150:
            description_text = description_text[:147] + "..."
        
        # 材料名（正式名を優先）
        material_name = material.name_official or material.name or "名称不明"
        
        # カード表示
        st.markdown("---")
        
        # 画像と情報を横並び
        col_img, col_info = st.columns([1, 2])
        
        with col_img:
            if image_src:
                # st.imageを使用（最も堅い実装）
                st.image(image_src, use_container_width=True)
            else:
                # 画像がない場合は小さな灰色枠を表示
                st.markdown("<div style='width:100%;height:120px;background:#f0f0f0;'></div>", unsafe_allow_html=True)
        
        with col_info:
            st.markdown(f"### {material_name}")
            st.markdown(f"**カテゴリ**: {category_name}")
            st.markdown(f"{description_text}")
            if prop_count > 0:
                st.caption(f"物性データ: {prop_count}個")
            
            # 詳細を見るボタン
            if st.button(f"詳細を見る", key=f"search_detail_{material.id}_{idx}"):
                st.session_state.selected_material_id = material.id
                st.session_state.page = "材料一覧"
                st.rerun()
    except Exception as e:
        # 例外時はDEBUG=1のときだけエラーを表示
        if is_debug:
            st.error(f"DEBUG: Exception in _render_material_search_card() for material.id={material.id}")
            st.code(traceback.format_exc())
        
        # フォールバック: テキストだけの簡易カードを表示（常に表示）
        try:
            material_name = getattr(material, "name_official", None) or getattr(material, "name", None) or "名称不明"
            category_name = getattr(material, "category_main", None) or getattr(material, "category", None) or "未分類"
            description_text = getattr(material, "description", None) or getattr(material, "development_background_short", None) or "説明なし"
            
            st.markdown("---")
            st.write(f"**{material_name}**")
            st.write(f"カテゴリ: {category_name}")
            st.write(description_text)
        except Exception as e2:
            # フォールバックも失敗した場合は最小限の情報のみ
            st.write(f"材料ID: {material.id if material else 'unknown'}")
            if is_debug:
                st.write(f"エラー: {str(e2)}")


def show_approval_queue():
    """承認待ち一覧ページ（管理者のみ）"""
    from features.approval import show_approval_queue as _impl
    return _impl()
    

# ===== Phase 3: 承認フローのTx分離固定 =====

def _tx1_upsert_material_core(submission: MaterialSubmission, form_data: dict, update_existing: bool = True) -> tuple[int, str]:
    """
    Tx1: materials本体のみ。副作用（images/properties/embeddings/submission更新）は禁止。
    
    Args:
        submission: MaterialSubmissionオブジェクト
        form_data: フォームデータの辞書（payload_jsonからパース済み）
        update_existing: True なら同名素材（is_deleted=0）があれば更新、False なら常に新規作成
    
    Returns:
        material_id: 作成/更新されたMaterialのID
    
    Raises:
        Exception: Tx1失敗時（呼び出し元でcatchして即return）
    
    Note:
        - NOT NULL補完を flush前に行う
        - commit成功後、material_idを返す
        - 副作用（images/properties/embeddings/submission更新）は絶対に含めない
    """
    from utils.db import session_scope
    from sqlalchemy import select
    import uuid
    
    with session_scope() as db:
        # name_official の必須チェック
        name_official = form_data.get("name_official", "").strip()
        if not name_official:
            raise ValueError("材料名（正式）が空です。承認できません。")
        
        # Phase 4: NOT NULL補完を最初に実行（flush前）
        from utils.material_defaults import apply_material_defaults
        form_data = apply_material_defaults(form_data)
        
        # payload をサニタイズ：Material カラムだけに絞る（補完済みform_dataから）
        allowed_columns = {c.name for c in Material.__table__.columns}
        relationship_keys = {"images", "uploaded_images", "reference_urls", "use_examples", "properties", "metadata_items", "process_example_images"}
        system_keys = {"id", "created_at", "updated_at", "deleted_at", "uuid"}
        payload_for_material = {
            k: v for k, v in form_data.items()
            if k in allowed_columns 
            and k not in relationship_keys 
            and k not in system_keys
            and v is not None
        }
        
        # 既存Materialを検索（update_existing=True の場合のみ、is_deleted=0 のみ対象）
        material = None
        action = None
        
        if update_existing and name_official:
            existing_stmt = (
                select(Material)
                .where(Material.name_official == name_official)
                .where(Material.is_deleted == 0)
            )
            existing = db.execute(existing_stmt).scalar_one_or_none()
            
            if existing is not None:
                material = existing
                action = "updated"
                logger.info(f"[APPROVE][Tx1] Updating existing material (id={material.id}, name_official='{name_official}')")
        
        if material is None:
            # 新規作成前に、同名の active があるかチェック
            if name_official:
                active_check_stmt = (
                    select(Material.id)
                    .where(Material.name_official == name_official)
                    .where(Material.is_deleted == 0)
                    .limit(1)
                )
                active_existing = db.execute(active_check_stmt).scalar_one_or_none()
                if active_existing is not None:
                    if update_existing:
                        raise ValueError(f"同名の材料が既に存在します（ID: {active_existing}）。「既存へ反映」モードで承認してください。")
                    else:
                        raise ValueError(f"同名の材料が既に存在します（ID: {active_existing}）。材料名を変更して再投稿してください。")
            
            # 新規作成
            material_uuid = str(uuid.uuid4())
            material = Material(uuid=material_uuid)
            db.add(material)
            action = 'created'
            logger.info(f"[APPROVE][Tx1] Creating new material (name_official='{name_official}')")
        
        # 補完済みのpayload_for_materialをMaterialオブジェクトに設定（システム列は除外）
        for field, value in payload_for_material.items():
            if hasattr(material, field) and field not in system_keys:
                if value is not None:
                    setattr(material, field, value)
        
        # JSON配列フィールドの処理（補完後に上書き、リストの場合はJSON文字列に変換）
        json_fields = ['name_aliases', 'material_forms', 'color_tags', 'processing_methods',
                      'use_categories', 'safety_tags', 'question_templates', 'main_elements']
        for field in json_fields:
            if field in form_data and form_data[field]:
                if isinstance(form_data[field], list):
                    material.__setattr__(field, json.dumps(form_data[field], ensure_ascii=False))
                elif isinstance(form_data[field], str) and not form_data[field].startswith('['):
                    # 文字列の場合はそのまま（既にJSON文字列の可能性）
                    material.__setattr__(field, form_data[field])
        
        # 後方互換フィールド
        if form_data.get('name_official'):
            material.name = form_data.get('name_official')
        if form_data.get('category_main'):
            material.category = form_data.get('category_main')
        
        # search_textを生成して設定
        from utils.search import generate_search_text
        material.search_text = generate_search_text(material)
        
        db.flush()
        
        # 参照URL保存（更新モードの場合は既存を削除して置き換え）
        if action == "updated":
            db.query(ReferenceURL).filter(ReferenceURL.material_id == material.id).delete()
            db.query(UseExample).filter(UseExample.material_id == material.id).delete()
            db.flush()
        
        # 参照URL保存
        for ref in form_data.get('reference_urls', []):
            if ref.get('url'):
                ref_url = ReferenceURL(
                    material_id=material.id,
                    url=ref['url'],
                    url_type=ref.get('type'),
                    description=ref.get('desc')
                )
                db.add(ref_url)
        
        # 使用例保存
        for ex in form_data.get('use_examples', []):
            if ex.get('name'):
                use_ex = UseExample(
                    material_id=material.id,
                    example_name=ex['name'],
                    example_url=ex.get('url'),
                    description=ex.get('desc')
                )
                db.add(use_ex)
        
        # material.id を確定（flush してから取得）
        db.flush()
        material_id = material.id
        if not material_id:
            raise ValueError("material.id is None after flush")
        
        # session_scopeが自動commit（例外時は自動rollback）
        logger.info(f"[APPROVE][Tx1] commit success: material_id={material_id}, action={action}, uuid={material.uuid}")
        return material_id, action


def _tx2_upsert_images(material_id: int, uploaded_images: list, payload_dict: dict, *, submission_id: int = None) -> None:
    """
    Tx2: images upsert。失敗しても承認は継続。
    
    Args:
        material_id: MaterialのID
        uploaded_images: アップロード済み画像情報のリスト
        payload_dict: submissionのpayload_json（images_info取得用）
        submission_id: オプション（ログ用）
    
    Note:
        - R2 upload は DB Tx の外で行う（ネットワークI/OでTxを長引かせない）
        - DB upsert のみ session_scope() を使う
        - 失敗しても承認は継続（ログは残す）
    """
    from utils.db import session_scope
    import base64
    import hashlib
    
    # 一括登録の承認待ち送信で保存した images_info を処理（R2 upload）
    images_info = payload_dict.get("images_info", [])
    if isinstance(images_info, list) and len(images_info) > 0:
        from utils.bulk_import import upload_image_to_r2
        
        for img_info in images_info:
            if not isinstance(img_info, dict):
                continue
            
            kind = img_info.get('kind', 'primary')
            file_name = img_info.get('file_name', '')
            data_base64 = img_info.get('data_base64', '')
            
            if not data_base64:
                continue
            
            try:
                # base64デコード
                image_data = base64.b64decode(data_base64)
                
                # R2にアップロード（DB Txの外）
                r2_result = upload_image_to_r2(material_id, image_data, kind, file_name)
                
                if r2_result:
                    uploaded_images.append({
                        'kind': kind,
                        'r2_key': r2_result['r2_key'],
                        'public_url': r2_result['public_url'],
                        'mime': r2_result.get('mime', 'image/jpeg'),
                        'sha256': hashlib.sha256(image_data).hexdigest(),
                        'bytes': len(image_data)
                    })
                    logger.info(f"[APPROVE][Tx2] Uploaded image from images_info: kind={kind}, file_name={file_name}")
            except Exception as e:
                logger.warning(f"[APPROVE][Tx2] Failed to process image from images_info: {e}")
    
    uploaded_images_count = len(uploaded_images)
    if uploaded_images_count == 0:
        logger.info(f"[APPROVE][Tx2] No images to upsert (uploaded_images_count=0), skipping Tx2")
        return
    
    # DB upsert（session_scope内）
    with session_scope() as db:
        from utils.image_repo import upsert_image
        
        for idx, img_info in enumerate(uploaded_images):
            if not isinstance(img_info, dict):
                logger.warning(f"[APPROVE][Tx2] Image {idx+1} is not a dict: type={type(img_info)}, skipping")
                continue
            
            kind = img_info.get('kind', 'primary')
            r2_key = img_info.get('r2_key')
            public_url = img_info.get('public_url')
            mime = img_info.get('mime')
            sha256 = img_info.get('sha256')
            bytes_value = img_info.get('bytes')
            
            # bytes が None でない場合は int に変換（bigint対応）
            if bytes_value is not None:
                try:
                    bytes_value = int(bytes_value)
                except (ValueError, TypeError):
                    logger.warning(f"[APPROVE][Tx2] Image {idx+1} bytes value is not int-convertible: {bytes_value}, using None")
                    bytes_value = None
            
            logger.info(f"[APPROVE][Tx2] Upserting image {idx+1}/{uploaded_images_count}: kind={kind}, r2_key={r2_key}, public_url={public_url}, mime={mime}, sha256={sha256[:16] if sha256 else None}...")
            
            upsert_image(
                db=db,
                material_id=material_id,
                kind=kind,
                r2_key=r2_key,
                public_url=public_url,
                bytes=bytes_value,
                mime=mime,
                sha256=sha256,
            )
                
        # session_scopeが自動commit（例外時は自動rollback）
        logger.info(f"[APPROVE][Tx2] success: images upserted for material_id={material_id} (count={uploaded_images_count})")


def _txprops_upsert_properties(material_id: int, properties_list: list, *, submission_id: int = None) -> None:
    """
    TxProps: properties upsert。失敗しても承認は継続。
    
    Args:
        material_id: MaterialのID
        properties_list: 物性データのリスト [{"key": str, "value": float, "unit": str}, ...]
        submission_id: オプション（ログ用）
    
    Note:
        - 失敗しても承認は継続（ログは残す）
    """
    from utils.db import session_scope
    
    if not properties_list:
        return
    
    with session_scope() as db:
        property_keys = [prop.get('key') for prop in properties_list if prop.get('key')]
        if property_keys:
            db.query(Property).filter(
                Property.material_id == material_id,
                Property.property_name.in_(property_keys)
            ).delete(synchronize_session=False)
            db.flush()
        
        for prop in properties_list:
            prop_key = prop.get('key')
            prop_value = prop.get('value')
            prop_unit = prop.get('unit')
            if not prop_key or prop_value is None:
                continue
            try:
                new_property = Property(
                    material_id=material_id,
                    property_name=prop_key,
                    value=float(prop_value),
                    unit=prop_unit,
                )
                db.add(new_property)
            except (ValueError, TypeError) as prop_convert_error:
                logger.warning(f"[APPROVE][TxProps] Failed to convert property value for {prop_key}: {prop_convert_error}, skipping")
        
        # session_scopeが自動commit（例外時は自動rollback）
        logger.info(f"[APPROVE][TxProps] success: properties upserted for material_id={material_id} (count={len(properties_list)})")


def _txemb_update_embeddings(material_id: int, *, force: bool = False) -> None:
    """
    TxEmb: ENABLE_VECTOR_SEARCH==1 のときだけ実行。失敗しても承認は継続。
    
    Args:
        material_id: MaterialのID
        force: True なら ENABLE_VECTOR_SEARCH を無視して実行
    
    Note:
        - ENABLE_VECTOR_SEARCH=0 のときはスキップ
        - 失敗しても承認は継続（ログは残す）
    """
    import os
    from utils.db import session_scope
    
    enable_vector_search = os.getenv("ENABLE_VECTOR_SEARCH", "0") == "1"
    if not enable_vector_search and not force:
        return
    
    with session_scope() as db:
        from utils.search import update_material_embedding
        # materialを再取得（Tx1とは別セッション）
        material_for_emb = db.query(Material).filter(Material.id == material_id).first()
        if material_for_emb:
            update_material_embedding(db, material_for_emb)
            # session_scopeが自動commit（例外時は自動rollback）
            logger.info(f"[APPROVE][TxEmb] success: embedding updated for material_id={material_id}")
        else:
            logger.warning(f"[APPROVE][TxEmb] skipped: material_id={material_id} not found")


def _txsub_mark_submission_approved(submission_id: int, material_id: int, editor_note: str = None) -> None:
    """
    TxSub: submissionsを approved にし、approved_material_id を設定する。Tx1成功後にのみ呼ぶ。
    
    Args:
        submission_id: MaterialSubmissionのID
        material_id: 承認されたMaterialのID（FK整合性のため必須）
        editor_note: 承認メモ（任意）
    
    Raises:
        Exception: TxSub失敗時（呼び出し元でcatchして承認失敗扱い）
    
    Note:
        - material_idの存在確認は呼び出し元で済んでいる前提
        - status='approved', approved_material_id=material_id を設定
        - このTxは必須（失敗時は承認全体を失敗扱い）
    """
    from utils.db import session_scope, normalize_submission_key
    from datetime import datetime
    
    with session_scope() as db:
        kind, normalized_key = normalize_submission_key(submission_id)
        if kind is None or normalized_key is None:
            raise ValueError(f"Submission {submission_id} not found in TxSub")
        
        # 型ガード：kind=="id" でも normalized_key が int でなければ uuid検索にフォールバック
        if kind == "id" and isinstance(normalized_key, int):
            submission = db.query(MaterialSubmission).filter(MaterialSubmission.id == normalized_key).first()
        else:
            # kind=="uuid" または kind=="id" だが normalized_key が int でない場合
            if not isinstance(normalized_key, str):
                normalized_key = str(normalized_key)
            submission = db.query(MaterialSubmission).filter(MaterialSubmission.uuid == normalized_key).first()
            
        if not submission:
            raise ValueError(f"Submission {submission_id} not found in TxSub")
        
        # statusがpendingのままか確認
        if submission.status != "pending":
            raise ValueError(f"Submission {submission_id} status is '{submission.status}', not 'pending'. Cannot approve.")
        
        submission.status = "approved"
        submission.approved_material_id = material_id
        if editor_note and editor_note.strip():
            submission.editor_note = editor_note.strip()
        
        # session_scopeが自動commit（例外時は自動rollback）
        logger.info(f"[APPROVE][TxSub] success: submission_id={submission_id}, approved_material_id={material_id}")


# Phase 4: 旧関数は削除済み（utils/material_defaults.py に集約）
# 補完ロジックは utils.material_defaults.apply_material_defaults() のみを使用


def approve_submission(submission_id: int, editor_note: str = None, update_existing: bool = True, db=None):
    """
    投稿を承認してmaterialsテーブルに反映（トランザクション分離版）
    
    Args:
        submission_id: MaterialSubmissionのID
        editor_note: 承認メモ（任意）
        update_existing: True なら同名素材（is_deleted=0）があれば更新、False なら常に新規作成
        db: データベースセッション（Noneの場合は新規作成、使用しない）
    
    Returns:
        dict: {"ok": True/False, "material_id": int, "action": str, "error": str, "traceback": str}
    
    Note:
        トランザクションを3つに分離:
        - Tx1: materials反映（commit）- 新規作成 or 既存更新（is_deleted=0のみ）
        - Tx2: images upsert（失敗しても rollback、全体は落とさない）
        - Tx3: submissions更新（commit）
    """
    from features.approval_actions import approve_submission as _impl
    # editor_note が None の場合は空文字列に変換（approval_actions のシグネチャに合わせる）
    editor_note_str = editor_note if editor_note is not None else ""
    result = _impl(submission_id, editor_note=editor_note_str, update_existing=update_existing, db=db)
    # キャッシュクリアは呼び出し元で行う（UI依存のため）
    if result.get("ok"):
        try:
            clear_material_cache()
        except Exception:
            pass  # キャッシュクリア失敗は無視
    return result


def calculate_submission_diff(existing_material: Material, payload: dict) -> dict:
    """
    既存材料とsubmission payloadの差分を計算
    
    Args:
        existing_material: 既存のMaterialオブジェクト
        payload: submissionのpayload_json（パース済み）
    
    Returns:
        dict: {key: (old_value, new_value)} の形式で差分のみを返す
    """
    from features.approval_actions import calculate_submission_diff as _impl
    # approval_actions のシグネチャは (submission, material=None) なので、引数を変換
    # payload を submission として、existing_material を material として渡す
    return _impl(payload, material=existing_material)


def reopen_submission(submission_id: int, db=None):
    """
    却下済みsubmissionを再審査（pendingに戻す）
    
    Args:
        submission_id: MaterialSubmissionのID
        db: データベースセッション（Noneの場合は新規作成）
    
    Returns:
        dict: {"ok": True/False, "error": str, "traceback": str}
    """
    from features.approval_actions import reopen_submission as _impl
    return _impl(submission_id, db=db)


def reject_submission(submission_id: int, reject_reason: str = None, db=None):
    """
    投稿を却下
    
    Args:
        submission_id: MaterialSubmissionのID
        reject_reason: 却下理由
        db: データベースセッション（Noneの場合は新規作成）
    
    Returns:
        dict: {"ok": True/False, "error": str, "traceback": str}
    """
    from features.approval_actions import reject_submission as _impl
    # approval_actions のシグネチャは (submission_id: int, reason: str = '', db=None) なので、引数名を変換
    return _impl(submission_id, reject_reason=reject_reason, db=db)


def show_bulk_import(embedded: bool = False):
    """
    一括登録ページ
    
    Args:
        embedded: Trueの場合は埋め込みモード（ヘッダーなし、戻るボタンあり）
    """
    from utils.settings import is_admin_mode
    is_admin = is_admin_mode()
    
    if not embedded:
        is_debug = show_debug_ui()
        st.markdown(render_site_header(debug=is_debug), unsafe_allow_html=True)
        st.markdown('<h2 class="section-title">📦 一括登録</h2>', unsafe_allow_html=True)
    else:
        # 埋め込みモード：戻るボタンを表示
        if st.button("← 材料登録に戻る", key="back_to_material_form"):
            st.session_state.bulk_import_mode = False
            st.rerun()
        st.markdown('<h2 class="section-title">📦 材料一括登録</h2>', unsafe_allow_html=True)
    
    st.info("""
    **一括登録機能**
    
    CSVファイルと画像ZIPファイルを使用して材料を一括登録・更新できます。
    
    **CSVファイル形式:**
    - 必須カラム: `name_official`, `category_main`, `supplier_org`, `supplier_type`, `origin_type`, `origin_detail`, `transparency`, `hardness_qualitative`, `weight_qualitative`, `water_resistance`, `weather_resistance`, `equipment_level`, `cost_level`, `use_categories`
    - JSON配列フィールド（`use_categories`, `processing_methods`など）はカンマ区切りで記入可能
    
    **画像ファイル命名規則:**
    - primary画像: `{材料名}.jpg`（例: `真鍮.jpg`）
    - space画像: `{材料名}1.jpg`（例: `真鍮1.jpg`）
    - product画像: `{材料名}2.jpg`（例: `真鍮2.jpg`）
    - 拡張子: `.jpg`, `.jpeg`, `.png`, `.webp` に対応
    - 括弧揺れに対応（例: `真鍮（黄銅）` → `真鍮1.jpg` も検索可能）
    """)
    
    # CSVファイルとZIPファイルのアップロード
    csv_file = st.file_uploader("CSVファイル", type=['csv'], key="bulk_import_csv")
    zip_file = st.file_uploader("画像ZIPファイル", type=['zip'], key="bulk_import_zip")
    
    if csv_file and zip_file:
        st.markdown("---")
        
        # プレビューモードと実行モードの切り替え
        preview_mode = st.checkbox("プレビューモード（実行前に確認）", value=True, key="bulk_import_preview")
        
        try:
            # CSVをパース
            from utils.bulk_import import parse_csv, extract_zip_images, find_image_files, validate_csv_row
            
            csv_rows = parse_csv(csv_file)
            st.success(f"✅ CSVファイルを読み込みました（{len(csv_rows)}行）")
            
            # ZIPを展開
            image_files_dict, zip_stats = extract_zip_images(zip_file)
            st.success(f"✅ ZIPファイルを展開しました（画像: {zip_stats['images_used']}ファイル）")
            st.caption(f"📊 ZIP統計: 総数={zip_stats['zip_total']}, 除外={zip_stats['excluded']}, 画像採用={zip_stats['images_used']}")
            
            # プレビュー表示
            st.markdown("### プレビュー")
            
            preview_data = []
            for row_num, row in enumerate(csv_rows, start=2):
                name_official = row.get('name_official', '').strip()
                is_valid, errors = validate_csv_row(row, row_num)
                
                # 画像の有無を確認
                images_found = {}
                for kind in ['primary', 'space', 'product']:
                    image_match = find_image_files(name_official, image_files_dict, kind)
                    images_found[kind] = '✅' if image_match else '❌'
                
                preview_data.append({
                    '行番号': row_num,
                    '材料名': name_official,
                    '検証': '✅ OK' if is_valid else f'❌ {"; ".join(errors)}',
                    'primary': images_found['primary'],
                    'space': images_found['space'],
                    'product': images_found['product']
                })
            
            st.dataframe(preview_data, use_container_width=True)
            
            # 同名衝突チェック
            names = [row.get('name_official', '').strip() for row in csv_rows]
            duplicates = [name for name in names if names.count(name) > 1]
            if duplicates:
                st.warning(f"⚠️ CSV内に同名の材料があります: {', '.join(set(duplicates))}")
            
            # 検証結果を確認（すべての行がOKなら preview_ok = True）
            preview_ok = all(
                validate_csv_row(row, row_num)[0] 
                for row_num, row in enumerate(csv_rows, start=2)
            )
            
            # 検証がOKなら、プレビューモードの状態に関係なくボタンを表示
            if preview_ok:
                st.markdown("---")
                
                # プレビューモードの場合は警告メッセージを表示
                if preview_mode:
                    st.info("ℹ️ プレビューモード：検証はOKです。下のボタンで実行または送信できます。")
                
                # 管理者の場合は直接実行、非管理者の場合は承認待ちに送信
                if is_admin:
                    if st.button("🚀 一括登録を実行", type="primary", key="bulk_import_execute"):
                        from utils.db import session_scope
                        from utils.bulk_import import process_bulk_import, generate_report_csv
                        
                        with session_scope() as db:
                            with st.spinner("一括登録を実行中..."):
                                results = process_bulk_import(db, csv_rows, image_files_dict)
                            
                            # 結果サマリー
                            created = sum(1 for r in results if r['action'] == 'created')
                            updated = sum(1 for r in results if r['action'] == 'updated')
                            errors = sum(1 for r in results if r['status'] == 'error')
                            
                            st.success(f"""
                            **処理完了**
                            - 作成: {created}件
                            - 更新: {updated}件
                            - エラー: {errors}件
                            """)
                            
                            # エラーがある場合は表示
                            if errors > 0:
                                st.markdown("### エラー詳細")
                                error_results = [r for r in results if r['status'] == 'error']
                                for err in error_results[:10]:  # 最大10件表示
                                    st.error(f"行{err['row_num']}: {err['name_official']} - {err.get('error', 'Unknown error')}")
                            
                            # レポートCSVをダウンロード
                            report_csv = generate_report_csv(results)
                            st.download_button(
                                label="📥 結果レポートをダウンロード",
                                data=report_csv.encode('utf-8-sig'),  # BOM付きUTF-8
                                file_name=f"bulk_import_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                mime="text/csv",
                                key="bulk_import_report"
                            )
                        # 例外時はsession_scopeが自動rollback
                else:
                    # 非管理者の場合は承認待ちに送信
                    submitted_by = st.text_input(
                        "投稿者情報（任意）",
                        placeholder="ニックネーム / メールアドレス",
                        key="bulk_import_submitted_by"
                    )
                    
                    if st.button("📤 承認待ちに送信", type="primary", key="bulk_import_submit"):
                        from utils.db import session_scope
                        from utils.bulk_import import create_bulk_submissions, generate_report_csv
                        
                        with session_scope() as db:
                            with st.spinner("承認待ちに送信中..."):
                                results = create_bulk_submissions(
                                    db, csv_rows, image_files_dict,
                                    submitted_by=submitted_by.strip() if submitted_by else None
                                )
                            
                            # 結果サマリー
                            submitted = sum(1 for r in results if r['status'] == 'success')
                            errors = sum(1 for r in results if r['status'] == 'error')
                            
                            st.success(f"""
                            **送信完了**
                            - 承認待ちに送信: {submitted}件
                            - エラー: {errors}件
                            
                            ⚠️ 管理者が承認すると材料が公開されます。
                            """)
                            
                            # エラーがある場合は表示
                            if errors > 0:
                                st.markdown("### エラー詳細")
                                error_results = [r for r in results if r['status'] == 'error']
                                for err in error_results[:10]:  # 最大10件表示
                                    st.error(f"行{err['row_num']}: {err['name_official']} - {err.get('error', 'Unknown error')}")
                            
                            # 送信されたSubmission IDを表示
                            if submitted > 0:
                                st.markdown("### 送信された投稿ID")
                                submission_ids = [r['submission_id'] for r in results if r['submission_id']]
                                st.info(f"投稿ID: {', '.join(map(str, submission_ids[:10]))}" + (f" 他{submitted-10}件" if submitted > 10 else ""))
                            
                            # レポートCSVをダウンロード
                            report_csv = generate_report_csv(results)
                            st.download_button(
                                label="📥 結果レポートをダウンロード",
                                data=report_csv.encode('utf-8-sig'),  # BOM付きUTF-8
                                file_name=f"bulk_submission_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                mime="text/csv",
                                key="bulk_submission_report"
                            )
                        
                        # 例外時はsession_scopeが自動rollback
            else:
                # 検証エラーがある場合は警告を表示
                st.markdown("---")
                st.error("❌ CSVファイルに検証エラーがあります。上記のプレビューを確認して修正してください。")
        
        except Exception as e:
            st.error(f"ファイル処理中にエラーが発生しました: {e}")
            if is_debug:
                import traceback
                st.code(traceback.format_exc(), language="python")
            logger.exception(f"Bulk import file processing error: {e}")


def show_submission_status():
    """投稿ステータス確認ページ（投稿者用、エラーハンドリング強化）"""
    try:
        is_debug = show_debug_ui()
        st.markdown(render_site_header(debug=is_debug), unsafe_allow_html=True)
        st.markdown('<h2 class="section-title">📋 投稿ステータス確認</h2>', unsafe_allow_html=True)
        st.info("💡 投稿時に表示された投稿IDまたはUUIDを入力してください。")
        
        submission_id_input = st.text_input(
            "投稿ID または UUID",
            placeholder="例: 1 または abc123-def456-...",
            key="submission_status_id"
        )
        
        if submission_id_input and submission_id_input.strip():
            from utils.db import get_session, normalize_submission_key
            with get_session() as db:
                kind, normalized_key = normalize_submission_key(submission_id_input)
                if kind is None or normalized_key is None:
                    submission = None
                # 型ガード：kind=="id" でも normalized_key が int でなければ uuid検索にフォールバック
                elif kind == "id" and isinstance(normalized_key, int):
                    submission = db.query(MaterialSubmission).filter(MaterialSubmission.id == normalized_key).first()
                else:
                    # kind=="uuid" または kind=="id" だが normalized_key が int でない場合
                    if not isinstance(normalized_key, str):
                        normalized_key = str(normalized_key)
                    submission = db.query(MaterialSubmission).filter(MaterialSubmission.uuid == normalized_key).first()
                
                if submission:
                    st.markdown("---")
                    st.markdown("### 📄 投稿情報")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**投稿ID**: {submission.id}")
                        st.write(f"**UUID**: {submission.uuid}")
                        st.write(f"**投稿者**: {submission.submitted_by or '匿名'}")
                        st.write(f"**投稿日時**: {submission.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    with col2:
                        status_icon = {
                            "pending": "⏳",
                            "approved": "✅",
                            "rejected": "❌"
                        }.get(submission.status, "📄")
                        
                        status_color = {
                            "pending": "#FFA500",
                            "approved": "#28A745",
                            "rejected": "#DC3545"
                        }.get(submission.status, "#666")
                        
                        st.markdown(f"**ステータス**: <span style='color: {status_color}; font-size: 1.2em'>{status_icon} {submission.status}</span>", unsafe_allow_html=True)
                        st.write(f"**更新日時**: {submission.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
                        if submission.approved_material_id:
                            st.write(f"**承認済み材料ID**: {submission.approved_material_id}")
                    
                    # payload_jsonをパースして表示
                    try:
                        from utils.db import load_payload_json
                        payload = load_payload_json(submission.payload_json)
                        if payload:
                            st.markdown("---")
                            st.markdown("### 📝 投稿内容")
                            st.write(f"**材料名（正式）**: {payload.get('name_official', 'N/A')}")
                            st.write(f"**カテゴリ**: {payload.get('category_main', 'N/A')}")
                            st.write(f"**供給元**: {payload.get('supplier_org', 'N/A')}")
                    except:
                        pass
                    
                    # ステータス別のメッセージ
                    if submission.status == "pending":
                        st.info("⏳ 承認待ちです。管理者の承認をお待ちください。")
                    elif submission.status == "approved":
                        st.success("✅ 承認されました！")
                        if submission.approved_material_id:
                            material = db.query(Material).filter(Material.id == submission.approved_material_id).first()
                            if material:
                                st.info(f"📝 材料名: {material.name_official} (ID: {material.id})")
                                st.info(f"📢 公開状態: {'公開' if material.is_published == 1 else '非公開（管理者が公開するまでお待ちください）'}")
                    elif submission.status == "rejected":
                        st.warning("❌ 却下されました。")
                        if submission.reject_reason:
                            st.markdown("### 却下理由")
                            st.error(submission.reject_reason)
                    
                    # 編集者メモ（あれば）
                    if submission.editor_note:
                        st.markdown("---")
                        st.markdown("### 📝 編集者メモ")
                        st.info(submission.editor_note)
                else:
                    st.error("❌ 投稿が見つかりませんでした。投稿IDまたはUUIDを確認してください。")
                # get_session()が自動でcloseするため、finallyは不要
        else:
            st.info("💡 投稿IDまたはUUIDを入力してください。")
    except Exception as e:
        logger.exception(f"[SUBMISSION STATUS] Error: {e}")
        st.error(f"❌ 投稿ステータス確認中にエラーが発生しました: {e}")
        if show_debug_ui():
            import traceback
            st.code("".join(traceback.format_exception(type(e), e, e.__traceback__)), language="python")


def show_material_cards():
    """素材カード表示ページ（3タブ構造、エラーハンドリング強化）"""
    try:
        is_debug = show_debug_ui()
        st.markdown(render_site_header(debug=is_debug), unsafe_allow_html=True)
        st.markdown('<h2 class="section-title">素材カード</h2>', unsafe_allow_html=True)
        
        # 管理者表示フラグを取得
        include_unpublished = st.session_state.get("include_unpublished", False)
        
        # ページングで材料を取得（軽量クエリ、limit=100）
        from utils.settings import get_database_url
        db_url = get_database_url()
        materials_dicts = fetch_materials_page_cached(
            db_url=db_url,
            include_unpublished=include_unpublished,
            include_deleted=False,
            limit=100,
            offset=0
        )
        
        if not materials_dicts:
            st.info("材料が登録されていません。")
            return
        
        # dict から Material 風のオブジェクトを作成（後方互換のため）
        class MaterialProxy:
            def __init__(self, d):
                self.id = d.get("id")
                self.name_official = d.get("name_official")
                self.name = d.get("name")
                self.category_main = d.get("category_main")
                self.category = d.get("category")
        
        materials = [MaterialProxy(d) for d in materials_dicts]
        
        material_options = {f"{m.name_official or m.name or '名称不明'} (ID: {m.id})": m.id for m in materials}
        selected_material_name = st.selectbox("材料を選択", list(material_options.keys()))
        material_id = material_options[selected_material_name]
        
        # properties を一括取得（N+1問題を回避）
        material_ids = [m.id for m in materials]
        properties_dict = {}  # {material_id: [Property, ...]}
        if material_ids:
            from utils.db import get_session
            from sqlalchemy import select
            try:
                with get_session() as db:
                    properties_list = db.execute(
                        select(Property)
                        .where(Property.material_id.in_(material_ids))
                    ).scalars().all()
                    for prop in properties_list:
                        if prop.material_id not in properties_dict:
                            properties_dict[prop.material_id] = []
                        properties_dict[prop.material_id].append(prop)
            except Exception as prop_e:
                logger.warning(f"[CARDS] Failed to fetch properties: {prop_e}")
            # 例外時はget_sessionが自動close
        
        material = get_material_by_id(material_id)
        
        if material:
            # 材料名と基本情報
            st.markdown("---")
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown(f"## {material.name_official or material.name}")
                if material.category_main or material.category:
                    st.markdown(f"**カテゴリ**: {material.category_main or material.category}")
                if material.description:
                    st.markdown(f"**説明**: {material.description}")
        
            with col2:
                # QRコードをPNG bytesとして生成（TypeErrorを防ぐ）
                from utils.qr import generate_qr_png_bytes
                qr_bytes = generate_qr_png_bytes(f"Material ID: {material.id}")
                if qr_bytes:
                    st.image(qr_bytes, caption="QRコード", width=150)
                else:
                    st.caption("QRコード生成に失敗しました")
            
            # 3タブ構造で詳細表示
            show_material_detail_tabs(material)
            
            # カードのHTML生成と表示（印刷用）
            st.markdown("---")
            st.markdown("### 素材カード（印刷用）")
            
            # Lazy import: card_generatorとschemas（起動時クラッシュを避けるため）
            card_html = None
            error_message = None
            
            # グローバル変数の宣言（tryブロックの外で宣言）
            global _card_generator_import_error, _card_generator_import_traceback
            
            try:
                # 使用する時だけimportする（lazy import）
                from schemas import MaterialCardPayload, MaterialCard, PropertyDTO
                from card_generator import generate_material_card
                # 成功時はエラー情報をクリア
                _card_generator_import_error = None
                _card_generator_import_traceback = None
                # 主要画像を取得（安全に）
                primary_image = None
                primary_image_path = None
                primary_image_type = None
                primary_image_description = None
                
                # 画像情報の取得（安全モード対応）
                # 注意: 安全モードでは material.images は noload されているため空のリストになる
                # そのため、hasattr と len チェックで安全に処理
                primary_image = None
                primary_image_path = None
                primary_image_type = None
                primary_image_description = None
                
                try:
                    # material.images にアクセス（安全モードでは空のリスト）
                    if hasattr(material, 'images') and material.images and len(material.images) > 0:
                        primary_image = material.images[0]
                        primary_image_path = getattr(primary_image, 'file_path', None) if primary_image else None
                        primary_image_type = getattr(primary_image, 'image_type', None) if primary_image else None
                        primary_image_description = getattr(primary_image, 'description', None) if primary_image else None
                except Exception as img_e:
                    # 安全モードやスキーマ不整合時は material.images が空またはアクセス不可
                    # エラーは握り潰して続行（画像なしでカード生成）
                    if os.getenv("DEBUG", "0") == "1":
                        print(f"画像取得エラー（続行、安全モードの可能性）: {img_e}")
            
                # 物性データをDTOに変換（一括取得した properties_dict を使用）
                properties_dto = []
                try:
                    # 一括取得した properties_dict から取得（N+1問題を回避）
                    material_properties = properties_dict.get(material.id, [])
                    # 表示するキー配列を定義（density, tensile_strength, yield_strength のみ）
                    display_keys = ["density", "tensile_strength", "yield_strength"]
                    display_labels = {
                        "density": "密度",
                        "tensile_strength": "引張強度",
                        "yield_strength": "降伏強度"
                    }
                    
                    for prop in material_properties:
                        prop_name = getattr(prop, 'property_name', None)
                        # 表示対象のキーのみ処理
                        if prop_name in display_keys:
                            try:
                                prop_value = getattr(prop, 'value', None)
                                prop_unit = getattr(prop, 'unit', None)
                                prop_condition = getattr(prop, 'measurement_condition', None)
                                
                                # 表示ラベルを使用（日本語化）
                                display_name = display_labels.get(prop_name, prop_name)
                                
                                prop_dto = PropertyDTO(
                                    property_name=display_name,  # 日本語ラベルを使用
                                    value=float(prop_value) if prop_value is not None else None,
                                    unit=str(prop_unit) if prop_unit else None,
                                    measurement_condition=str(prop_condition) if prop_condition else None
                                )
                                properties_dto.append(prop_dto)
                            except Exception as prop_e:
                                # 個別の物性データでエラーが発生しても続行
                                print(f"物性データ変換エラー（スキップ）: {prop_e}")
                                continue
                except Exception as props_e:
                    print(f"物性データ取得エラー（続行）: {props_e}")
                
                # DTOを作成（欠損はNone/[]に埋める）
                material_name = material.name or getattr(material, 'name_official', None) or "名称不明"
                material_name_official = getattr(material, 'name_official', None)
                material_category = material.category or getattr(material, 'category_main', None)
                material_category_main = getattr(material, 'category_main', None)
                material_description = getattr(material, 'description', None)
                
                card_payload = MaterialCardPayload(
                    id=int(material.id),
                    name=str(material_name),
                    name_official=str(material_name_official) if material_name_official else None,
                    category=str(material_category) if material_category else None,
                    category_main=str(material_category_main) if material_category_main else None,
                    description=str(material_description) if material_description else None,
                    properties=properties_dto,
                    primary_image_path=str(primary_image_path) if primary_image_path else None,
                    primary_image_type=str(primary_image_type) if primary_image_type else None,
                    primary_image_description=str(primary_image_description) if primary_image_description else None
                )
                
                card_data = MaterialCard(payload=card_payload)
                # Materialオブジェクトを直接渡せるようにする（画像URL取得のため）
                # 重要: material_objを必ず設定する（card_generatorで画像取得に必要）
                if material is None:
                    st.warning(f"⚠️ material is None for card generation (ID: {card_payload.id})")
                else:
                    card_data.material_obj = material
                card_html = generate_material_card(card_data)
            
            except Exception as e:
                # ImportError/KeyError/その他すべての例外をキャッチ（ホームは必ず表示される）
                error_message = str(e)
                import traceback
                error_traceback = traceback.format_exc()
                # グローバル変数に記録（render_debug_sidebar_early で表示される）
                _card_generator_import_error = error_message
                _card_generator_import_traceback = error_traceback
                print(f"カード生成エラー: {error_message}")
                print(error_traceback)
                
                # カード画面にエラーを表示（ホームには出さない）
                st.error(f"⚠️ カード生成中にエラーが発生しました: {error_message}")
                if show_debug_ui():
                    with st.expander("詳細エラー情報", expanded=False):
                        st.code(error_traceback, language="python")
                
                # フォールバック：最低限の情報だけのカード
                try:
                    material_name = material.name or getattr(material, 'name_official', None) or 'Unknown'
                    material_desc = material.description or 'No description'
                    card_html = f"""
                    <html>
                    <head>
                        <meta charset="utf-8">
                        <title>Material Card - {material_name}</title>
                        <style>
                            body {{ font-family: Arial, sans-serif; padding: 20px; }}
                            h1 {{ color: #333; }}
                            p {{ color: #666; }}
                        </style>
                    </head>
                    <body>
                        <h1>{material_name}</h1>
                        <p><strong>ID:</strong> {material.id}</p>
                        <p><strong>説明:</strong> {material_desc}</p>
                        <p style="color: #999; font-size: 12px; margin-top: 20px;">※ 詳細なカード生成に失敗しました。基本情報のみ表示しています。</p>
                    </body>
                    </html>
                    """
                except Exception as fallback_e:
                    # フォールバックも失敗した場合
                    card_html = f"""
                    <html>
                    <head>
                        <meta charset="utf-8">
                        <title>Material Card - Error</title>
                    </head>
                    <body>
                        <h1>カード生成エラー</h1>
                        <p>材料ID: {material.id if material else 'N/A'}</p>
                        <p>エラー: {str(fallback_e)}</p>
                    </body>
                    </html>
                    """
            
            # HTMLを表示（st.components.v1.html を優先、失敗時は st.markdown にフォールバック）
            if card_html:
                try:
                    # st.components.v1.html でHTMLをレンダリング（推奨）
                    st.components.v1.html(card_html, height=800, scrolling=True)
                except Exception as html_error:
                    # st.components.v1.html が失敗した場合、st.markdown にフォールバック
                    # unsafe_allow_html=True を必ず指定してHTMLをレンダリング
                    logger.warning(f"[CARD] st.components.v1.html failed, fallback to st.markdown: {html_error}")
                    st.markdown(card_html, unsafe_allow_html=True)
            else:
                # エラーが発生した場合、フォールバックカードが表示されない場合
                st.warning("⚠️ カード生成に失敗しました。上記のエラーメッセージを確認してください。")
            
            # ダウンロードボタン
            st.download_button(
                label="📥 カードをHTMLとしてダウンロード",
                data=card_html,
                file_name=f"material_card_{material.id}.html",
                mime="text/html",
                use_container_width=True
            )
    except Exception as e:
        logger.exception(f"[MATERIAL CARDS] Error: {e}")
        st.error(f"❌ 素材カード表示中にエラーが発生しました: {e}")
        if show_debug_ui():
            import traceback
            st.code("".join(traceback.format_exception(type(e), e, e.__traceback__)), language="python")


# --- すべての関数定義（main含む）が終わった一番最後に置く ---
# Streamlit 実行では __name__ ガードで事故ることがあるので、ガード無しで呼ぶ
run_app_entrypoint()
