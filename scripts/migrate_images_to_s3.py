"""
ローカル画像をS3に移行するバッチスクリプト
DBから画像レコードを走査し、S3にアップロードしてURLを保存
"""
import os
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal, Material, Image, UseExample, ProcessExampleImage, init_db
from utils.s3_storage import upload_file_to_s3, check_s3_config, test_s3_connection
from utils.paths import resolve_path


def determine_image_type(file_path: str) -> str:
    """
    ファイルパスから画像の種類を判定
    
    Args:
        file_path: ファイルパス（相対パスまたは絶対パス）
    
    Returns:
        画像の種類（"primary", "textures", "use_cases", "process_examples"）
    """
    path_str = str(file_path).lower()
    
    # フォルダ名で判定
    if "texture" in path_str or "material_textures" in path_str:
        return "textures"
    elif "use_case" in path_str or "use_cases" in path_str or "uses" in path_str:
        return "use_cases"
    elif "process_example" in path_str or "process_examples" in path_str:
        return "process_examples"
    elif "upload" in path_str or "images" in path_str:
        return "primary"
    else:
        # デフォルトはprimary
        return "primary"


def build_s3_key(material_id: int, image_type: str, filename: str) -> str:
    """
    S3オブジェクトキーを構築
    
    Args:
        material_id: 材料ID
        image_type: 画像の種類（"primary", "textures", "use_cases", "process_examples"）
        filename: ファイル名
    
    Returns:
        S3オブジェクトキー（例: "materials/1/primary/image.png"）
    """
    # ファイル名からディレクトリ部分を除去
    filename_only = Path(filename).name
    
    return f"materials/{material_id}/{image_type}/{filename_only}"


def migrate_image_records(
    db,
    dry_run: bool = False,
    limit: Optional[int] = None
) -> Dict[str, any]:
    """
    Imageテーブルの画像をS3に移行
    
    Args:
        db: データベースセッション
        dry_run: ドライランモード（アップロードしない）
        limit: 処理件数の上限（Noneの場合は全件）
    
    Returns:
        移行結果の辞書
    """
    results = {
        "total": 0,
        "migrated": 0,
        "skipped": 0,
        "failed": 0,
        "errors": []
    }
    
    # urlが空で、file_pathが存在するレコードを取得（idempotent: 既にurlがあるものはスキップ）
    images = db.query(Image).filter(
        ((Image.url == None) | (Image.url == "")),
        Image.file_path != None,
        Image.file_path != ""
    ).all()
    
    if limit:
        images = images[:limit]
    
    results["total"] = len(images)
    
    print(f"\n{'='*60}")
    print(f"Imageテーブル: {len(images)}件の画像を処理します")
    print(f"{'='*60}")
    
    for idx, image in enumerate(images, 1):
        try:
            # ローカルパスを解決
            local_path = resolve_path(image.file_path) if not Path(image.file_path).is_absolute() else Path(image.file_path)
            
            # ファイルが存在するか確認
            if not local_path.exists():
                results["skipped"] += 1
                error_msg = f"ファイルが存在しません: {image.file_path}"
                results["errors"].append({
                    "type": "Image",
                    "id": image.id,
                    "material_id": image.material_id,
                    "file_path": image.file_path,
                    "error": error_msg
                })
                print(f"[{idx}/{len(images)}] ⚠️  スキップ: {error_msg}")
                continue
            
            # 画像の種類を判定
            image_type = determine_image_type(image.file_path)
            
            # S3キーを構築
            s3_key = build_s3_key(image.material_id, image_type, image.file_path)
            
            # idempotent: 既にURLが設定されている場合はスキップ
            if image.url and image.url.strip():
                results["skipped"] += 1
                print(f"[{idx}/{len(images)}] ⏭️  スキップ: {image.file_path} (既にURLが設定されています)")
                continue
            
            if dry_run:
                print(f"[{idx}/{len(images)}] 🔍 ドライラン: {image.file_path} -> {s3_key}")
                results["migrated"] += 1
            else:
                # S3にアップロード
                try:
                    public_url = upload_file_to_s3(
                        local_path=str(local_path),
                        s3_key=s3_key,
                        make_public=True
                    )
                    
                    # DBにURLを保存（idempotent: 既にURLがあっても上書きしない）
                    if not image.url or not image.url.strip():
                        image.url = public_url
                        db.commit()
                        print(f"[{idx}/{len(images)}] ✅ 移行成功: {image.file_path} -> {public_url}")
                        results["migrated"] += 1
                    else:
                        # 既にURLがある場合はスキップ（idempotent）
                        results["skipped"] += 1
                        print(f"[{idx}/{len(images)}] ⏭️  スキップ: {image.file_path} (既にURLが設定されています)")
                except Exception as e:
                    # 例外時もアプリは落ちない（画像だけスキップ）
                    results["failed"] += 1
                    error_msg = f"S3アップロードエラー: {str(e)}"
                    results["errors"].append({
                        "type": "Image",
                        "id": image.id,
                        "material_id": image.material_id,
                        "file_path": image.file_path,
                        "error": error_msg
                    })
                    print(f"[{idx}/{len(images)}] ❌ 失敗: {error_msg}")
                    db.rollback()
                    # 例外をキャッチして続行（アプリは落ちない）
        
        except Exception as e:
            # 例外時もアプリは落ちない（画像だけスキップ）
            results["failed"] += 1
            error_msg = f"予期しないエラー: {str(e)}"
            results["errors"].append({
                "type": "Image",
                "id": getattr(image, 'id', None),
                "material_id": getattr(image, 'material_id', None),
                "file_path": getattr(image, 'file_path', None),
                "error": error_msg
            })
            print(f"[{idx}/{len(images)}] ❌ エラー: {error_msg}")
            # 例外をキャッチして続行（アプリは落ちない）
            try:
                db.rollback()
            except:
                pass
    
    return results


def migrate_texture_images(
    db,
    dry_run: bool = False,
    limit: Optional[int] = None
) -> Dict[str, any]:
    """
    Materialテーブルのtexture_image_pathをS3に移行
    
    Args:
        db: データベースセッション
        dry_run: ドライランモード
        limit: 処理件数の上限
    
    Returns:
        移行結果の辞書
    """
    results = {
        "total": 0,
        "migrated": 0,
        "skipped": 0,
        "failed": 0,
        "errors": []
    }
    
    # texture_image_urlが空で、texture_image_pathが存在するレコードを取得（idempotent）
    materials = db.query(Material).filter(
        ((Material.texture_image_url == None) | (Material.texture_image_url == "")),
        Material.texture_image_path != None,
        Material.texture_image_path != ""
    ).all()
    
    if limit:
        materials = materials[:limit]
    
    results["total"] = len(materials)
    
    print(f"\n{'='*60}")
    print(f"Materialテーブル（テクスチャ）: {len(materials)}件の画像を処理します")
    print(f"{'='*60}")
    
    for idx, material in enumerate(materials, 1):
        try:
            # ローカルパスを解決
            local_path = resolve_path(material.texture_image_path) if not Path(material.texture_image_path).is_absolute() else Path(material.texture_image_path)
            
            # ファイルが存在するか確認
            if not local_path.exists():
                results["skipped"] += 1
                error_msg = f"ファイルが存在しません: {material.texture_image_path}"
                results["errors"].append({
                    "type": "Material.texture_image_path",
                    "id": material.id,
                    "file_path": material.texture_image_path,
                    "error": error_msg
                })
                print(f"[{idx}/{len(materials)}] ⚠️  スキップ: {error_msg}")
                continue
            
            # S3キーを構築
            s3_key = build_s3_key(material.id, "textures", material.texture_image_path)
            
            # idempotent: 既にURLが設定されている場合はスキップ
            if material.texture_image_url and material.texture_image_url.strip():
                results["skipped"] += 1
                print(f"[{idx}/{len(materials)}] ⏭️  スキップ: {material.texture_image_path} (既にURLが設定されています)")
                continue
            
            if dry_run:
                print(f"[{idx}/{len(materials)}] 🔍 ドライラン: {material.texture_image_path} -> {s3_key}")
                results["migrated"] += 1
            else:
                # S3にアップロード
                try:
                    public_url = upload_file_to_s3(
                        local_path=str(local_path),
                        s3_key=s3_key,
                        make_public=True
                    )
                    
                    # DBにURLを保存（idempotent: 既にURLがあっても上書きしない）
                    if not material.texture_image_url or not material.texture_image_url.strip():
                        material.texture_image_url = public_url
                        db.commit()
                        print(f"[{idx}/{len(materials)}] ✅ 移行成功: {material.texture_image_path} -> {public_url}")
                        results["migrated"] += 1
                    else:
                        results["skipped"] += 1
                        print(f"[{idx}/{len(materials)}] ⏭️  スキップ: {material.texture_image_path} (既にURLが設定されています)")
                except Exception as e:
                    # 例外時もアプリは落ちない（画像だけスキップ）
                    results["failed"] += 1
                    error_msg = f"S3アップロードエラー: {str(e)}"
                    results["errors"].append({
                        "type": "Material.texture_image_path",
                        "id": material.id,
                        "file_path": material.texture_image_path,
                        "error": error_msg
                    })
                    print(f"[{idx}/{len(materials)}] ❌ 失敗: {error_msg}")
                    db.rollback()
                    # 例外をキャッチして続行（アプリは落ちない）
        
        except Exception as e:
            # 例外時もアプリは落ちない（画像だけスキップ）
            results["failed"] += 1
            error_msg = f"予期しないエラー: {str(e)}"
            results["errors"].append({
                "type": "Material.texture_image_path",
                "id": getattr(material, 'id', None),
                "file_path": getattr(material, 'texture_image_path', None),
                "error": error_msg
            })
            print(f"[{idx}/{len(materials)}] ❌ エラー: {error_msg}")
            # 例外をキャッチして続行（アプリは落ちない）
            try:
                db.rollback()
            except:
                pass
    
    return results


def migrate_use_example_images(
    db,
    dry_run: bool = False,
    limit: Optional[int] = None
) -> Dict[str, any]:
    """
    UseExampleテーブルのimage_pathをS3に移行
    
    Args:
        db: データベースセッション
        dry_run: ドライランモード
        limit: 処理件数の上限
    
    Returns:
        移行結果の辞書
    """
    results = {
        "total": 0,
        "migrated": 0,
        "skipped": 0,
        "failed": 0,
        "errors": []
    }
    
    # image_urlが空で、image_pathが存在するレコードを取得
    use_examples = db.query(UseExample).filter(
        ((UseExample.image_url == None) | (UseExample.image_url == "")),
        UseExample.image_path != None,
        UseExample.image_path != ""
    ).all()
    
    if limit:
        use_examples = use_examples[:limit]
    
    results["total"] = len(use_examples)
    
    print(f"\n{'='*60}")
    print(f"UseExampleテーブル: {len(use_examples)}件の画像を処理します")
    print(f"{'='*60}")
    
    for idx, use_example in enumerate(use_examples, 1):
        try:
            # ローカルパスを解決
            local_path = resolve_path(use_example.image_path) if not Path(use_example.image_path).is_absolute() else Path(use_example.image_path)
            
            # ファイルが存在するか確認
            if not local_path.exists():
                results["skipped"] += 1
                error_msg = f"ファイルが存在しません: {use_example.image_path}"
                results["errors"].append({
                    "type": "UseExample",
                    "id": use_example.id,
                    "material_id": use_example.material_id,
                    "file_path": use_example.image_path,
                    "error": error_msg
                })
                print(f"[{idx}/{len(use_examples)}] ⚠️  スキップ: {error_msg}")
                continue
            
            # S3キーを構築
            s3_key = build_s3_key(use_example.material_id, "use_cases", use_example.image_path)
            
            if dry_run:
                print(f"[{idx}/{len(use_examples)}] 🔍 ドライラン: {use_example.image_path} -> {s3_key}")
                results["migrated"] += 1
            else:
                # S3にアップロード
                try:
                    public_url = upload_file_to_s3(
                        local_path=str(local_path),
                        s3_key=s3_key,
                        make_public=True
                    )
                    
                    # DBにURLを保存
                    use_example.image_url = public_url
                    db.commit()
                    
                    print(f"[{idx}/{len(use_examples)}] ✅ 移行成功: {use_example.image_path} -> {public_url}")
                    results["migrated"] += 1
                except Exception as e:
                    results["failed"] += 1
                    error_msg = f"S3アップロードエラー: {str(e)}"
                    results["errors"].append({
                        "type": "UseExample",
                        "id": use_example.id,
                        "material_id": use_example.material_id,
                        "file_path": use_example.image_path,
                        "error": error_msg
                    })
                    print(f"[{idx}/{len(use_examples)}] ❌ 失敗: {error_msg}")
                    db.rollback()
        
        except Exception as e:
            results["failed"] += 1
            error_msg = f"予期しないエラー: {str(e)}"
            results["errors"].append({
                "type": "UseExample",
                "id": getattr(use_example, 'id', None),
                "material_id": getattr(use_example, 'material_id', None),
                "file_path": getattr(use_example, 'image_path', None),
                "error": error_msg
            })
            print(f"[{idx}/{len(use_examples)}] ❌ エラー: {error_msg}")
    
    return results


def migrate_process_example_images(
    db,
    dry_run: bool = False,
    limit: Optional[int] = None
) -> Dict[str, any]:
    """
    ProcessExampleImageテーブルのimage_pathをS3に移行
    
    Args:
        db: データベースセッション
        dry_run: ドライランモード
        limit: 処理件数の上限
    
    Returns:
        移行結果の辞書
    """
    results = {
        "total": 0,
        "migrated": 0,
        "skipped": 0,
        "failed": 0,
        "errors": []
    }
    
    # image_urlが空で、image_pathが存在するレコードを取得
    process_images = db.query(ProcessExampleImage).filter(
        ((ProcessExampleImage.image_url == None) | (ProcessExampleImage.image_url == "")),
        ProcessExampleImage.image_path != None,
        ProcessExampleImage.image_path != ""
    ).all()
    
    if limit:
        process_images = process_images[:limit]
    
    results["total"] = len(process_images)
    
    print(f"\n{'='*60}")
    print(f"ProcessExampleImageテーブル: {len(process_images)}件の画像を処理します")
    print(f"{'='*60}")
    
    for idx, process_image in enumerate(process_images, 1):
        try:
            # ローカルパスを解決
            local_path = resolve_path(process_image.image_path) if not Path(process_image.image_path).is_absolute() else Path(process_image.image_path)
            
            # ファイルが存在するか確認
            if not local_path.exists():
                results["skipped"] += 1
                error_msg = f"ファイルが存在しません: {process_image.image_path}"
                results["errors"].append({
                    "type": "ProcessExampleImage",
                    "id": process_image.id,
                    "material_id": process_image.material_id,
                    "file_path": process_image.image_path,
                    "error": error_msg
                })
                print(f"[{idx}/{len(process_images)}] ⚠️  スキップ: {error_msg}")
                continue
            
            # S3キーを構築
            s3_key = build_s3_key(process_image.material_id, "process_examples", process_image.image_path)
            
            if dry_run:
                print(f"[{idx}/{len(process_images)}] 🔍 ドライラン: {process_image.image_path} -> {s3_key}")
                results["migrated"] += 1
            else:
                # S3にアップロード
                try:
                    public_url = upload_file_to_s3(
                        local_path=str(local_path),
                        s3_key=s3_key,
                        make_public=True
                    )
                    
                    # DBにURLを保存
                    process_image.image_url = public_url
                    db.commit()
                    
                    print(f"[{idx}/{len(process_images)}] ✅ 移行成功: {process_image.image_path} -> {public_url}")
                    results["migrated"] += 1
                except Exception as e:
                    results["failed"] += 1
                    error_msg = f"S3アップロードエラー: {str(e)}"
                    results["errors"].append({
                        "type": "ProcessExampleImage",
                        "id": process_image.id,
                        "material_id": process_image.material_id,
                        "file_path": process_image.image_path,
                        "error": error_msg
                    })
                    print(f"[{idx}/{len(process_images)}] ❌ 失敗: {error_msg}")
                    db.rollback()
        
        except Exception as e:
            results["failed"] += 1
            error_msg = f"予期しないエラー: {str(e)}"
            results["errors"].append({
                "type": "ProcessExampleImage",
                "id": getattr(process_image, 'id', None),
                "material_id": getattr(process_image, 'material_id', None),
                "file_path": getattr(process_image, 'image_path', None),
                "error": error_msg
            })
            print(f"[{idx}/{len(process_images)}] ❌ エラー: {error_msg}")
    
    return results


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(description="ローカル画像をS3に移行するバッチスクリプト")
    parser.add_argument("--dry-run", action="store_true", help="ドライランモード（アップロードしない）")
    parser.add_argument("--limit", type=int, help="処理件数の上限（テスト用）")
    
    args = parser.parse_args()
    
    # S3設定の確認
    print("=" * 60)
    print("S3設定確認")
    print("=" * 60)
    config = check_s3_config()
    for key, value in config.items():
        print(f"  {key}: {value}")
    
    if not config["configured"]:
        print("\n❌ S3設定が不完全です。環境変数を確認してください。")
        sys.exit(1)
    
    # S3接続テスト
    if not args.dry_run:
        print("\n" + "=" * 60)
        print("S3接続テスト")
        print("=" * 60)
        success, message = test_s3_connection()
        if not success:
            print(f"❌ {message}")
            sys.exit(1)
        print(f"✅ {message}")
    
    # データベース初期化
    init_db()
    
    db = SessionLocal()
    try:
        all_results = {
            "image_records": {},
            "texture_images": {},
            "use_example_images": {},
            "process_example_images": {},
            "summary": {
                "total": 0,
                "migrated": 0,
                "skipped": 0,
                "failed": 0,
                "errors": []
            }
        }
        
        # 各テーブルを移行
        all_results["image_records"] = migrate_image_records(db, dry_run=args.dry_run, limit=args.limit)
        all_results["texture_images"] = migrate_texture_images(db, dry_run=args.dry_run, limit=args.limit)
        all_results["use_example_images"] = migrate_use_example_images(db, dry_run=args.dry_run, limit=args.limit)
        all_results["process_example_images"] = migrate_process_example_images(db, dry_run=args.dry_run, limit=args.limit)
        
        # サマリーを集計
        for result_key in ["image_records", "texture_images", "use_example_images", "process_example_images"]:
            result = all_results[result_key]
            all_results["summary"]["total"] += result["total"]
            all_results["summary"]["migrated"] += result["migrated"]
            all_results["summary"]["skipped"] += result["skipped"]
            all_results["summary"]["failed"] += result["failed"]
            all_results["summary"]["errors"].extend(result["errors"])
        
        # 結果を表示
        print("\n" + "=" * 60)
        print("移行結果サマリー")
        print("=" * 60)
        print(f"総対象数: {all_results['summary']['total']}件")
        if args.dry_run:
            print(f"🔍 ドライラン対象: {all_results['summary']['migrated']}件")
        else:
            print(f"✅ 移行成功: {all_results['summary']['migrated']}件")
        print(f"⚠️  スキップ: {all_results['summary']['skipped']}件")
        print(f"❌ 失敗: {all_results['summary']['failed']}件")
        
        # エラー詳細
        if all_results["summary"]["errors"]:
            print("\n" + "=" * 60)
            print("エラー詳細")
            print("=" * 60)
            for error in all_results["summary"]["errors"]:
                print(f"\nタイプ: {error['type']}")
                if 'id' in error:
                    print(f"  ID: {error['id']}")
                if 'material_id' in error:
                    print(f"  材料ID: {error['material_id']}")
                if 'file_path' in error:
                    print(f"  ファイルパス: {error['file_path']}")
                print(f"  エラー: {error['error']}")
        
        print("\n" + "=" * 60)
        if args.dry_run:
            print("🔍 ドライラン完了（実際のアップロードは行いませんでした）")
        else:
            print("✅ 移行完了")
        print("=" * 60)
    
    finally:
        db.close()


if __name__ == "__main__":
    main()

