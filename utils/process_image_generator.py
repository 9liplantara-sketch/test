"""
加工例画像生成/取得モジュール
加工方法ごとの代表例画像を生成または取得
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from typing import Optional, Tuple
import os


def generate_process_example_image(
    process_name: str,
    size: Tuple[int, int] = (400, 300),
    output_dir: str = "static/process_examples"
) -> Optional[str]:
    """
    加工例の画像を生成（抽象的・シンプルな表現）
    
    Args:
        process_name: 加工方法名（例: "射出成形", "レーザー加工"）
        size: 画像サイズ
        output_dir: 出力ディレクトリ
    
    Returns:
        生成された画像ファイルのパス（相対パス）
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 加工方法に応じた背景色
    process_colors = {
        "射出成形": (240, 250, 255),      # ライトブルー
        "圧縮成形": (255, 250, 240),      # ライトイエロー
        "3Dプリント": (250, 240, 250),    # ライトピンク
        "レーザー加工": (255, 240, 240),  # ライトレッド
        "熱成形": (240, 255, 240),        # ライトグリーン
        "接着": (255, 255, 240),          # ライトイエロー
        "切削": (240, 240, 240),          # ライトグレー
    }
    bg_color = process_colors.get(process_name, (245, 245, 245))
    
    # 画像を作成
    img = Image.new('RGB', size, bg_color)
    draw = ImageDraw.Draw(img)
    
    width, height = size
    
    # シンプルな図形的表現
    # 1. 中央に工具/装置っぽいシルエット（矩形）
    center_x, center_y = width // 2, height // 2
    box_size = min(width, height) // 3
    
    # 矩形の色（加工方法に応じて）
    box_color = (100, 100, 100)
    if "3D" in process_name or "プリント" in process_name:
        box_color = (200, 150, 200)  # ピンク系
    elif "レーザー" in process_name:
        box_color = (200, 100, 100)   # レッド系
    elif "熱" in process_name:
        box_color = (200, 150, 100)   # オレンジ系
    
    # 矩形を描画（工具/装置のイメージ）
    draw.rectangle(
        [center_x - box_size, center_y - box_size // 2,
         center_x + box_size, center_y + box_size // 2],
        fill=box_color,
        outline=(80, 80, 80),
        width=2
    )
    
    # 2. 材料片（小さな円/矩形）を描画
    material_color = (150, 150, 200)
    material_size = box_size // 3
    draw.ellipse(
        [center_x - box_size - material_size, center_y - material_size // 2,
         center_x - box_size, center_y + material_size // 2],
        fill=material_color,
        outline=(100, 100, 100),
        width=1
    )
    
    # 3. テキストを配置
    try:
        font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
    except:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    # 加工方法名（中央下）
    text_y = center_y + box_size // 2 + 20
    bbox = draw.textbbox((0, 0), process_name, font=font_large)
    text_width = bbox[2] - bbox[0]
    text_x = center_x - text_width // 2
    draw.text((text_x, text_y), process_name, fill=(50, 50, 50), font=font_large)
    
    # ファイル名を生成
    safe_name = "".join(c for c in process_name if c.isalnum() or c in (' ', '-', '_', '（', '）', '・')).rstrip()
    safe_name = safe_name.replace(' ', '_').replace('（', '').replace('）', '').replace('・', '_')
    filename = f"{safe_name}.png"
    filepath = output_path / filename
    
    # PNG形式で保存（RGBモード、白背景）
    img.save(filepath, 'PNG', quality=95)
    
    # 相対パスを返す
    try:
        return str(filepath.relative_to(Path.cwd()))
    except ValueError:
        return str(Path(output_dir) / filename)


def get_process_example_image(process_name: str, output_dir: str = "static/process_examples") -> Optional[str]:
    """
    加工例画像が存在しない場合、生成する
    
    Args:
        process_name: 加工方法名
        output_dir: 出力ディレクトリ
    
    Returns:
        画像ファイルのパス（相対パス）、生成失敗時はNone
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 既存の画像をチェック
    safe_name = "".join(c for c in process_name if c.isalnum() or c in (' ', '-', '_', '（', '）', '・')).rstrip()
    safe_name = safe_name.replace(' ', '_').replace('（', '').replace('）', '').replace('・', '_')
    filename = f"{safe_name}.png"
    filepath = output_path / filename
    
    if filepath.exists():
        try:
            return str(filepath.relative_to(Path.cwd()))
        except ValueError:
            return str(Path(output_dir) / filename)
    
    # 画像を生成
    try:
        generated_path = generate_process_example_image(process_name, output_dir=output_dir)
        return generated_path
    except Exception as e:
        print(f"  ✗ 加工例画像生成エラー ({process_name}): {e}")
        import traceback
        traceback.print_exc()
        return None


