#!/usr/bin/env python3
"""
画像解決のデバッグスクリプト
アプリを起動しなくても、DBから全materialsを読み、各materialで primary/space/product の
get_material_image_ref を呼び、chosen_branch と final_src_type と final_path_exists をprintする
"""
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal, Material
from utils.image_display import get_material_image_ref

def main():
    db = SessionLocal()
    try:
        materials = db.query(Material).all()
        print(f"=== 画像解決デバッグ (全{len(materials)}件) ===\n")
        
        for material in materials:
            material_name = material.name_official or material.name or "N/A"
            print(f"【{material_name}】")
            
            # primary/space/product それぞれをチェック
            for kind in ["primary", "space", "product"]:
                src, debug = get_material_image_ref(material, kind, project_root)
                
                chosen_branch = debug.get('chosen_branch', 'unknown')
                final_src_type = debug.get('final_src_type', 'unknown')
                final_path_exists = debug.get('final_path_exists', False)
                
                status = "✅" if (chosen_branch == "local" and final_path_exists) or (chosen_branch in ["db_url", "base_url"] and final_src_type == "url") else "❌"
                
                print(f"  {kind:8s}: {status} branch={chosen_branch:15s} type={final_src_type:6s} exists={final_path_exists}")
                
                if not src:
                    print(f"    ⚠️  画像が見つかりませんでした")
                    if debug.get('candidate_paths'):
                        print(f"    候補パス: {debug['candidate_paths'][:3]}")
            
            print()
        
        # サマリー
        print("=== サマリー ===")
        local_count = 0
        url_count = 0
        not_found_count = 0
        
        for material in materials:
            src, debug = get_material_image_ref(material, "primary", project_root)
            chosen_branch = debug.get('chosen_branch', 'unknown')
            final_path_exists = debug.get('final_path_exists', False)
            
            if chosen_branch == "local" and final_path_exists:
                local_count += 1
            elif chosen_branch in ["db_url", "base_url"]:
                url_count += 1
            else:
                not_found_count += 1
        
        print(f"✅ local (存在確認済み): {local_count}件")
        print(f"🌐 URL参照: {url_count}件")
        print(f"❌ 見つからない: {not_found_count}件")
        
        if not_found_count > 0:
            print(f"\n⚠️  {not_found_count}件の素材で画像が見つかりませんでした")
            return 1
        else:
            print(f"\n✅ 全素材で画像が解決されました")
            return 0
            
    finally:
        db.close()

if __name__ == "__main__":
    sys.exit(main())

