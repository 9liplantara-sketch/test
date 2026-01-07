"""
用途例画像表示の1本化モジュール
"""
import streamlit as st
from pathlib import Path
from PIL import Image as PILImage
from typing import Optional
from utils.image_health import resolve_image_path, normalize_image_path, check_image_health


def display_use_example_image(
    use_example,
    width: Optional[int] = 280,
    project_root: Optional[Path] = None
):
    """
    用途例の画像を表示（健康状態チェック付き、自動修復対応）
    
    Args:
        use_example: UseExampleオブジェクト
        width: 画像幅
        project_root: プロジェクトルートのパス
    """
    if project_root is None:
        project_root = Path.cwd()
    else:
        project_root = Path(project_root)
    
    # 画像パスが設定されているか確認
    if not use_example.image_path:
        # プレースホルダーを表示
        placeholder = PILImage.new('RGB', (280, 200), (240, 240, 240))
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(placeholder)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
        except:
            font = ImageFont.load_default()
        text = "画像なし"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        draw.text(
            ((280 - text_width) // 2, (200 - text_height) // 2),
            text,
            fill=(150, 150, 150),
            font=font
        )
        st.image(placeholder, width=width)
        return
    
    # パスを正規化・解決
    normalized_path = normalize_image_path(use_example.image_path, project_root)
    resolved_path = resolve_image_path(use_example.image_path, project_root)
    
    # 健康状態をチェック
    health = check_image_health(use_example.image_path, project_root)
    
    if health["status"] == "ok":
        # 正常な画像を読み込む
        try:
            pil_img = PILImage.open(resolved_path)
            # RGBモードに変換
            if pil_img.mode != 'RGB':
                if pil_img.mode in ('RGBA', 'LA', 'P'):
                    rgb_img = PILImage.new('RGB', pil_img.size, (255, 255, 255))
                    if pil_img.mode == 'RGBA':
                        rgb_img.paste(pil_img, mask=pil_img.split()[3])
                    elif pil_img.mode == 'LA':
                        rgb_img.paste(pil_img.convert('RGB'), mask=pil_img.split()[1])
                    else:
                        rgb_img = pil_img.convert('RGB')
                    pil_img = rgb_img
                else:
                    pil_img = pil_img.convert('RGB')
            
            st.image(pil_img, width=width)
        except Exception as e:
            st.warning(f"画像の読み込みに失敗: {e}")
            # プレースホルダーを表示
            placeholder = PILImage.new('RGB', (280, 200), (240, 240, 240))
            st.image(placeholder, width=width)
    else:
        # エラー時はプレースホルダーを表示
        st.warning(f"画像が利用できません: {health['reason']}")
        placeholder = PILImage.new('RGB', (280, 200), (240, 240, 240))
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(placeholder)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
        except:
            font = ImageFont.load_default()
        text = "画像なし"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        draw.text(
            ((280 - text_width) // 2, (200 - text_height) // 2),
            text,
            fill=(150, 150, 150),
            font=font
        )
        st.image(placeholder, width=width)

