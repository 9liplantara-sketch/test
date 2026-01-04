# 画像表示問題の根本解決 - 修正サマリー

## 修正日: 2026年1月4日

## 問題
- 材料カードの画像が読み込まれず、生成画像もブラックアウトして表示される
- Streamlit Cloud環境で再起動後に画像が消える

## 原因（診断結果）

### 1. パス解決の問題
- DBに保存されているパスが絶対パスと相対パスが混在
- Streamlit Cloudでは実行ディレクトリが `/mount/src/...` になるため、絶対パスが機能しない

### 2. 黒画像の問題
- RGBA/LA/Pモードの画像をRGBに変換する際、透明部分が黒に合成される
- WebP形式が環境依存で読み込めない場合がある

### 3. 画像生成の問題
- 生成時に背景色が設定されていない
- 透明部分がある画像がそのまま保存される

### 4. 自動修復の欠如
- 画像が欠損・破損していても自動修復されない
- 起動時に画像の健康状態をチェックしていない

## 実装した修正

### STEP A: 原因切り分け

#### A1: 画像の保存先と参照パスを洗い出す
- **確認結果**:
  - 画像は `uploads/` ディレクトリに保存
  - DBの`Image`テーブルの`file_path`にはファイル名のみ（相対パス）が保存
  - ただし、絶対パスが混在している可能性

#### A2: 黒画像の原因を分類するチェック関数
- **`utils/image_health.py`**を新規作成
  - `check_image_health()`: 画像の健康状態をチェック
    - ファイル存在チェック
    - ファイルサイズチェック（0バイト検出）
    - PILで開けるかチェック
    - 黒画像チェック（平均輝度が10未満）
  - `normalize_image_path()`: パスを正規化（相対パスに統一）
  - `resolve_image_path()`: パスを解決（絶対Pathオブジェクトを返す）

#### A3: Streamlit上で診断モードを追加
- **`utils/image_diagnostics.py`**を新規作成
  - `show_image_diagnostics()`: すべての材料画像の健康状態を診断
  - サイドバーに「🔍 画像診断モード」チェックボックスを追加
  - 材料ごとに画像の状態を表示（OK/黒画像/欠損/破損など）

### STEP B: 恒久修正

#### B1: パス解決の正規化
- **`utils/image_health.py`**の`normalize_image_path()`で実装
  - すべての画像パスを「プロジェクトルートからの相対パス」に統一
  - 例: `uploads/material_123.png`（絶対パスは相対パスに変換）

#### B2: 画像表示の1本化
- **`utils/image_display.py`**を新規作成
  - `get_material_image()`: 材料の画像を取得（健康状態チェック付き）
    - 画像が存在しない場合に自動再生成
    - 黒画像の場合は再生成
    - 必ずRGBモードに変換して返す
  - `display_material_image()`: 材料の画像を表示（自動修復対応）
    - エラー時はプレースホルダーを表示（決して黒画像は出さない）
  - `material_detail_tabs.py`で使用

#### B3: 画像の再生成（黒/壊れ/欠損の自動復旧）
- **`image_generator.py`**を修正
  - `generate_material_image()`:
    - **WebPからPNGに変更**（環境依存を避ける）
    - **必ずRGBモードに変換**（RGBA/LA/Pモードを排除）
    - 透明部分がある場合は白背景に合成
  - `ensure_material_image()`:
    - 既存画像の健康状態をチェック
    - 問題がある場合は再生成
    - パスを正規化してDBに保存

#### B4: 起動時の自動修復
- **`utils/ensure_images.py`**を新規作成
  - `ensure_images()`: 起動時にすべての材料画像をチェック
    - 画像がない場合は生成
    - 問題がある画像は再生成
    - パスを正規化
  - `app.py`の`main()`で起動時に自動実行

## 変更ファイル一覧

### 新規作成
1. `utils/image_health.py` - 画像健康状態チェック
2. `utils/image_diagnostics.py` - 画像診断モード（UI）
3. `utils/image_display.py` - 画像表示の1本化
4. `utils/ensure_images.py` - 起動時自動修復

### 修正
1. `image_generator.py` - 画像生成ロジック修正（PNG形式、RGB変換）
2. `material_detail_tabs.py` - 画像表示を`display_material_image()`に置き換え
3. `app.py` - 診断モード追加、起動時自動修復追加

## 技術的詳細

### 画像形式の変更
```python
# 修正前
img.save(filepath, 'WEBP', quality=85)  # WebP形式

# 修正後
img.save(filepath, 'PNG', quality=95)  # PNG形式（環境依存を避ける）
```

### RGB変換の実装
```python
# RGBA/LA/PモードをRGBに変換（透明部分を白背景に合成）
if img.mode != 'RGB':
    if img.mode in ('RGBA', 'LA', 'P'):
        rgb_img = Image.new('RGB', img.size, (255, 255, 255))  # 白背景
        if img.mode == 'RGBA':
            rgb_img.paste(img, mask=img.split()[3])  # alphaチャンネルをマスクとして使用
        # ...
        img = rgb_img
```

### パス正規化
```python
# 絶対パスを相対パスに変換
normalized = normalize_image_path(file_path, project_root)
# 例: "/Users/.../uploads/img.png" → "uploads/img.png"
```

## 動作確認項目

- [x] 画像診断モードで原因を特定できる
- [x] 画像が存在しない場合に自動再生成される
- [x] 黒画像が検出され、自動再生成される
- [x] パスが正規化される（相対パスに統一）
- [x] 起動時に自動修復が実行される
- [x] エラー時はプレースホルダーが表示される（黒画像は出さない）

## 今後の改善点

1. **複数画像の対応**: 現在は最初の画像のみ詳細チェック。2枚目以降も同様のチェックを実装可能
2. **画像キャッシュ**: 健康状態チェック結果をキャッシュしてパフォーマンス向上
3. **バッチ再生成**: 診断モードから一括再生成機能を追加可能

