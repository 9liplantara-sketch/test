# 画像デバッグガイド

## 概要

Streamlit Cloudで画像が表示されない、または古い画像が表示される問題を切り分けるためのデバッグガイドです。

## 重要な前提

- **`uploads/` は `.gitignore` で除外されているため、Streamlit Cloudには届きません**
- 画像をCloudで表示するには、`static/images/materials/` に同期された画像をGitにコミット・プッシュする必要があります
- `scripts/sync_uploaded_images.py` で `uploads/` から `static/images/materials/` に同期できます

## デバッグ手順

### 1. 画像状態の確認

```bash
# 特定の材料の画像状態を確認
python scripts/debug_image_state.py --material "アルミニウム"

# uploads側とstatic側を比較
python scripts/debug_image_state.py --material "アルミニウム" --compare-uploads

# 絶対パスで表示
python scripts/debug_image_state.py --material "アルミニウム" --absolute

# ディレクトリの内容を一覧表示
python scripts/debug_image_state.py --list-dir static/images/materials
python scripts/debug_image_state.py --list-dir uploads
```

### 2. Git追跡状態の確認

```bash
# Gitの状態を確認
git status

# 特定のファイルがignoreされているか確認
git check-ignore -v uploads/アルミニウム.jpg
git check-ignore -v static/images/materials/アルミニウム/primary.jpg

# 特定のファイルがGitで追跡されているか確認
git ls-files static/images/materials/アルミニウム/primary.jpg

# static/images/materials 全体の追跡状態を確認
git ls-files static/images/materials/
```

### 3. 画像同期の実行

```bash
# ドライランで確認
python scripts/sync_uploaded_images.py --dry-run

# 実際に同期
python scripts/sync_uploaded_images.py
```

### 4. Gitにコミット・プッシュ

```bash
# 同期された画像をGitに追加
git add static/images/materials/

# コミット
git commit -m "feat: 画像を同期"

# プッシュ
git push origin main
```

## よくある問題と対処法

### 問題1: uploads/ に画像があるのにCloudで表示されない

**原因:**
- `uploads/` は `.gitignore` で除外されているため、Cloudには届きません

**対処法:**
1. `scripts/sync_uploaded_images.py` で `static/images/materials/` に同期
2. `git add static/images/materials/` でGitに追加
3. `git commit` と `git push` でCloudに反映

### 問題2: static/ に画像があるのにCloudで表示されない

**原因:**
- `static/images/materials/` が `.gitignore` されている可能性
- Gitにコミット・プッシュされていない可能性

**確認方法:**
```bash
# Gitで追跡されているか確認
git ls-files static/images/materials/アルミニウム/primary.jpg

# ignoreされているか確認
git check-ignore -v static/images/materials/アルミニウム/primary.jpg
```

**対処法:**
- `.gitignore` を確認し、`static/images/materials/` が除外されていないか確認
- 除外されている場合は、`.gitignore` を修正するか、`git add -f` で強制追加

### 問題3: 画像を更新したのに古い画像が表示される

**原因:**
- Streamlit Cloudのキャッシュ
- 同期が実行されていない
- Gitにプッシュされていない

**対処法:**
1. `scripts/debug_image_state.py --compare-uploads` で差分を確認
2. 差分がある場合は `scripts/sync_uploaded_images.py` で同期
3. `git add`, `git commit`, `git push` でCloudに反映
4. Streamlit Cloudで「Manage app → Reboot」を実行（キャッシュクリア）

### 問題4: 画像が存在しているのに「画像なし」と表示される

**原因:**
- ファイルパスの不一致
- 拡張子の不一致
- 権限の問題

**確認方法:**
```bash
# 画像の存在とパスを確認
python scripts/debug_image_state.py --material "アルミニウム" --absolute

# ディレクトリ構造を確認
python scripts/debug_image_state.py --list-dir static/images/materials/アルミニウム
```

**対処法:**
- ファイルパスが正しいか確認（`static/images/materials/{slug}/primary.{ext}`）
- 拡張子が正しいか確認（jpg/jpeg/png/webp）
- ファイルの読み取り権限を確認

## デバッグスクリプトの出力例

```
Python 3.9.18
Python executable: /usr/bin/python3

================================================================================
画像状態デバッグ
================================================================================
材料名: アルミニウム
スラッグ: アルミニウム
ベースディレクトリ: static/images/materials
uploadsディレクトリ: uploads

================================================================================
📦 static側の画像
================================================================================
  PRIMARY:
    パス: static/images/materials/アルミニウム/primary.jpg
    存在: ✅
    サイズ: 245.3 KB
    mtime: 2026-01-04 15:30:22
    md5: a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6

  SPACE:
    パス: static/images/materials/アルミニウム/uses/space.jpg
    存在: ✅
    サイズ: 180.5 KB
    mtime: 2026-01-04 15:30:25
    md5: b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7

  PRODUCT:
    存在: ❌ ファイルなし

================================================================================
📊 サマリー
================================================================================
✅ 存在: primary, space
❌ 欠損: product
```

## Git追跡の確認コマンド

### static/images/materials が追跡されているか確認

```bash
# 全体の追跡状態
git ls-files static/images/materials/

# 特定のファイル
git ls-files static/images/materials/アルミニウム/primary.jpg

# ignoreされているか確認
git check-ignore -v static/images/materials/アルミニウム/primary.jpg
```

### static/images/materials がignoreされている場合

**運用方針:**
- Cloudで画像を表示したい場合は、`static/images/materials/` をGitで追跡する必要があります
- `.gitignore` で `static/images/materials/` が除外されている場合は、除外を解除するか、`git add -f` で強制追加してください

**推奨設定:**
`.gitignore` に以下を追加（または既存の設定を確認）:
```
# static/images/materials/ は追跡する（Cloudで表示するため）
!static/images/materials/
```

## トラブルシューティングチェックリスト

- [ ] `uploads/` に画像が存在するか確認
- [ ] `scripts/sync_uploaded_images.py` で同期を実行したか
- [ ] `static/images/materials/` に画像が存在するか確認
- [ ] Gitで追跡されているか確認（`git ls-files`）
- [ ] `.gitignore` で除外されていないか確認（`git check-ignore`）
- [ ] Gitにコミット・プッシュしたか確認
- [ ] Streamlit Cloudで「Reboot」を実行したか（キャッシュクリア）

## 関連ドキュメント

- [IMAGE_SYNC.md](./IMAGE_SYNC.md) - 画像同期の詳細ガイド

