# S3ストレージ設定ガイド

## 概要

画像ファイルをS3にアップロードし、公開URLを取得する機能を実装しました。

## 環境変数設定

### 必須環境変数

```bash
# S3バケット名
S3_BUCKET=your-bucket-name

# AWS認証情報
AWS_ACCESS_KEY_ID=your_access_key_id
AWS_SECRET_ACCESS_KEY=your_secret_access_key
```

### オプション環境変数

```bash
# AWSリージョン（デフォルト: ap-northeast-1）
AWS_REGION=ap-northeast-1

# MinIO等の互換S3エンドポイント（ローカル開発用）
S3_ENDPOINT_URL=http://localhost:9000

# CloudFront等のCDN URL（公開URLのベースURL）
S3_PUBLIC_BASE_URL=https://d1234567890.cloudfront.net
```

## Streamlit Cloudでの設定

### Secrets管理

Streamlit Cloudでは、`.streamlit/secrets.toml`ファイルまたはSecrets管理画面で環境変数を設定します。

#### 方法1: Secrets管理画面（推奨）

1. Streamlit Cloudのアプリ管理画面にアクセス
2. 「Settings」→「Secrets」を開く
3. 以下の形式でSecretsを追加：

```toml
# .streamlit/secrets.toml 形式
S3_BUCKET = "your-bucket-name"
AWS_ACCESS_KEY_ID = "your_access_key_id"
AWS_SECRET_ACCESS_KEY = "your_secret_access_key"
AWS_REGION = "ap-northeast-1"
S3_PUBLIC_BASE_URL = "https://d1234567890.cloudfront.net"
```

#### 方法2: `.streamlit/secrets.toml`ファイル（ローカル開発用）

**⚠️ 注意: このファイルはGitにコミットしないでください！**

`.gitignore`に以下を追加：

```
.streamlit/secrets.toml
```

ローカル開発時のみ使用：

```toml
# .streamlit/secrets.toml
S3_BUCKET = "your-bucket-name"
AWS_ACCESS_KEY_ID = "your_access_key_id"
AWS_SECRET_ACCESS_KEY = "your_secret_access_key"
AWS_REGION = "ap-northeast-1"
S3_PUBLIC_BASE_URL = "https://d1234567890.cloudfront.net"
```

Streamlitでは、`secrets.toml`の値が自動的に環境変数として読み込まれます。

## 使用方法

### 基本的な使用例

```python
from utils.s3_storage import upload_file_to_s3

# ローカルファイルをS3にアップロード
local_path = "static/material_textures/1_aluminum.png"
s3_key = "material_textures/1_aluminum.png"

try:
    public_url = upload_file_to_s3(
        local_path=local_path,
        s3_key=s3_key,
        make_public=True  # 公開読み取りを許可
    )
    print(f"アップロード成功: {public_url}")
except Exception as e:
    print(f"アップロードエラー: {e}")
```

### Content-Typeの自動推測

```python
# Content-Typeは自動推測されます（PNG, JPEG, WebP等）
public_url = upload_file_to_s3(
    local_path="image.png",
    s3_key="images/image.png"
)
```

### 明示的なContent-Type指定

```python
public_url = upload_file_to_s3(
    local_path="image.png",
    s3_key="images/image.png",
    content_type="image/png"
)
```

### S3設定の確認

```python
from utils.s3_storage import check_s3_config, test_s3_connection

# 設定状態を確認
config = check_s3_config()
print(f"S3設定状態: {config}")

# 接続テスト
success, message = test_s3_connection()
if success:
    print("✅ S3接続成功")
else:
    print(f"❌ S3接続失敗: {message}")
```

## セキュリティ注意事項

### ⚠️ 重要: 認証情報の管理

1. **コードに直書き禁止**: 認証情報は環境変数のみから読み込む
2. **Git管理外**: `.streamlit/secrets.toml`は`.gitignore`に追加
3. **最小権限の原則**: IAMユーザーには必要最小限の権限のみ付与
4. **定期的なローテーション**: アクセスキーは定期的に更新

### IAMポリシー例

S3アップロードに必要な最小権限：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:PutObjectAcl",
        "s3:GetObject",
        "s3:HeadBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-bucket-name/*",
        "arn:aws:s3:::your-bucket-name"
      ]
    }
  ]
}
```

### 公開読み取りの設定

`make_public=True`の場合、アップロードしたオブジェクトは公開読み取り可能になります。

**注意**: 機密情報を含むファイルは公開しないでください。

## トラブルシューティング

### エラー: "S3_BUCKET環境変数が設定されていません"

→ 環境変数`S3_BUCKET`が設定されていません。Secrets管理画面で確認してください。

### エラー: "AWS_ACCESS_KEY_ID または AWS_SECRET_ACCESS_KEY が設定されていません"

→ AWS認証情報が設定されていません。Secrets管理画面で確認してください。

### エラー: "バケットが見つかりません"

→ 指定したバケットが存在しないか、リージョンが間違っています。

### エラー: "バケットへのアクセス権限がありません"

→ IAMユーザーに適切な権限が付与されていません。IAMポリシーを確認してください。

## ローカル開発（MinIO等の互換S3）

MinIO等の互換S3を使用する場合：

```bash
# 環境変数設定
export S3_BUCKET=test-bucket
export AWS_ACCESS_KEY_ID=minioadmin
export AWS_SECRET_ACCESS_KEY=minioadmin
export S3_ENDPOINT_URL=http://localhost:9000
```

## CloudFront等のCDN使用

CloudFront等のCDNを使用する場合：

```bash
# 環境変数設定
export S3_PUBLIC_BASE_URL=https://d1234567890.cloudfront.net
```

この場合、`upload_file_to_s3()`が返すURLはCDN URLになります。

