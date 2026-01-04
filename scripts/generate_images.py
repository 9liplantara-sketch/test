"""
材料画像一括生成スクリプト
DBから材料一覧を取得し、テクスチャ・用途・加工例画像を生成して保存
"""
import os
import sys
import json
import time
from pathlib import Path
from typing import List, Dict, Optional
from PIL import Image
import requests

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal, Material, UseExample, ProcessExampleImage, init_db
from scripts.prompt_templates import (
    build_texture_prompt,
    build_use_case_prompt,
    build_process_prompt,
    get_material_slug,
    get_use_case_slug,
    get_process_slug
)
from utils.paths import resolve_path, get_generated_dir


# 画像生成API設定（環境変数から取得）
IMAGE_API_PROVIDER = os.getenv("IMAGE_API_PROVIDER", "openai")  # "openai" or "stability"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
STABILITY_API_KEY = os.getenv("STABILITY_API_KEY", "")

# レート制限設定
RATE_LIMIT_DELAY = 2.0  # 秒（API呼び出し間隔）
MAX_RETRIES = 3  # 最大リトライ回数


def generate_image_with_openai(prompt: str, size: str = "1024x1024") -> Optional[bytes]:
    """
    OpenAI DALL-E 3で画像を生成
    
    Args:
        prompt: プロンプト
        size: 画像サイズ（"1024x1024" or "1792x1024"）
    
    Returns:
        画像のバイトデータ、失敗時はNone
    """
    if not OPENAI_API_KEY:
        print("警告: OPENAI_API_KEYが設定されていません")
        return None
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality="standard",
            n=1,
        )
        
        image_url = response.data[0].url
        
        # URLから画像をダウンロード
        img_response = requests.get(image_url, timeout=30)
        if img_response.status_code == 200:
            return img_response.content
        else:
            print(f"画像ダウンロードエラー: {img_response.status_code}")
            return None
            
    except ImportError:
        print("警告: openaiライブラリがインストールされていません。pip install openai を実行してください。")
        return None
    except Exception as e:
        print(f"OpenAI画像生成エラー: {e}")
        return None


def generate_image_with_stability(prompt: str, width: int = 1024, height: int = 1024) -> Optional[bytes]:
    """
    Stability AIで画像を生成
    
    Args:
        prompt: プロンプト
        width: 画像幅
        height: 画像高さ
    
    Returns:
        画像のバイトデータ、失敗時はNone
    """
    if not STABILITY_API_KEY:
        print("警告: STABILITY_API_KEYが設定されていません")
        return None
    
    try:
        import stability_sdk.client
        from stability_sdk import client
        
        stability_api = client.StabilityInference(
            key=STABILITY_API_KEY,
            verbose=True,
            engine="stable-diffusion-xl-1024-v1-0"
        )
        
        answers = stability_api.generate(
            prompt=prompt,
            width=width,
            height=height,
            samples=1,
        )
        
        for resp in answers:
            for artifact in resp.artifacts:
                if artifact.finish_reason == client.generation.FINISH_REASON_SUCCESS:
                    return artifact.binary
                else:
                    print(f"生成失敗: {artifact.finish_reason}")
                    return None
        
        return None
        
    except ImportError:
        print("警告: stability-sdkライブラリがインストールされていません。pip install stability-sdk を実行してください。")
        return None
    except Exception as e:
        print(f"Stability AI画像生成エラー: {e}")
        return None


def generate_image(prompt: str, width: int = 1024, height: int = 1024, retries: int = MAX_RETRIES) -> Optional[bytes]:
    """
    画像生成APIを呼び出し（プロバイダー自動選択）
    
    Args:
        prompt: プロンプト
        width: 画像幅
        height: 画像高さ
        retries: リトライ回数
    
    Returns:
        画像のバイトデータ、失敗時はNone
    """
    size_str = f"{width}x{height}"
    
    for attempt in range(retries):
        try:
            if IMAGE_API_PROVIDER == "openai":
                # DALL-E 3のサイズ制限に合わせる
                if width == 1024 and height == 1024:
                    size = "1024x1024"
                elif width == 1280 and height == 720:
                    size = "1792x1024"  # 最も近いサイズ
                else:
                    size = "1024x1024"
                return generate_image_with_openai(prompt, size)
            elif IMAGE_API_PROVIDER == "stability":
                return generate_image_with_stability(prompt, width, height)
            else:
                print(f"不明なAPIプロバイダー: {IMAGE_API_PROVIDER}")
                return None
        except Exception as e:
            if attempt < retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"リトライ {attempt + 1}/{retries} ({wait_time}秒待機)...")
                time.sleep(wait_time)
            else:
                print(f"画像生成失敗（{retries}回試行）: {e}")
                return None
    
    return None


def save_image(image_bytes: bytes, filepath: Path, format: str = "PNG") -> bool:
    """
    画像を保存（PNG形式、RGB固定）
    
    Args:
        image_bytes: 画像のバイトデータ
        filepath: 保存先パス
        format: 画像形式（PNG固定推奨）
    
    Returns:
        成功時True
    """
    try:
        # ディレクトリを作成
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # 画像を読み込み
        from io import BytesIO
        img = Image.open(BytesIO(image_bytes))
        
        # RGBモードに変換（透明は白背景に合成）
        if img.mode != 'RGB':
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'RGBA':
                rgb_img.paste(img, mask=img.split()[3])
            else:
                rgb_img = img.convert('RGB')
            img = rgb_img
        
        # PNGとして保存
        img.save(filepath, format, quality=95)
        return True
    except Exception as e:
        print(f"画像保存エラー ({filepath}): {e}")
        return False


def generate_texture_image(material: Material, output_dir: Path) -> Optional[str]:
    """
    テクスチャ画像を生成
    
    Args:
        material: Materialオブジェクト
        output_dir: 出力ディレクトリ
    
    Returns:
        相対パス、失敗時はNone
    """
    # 既存画像をチェック
    slug = get_material_slug(material.name_official or material.name, material.id)
    filename = f"{material.id}_{slug}.png"
    filepath = output_dir / filename
    
    if filepath.exists() and filepath.stat().st_size > 0:
        print(f"  スキップ: {filename} (既存)")
        return f"static/material_textures/{filename}"
    
    # プロンプト生成
    category = material.category_main or material.category or "その他"
    description = material.description
    prompt = build_texture_prompt(
        material_name=material.name_official or material.name,
        category=category,
        description=description
    )
    
    print(f"  生成中: {filename}")
    print(f"    プロンプト: {prompt[:100]}...")
    
    # 画像生成（1024x1024）
    image_bytes = generate_image(prompt, width=1024, height=1024)
    if not image_bytes:
        print(f"    ✗ 生成失敗")
        return None
    
    # 保存
    if save_image(image_bytes, filepath):
        print(f"    ✓ 保存完了: {filepath}")
        time.sleep(RATE_LIMIT_DELAY)
        return f"static/material_textures/{filename}"
    else:
        print(f"    ✗ 保存失敗")
        return None


def generate_use_case_images(material: Material, output_dir: Path, db) -> List[str]:
    """
    用途写真を生成
    
    Args:
        material: Materialオブジェクト
        output_dir: 出力ディレクトリ
        db: データベースセッション
    
    Returns:
        生成された画像の相対パスリスト
    """
    generated_paths = []
    
    # 用途例を取得（既存のUseExampleから）
    use_examples = db.query(UseExample).filter(UseExample.material_id == material.id).all()
    
    if not use_examples:
        # 用途例がない場合、カテゴリから推測
        category = material.category_main or material.category or "その他"
        default_use_cases = {
            "金属・合金": ["調理器具", "建材パネル"],
            "高分子（樹脂・エラストマー等）": ["収納ケース", "射出成形品"],
            "木材・紙・セルロース系": ["家具", "内装材"],
        }
        use_cases = default_use_cases.get(category, ["製品例"])
        
        for use_case in use_cases[:2]:  # 最大2件
            use_example = UseExample(
                material_id=material.id,
                example_name=use_case,
                domain="プロダクト",
                description=f"{material.name_official or material.name}の{use_case}",
                source_name="Generated",
                license_note="AI Generated"
            )
            db.add(use_example)
            use_examples.append(use_example)
        db.commit()
    
    for use_example in use_examples[:3]:  # 最大3件
        # 既存画像をチェック
        if use_example.image_path and Path(use_example.image_path).exists():
            print(f"  スキップ: {use_example.example_name} (既存)")
            generated_paths.append(use_example.image_path)
            continue
        
        # プロンプト生成
        category = material.category_main or material.category or "その他"
        prompt = build_use_case_prompt(
            material_name=material.name_official or material.name,
            category=category,
            use_case=use_example.example_name,
            domain=use_example.domain
        )
        
        slug = get_use_case_slug(use_example.example_name)
        filename = f"{material.id}_{slug}.png"
        filepath = output_dir / filename
        
        print(f"  生成中: {use_example.example_name} ({filename})")
        print(f"    プロンプト: {prompt[:100]}...")
        
        # 画像生成（1280x720）
        image_bytes = generate_image(prompt, width=1280, height=720)
        if not image_bytes:
            print(f"    ✗ 生成失敗")
            continue
        
        # 保存
        if save_image(image_bytes, filepath):
            relative_path = f"static/use_cases/{filename}"
            use_example.image_path = relative_path
            db.commit()
            print(f"    ✓ 保存完了: {filepath}")
            generated_paths.append(relative_path)
            time.sleep(RATE_LIMIT_DELAY)
        else:
            print(f"    ✗ 保存失敗")
    
    return generated_paths


def generate_process_images(material: Material, output_dir: Path, db) -> List[str]:
    """
    加工例画像を生成
    
    Args:
        material: Materialオブジェクト
        output_dir: 出力ディレクトリ
        db: データベースセッション
    
    Returns:
        生成された画像の相対パスリスト
    """
    generated_paths = []
    
    # 加工方法を取得
    processing_methods_str = material.processing_methods
    if not processing_methods_str:
        return generated_paths
    
    try:
        processing_methods = json.loads(processing_methods_str)
    except:
        processing_methods = [processing_methods_str] if isinstance(processing_methods_str, str) else []
    
    if not processing_methods:
        return generated_paths
    
    category = material.category_main or material.category or "その他"
    
    for process_method in processing_methods[:3]:  # 最大3件
        # 既存画像をチェック
        existing = db.query(ProcessExampleImage).filter(
            ProcessExampleImage.material_id == material.id,
            ProcessExampleImage.process_method == process_method
        ).first()
        
        if existing and existing.image_path and Path(existing.image_path).exists():
            print(f"  スキップ: {process_method} (既存)")
            generated_paths.append(existing.image_path)
            continue
        
        # プロンプト生成
        prompt = build_process_prompt(
            material_name=material.name_official or material.name,
            process_method=process_method,
            category=category
        )
        
        slug = get_process_slug(process_method)
        filename = f"{material.id}_{slug}.png"
        filepath = output_dir / filename
        
        print(f"  生成中: {process_method} ({filename})")
        print(f"    プロンプト: {prompt[:100]}...")
        
        # 画像生成（1280x720）
        image_bytes = generate_image(prompt, width=1280, height=720)
        if not image_bytes:
            print(f"    ✗ 生成失敗")
            continue
        
        # 保存
        if save_image(image_bytes, filepath):
            relative_path = f"static/process_examples/{filename}"
            
            # DBに登録
            if existing:
                existing.image_path = relative_path
            else:
                process_image = ProcessExampleImage(
                    material_id=material.id,
                    process_method=process_method,
                    image_path=relative_path,
                    description=f"{material.name_official or material.name}の{process_method}加工例",
                    source_name="Generated",
                    license_note="AI Generated"
                )
                db.add(process_image)
            
            db.commit()
            print(f"    ✓ 保存完了: {filepath}")
            generated_paths.append(relative_path)
            time.sleep(RATE_LIMIT_DELAY)
        else:
            print(f"    ✗ 保存失敗")
    
    return generated_paths


def generate_all_images(material_ids: Optional[List[int]] = None, skip_existing: bool = True):
    """
    すべての材料の画像を生成
    
    Args:
        material_ids: 生成する材料IDのリスト（Noneの場合は全材料）
        skip_existing: 既存画像をスキップするか
    """
    db = SessionLocal()
    try:
        # 材料一覧を取得
        if material_ids:
            materials = db.query(Material).filter(Material.id.in_(material_ids)).all()
        else:
            materials = db.query(Material).all()
        
        if not materials:
            print("材料が見つかりません")
            return
        
        print(f"============================================================")
        print(f"材料画像一括生成を開始します")
        print(f"対象材料数: {len(materials)}")
        print(f"============================================================")
        
        # 出力ディレクトリ
        texture_dir = resolve_path("static/material_textures")
        use_case_dir = resolve_path("static/use_cases")
        process_dir = resolve_path("static/process_examples")
        
        texture_dir.mkdir(parents=True, exist_ok=True)
        use_case_dir.mkdir(parents=True, exist_ok=True)
        process_dir.mkdir(parents=True, exist_ok=True)
        
        stats = {
            "total": len(materials),
            "texture_generated": 0,
            "texture_failed": 0,
            "use_case_generated": 0,
            "process_generated": 0,
        }
        
        for idx, material in enumerate(materials, 1):
            print(f"\n[{idx}/{len(materials)}] {material.name_official or material.name} (ID: {material.id})")
            print("=" * 60)
            
            # テクスチャ画像
            try:
                texture_path = generate_texture_image(material, texture_dir)
                if texture_path:
                    material.texture_image_path = texture_path
                    db.commit()
                    stats["texture_generated"] += 1
                else:
                    stats["texture_failed"] += 1
            except Exception as e:
                print(f"  テクスチャ生成エラー: {e}")
                stats["texture_failed"] += 1
            
            # 用途写真
            try:
                use_case_paths = generate_use_case_images(material, use_case_dir, db)
                stats["use_case_generated"] += len(use_case_paths)
            except Exception as e:
                print(f"  用途写真生成エラー: {e}")
            
            # 加工例画像
            try:
                process_paths = generate_process_images(material, process_dir, db)
                stats["process_generated"] += len(process_paths)
            except Exception as e:
                print(f"  加工例画像生成エラー: {e}")
        
        print("\n" + "=" * 60)
        print("✅ 画像生成完了")
        print("=" * 60)
        print(f"総材料数: {stats['total']}")
        print(f"テクスチャ: 生成={stats['texture_generated']}, 失敗={stats['texture_failed']}")
        print(f"用途写真: {stats['use_case_generated']}件")
        print(f"加工例画像: {stats['process_generated']}件")
        print("=" * 60)
        
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="材料画像一括生成スクリプト")
    parser.add_argument("--material-ids", type=int, nargs="+", help="生成する材料ID（指定しない場合は全材料）")
    parser.add_argument("--skip-existing", action="store_true", default=True, help="既存画像をスキップ")
    parser.add_argument("--test", action="store_true", help="テストモード（3材料のみ）")
    
    args = parser.parse_args()
    
    # データベース初期化
    init_db()
    
    if args.test:
        # テストモード：最初の3材料のみ
        db = SessionLocal()
        try:
            test_materials = db.query(Material).limit(3).all()
            test_ids = [m.id for m in test_materials]
            generate_all_images(material_ids=test_ids, skip_existing=args.skip_existing)
        finally:
            db.close()
    else:
        generate_all_images(material_ids=args.material_ids, skip_existing=args.skip_existing)

