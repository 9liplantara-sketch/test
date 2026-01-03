"""
マテリアル画像生成モジュール
材料のイメージ画像を生成します
"""
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import numpy as np
import os
from pathlib import Path


def generate_wood_texture(name, color_base=(139, 90, 43), size=(800, 600)):
    """木材テクスチャを生成"""
    img = Image.new('RGB', size, color_base)
    draw = ImageDraw.Draw(img)
    
    # 木目を描画
    width, height = size
    for i in range(0, height, 20):
        # 木目の線
        y = i + np.random.randint(-5, 5)
        color = tuple(max(0, min(255, c + np.random.randint(-20, 20))) for c in color_base)
        draw.line([(0, y), (width, y)], fill=color, width=2)
    
    # ノイズを追加
    noise = np.random.randint(-10, 10, (height, width, 3), dtype=np.int16)
    img_array = np.array(img).astype(np.int16)
    img_array = np.clip(img_array + noise, 0, 255).astype(np.uint8)
    img = Image.fromarray(img_array)
    
    # ぼかしで自然な質感に
    img = img.filter(ImageFilter.GaussianBlur(radius=1))
    
    return img


def generate_metal_texture(name, color_base=(192, 192, 192), size=(800, 600)):
    """金属テクスチャを生成"""
    img = Image.new('RGB', size, color_base)
    draw = ImageDraw.Draw(img)
    
    width, height = size
    
    # 金属の反射を模擬
    for i in range(0, width, 30):
        x = i
        gradient = Image.new('L', (1, height))
        for y in range(height):
            value = int(128 + 127 * np.sin(y / 50))
            gradient.putpixel((0, y), value)
        
        mask = gradient.resize((30, height))
        overlay = Image.new('RGB', (30, height), (255, 255, 255))
        img.paste(overlay, (x, 0), mask)
    
    # 微細なテクスチャ
    noise = np.random.randint(-15, 15, (height, width, 3), dtype=np.int16)
    img_array = np.array(img).astype(np.int16)
    img_array = np.clip(img_array + noise, 0, 255).astype(np.uint8)
    img = Image.fromarray(img_array)
    
    return img


def generate_plastic_texture(name, color_base=(200, 200, 200), size=(800, 600)):
    """プラスチックテクスチャを生成"""
    img = Image.new('RGB', size, color_base)
    
    # 滑らかなプラスチック感
    noise = np.random.randint(-5, 5, (size[1], size[0], 3), dtype=np.int16)
    img_array = np.array(img).astype(np.int16)
    img_array = np.clip(img_array + noise, 0, 255).astype(np.uint8)
    img = Image.fromarray(img_array)
    
    # 滑らかに
    img = img.filter(ImageFilter.GaussianBlur(radius=2))
    
    # 光沢を追加
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(1.1)
    
    return img


def generate_material_image(material_name, category, output_dir="uploads"):
    """材料のイメージ画像を生成"""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # カテゴリに応じたテクスチャ生成
    if "木材" in category or "木" in category:
        # 木材の色を材料名に応じて変更
        wood_colors = {
            "カリン": (180, 140, 100),
            "栗": (139, 90, 43),
            "樫": (101, 67, 33),
        }
        color = wood_colors.get(material_name.split()[0] if " " in material_name else material_name, (139, 90, 43))
        img = generate_wood_texture(material_name, color)
    elif "金属" in category or "アルミ" in material_name or "ステンレス" in material_name or "真鍮" in material_name:
        # 金属の色を材料名に応じて変更
        metal_colors = {
            "アルミ": (192, 192, 192),
            "ステンレス": (220, 220, 220),
            "真鍮": (181, 166, 66),
        }
        color = metal_colors.get(material_name.split()[0] if " " in material_name else material_name, (192, 192, 192))
        img = generate_metal_texture(material_name, color)
    elif "プラスチック" in category or "PP" in material_name or "PE" in material_name or "PVC" in material_name:
        # プラスチックの色
        plastic_colors = {
            "PP": (255, 255, 200),
            "PE": (240, 240, 240),
            "PVC": (255, 255, 255),
        }
        color = plastic_colors.get(material_name.split()[0] if " " in material_name else material_name, (200, 200, 200))
        img = generate_plastic_texture(material_name, color)
    else:
        # デフォルト
        img = Image.new('RGB', (800, 600), (200, 200, 200))
    
    # ファイル名を生成（安全な形式）
    safe_name = "".join(c for c in material_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    filename = f"{safe_name.replace(' ', '_')}.webp"
    filepath = output_path / filename
    
    # WebP形式で保存
    img.save(filepath, 'WEBP', quality=85)
    
    return str(filepath)


def ensure_material_image(material_name, category, material_id, db):
    """材料の画像が存在しない場合、生成してデータベースに登録"""
    from database import Image as ImageModel
    
    # 既存の画像をチェック
    existing = db.query(ImageModel).filter(ImageModel.material_id == material_id).first()
    if existing:
        return existing.file_path
    
    # 画像を生成
    try:
        image_path = generate_material_image(material_name, category)
        if not image_path:
            return None
            
        file_name = Path(image_path).name
        
        # データベースに登録
        db_image = ImageModel(
            material_id=material_id,
            file_path=file_name,
            image_type="generated",
            description=f"{material_name}の生成画像"
        )
        db.add(db_image)
        db.flush()
        
        print(f"  ✓ 画像生成: {file_name}")
        return file_name
    except Exception as e:
        print(f"  ✗ 画像生成エラー ({material_name}): {e}")
        import traceback
        traceback.print_exc()
        return None

