# 材料重複問題の修正サマリー

## 問題の原因

1. **DBクエリの重複**: `get_all_materials()`で`selectinload`を使用していたが、重複除去処理がなかった
2. **seedの重複投入**: `ensure_sample_data()`と`init_sample_data()`で重複チェックがなく、再起動時に同じ材料が複数回投入される可能性があった
3. **表示ソースの混在**: サンプルJSONやハードコード配列が混在していた可能性

## 修正内容

### 1. `get_all_materials()`の重複除去

**ファイル**: `app.py`

**変更前**:
```python
materials = db.execute(stmt).scalars().all()
return materials
```

**変更後**:
```python
# SQLAlchemy 2.0のunique()で重複を除去
result = db.execute(stmt)
materials = result.unique().scalars().all()
return materials
```

**効果**: DBクエリ結果の重複を確実に除去

### 2. `ensure_sample_data()`のidempotent化

**ファイル**: `app.py`

**変更内容**:
- 既存の材料名を取得してチェック
- サンプルデータで投入予定の材料名リストと比較
- 差分のみ投入（重複投入を防ぐ）

**効果**: 再起動時に同じ材料が複数回投入されない

### 3. `init_sample_data()`のidempotent化

**ファイル**: `init_sample_data.py`

**変更内容**:
- 各材料の登録前に既存の材料名をチェック
- 既に登録されている場合はスキップ
- 登録した材料名を`existing_names`に追加して追跡

**変更例**:
```python
# 変更前
material1 = Material(...)
db.add(material1)

# 変更後
if "カリン材" in existing_names:
    print("  ⏭️  スキップ: カリン材（既に登録されています）")
else:
    material1 = Material(...)
    db.add(material1)
    existing_names.add("カリン材")
```

**効果**: 手動で`init_sample_data()`を実行しても重複投入されない

### 4. 材料重複診断機能の追加

**ファイル**: `app.py`

**追加関数**: `show_materials_duplicate_diagnostics()`

**機能**:
- DB materials count（DB内の材料数）
- UI materials count（`get_all_materials()`で取得した材料数）
- Unique names count（ユニークな材料名数）
- Duplicate name list（重複している材料名のリスト、上位20件）

**使用方法**:
- サイドバーで「🔍 材料重複診断」チェックボックスを有効化
- 診断結果が表示される

### 5. 重複削除スクリプトの追加

**ファイル**: `scripts/dedupe_materials.py`

**機能**:
- 同名の材料が複数ある場合を検出
- 最も古いIDを残して他を削除する方針を提示
- `--dry-run`モード（デフォルト）で削除前の確認
- `--execute`フラグで実際の削除を実行

**使用方法**:
```bash
# ドライラン（削除しない）
python scripts/dedupe_materials.py --dry-run

# 実際に削除を実行
python scripts/dedupe_materials.py --execute
```

## 変更したファイル一覧

1. **`app.py`**
   - `get_all_materials()`: 重複除去処理を追加（`result.unique().scalars().all()`）
   - `ensure_sample_data()`: idempotent化（既存材料名チェック）
   - `show_materials_duplicate_diagnostics()`: 新規追加（診断機能）

2. **`init_sample_data.py`**
   - 全9材料の登録処理をidempotent化（重複チェック追加）

3. **`scripts/dedupe_materials.py`**
   - 新規追加（重複削除スクリプト）

## 確認手順

### 1. ローカルでの確認

```bash
# 1. アプリを起動
streamlit run app.py

# 2. サイドバーで「🔍 材料重複診断」を有効化
# 3. 以下を確認:
#    - DB materials count == UI materials count
#    - UI materials count == Unique names count
#    - Duplicate name list が空であること

# 4. 重複削除スクリプトを実行（ドライラン）
python scripts/dedupe_materials.py --dry-run
```

### 2. Streamlit Cloudでの確認

1. Streamlit CloudでReboot
2. サイドバーで「🔍 材料重複診断」を有効化
3. 以下を確認:
   - ✅ 材料一覧で重複が消えること
   - ✅ Diagnosticsで `UI materials count == Unique names count` であること
   - ✅ seedが再起動で増殖しないこと（再起動前後で材料数が変わらない）

### 3. 重複削除の実行（必要に応じて）

既にDBに重複レコードが入っている場合:

```bash
# 1. ドライランで確認
python scripts/dedupe_materials.py --dry-run

# 2. 問題なければ実際に削除
python scripts/dedupe_materials.py --execute
```

## 再現→修正→確認の手順

### 再現手順（修正前）

1. `init_sample_data()`を複数回実行
2. 材料一覧で同じ材料が2つずつ表示される
3. 診断モードで `UI materials count != Unique names count` が確認できる

### 修正手順（実施済み）

1. `get_all_materials()`に`unique()`を追加
2. `ensure_sample_data()`と`init_sample_data()`をidempotent化
3. 診断機能を追加
4. 重複削除スクリプトを作成

### 確認手順（実施）

1. 診断モードで重複がないことを確認
2. 再起動後も材料数が変わらないことを確認
3. 材料一覧で重複が表示されないことを確認

## 期待される結果

- ✅ 材料一覧で同じ材料が2つずつ表示されない
- ✅ 診断モードで `UI materials count == Unique names count`
- ✅ 再起動しても材料数が増えない（seedの重複投入が防がれる）
- ✅ 重複削除スクリプトで既存の重複を検出・削除できる


