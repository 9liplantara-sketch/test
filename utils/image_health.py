"""
画像の健康状態をチェックするモジュール
黒画像、壊れ画像、欠損画像を検出する
"""
from pathlib import Path
from PIL import Image
from typing import Optional, Tuple, Dict
import os


def check_image_health(image_path: str, project_root: Optional[Path] = None) -> Dict[str, any]:
    """
    画像の健康状態をチェック
    
    Args:
        image_path: 画像ファイルのパス（絶対パスまたは相対パス）
        project_root: プロジェクトルートのパス（相対パス解決用）
    
    Returns:
        {
            "status": "ok" | "missing" | "corrupt" | "decode_error" | "zero_byte" | "blackout",
            "reason": str,  # エラーの理由
            "file_path": str,  # 解決されたファイルパス
            "file_size": int,  # ファイルサイズ（バイト）
            "image_size": Tuple[int, int] | None,  # 画像サイズ (width, height)
            "mode": str | None,  # 画像モード（RGB, RGBA等）
            "average_brightness": float | None,  # 平均輝度（0-255）
        }
    """
    result = {
        "status": "ok",
        "reason": "",
        "file_path": "",
        "file_size": 0,
        "image_size": None,
        "mode": None,
        "average_brightness": None,
    }
    
    # パス解決
    if project_root is None:
        project_root = Path.cwd()
    else:
        project_root = Path(project_root)
    
    # 絶対パスか相対パスかを判定
    if Path(image_path).is_absolute():
        resolved_path = Path(image_path)
    else:
        # 相対パスの場合、プロジェクトルートからの相対パスとして解決
        resolved_path = project_root / image_path
    
    result["file_path"] = str(resolved_path)
    
    # 1. ファイル存在チェック
    if not resolved_path.exists():
        result["status"] = "missing"
        result["reason"] = f"ファイルが存在しません: {resolved_path}"
        return result
    
    # 2. ファイルサイズチェック
    file_size = resolved_path.stat().st_size
    result["file_size"] = file_size
    
    if file_size == 0:
        result["status"] = "zero_byte"
        result["reason"] = "ファイルサイズが0バイトです"
        return result
    
    if file_size < 100:  # 極端に小さいファイル
        result["status"] = "corrupt"
        result["reason"] = f"ファイルサイズが異常に小さいです: {file_size}バイト"
        return result
    
    # 3. PILで開けるかチェック
    try:
        img = Image.open(resolved_path)
        img.load()  # 画像を完全に読み込む（遅延読み込みのため）
    except Exception as e:
        result["status"] = "decode_error"
        result["reason"] = f"画像のデコードに失敗しました: {str(e)}"
        return result
    
    # 4. 画像情報を取得
    result["image_size"] = img.size
    result["mode"] = img.mode
    
    # 5. 黒画像チェック（平均輝度が極端に低い場合）
    try:
        # RGBまたはRGBAに変換してから平均輝度を計算
        if img.mode in ("RGBA", "LA", "P"):
            # 透明部分がある場合は白背景に合成してからチェック
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                rgb_img.paste(img, mask=img.split()[3])  # alphaチャンネルをマスクとして使用
            elif img.mode == "LA":
                rgb_img.paste(img.convert("RGB"), mask=img.split()[1])
            else:  # P (パレット)
                rgb_img = img.convert("RGB")
            img_for_check = rgb_img
        else:
            img_for_check = img.convert("RGB")
        
        # 平均輝度を計算
        import numpy as np
        img_array = np.array(img_for_check)
        average_brightness = np.mean(img_array)
        result["average_brightness"] = float(average_brightness)
        
        # 平均輝度が10未満の場合は「黒画像」と判定
        if average_brightness < 10:
            result["status"] = "blackout"
            result["reason"] = f"画像がほぼ黒です（平均輝度: {average_brightness:.2f}）"
            return result
        
        # 平均輝度が255に近い場合は「白画像」の可能性もあるが、今回はOKとする
        
    except Exception as e:
        # 輝度計算に失敗しても、画像自体は読めるので警告のみ
        result["reason"] = f"輝度計算に失敗しましたが、画像は読み込めました: {str(e)}"
    
    # すべてのチェックを通過
    result["status"] = "ok"
    result["reason"] = "画像は正常です"
    return result


def normalize_image_path(file_path: str, project_root: Optional[Path] = None) -> str:
    """
    画像パスを正規化（プロジェクトルートからの相対パスに統一）
    
    Args:
        file_path: 画像ファイルのパス（絶対パスまたは相対パス）
        project_root: プロジェクトルートのパス
    
    Returns:
        正規化された相対パス（例: "uploads/material_123.png"）
    """
    if project_root is None:
        project_root = Path.cwd()
    else:
        project_root = Path(project_root)
    
    path = Path(file_path)
    
    # 絶対パスの場合
    if path.is_absolute():
        try:
            # プロジェクトルートからの相対パスに変換
            relative = path.relative_to(project_root)
            return str(relative).replace("\\", "/")  # Windowsパスを統一
        except ValueError:
            # プロジェクトルート外の場合は、そのまま返す（後方互換）
            return str(path)
    
    # 相対パスの場合、そのまま返す（既に正規化されている想定）
    return str(path).replace("\\", "/")


def resolve_image_path(file_path: str, project_root: Optional[Path] = None) -> Path:
    """
    画像パスを解決（絶対Pathオブジェクトを返す）
    
    Args:
        file_path: 画像ファイルのパス（絶対パスまたは相対パス）
        project_root: プロジェクトルートのパス
    
    Returns:
        解決された絶対Pathオブジェクト
    """
    if project_root is None:
        project_root = Path.cwd()
    else:
        project_root = Path(project_root)
    
    path = Path(file_path)
    
    # 絶対パスの場合
    if path.is_absolute():
        return path
    
    # 相対パスの場合、プロジェクトルートからの相対パスとして解決
    return project_root / path

