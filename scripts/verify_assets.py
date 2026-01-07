#!/usr/bin/env python3
"""
画像アセットの検証スクリプト
DBから materials を読み、safe_slug を取得し、primary/space/product が解決できるか検査
"""
import sys
import os
from pathlib import Path

# プロジェクトルートを取得
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal, Material
from utils.image_display import get_material_image_ref, safe_slug_from_material


def verify_assets(project_root: Path, strict: bool = False) -> tuple[bool, list[str]]:
    """
    画像アセットの検証
    
    Args:
        project_root: プロジェクトルートのパス
        strict: Trueの場合、local branch時はexists必須
    
    Returns:
        (success: bool, errors: list[str])
    """
    errors = []
    db = SessionLocal()
    
    try:
        materials = db.query(Material).all()
        print(f"📦 材料数: {len(materials)}")
        
        if len(materials) == 0:
            print("⚠️  材料が0件です")
            return True, []  # 空DBはエラーとしない
        
        missing_count = 0
        for material in materials:
            material_name = getattr(material, 'name_official', None) or getattr(material, 'name', None) or "N/A"
            safe_slug = safe_slug_from_material(material)
            
            for kind in ["primary", "space", "product"]:
                src, debug = get_material_image_ref(material, kind, project_root)
                chosen_branch = debug.get("chosen_branch", "none")
                final_src_type = debug.get("final_src_type")
                
                # strictモードの場合、local branch時はexists必須
                if strict and chosen_branch == "local":
                    if src is None or not (isinstance(src, Path) and src.exists()):
                        missing_count += 1
                        error_msg = f"❌ {material_name} ({safe_slug}) {kind}: local branchだが画像が見つからない"
                        errors.append(error_msg)
                        print(error_msg)
                        print(f"   candidate_paths: {debug.get('candidate_paths', [])}")
                        print(f"   failed_paths: {debug.get('failed_paths', [])}")
                elif src is None:
                    # 画像が見つからない場合（警告のみ、エラーにはしない）
                    print(f"⚠️  {material_name} ({safe_slug}) {kind}: 画像が見つかりません (branch: {chosen_branch})")
                else:
                    # 画像が見つかった場合
                    branch_icon = {
                        "db_url": "🌐",
                        "base_url": "🔗",
                        "local": "📁",
                        "legacy_jp": "📂",
                    }.get(chosen_branch, "❓")
                    print(f"✅ {material_name} ({safe_slug}) {kind}: {branch_icon} {chosen_branch} ({final_src_type})")
        
        if missing_count > 0:
            print(f"\n❌ {missing_count}件の画像が見つかりません（strict mode）")
            return False, errors
        else:
            print(f"\n✅ すべての画像が解決できました")
            return True, errors
    
    except Exception as e:
        error_msg = f"❌ 検証中にエラーが発生: {e}"
        errors.append(error_msg)
        print(error_msg)
        import traceback
        traceback.print_exc()
        return False, errors
    
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="画像アセットの検証")
    parser.add_argument("--strict", action="store_true", help="strict mode: local branch時はexists必須")
    parser.add_argument("--project-root", type=str, default=None, help="プロジェクトルートのパス")
    
    args = parser.parse_args()
    
    project_root_path = Path(args.project_root) if args.project_root else Path.cwd()
    
    success, errors = verify_assets(project_root_path, strict=args.strict)
    
    if not success:
        print("\n" + "=" * 80)
        print("検証失敗:")
        for error in errors:
            print(f"  {error}")
        sys.exit(1)
    else:
        sys.exit(0)

