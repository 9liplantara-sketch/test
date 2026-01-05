"""
画像診断モジュール（Streamlit UI用）
"""
import streamlit as st
from pathlib import Path
from PIL import Image as PILImage
from typing import List, Dict
from utils.image_health import check_image_health, resolve_image_path, normalize_image_path
from database import Material, Image as ImageModel


def show_image_diagnostics(materials: List[Material], project_root: Path = None):
    """
    画像診断モードを表示
    
    Args:
        materials: 材料リスト
        project_root: プロジェクトルートのパス
    """
    if project_root is None:
        project_root = Path.cwd()
    
    st.markdown("## 🔍 画像診断モード")
    st.info("このモードでは、すべての材料画像の健康状態を診断します。")
    
    # 統計情報
    total_materials = len(materials)
    total_images = sum(len(m.images) for m in materials if m.images)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("材料数", total_materials)
    with col2:
        st.metric("画像総数", total_images)
    with col3:
        materials_with_images = sum(1 for m in materials if m.images)
        st.metric("画像あり材料", materials_with_images)
    
    st.markdown("---")
    
    # 材料ごとに診断
    if not materials:
        st.warning("材料が登録されていません。")
        return
    
    # 診断結果の集計
    status_counts = {
        "ok": 0,
        "missing": 0,
        "corrupt": 0,
        "decode_error": 0,
        "zero_byte": 0,
        "blackout": 0,
    }
    
    for material in materials:
        st.markdown(f"### 📦 {material.name_official or material.name} (ID: {material.id})")
        
        if not material.images:
            st.warning("⚠️ 画像が登録されていません")
            st.markdown("---")
            continue
        
        # 画像ごとに診断
        for idx, img in enumerate(material.images):
            st.markdown(f"#### 画像 {idx+1}: `{img.file_path}`")
            
            # パス正規化
            normalized_path = normalize_image_path(img.file_path, project_root)
            resolved_path = resolve_image_path(img.file_path, project_root)
            
            # 健康状態チェック
            health = check_image_health(img.file_path, project_root)
            status_counts[health["status"]] += 1
            
            # 診断結果を表示
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # ステータスバッジ
                status_colors = {
                    "ok": "🟢",
                    "missing": "🔴",
                    "corrupt": "🟠",
                    "decode_error": "🟠",
                    "zero_byte": "🔴",
                    "blackout": "⚫",
                }
                status_labels = {
                    "ok": "正常",
                    "missing": "ファイル不存在",
                    "corrupt": "破損",
                    "decode_error": "デコードエラー",
                    "zero_byte": "0バイト",
                    "blackout": "黒画像",
                }
                
                status_emoji = status_colors.get(health["status"], "❓")
                status_label = status_labels.get(health["status"], health["status"])
                
                st.markdown(f"**状態**: {status_emoji} {status_label}")
                
                if health["reason"]:
                    st.caption(f"理由: {health['reason']}")
                
                # 詳細情報
                with st.expander("詳細情報"):
                    st.json({
                        "DB保存パス": img.file_path,
                        "正規化パス": normalized_path,
                        "解決パス": str(resolved_path),
                        "ファイルサイズ": f"{health['file_size']:,} バイト",
                        "画像サイズ": health["image_size"],
                        "画像モード": health["mode"],
                        "平均輝度": health["average_brightness"],
                    })
            
            with col2:
                # 画像プレビュー
                if health["status"] == "ok":
                    try:
                        pil_img = PILImage.open(resolved_path)
                        st.image(pil_img, caption="プレビュー", width=150)
                    except Exception as e:
                        st.error(f"プレビューエラー: {e}")
                else:
                    st.error("画像を表示できません")
            
            st.markdown("---")
    
    # 診断結果のサマリー
    st.markdown("## 📊 診断結果サマリー")
    
    summary_cols = st.columns(6)
    for idx, (status, count) in enumerate(status_counts.items()):
        with summary_cols[idx]:
            st.metric(
                status_labels.get(status, status),
                count,
                delta=None if status == "ok" else count
            )
    
    # 原因候補の提示
    st.markdown("---")
    st.markdown("## 🔍 原因候補")
    
    issues = []
    if status_counts["missing"] > 0:
        issues.append("**ファイル不存在**: 画像ファイルが削除されているか、パスが間違っています")
    if status_counts["blackout"] > 0:
        issues.append("**黒画像**: 画像生成時に透明背景が黒に合成されている可能性があります")
    if status_counts["corrupt"] > 0 or status_counts["decode_error"] > 0:
        issues.append("**破損/デコードエラー**: 画像ファイルが破損しているか、形式が正しくありません")
    if status_counts["zero_byte"] > 0:
        issues.append("**0バイト**: 画像生成が失敗している可能性があります")
    
    if issues:
        for issue in issues:
            st.warning(issue)
    else:
        st.success("✅ すべての画像が正常です！")
    
    return {
        "status_counts": status_counts,
        "total_images": total_images,
        "issues": issues,
    }


