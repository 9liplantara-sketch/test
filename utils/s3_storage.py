"""
S3ストレージユーティリティ
画像ファイルをS3にアップロードし、公開URLを取得
"""
import os
import mimetypes
from pathlib import Path
from typing import Optional, Tuple
import boto3
from botocore.exceptions import ClientError, BotoCoreError


# 環境変数からS3設定を取得
S3_BUCKET = os.getenv("S3_BUCKET", "")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-1")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", None)  # MinIO等の互換S3用
S3_PUBLIC_BASE_URL = os.getenv("S3_PUBLIC_BASE_URL", None)  # CloudFront等のCDN URL


def get_s3_client():
    """
    S3クライアントを取得
    
    Returns:
        boto3.client: S3クライアント
    """
    if not S3_BUCKET:
        raise ValueError("S3_BUCKET環境変数が設定されていません")
    
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        raise ValueError("AWS_ACCESS_KEY_ID または AWS_SECRET_ACCESS_KEY が設定されていません")
    
    client_kwargs = {
        "aws_access_key_id": AWS_ACCESS_KEY_ID,
        "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
        "region_name": AWS_REGION,
    }
    
    # MinIO等の互換S3エンドポイントがある場合
    if S3_ENDPOINT_URL:
        client_kwargs["endpoint_url"] = S3_ENDPOINT_URL
    
    return boto3.client("s3", **client_kwargs)


def guess_content_type(file_path: str) -> Optional[str]:
    """
    ファイルパスからContent-Typeを推測
    
    Args:
        file_path: ファイルパス
    
    Returns:
        Content-Type文字列（例: "image/png"）、推測できない場合はNone
    """
    content_type, _ = mimetypes.guess_type(file_path)
    
    # 推測できない場合のフォールバック
    if not content_type:
        ext = Path(file_path).suffix.lower()
        content_type_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
        }
        content_type = content_type_map.get(ext)
    
    return content_type


def build_public_url(s3_key: str) -> str:
    """
    S3オブジェクトの公開URLを構築
    
    Args:
        s3_key: S3オブジェクトキー（パス）
    
    Returns:
        公開URL
    """
    # S3_PUBLIC_BASE_URLが設定されている場合（CloudFront等のCDN）
    if S3_PUBLIC_BASE_URL:
        base_url = S3_PUBLIC_BASE_URL.rstrip("/")
        s3_key_clean = s3_key.lstrip("/")
        return f"{base_url}/{s3_key_clean}"
    
    # AWS標準のURL形式
    # https://{bucket}.s3.{region}.amazonaws.com/{key}
    # または
    # https://s3.{region}.amazonaws.com/{bucket}/{key}
    if S3_ENDPOINT_URL:
        # MinIO等の互換S3の場合
        base_url = S3_ENDPOINT_URL.rstrip("/")
        s3_key_clean = s3_key.lstrip("/")
        return f"{base_url}/{S3_BUCKET}/{s3_key_clean}"
    else:
        # AWS標準形式
        s3_key_clean = s3_key.lstrip("/")
        return f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{s3_key_clean}"


def upload_file_to_s3(
    local_path: str,
    s3_key: str,
    content_type: Optional[str] = None,
    make_public: bool = True
) -> str:
    """
    ローカルファイルをS3にアップロードし、公開URLを返す
    
    Args:
        local_path: ローカルファイルパス
        s3_key: S3オブジェクトキー（パス、例: "images/material_1.png"）
        content_type: Content-Type（Noneの場合は自動推測）
        make_public: 公開読み取りを許可するか（デフォルト: True）
    
    Returns:
        公開URL
    
    Raises:
        ValueError: 環境変数が設定されていない場合
        FileNotFoundError: ローカルファイルが存在しない場合
        ClientError: S3アップロードエラー
    """
    # 環境変数チェック
    if not S3_BUCKET:
        raise ValueError("S3_BUCKET環境変数が設定されていません")
    
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        raise ValueError("AWS_ACCESS_KEY_ID または AWS_SECRET_ACCESS_KEY が設定されていません")
    
    # ローカルファイルの存在確認
    local_file = Path(local_path)
    if not local_file.exists():
        raise FileNotFoundError(f"ローカルファイルが見つかりません: {local_path}")
    
    # Content-Typeの推測
    if not content_type:
        content_type = guess_content_type(local_path)
    
    # S3クライアントを取得
    s3_client = get_s3_client()
    
    # アップロード時のメタデータ
    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type
    
    # 公開読み取りを許可する場合
    if make_public:
        extra_args["ACL"] = "public-read"
    
    try:
        # ファイルをアップロード
        s3_client.upload_file(
            str(local_file),
            S3_BUCKET,
            s3_key,
            ExtraArgs=extra_args if extra_args else None
        )
        
        # 公開URLを構築して返す
        public_url = build_public_url(s3_key)
        return public_url
        
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        raise ClientError(
            {
                "Error": {
                    "Code": error_code,
                    "Message": f"S3アップロードエラー: {error_message}",
                }
            },
            "upload_file"
        ) from e
    except BotoCoreError as e:
        raise RuntimeError(f"S3接続エラー: {str(e)}") from e
    except Exception as e:
        raise RuntimeError(f"予期しないエラー: {str(e)}") from e


def check_s3_config() -> dict:
    """
    S3設定の状態を確認
    
    Returns:
        設定状態の辞書
    """
    config_status = {
        "s3_bucket": bool(S3_BUCKET),
        "aws_access_key_id": bool(AWS_ACCESS_KEY_ID),
        "aws_secret_access_key": bool(AWS_SECRET_ACCESS_KEY),
        "aws_region": AWS_REGION,
        "s3_endpoint_url": bool(S3_ENDPOINT_URL),
        "s3_public_base_url": bool(S3_PUBLIC_BASE_URL),
        "configured": bool(S3_BUCKET and AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY),
    }
    return config_status


def test_s3_connection() -> Tuple[bool, str]:
    """
    S3接続をテスト
    
    Returns:
        (成功フラグ, メッセージ) のタプル
    """
    try:
        s3_client = get_s3_client()
        # バケットの存在確認
        s3_client.head_bucket(Bucket=S3_BUCKET)
        return True, "S3接続成功"
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "404":
            return False, f"バケットが見つかりません: {S3_BUCKET}"
        elif error_code == "403":
            return False, f"バケットへのアクセス権限がありません: {S3_BUCKET}"
        else:
            return False, f"S3接続エラー: {error_code}"
    except Exception as e:
        return False, f"S3接続エラー: {str(e)}"

