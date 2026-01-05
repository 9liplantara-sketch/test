# S3画像移行 - 変更対象ファイル一覧

## 現状把握サマリー

### 画像保存場所
- `uploads/` - ユーザーアップロード
- `static/material_textures/` - テクスチャ（生成）
- `static/use_cases/` - 用途写真（生成）
- `static/process_examples/` - 加工例（生成）
- `static/generated/` - 自動生成（元素等）
- `static/images/` - 静的ファイル

### DB画像モデル
- `Image.file_path` (String(500)) - 材料汎用画像
- `Material.texture_image_path` (String(500)) - テクスチャ
- `UseExample.image_path` (String(500)) - 用途写真
- `ProcessExampleImage.image_path` (String(500)) - 加工例

### 統一画像関数
- `utils/image_display.py`: `get_material_image()`, `display_material_image()`
- `utils/use_example_display.py`: `display_use_example_image()`
- `utils/paths.py`: `resolve_path()`

---

## 変更対象ファイル（優先順位順）

### 🔴 必須変更（Phase 1: スキーマ拡張）

1. **`database.py`**
   - `Image.url` カラム追加（既存`file_path`は保持）
   - `Material.texture_image_url` カラム追加
   - `UseExample.image_url` カラム追加
   - `ProcessExampleImage.image_url` カラム追加
   - `init_db()`でALTER TABLE実行

### 🟡 必須変更（Phase 2: 統一インターフェース）

2. **`utils/image_url.py`** ⭐ 新規作成
   - `get_image_url(file_path, url)` - 統一URL解決（S3優先、ローカルフォールバック）
   - `is_s3_url(url)` - S3 URL判定
   - `upload_to_s3()` - S3アップロード（将来用）

3. **`utils/image_display.py`**
   - `get_material_image()`: `url`カラムを優先参照
   - `display_material_image()`: `get_image_url()`経由に変更

4. **`utils/use_example_display.py`**
   - `display_use_example_image()`: `image_url`を優先参照

5. **`material_detail_tabs.py`**
   - テクスチャ画像表示: `get_image_url()`経由
   - 用途写真表示: `get_image_url()`経由
   - 加工例画像表示: `get_image_url()`経由

6. **`card_generator.py`**
   - `get_image_path()` → `get_image_url()`に置き換え
   - S3 URL対応

### 🟢 推奨変更（Phase 3: S3アップロード）

7. **`main.py`** (FastAPI)
   - 画像アップロード時にS3保存（オプション）
   - `url`カラムにS3 URL保存

8. **`scripts/generate_images.py`**
   - 画像生成後にS3アップロード（オプション）
   - `url`カラムにS3 URL保存

9. **`app.py`**
   - 画像表示箇所を`get_image_url()`経由に変更（段階的）

10. **`requirements.txt`**
    - `boto3>=1.28.0` 追加

---

## 設計のポイント

### 1. 後方互換性
```python
# 既存コードはそのまま動作
image_url = get_image_url(file_path=img.file_path, url=img.url)
# → urlが空ならfile_pathを使用（ローカル開発環境でも動作）
```

### 2. 段階的移行
- 新規データ: S3に保存、`url`カラムに保存
- 既存データ: `file_path`のまま動作（後で移行スクリプトで一括移行）

### 3. 拡張可能
```python
# 将来の署名付きURL対応
def get_signed_url(url: str, expires_in: int = 3600) -> str:
    # プライベートバケット対応
    pass
```

---

## 環境変数

```bash
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=ap-northeast-1
S3_BUCKET_NAME=material-db-images
S3_BASE_URL=https://material-db-images.s3.ap-northeast-1.amazonaws.com
USE_S3=false  # 開発時はfalse（ローカル優先）
```

---

## 実装順序

1. ✅ スキーマ拡張（`database.py`）
2. ✅ 統一インターフェース作成（`utils/image_url.py`）
3. ✅ 既存関数の段階的置き換え
4. ⏳ S3アップロード実装（新規データから）
5. ⏳ 既存データ移行スクリプト（将来）

