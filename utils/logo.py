"""
ロゴ表示ユーティリティ
SVGロゴをHTML inline SVGとして描画する
Unicode正規化（NFKC）でファイル名の表記ゆれに対応
"""
from pathlib import Path
from typing import Optional, Dict, Any
import streamlit as st
import unicodedata
import os
import subprocess


def get_git_sha() -> str:
    """
    Gitの短縮SHAを取得（失敗時は'unknown'を返す）
    
    Returns:
        Gitの短縮SHA（例: 'a1b2c3d'）、取得できない場合は'unknown'
    
    Note:
        Cloud環境でgitが使えない場合があるため、例外は握りつぶす
    """
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        return sha
    except (subprocess.CalledProcessError, FileNotFoundError, Exception):
        return "unknown"


def get_project_root() -> Path:
    """
    プロジェクトルートを堅牢に解決（Cloud前提）
    app.pyの位置から上に辿って「logo/」「static/」「写真/」の存在でproject_rootを決める
    見つからなければ fallback で repoルート推定（app.pyの親）
    
    Returns:
        プロジェクトルートのPath
    """
    # app.pyの位置を基準に（utils/logo.pyから見て1階層上）
    # utils/logo.py -> utils/ -> プロジェクトルート
    current = Path(__file__).resolve().parent.parent
    
    # 上方向に辿ってlogo/、static/、写真/の存在を確認
    while current != current.parent:  # ルートディレクトリに到達するまで
        logo_dir = current / "logo"
        static_dir = current / "static"
        photo_dir = current / "写真"
        
        # logo/、static/、写真/のいずれかが存在すればproject_rootとみなす
        if (logo_dir.exists() and logo_dir.is_dir()) or \
           (static_dir.exists() and static_dir.is_dir()) or \
           (photo_dir.exists() and photo_dir.is_dir()):
            return current
        
        current = current.parent
    
    # 見つからなければ fallback で repoルート推定（app.pyの親）
    return Path(__file__).resolve().parent.parent


def get_logo_paths() -> Dict[str, Path]:
    """
    ロゴファイルのパスを取得（Unicode正規化対応）
    プロジェクトルート基準で確実に解決
    
    Returns:
        dict: {"type_logo": Path, "mark": Path}
        ファイルが見つからない場合は、存在しないPathを返す（代替ロゴ生成はしない）
    """
    # プロジェクトルートを取得（堅牢な解決方法を使用）
    project_root = get_project_root()
    
    # ロゴディレクトリ（必ず logo/ を使用）
    logo_dir = project_root / "logo"
    
    # 期待するファイル名（NFKC正規化済み）
    # 必ず logo/タイプロゴ.svg と logo/ロゴマーク.svg を使用
    expected_names = {
        "type_logo": unicodedata.normalize("NFKC", "タイプロゴ.svg"),
        "mark": unicodedata.normalize("NFKC", "ロゴマーク.svg")
    }
    
    # 結果辞書（初期値は正規化されたファイル名のパス）
    result = {
        "type_logo": logo_dir / expected_names["type_logo"],
        "mark": logo_dir / expected_names["mark"]
    }
    
    # logo_dirが存在する場合、実ファイル一覧を読み込んで正規化マッチング
    if logo_dir.exists() and logo_dir.is_dir():
        # 実ファイル一覧を取得
        actual_files = {}
        for file_path in logo_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() == ".svg":
                # NFKC正規化したファイル名をキーに
                normalized_name = unicodedata.normalize("NFKC", file_path.name)
                actual_files[normalized_name] = file_path
        
        # 期待するファイル名とマッチング
        for key, expected_name in expected_names.items():
            if expected_name in actual_files:
                result[key] = actual_files[expected_name]
    
    return result


@st.cache_data
def read_svg(path: Path, mtime: float) -> Optional[str]:
    """
    SVGファイルをUTF-8で読み込む（キャッシュキーにmtimeを含める）
    
    Args:
        path: SVGファイルのパス
        mtime: ファイルの更新時刻（stat().st_mtime）
    
    Returns:
        SVGコンテンツ（文字列）、見つからなければNone
    """
    try:
        if path.exists() and path.is_file():
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        print(f"Warning: Failed to read SVG {path}: {e}")
    return None


def render_svg_inline_html(svg: str, height_px: int, class_name: str = "") -> str:
    """
    SVGをHTML inline SVGとして描画するためのHTMLを生成（HTML文字列を返す）
    サイズはinline styleで確実に指定（CSSに依存しない）
    
    Args:
        svg: SVGコンテンツ（文字列、<svg>タグを含む可能性がある）
        height_px: 高さ（ピクセル）- この値が確実に適用される
        class_name: CSSクラス名（任意、余白や整列用）
    
    Returns:
        HTML文字列
    """
    # SVGが既に<svg>タグを含んでいる場合は、そのまま使用
    if "<svg" in svg.lower():
        # 既存の<svg>タグを使用し、style属性を追加/更新
        import re
        # style属性を追加または更新（既存のheight指定を上書き）
        if re.search(r'style\s*=', svg, re.IGNORECASE):
            # 既存のstyle属性からheightを削除してから追加（確実に指定値を適用）
            height_pattern = r'height\s*:\s*[^;]+;?'
            def replace_style(m):
                old_style = m.group(1)
                # heightを削除
                cleaned_style = re.sub(height_pattern, "", old_style, flags=re.IGNORECASE).strip()
                # セミコロンで区切って整理
                if cleaned_style and not cleaned_style.endswith(';'):
                    cleaned_style += ';'
                return f'style="{cleaned_style} height: {height_px}px !important; width: auto; max-width: 100%; vertical-align: middle;"'
            svg = re.sub(
                r'style\s*=\s*["\']([^"\']*)["\']',
                replace_style,
                svg,
                flags=re.IGNORECASE
            )
        else:
            # style属性がない場合は追加
            svg = re.sub(
                r'<svg([^>]*)>',
                f'<svg\\1 style="height: {height_px}px !important; width: auto; max-width: 100%; vertical-align: middle;">',
                svg,
                flags=re.IGNORECASE
            )
        
        class_attr = f' class="{class_name}"' if class_name else ""
        return f'<div{class_attr} style="display: inline-block; line-height: 0; margin: 0; padding: 0;">{svg}</div>'
    else:
        # <svg>タグがない場合は追加（通常は発生しない）
        class_attr = f' class="{class_name}"' if class_name else ""
        return f"""
        <div{class_attr} style="display: inline-block; line-height: 0; margin: 0; padding: 0;">
            <svg style="height: {height_px}px !important; width: auto; max-width: 100%; vertical-align: middle;" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">
                {svg}
            </svg>
        </div>
        """


def render_svg_inline(svg: str, height_px: int, class_name: str = "") -> str:
    """
    SVGをHTML inline SVGとして描画するためのHTMLを生成（後方互換性のため残す）
    
    Args:
        svg: SVGコンテンツ（文字列、<svg>タグを含む可能性がある）
        height_px: 高さ（ピクセル）
        class_name: CSSクラス名（任意）
    
    Returns:
        HTML文字列
    """
    return render_svg_inline_html(svg, height_px, class_name)


def render_svg_component(svg: str, height_px: int, class_name: str = ""):
    """
    SVGをst.components.v1.htmlで描画（Cloud環境で確実に表示される）
    
    Args:
        svg: SVGコンテンツ（文字列、<svg>タグを含む可能性がある）
        height_px: 高さ（ピクセル）
        class_name: CSSクラス名（任意、余白や整列用）
    """
    import streamlit.components.v1 as components
    
    # HTML文字列を生成（wrapper div付き、余白なし）
    html_content = render_svg_inline_html(svg, height_px, class_name)
    
    # iframe内で表示されるので、wrapper divを付けて余白が出ないようにする
    # heightは height_px + 10 程度で固定し、scrolling=False
    iframe_height = height_px + 10
    
    # 完全なHTMLドキュメントとして生成（余白なし）
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                margin: 0;
                padding: 0;
                display: flex;
                align-items: center;
                justify-content: flex-start;
            }}
            .svg-wrapper {{
                margin: 0;
                padding: 0;
                line-height: 0;
            }}
        </style>
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """
    
    components.html(full_html, height=iframe_height, scrolling=False)
    """
    SVGをHTML inline SVGとして描画するためのHTMLを生成
    サイズはinline styleで確実に指定（CSSに依存しない）
    
    Args:
        svg: SVGコンテンツ（文字列、<svg>タグを含む可能性がある）
        height_px: 高さ（ピクセル）- この値が確実に適用される
        class_name: CSSクラス名（任意、余白や整列用）
    
    Returns:
        HTML文字列
    """
    # SVGが既に<svg>タグを含んでいる場合は、そのまま使用
    if "<svg" in svg.lower():
        # 既存の<svg>タグを使用し、style属性を追加/更新
        import re
        # style属性を追加または更新（既存のheight指定を上書き）
        if re.search(r'style\s*=', svg, re.IGNORECASE):
            # 既存のstyle属性からheightを削除してから追加（確実に指定値を適用）
            height_pattern = r'height\s*:\s*[^;]+;?'
            def replace_style(m):
                old_style = m.group(1)
                # heightを削除
                cleaned_style = re.sub(height_pattern, "", old_style, flags=re.IGNORECASE).strip()
                # セミコロンで区切って整理
                if cleaned_style and not cleaned_style.endswith(';'):
                    cleaned_style += ';'
                return f'style="{cleaned_style} height: {height_px}px !important; width: auto; max-width: 100%; vertical-align: middle;"'
            svg = re.sub(
                r'style\s*=\s*["\']([^"\']*)["\']',
                replace_style,
                svg,
                flags=re.IGNORECASE
            )
        else:
            # style属性がない場合は追加
            svg = re.sub(
                r'<svg([^>]*)>',
                f'<svg\\1 style="height: {height_px}px !important; width: auto; max-width: 100%; vertical-align: middle;">',
                svg,
                flags=re.IGNORECASE
            )
        
        class_attr = f' class="{class_name}"' if class_name else ""
        return f'<div{class_attr} style="display: inline-block; line-height: 0;">{svg}</div>'
    else:
        # <svg>タグがない場合は追加（通常は発生しない）
        class_attr = f' class="{class_name}"' if class_name else ""
        return f"""
        <div{class_attr} style="display: inline-block; line-height: 0;">
            <svg style="height: {height_px}px !important; width: auto; max-width: 100%; vertical-align: middle;" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">
                {svg}
            </svg>
        </div>
        """


def render_type_logo(height_px: int = 36, fallback_text: str = "Material Map", debug: bool = False, use_component: bool = True) -> Optional[str]:
    """
    タイプロゴを描画（全ページ共通のヘッダー用）
    
    Args:
        height_px: ロゴの高さ（デフォルト36px）
        fallback_text: SVGが見つからない場合のフォールバックテキスト
        debug: デバッグ情報を表示するか
        use_component: Trueの場合はst.components.v1.htmlを使用、Falseの場合はHTML文字列を返す
    
    Returns:
        use_component=Trueの場合はNone（直接描画）、Falseの場合はHTML文字列
    """
    paths = get_logo_paths()
    type_logo_path = paths["type_logo"]
    
    # ファイルの存在確認とmtime取得
    if type_logo_path.exists() and type_logo_path.is_file():
        mtime = type_logo_path.stat().st_mtime
        svg_content = read_svg(type_logo_path, mtime)
        
        if svg_content:
            if use_component:
                # st.components.v1.htmlで直接描画
                render_svg_component(svg_content, height_px, "site-logo")
                return None
            else:
                # HTML文字列を返す（後方互換性）
                return render_svg_inline_html(svg_content, height_px, "site-logo")
    
    # フォールバック：テキスト表示
    if debug:
        st.warning(f"⚠️ タイプロゴが見つかりません: {type_logo_path}")
        with st.expander("🔍 デバッグ情報", expanded=False):
            st.write(f"**探したパス**: `{type_logo_path}`")
            st.write(f"**存在**: {type_logo_path.exists()}")
            if type_logo_path.parent.exists():
                st.write(f"**logoディレクトリ内のファイル**:")
                logo_dir = type_logo_path.parent
                svg_files = [f.name for f in logo_dir.iterdir() if f.is_file() and f.suffix.lower() == ".svg"]
                for svg_file in svg_files[:20]:  # 先頭20件
                    st.write(f"- {svg_file}")
    
    if use_component:
        # フォールバックテキストもst.components.v1.htmlで表示
        import streamlit.components.v1 as components
        fallback_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    margin: 0;
                    padding: 0;
                    display: flex;
                    align-items: center;
                    justify-content: flex-start;
                }}
            </style>
        </head>
        <body>
            <div class="site-logo-fallback" style="font-size: {height_px}px; font-weight: 600; color: #1a1a1a;">{fallback_text}</div>
        </body>
        </html>
        """
        components.html(fallback_html, height=height_px + 10, scrolling=False)
        return None
    
    return f'<div class="site-logo-fallback" style="font-size: {height_px}px; font-weight: 600; color: #1a1a1a;">{fallback_text}</div>'


def render_logo_mark(height_px: int = 72, debug: bool = False, use_component: bool = True) -> Optional[str]:
    """
    ロゴマークを描画（ホーム画面専用）
    
    Args:
        height_px: ロゴの高さ（デフォルト72px、3/4サイズ）
        debug: デバッグ情報を表示するか
        use_component: Trueの場合はst.components.v1.htmlを使用、Falseの場合はHTML文字列を返す
    
    Returns:
        use_component=Trueの場合はNone（直接描画）、Falseの場合はHTML文字列（SVGが見つからない場合はNone）
    """
    paths = get_logo_paths()
    mark_path = paths["mark"]
    
    # ファイルの存在確認とmtime取得
    if mark_path.exists() and mark_path.is_file():
        mtime = mark_path.stat().st_mtime
        svg_content = read_svg(mark_path, mtime)
        
        if svg_content:
            if use_component:
                # st.components.v1.htmlで直接描画
                render_svg_component(svg_content, height_px, "site-mark")
                return None
            else:
                # HTML文字列を返す（後方互換性）
                return render_svg_inline_html(svg_content, height_px, "site-mark")
    
    # 見つからない場合（代替ロゴ生成はしない、空表示でOK）
    if debug:
        paths = get_logo_paths()
        project_root = get_project_root()
        logo_dir = project_root / "logo"
        
        st.sidebar.warning("⚠️ ロゴマークが見つかりません")
        with st.sidebar.expander("🔍 デバッグ情報", expanded=False):
            st.write(f"**プロジェクトルート**: `{project_root}`")
            st.write(f"**logoディレクトリ**: `{logo_dir}`")
            st.write(f"**存在**: {logo_dir.exists()}")
            st.write(f"**探したパス**: `{mark_path}`")
            st.write(f"**ファイル存在**: {mark_path.exists()}")
            if mark_path.exists():
                st.write(f"**ファイルサイズ**: {mark_path.stat().st_size} bytes")
                st.write(f"**更新時刻**: {mark_path.stat().st_mtime}")
            
            if logo_dir.exists() and logo_dir.is_dir():
                st.write(f"**logoディレクトリ内のファイル**:")
                svg_files = [f for f in logo_dir.iterdir() if f.is_file() and f.suffix.lower() == ".svg"]
                if svg_files:
                    for svg_file in svg_files[:20]:  # 先頭20件
                        st.write(f"- {svg_file.name}")
                else:
                    st.write("（SVGファイルが見つかりません）")
            
            st.write(f"**期待するファイル名**: `{unicodedata.normalize('NFKC', 'ロゴマーク.svg')}`")
    
    return None


def render_site_header(subtitle: Optional[str] = None, debug: bool = False, use_component: bool = True) -> Optional[str]:
    """
    サイトヘッダーを描画（タイプロゴ + サブタイトル）
    サブタイトルはタイプロゴの下に配置（縦並び）
    
    Args:
        subtitle: サブタイトル（任意、例：「素材の可能性を探索するデータベース」）
        debug: デバッグ情報を表示するか
        use_component: Trueの場合はst.components.v1.htmlを使用、Falseの場合はHTML文字列を返す
    
    Returns:
        use_component=Trueの場合はNone（直接描画）、Falseの場合はHTML文字列
    """
    if use_component:
        # st.components.v1.htmlで直接描画
        import streamlit.components.v1 as components
        
        # タイプロゴを描画
        render_type_logo(height_px=36, debug=debug, use_component=True)
        
        # サブタイトルを表示
        if subtitle:
            st.markdown(f'<div class="site-subtitle" style="font-size: 14px; color: #666; margin-top: 8px;">{subtitle}</div>', unsafe_allow_html=True)
        
        return None
    else:
        # HTML文字列を返す（後方互換性）
        logo_html = render_type_logo(height_px=36, debug=debug, use_component=False)
        
        if subtitle:
            return f"""
            <div class="site-header">
                <div class="site-title-block">
                    {logo_html}
                    <div class="site-subtitle">
                        {subtitle}
                    </div>
                </div>
            </div>
            """
        else:
            return f"""
            <div class="site-header">
                <div class="site-title-block">
                    {logo_html}
                </div>
            </div>
            """


def get_logo_debug_info() -> Dict[str, Any]:
    """
    ロゴファイルのデバッグ情報を辞書形式で返す（DEBUG表示用）
    
    Returns:
        デバッグ情報の辞書
    """
    project_root = get_project_root()
    logo_dir = project_root / "logo"
    
    # 期待するファイル名（NFKC正規化済み）
    expected_names = {
        "type_logo": unicodedata.normalize("NFKC", "タイプロゴ.svg"),
        "mark": unicodedata.normalize("NFKC", "ロゴマーク.svg")
    }
    
    # logoディレクトリ内のSVGファイル一覧
    svg_files = []
    if logo_dir.exists() and logo_dir.is_dir():
        svg_files = [
            {
                "name": f.name,
                "normalized": unicodedata.normalize("NFKC", f.name),
                "exists": f.exists(),
                "size": f.stat().st_size if f.exists() else 0,
                "mtime": f.stat().st_mtime if f.exists() else 0,
            }
            for f in logo_dir.iterdir()
            if f.is_file() and f.suffix.lower() == ".svg"
        ][:20]  # 先頭20件
    
    # 解決されたパス
    paths = get_logo_paths()
    resolved_paths = {}
    for key, path in paths.items():
        resolved_paths[key] = {
            "path": str(path),
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() else 0,
            "mtime": path.stat().st_mtime if path.exists() else 0,
        }
    
    return {
        "project_root": str(project_root),
        "logo_dir": str(logo_dir),
        "logo_dir_exists": logo_dir.exists(),
        "expected_names": expected_names,
        "svg_files_in_logo_dir": svg_files,
        "resolved_paths": resolved_paths,
    }


def show_logo_debug_info():
    """
    ロゴファイルのデバッグ情報を表示（管理者デバッグ時のみ）
    """
    try:
        from utils.settings import show_debug_ui
        if not show_debug_ui():
            return
    except Exception:
        if os.getenv("DEBUG", "0") != "1":
            return
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔍 ロゴファイル実在確認")
    
    debug_info = get_logo_debug_info()
    
    st.sidebar.write(f"**プロジェクトルート**: `{debug_info['project_root']}`")
    st.sidebar.write(f"**logoディレクトリ**: `{debug_info['logo_dir']}`")
    st.sidebar.write(f"**存在**: {debug_info['logo_dir_exists']}")
    
    if debug_info['logo_dir_exists']:
        st.sidebar.write(f"**検出したSVGファイル数**: {len(debug_info['svg_files_in_logo_dir'])}")
        
        with st.sidebar.expander("検出したファイル一覧（先頭20件）", expanded=False):
            for svg_file in debug_info['svg_files_in_logo_dir']:
                st.write(f"- `{svg_file['name']}` (正規化: `{svg_file['normalized']}`)")
                if svg_file['exists']:
                    st.write(f"  - サイズ: {svg_file['size']} bytes")
                    st.write(f"  - mtime: {svg_file['mtime']}")
        
        st.sidebar.markdown("---")
        st.sidebar.write("**解決されたパス**:")
        
        for key, info in debug_info['resolved_paths'].items():
            st.sidebar.write(f"**{key}**:")
            st.sidebar.write(f"- パス: `{info['path']}`")
            st.sidebar.write(f"- 存在: {info['exists']}")
            if info['exists']:
                st.sidebar.write(f"- サイズ: {info['size']} bytes")
                st.sidebar.write(f"- mtime: {info['mtime']}")
            else:
                st.sidebar.warning(f"⚠️ {key}が見つかりません")
    else:
        st.sidebar.error("❌ logoディレクトリが存在しません")
