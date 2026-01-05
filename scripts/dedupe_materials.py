"""
材料の重複を検出・削除するスクリプト（dry-run対応）
同名の材料が複数ある場合、最も古いIDを残して他を削除する方針を提示
"""
import sys
import argparse
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Tuple

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal, Material, init_db
from sqlalchemy import select, func


def find_duplicate_materials(dry_run: bool = True) -> Dict[str, List[Material]]:
    """
    重複している材料を検出
    
    Args:
        dry_run: ドライランモード（削除しない）
    
    Returns:
        重複材料の辞書（材料名 -> 材料リスト）
    """
    init_db()
    db = SessionLocal()
    
    try:
        # 全材料を取得
        materials = db.query(Material).order_by(Material.id.asc()).all()
        
        # 材料名でグループ化
        name_groups = defaultdict(list)
        for material in materials:
            name = material.name_official or material.name
            if name:
                name_groups[name].append(material)
        
        # 重複しているものだけを抽出（2件以上）
        duplicates = {name: mats for name, mats in name_groups.items() if len(mats) > 1}
        
        return duplicates
    
    finally:
        db.close()


def show_duplicate_report(duplicates: Dict[str, List[Material]], dry_run: bool = True):
    """
    重複レポートを表示
    
    Args:
        duplicates: 重複材料の辞書
        dry_run: ドライランモード
    """
    print("=" * 60)
    if dry_run:
        print("🔍 重複材料検出レポート（ドライラン）")
    else:
        print("⚠️  重複材料削除レポート")
    print("=" * 60)
    
    if not duplicates:
        print("✅ 重複している材料はありません。")
        return
    
    total_duplicates = sum(len(mats) - 1 for mats in duplicates.values())  # 各グループで1件残すので-1
    print(f"\n重複材料グループ数: {len(duplicates)}")
    print(f"削除対象件数: {total_duplicates}件（各グループで最も古いIDを残す）")
    print("\n" + "=" * 60)
    
    for name, materials in sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"\n📦 材料名: {name}")
        print(f"   重複数: {len(materials)}件")
        print(f"   材料ID: {', '.join([str(m.id) for m in materials])}")
        
        # 最も古いIDを特定（残すもの）
        keep_material = min(materials, key=lambda m: m.id)
        delete_materials = [m for m in materials if m.id != keep_material.id]
        
        print(f"   ✅ 残す: ID {keep_material.id} (作成日: {keep_material.created_at or '不明'})")
        print(f"   ❌ 削除対象: {len(delete_materials)}件")
        for m in delete_materials:
            print(f"      - ID {m.id} (作成日: {m.created_at or '不明'})")


def dedupe_materials(dry_run: bool = True) -> Tuple[int, int]:
    """
    重複材料を削除（最も古いIDを残す）
    
    Args:
        dry_run: ドライランモード（削除しない）
    
    Returns:
        (削除件数, 残存件数) のタプル
    """
    duplicates = find_duplicate_materials(dry_run=dry_run)
    
    if not duplicates:
        print("✅ 重複している材料はありません。")
        return 0, 0
    
    show_duplicate_report(duplicates, dry_run=dry_run)
    
    if dry_run:
        print("\n" + "=" * 60)
        print("🔍 ドライラン完了（実際の削除は行いませんでした）")
        print("=" * 60)
        return 0, 0
    
    # 実際の削除処理
    db = SessionLocal()
    deleted_count = 0
    
    try:
        for name, materials in duplicates.items():
            # 最も古いIDを残す
            keep_material = min(materials, key=lambda m: m.id)
            delete_materials = [m for m in materials if m.id != keep_material.id]
            
            for material in delete_materials:
                print(f"削除中: {name} (ID: {material.id})")
                db.delete(material)
                deleted_count += 1
        
        db.commit()
        print(f"\n✅ {deleted_count}件の重複材料を削除しました。")
        
        # 残存件数を確認
        remaining_count = db.query(func.count(Material.id)).scalar() or 0
        print(f"残存材料数: {remaining_count}件")
        
        return deleted_count, remaining_count
    
    except Exception as e:
        db.rollback()
        print(f"❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        return 0, 0
    
    finally:
        db.close()


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(description="材料の重複を検出・削除するスクリプト")
    parser.add_argument("--dry-run", action="store_true", default=True, help="ドライランモード（削除しない、デフォルト）")
    parser.add_argument("--execute", action="store_true", help="実際に削除を実行する（--dry-runを無効化）")
    
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    if not dry_run:
        print("⚠️  警告: 実際に削除を実行します。")
        confirm = input("続行しますか？ (yes/no): ")
        if confirm.lower() != "yes":
            print("キャンセルしました。")
            return
    
    deleted_count, remaining_count = dedupe_materials(dry_run=dry_run)
    
    if not dry_run:
        print("\n" + "=" * 60)
        print(f"✅ 削除完了: {deleted_count}件削除、{remaining_count}件残存")
        print("=" * 60)


if __name__ == "__main__":
    main()

