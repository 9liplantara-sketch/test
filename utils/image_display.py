"""
画像表示の1本化モジュール
すべての画像表示をこのモジュール経由で行う
safe_slug基準で統一、IMAGE_BASE_URL対応
"""
import os
import streamlit as st
from pathlib import Path
from PIL import Image as PILImage
from typing import Optional, Tuple, Union, Dict, Literal
import re
import base64

try:
    from material_map_version import APP_VERSION
except ImportError:
    APP_VERSION = os.getenv("APP_VERSION", "dev")


def safe_slug_from_material(material) -> str:
    """
    材料オブジェクトからsafe_slugを生成（唯一のキー）
    
    Args:
        material: Materialオブジェクト
    
    Returns:
        safe_slug（パス安全な文字列）
    """
    material_name = getattr(material, 'name_official', None) or getattr(material, 'name', None) or ""
    slug = material_name.strip()
    forbidden_chars = r'[/\\:*?"<>|]'
    slug = re.sub(forbidden_chars, '_', slug)
    return slug


def get_material_image_ref(
    material,
    kind: Literal["primary", "space", "product"],
    project_root: Optional[Path] = None
) -> Tuple[Optional[Union[str, Path]], Dict]:
    """
    材料の画像参照を取得（safe_slug基準で統一）
    
    優先順位:
    A. DBに明示URLがあるならそれ（texture_image_url / use_examples.image_url）
    B. 環境変数 IMAGE_BASE_URL があれば、規約URLを組み立ててそれ
    C. ローカル fallback: static/images/materials/{safe_slug}/primary.jpg 等
    
    Args:
        material: Materialオブジェクト
        kind: 画像の種類（"primary", "space", "product"）
        project_root: プロジェクトルートのパス
    
    Returns:
        (src, debug_info) のタプル
        - src: URL文字列、Pathオブジェクト、またはNone
        - debug_info: デバッグ情報の辞書
    """
    if project_root is None:
        project_root = Path.cwd()
    else:
        project_root = Path(project_root)
    
    # safe_slugを生成（唯一のキー）
    safe_slug = safe_slug_from_material(material)
    
    debug_info = {
        "kind": kind,
        "material_id": getattr(material, 'id', None),
        "material_name": getattr(material, 'name_official', None) or getattr(material, 'name', None),
        "safe_slug": safe_slug,
        "source": None,
        "chosen_branch": None,
        "candidate_urls": [],
        "candidate_paths": [],
        "final_src_type": None,
        "final_path_exists": None,
        "final_url": None,
        "base_dir_sample": [],
    }
    
    # base_dirのディレクトリ一覧を取得（デバッグ用）
    base_dir = project_root / 'static' / 'images' / 'materials'
    if base_dir.exists():
        try:
            dirs = [d.name for d in base_dir.iterdir() if d.is_dir()]
            debug_info["base_dir_sample"] = sorted(dirs)[:20]  # 最初の20件
        except Exception as e:
            debug_info["base_dir_error"] = str(e)
    
    # A. DBに明示URLがあるならそれ
    url = None
    
    if kind == "primary":
        url = getattr(material, 'texture_image_url', None)
    elif kind in ["space", "product"]:
        use_examples = getattr(material, 'use_examples', [])
        if use_examples:
            for use_ex in use_examples:
                use_type = getattr(use_ex, 'domain', None) or ""
                if (kind == "space" and "空間" in use_type) or (kind == "product" and "プロダクト" in use_type):
                    url = getattr(use_ex, 'image_url', None)
                    if url:
                        break
    
    if url and url.startswith(('http://', 'https://')):
        debug_info["candidate_urls"].append(url)
        separator = "&" if "?" in url else "?"
        image_version = os.getenv("IMAGE_VERSION") or APP_VERSION or "dev"
        url_with_cache = f"{url}{separator}v={image_version}"
        debug_info["source"] = "db_url"
        debug_info["chosen_branch"] = "db_url"
        debug_info["final_src_type"] = "url"
        debug_info["final_url"] = url_with_cache
        debug_info["cache_buster"] = image_version
        return url_with_cache, debug_info
    
    # B. 環境変数 IMAGE_BASE_URL があれば、規約URLを組み立ててそれ
    image_base_url = os.getenv("IMAGE_BASE_URL")
    if image_base_url:
        base_url_clean = image_base_url.rstrip('/')
        if kind == "primary":
            base_url = f"{base_url_clean}/materials/{safe_slug}/primary.jpg"
        elif kind == "space":
            base_url = f"{base_url_clean}/materials/{safe_slug}/uses/space.jpg"
        elif kind == "product":
            base_url = f"{base_url_clean}/materials/{safe_slug}/uses/product.jpg"
        else:
            base_url = None
        
        if base_url:
            debug_info["candidate_urls"].append(base_url)
            separator = "&" if "?" in base_url else "?"
            image_version = os.getenv("IMAGE_VERSION") or APP_VERSION or "dev"
            url_with_cache = f"{base_url}{separator}v={image_version}"
            debug_info["source"] = "base_url"
            debug_info["chosen_branch"] = "base_url"
            debug_info["base_url"] = image_base_url
            debug_info["final_src_type"] = "url"
            debug_info["final_url"] = url_with_cache
            debug_info["cache_buster"] = image_version
            return url_with_cache, debug_info
    
    # C. ローカル fallback: static/images/materials/{safe_slug}/primary.jpg 等
    material_dir = base_dir / safe_slug
    
    # kindに応じた画像パスを取得
    candidates = []
    if kind == "primary":
        candidates = [material_dir / "primary.jpg"]
    elif kind == "space":
        candidates = [material_dir / "uses" / "space.jpg"]
    elif kind == "product":
        candidates = [material_dir / "uses" / "product.jpg"]
    
    # 候補パスをdebug_infoに追加
    for candidate in candidates:
        abs_path = str(candidate.resolve())
        debug_info["candidate_paths"].append(abs_path)
        exists = candidate.exists() and candidate.is_file()
        if not exists:
            debug_info.setdefault("failed_paths", []).append({
                "path": abs_path,
                "exists": False,
                "is_file": candidate.is_file() if candidate.exists() else False
            })
    
    # 存在する最初の候補を採用
    image_path = None
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            image_path = candidate
            break
    
    # 旧日本語フォルダのフォールバック（safe_slugパスが無い場合のみ）
    if image_path is None:
        material_name = getattr(material, 'name_official', None) or getattr(material, 'name', None) or ""
        if material_name:
            # 注釈を除去（例: "アルミニウム（Al）" -> "アルミニウム"）
            name_without_annotation = re.sub(r'[（(].*?[）)]', '', material_name).strip()
            old_safe_slug = name_without_annotation.strip()
            forbidden_chars = r'[/\\:*?"<>|]'
            old_safe_slug = re.sub(forbidden_chars, '_', old_safe_slug)
            
            old_material_dir = base_dir / old_safe_slug
            old_candidates = []
            if kind == "primary":
                old_candidates = [old_material_dir / "primary.jpg"]
            elif kind == "space":
                old_candidates = [old_material_dir / "uses" / "space.jpg"]
            elif kind == "product":
                old_candidates = [old_material_dir / "uses" / "product.jpg"]
            
            for old_candidate in old_candidates:
                abs_path = str(old_candidate.resolve())
                debug_info["candidate_paths"].append(abs_path)
                if old_candidate.exists() and old_candidate.is_file():
                    image_path = old_candidate
                    debug_info["chosen_branch"] = "local_old_slug"
                    debug_info["old_safe_slug"] = old_safe_slug
                    break
                else:
                    debug_info.setdefault("failed_paths", []).append({
                        "path": abs_path,
                        "exists": False,
                        "is_file": old_candidate.is_file() if old_candidate.exists() else False
                    })
    
    if image_path:
        debug_info["source"] = "local"
        debug_info["chosen_branch"] = debug_info.get("chosen_branch", "local")
        debug_info["resolved_path"] = str(image_path.resolve())
        debug_info["final_src_type"] = "path"
        debug_info["final_path_exists"] = True
        try:
            stat = image_path.stat()
            debug_info["size"] = stat.st_size
            debug_info["mtime"] = stat.st_mtime
        except Exception as e:
            debug_info["stat_error"] = str(e)
        return image_path, debug_info
    else:
        debug_info["source"] = "not_found"
        debug_info["chosen_branch"] = "not_found"
        debug_info["final_src_type"] = None
        debug_info["final_path_exists"] = False
    
    return None, debug_info


def to_data_url(image_path: Path) -> Optional[str]:
    """
    画像ファイルをdata URLに変換
    
    Args:
        image_path: 画像ファイルのパス
    
    Returns:
        data URL文字列、またはNone
    """
    try:
        if not image_path.exists():
            return None
        
        with open(image_path, 'rb') as f:
            img_data = f.read()
        
        # 拡張子からMIMEタイプを判定
        ext = image_path.suffix.lower()
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.webp': 'image/webp',
            '.gif': 'image/gif',
        }
        mime_type = mime_types.get(ext, 'image/jpeg')
        
        # base64エンコード
        base64_data = base64.b64encode(img_data).decode('utf-8')
        return f"data:{mime_type};base64,{base64_data}"
    except Exception:
        return None


def display_image_unified(
    image_source: Optional[Union[str, Path, PILImage.Image]],
    caption: Optional[str] = None,
    width: Optional[int] = None,
    use_container_width: bool = False
):
    """
    画像を統一的な方法で表示（URL/Path/PILImage対応）
    
    Args:
        image_source: URL文字列、Pathオブジェクト、またはPILImage
        caption: キャプション
        width: 幅（ピクセル）
        use_container_width: コンテナ幅を使用するか
    """
    if image_source is None:
        # プレースホルダーを表示
        st.markdown(
            f'<div style="width: 100%; height: 200px; background: #f0f0f0; display: flex; align-items: center; justify-content: center; color: #666;">画像なし</div>',
            unsafe_allow_html=True
        )
        return
    
    try:
        if isinstance(image_source, str):
            # URLまたはdata URL
            if image_source.startswith(('http://', 'https://', 'data:')):
                st.image(image_source, caption=caption, width=width, use_container_width=use_container_width)
            else:
                # ローカルパス文字列
                path = Path(image_source)
                if path.exists():
                    st.image(str(path), caption=caption, width=width, use_container_width=use_container_width)
                else:
                    display_image_unified(None, caption=caption)
        elif isinstance(image_source, Path):
            # Pathオブジェクト
            if image_source.exists():
                st.image(str(image_source), caption=caption, width=width, use_container_width=use_container_width)
            else:
                display_image_unified(None, caption=caption)
        elif isinstance(image_source, PILImage.Image):
            # PILImage
            st.image(image_source, caption=caption, width=width, use_container_width=use_container_width)
        else:
            display_image_unified(None, caption=caption)
    except Exception as e:
        if os.getenv("DEBUG_IMAGE", "false").lower() == "true":
            st.error(f"画像表示エラー: {e}")
        display_image_unified(None, caption=caption)
