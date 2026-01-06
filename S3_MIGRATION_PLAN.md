# S3画像移行計画

## STEP 1: 現状把握

### 画像ファイルの保存場所

| ディレクトリ | 用途 | 生成元 |
|------------|------|--------|
| `uploads/` | ユーザーアップロード画像 | FastAPI (`main.py`) |
| `static/material_textures/` | テクスチャ画像（1024x1024） | `scripts/generate_images.py` |
| `static/use_cases/` | 用途写真（1280x720） | `scripts/generate_images.py` |
| `static/process_examples/` | 加工例画像（材料別、1280x720） | `scripts/generate_images.py` |
| `static/generated/` | 自動生成画像（元素画像等） | `image_generator.py`, `utils/ensure_assets.py` |
| `static/images/` | 静的画像ファイル | 手動配置 |

### DBの画像モデル

| テーブル/カラム | 型 | 現在の値 | 用途 |
|---------------|-----|---------|------|
| `Image.file_path` | String(500) | 相対パス（例: `"1_material.webp"`） | 材料の汎用画像 |
| `Material.texture_image_path` | String(500) | 相対パス（例: `"static/material_textures/1_aluminum.png"`） | テクスチャ画像 |
| `UseExample.image_path` | String(500) | 相対パス | 用途写真 |
| `ProcessExampleImage.image_path` | String(500) | 相対パス | 加工例画像 |

### 画像表示の統一関数

| 関数 | ファイル | 用途 |
|------|---------|------|
| `get_material_image()` | `utils/image_display.py` | 材料画像取得（健康チェック付き） |
| `display_material_image()` | `utils/image_display.py` | 材料画像表示（自動修復対応） |
| `display_use_example_image()` | `utils/use_example_display.py` | 用途例画像表示 |
| `resolve_path()` | `utils/paths.py` | パス解決（プロジェクトルート基準） |

### 画像参照箇所（主要）

- `app.py`: 材料一覧・検索・詳細表示（`get_material_image()`使用）
- `material_detail_tabs.py`: タブ表示（テクスチャ・用途・加工例）
- `card_generator.py`: 素材カード生成（`get_image_path()`, `get_base64_image()`）
- `main.py`: FastAPI画像アップロード（`uploads/`に保存）
- `scripts/generate_images.py`: 画像生成スクリプト（S3アップロード未対応）

---

## STEP 2: S3移行設計（最小変更）

### 設計方針

1. **後方互換性を維持**: 移行期間中はローカルパスとS3 URLの両方に対応
2. **統一インターフェース**: すべての画像取得を`utils/image_url.py`経由に統一
3. **段階的移行**: 既存データはそのまま動作、新規データからS3に保存

### データベーススキーマ変更

#### 変更1: `Image`テーブルに`url`カラム追加

```python
class Image(Base):
    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    file_path = Column(String(500))  # 後方互換のためNULL許可に変更
    url = Column(String(1000))  # S3 URL（新規追加）
    image_type = Column(String(50))
    description = Column(Text)
```

#### 変更2: その他の画像パスカラムも`url`追加

- `Material.texture_image_path` → `Material.texture_image_url`（追加、既存は保持）
- `UseExample.image_path` → `UseExample.image_url`（追加、既存は保持）
- `ProcessExampleImage.image_path` → `ProcessExampleImage.image_url`（追加、既存は保持）

**注意**: 既存カラムは削除せず、移行完了まで保持

### 統一画像URL解決関数

**新規作成**: `utils/image_url.py`

```python
def get_image_url(file_path: Optional[str] = None, url: Optional[str] = None) -> Optional[str]:
    """
    画像URLを取得（S3優先、フォールバックでローカルパス）
    
    Args:
        file_path: ローカルパス（後方互換）
        url: S3 URL（優先）
    
    Returns:
        画像URL（S3 URL または ローカルパス解決後のURL）
    """
    # 1. S3 URLが存在する場合はそれを返す
    if url:
        return url
    
    # 2. ローカルパスの場合、相対パスを解決して返す
    if file_path:
        # ローカル開発環境: 相対パスをそのまま返す（Streamlitが解決）
        # 本番環境: 必要に応じてCDN URLに変換
        return file_path
    
    return None
```

### 変更対象ファイル一覧

#### 優先度: 高（必須変更）

1. **`database.py`**
   - `Image.url`カラム追加
   - `Material.texture_image_url`カラム追加
   - `UseExample.image_url`カラム追加
   - `ProcessExampleImage.image_url`カラム追加
   - `init_db()`でALTER TABLE実行

2. **`utils/image_url.py`**（新規作成）
   - `get_image_url()`: 統一URL解決関数
   - `is_s3_url()`: S3 URL判定
   - `upload_to_s3()`: S3アップロード関数（将来用）

3. **`utils/image_display.py`**
   - `get_material_image()`: `url`カラムを優先参照
   - `display_material_image()`: URL解決を`get_image_url()`経由に変更

4. **`utils/use_example_display.py`**
   - `display_use_example_image()`: `image_url`を優先参照

5. **`material_detail_tabs.py`**
   - テクスチャ・用途・加工例画像の表示を`get_image_url()`経由に変更

6. **`card_generator.py`**
   - `get_image_path()` → `get_image_url()`に置き換え
   - S3 URL対応

7. **`main.py`**（FastAPI）
   - 画像アップロード時にS3に保存（オプション）
   - `url`カラムにS3 URLを保存

8. **`scripts/generate_images.py`**
   - 画像生成後にS3アップロード（オプション）
   - `url`カラムにS3 URLを保存

#### 優先度: 中（段階的変更）

9. **`app.py`**
   - 画像表示箇所を`get_image_url()`経由に変更

10. **`image_generator.py`**
    - 画像生成時にS3アップロード（オプション）

#### 優先度: 低（将来対応）

11. **署名付きURL対応**
    - `utils/image_url.py`に`get_signed_url()`追加
    - プライベートバケット対応

---

## STEP 3: 実装手順

### Phase 1: スキーマ拡張（後方互換）

1. `database.py`に`url`カラム追加（既存カラムは保持）
2. `init_db()`でALTER TABLE実行
3. 既存データは`file_path`のまま動作

### Phase 2: 統一インターフェース作成

1. `utils/image_url.py`を作成
2. 既存の画像取得関数を段階的に置き換え

### Phase 3: S3アップロード実装

1. `boto3`を`requirements.txt`に追加
2. S3設定を環境変数から取得
3. 新規画像生成時にS3アップロード

### Phase 4: 既存データ移行

1. 移行スクリプト作成（`scripts/migrate_images_to_s3.py`）
2. 既存画像をS3にアップロード
3. DBの`url`カラムを更新

---

## 環境変数設定

```bash
# S3設定
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=ap-northeast-1
S3_BUCKET_NAME=material-db-images
S3_BASE_URL=https://material-db-images.s3.ap-northeast-1.amazonaws.com

# 移行モード（開発時はローカル優先）
USE_S3=false  # trueにするとS3を使用
```

---

## 変更ファイル一覧（まとめ）

### 新規作成
- `utils/image_url.py` - 統一画像URL解決
- `scripts/migrate_images_to_s3.py` - 既存画像移行スクリプト（将来）

### 変更
- `database.py` - スキーマ拡張
- `utils/image_display.py` - URL解決対応
- `utils/use_example_display.py` - URL解決対応
- `material_detail_tabs.py` - URL解決対応
- `card_generator.py` - URL解決対応
- `main.py` - S3アップロード対応
- `scripts/generate_images.py` - S3アップロード対応
- `app.py` - 画像表示をURL解決経由に変更
- `requirements.txt` - `boto3`追加

### 設計のポイント

1. **最小変更**: 既存の`file_path`は保持し、`url`を追加するだけ
2. **後方互換**: `url`が空の場合は`file_path`を使用（ローカル開発環境でも動作）
3. **拡張可能**: 将来の署名付きURLにも対応可能な設計
4. **段階的移行**: 新規データからS3、既存データは後で移行


