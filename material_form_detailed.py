"""
詳細仕様対応の材料登録フォーム
レイヤー①（必須）とレイヤー②（任意）を含む包括的なフォーム
"""
import streamlit as st
import uuid
import json
import os
import re
import inspect
import logging
from database import Material, Property, Image, MaterialMetadata, ReferenceURL, UseExample, MaterialSubmission, init_db
# Phase 2.5: SessionLocal()は使用禁止。読み取りはget_session()、書き込みはsession_scope()を使用

# ロガーを設定（Cloudで確実に追えるように）
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('[%(name)s] %(levelname)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _show_debug_ui() -> bool:
    try:
        from utils.settings import show_debug_ui
        return show_debug_ui()
    except Exception:
        return os.getenv("DEBUG", "0") == "1"


# ===== Widget Key統一管理 =====

# 主要5項目（wkey完全統一対象）
CORE_FIELDS = {
    'name_official',
    'category_main',
    'origin_type',
    'transparency',
    'visibility',
    'is_published',  # 可能なら追加
}

# Canonical fields: DBに保存するフィールドの一覧（補助キーは除外）
CANONICAL_FIELDS = {
    # 基本識別情報
    'name_official', 'name_aliases',
    # 供給元
    'supplier_org', 'supplier_type', 'supplier_other',
    # 分類
    'category_main', 'category_other', 'material_forms', 'material_forms_other',
    # 由来・原料
    'origin_type', 'origin_other', 'origin_detail', 'recycle_bio_rate', 'recycle_bio_basis',
    # 基本特性
    'color_tags', 'transparency', 'hardness_qualitative', 'hardness_value',
    'weight_qualitative', 'specific_gravity', 'water_resistance',
    'heat_resistance_temp', 'heat_resistance_range', 'weather_resistance',
    # 加工・実装条件
    'processing_methods', 'processing_other', 'equipment_level', 'prototyping_difficulty',
    # 用途・市場状態
    'use_categories', 'use_other', 'procurement_status', 'cost_level', 'cost_value', 'cost_unit',
    # 制約・安全・法規
    'safety_tags', 'safety_other', 'restrictions',
    # 公開範囲
    'visibility', 'is_published',
    # リレーション
    'reference_urls', 'use_examples',
    # レイヤー②
    'development_motives', 'development_motive_other', 'development_background_short', 'development_story',
    'tactile_tags', 'tactile_other', 'visual_tags', 'visual_other', 'sound_smell',
    'circularity', 'certifications', 'certifications_other',
    # STEP 6
    'main_elements',
}


def wkey(field: str, scope: str, material_id=None, submission_id=None) -> str:
    """
    Widget keyを統一生成する関数
    
    Args:
        field: フィールド名（例: "name_official", "category_main"）
        scope: スコープ（"create", "edit", "approve"）
        material_id: 材料ID（編集モードの場合）
        submission_id: 投稿ID（承認画面の場合）
    
    Returns:
        str: "mf:{scope}:{mid or 'new'}:{sid or 'nosub'}:{field}" 形式のキー
    """
    mid_str = str(material_id) if material_id else "new"
    sid_str = str(submission_id) if submission_id else "nosub"
    return f"mf:{scope}:{mid_str}:{sid_str}:{field}"


def mark_touched(key: str):
    """
    Widgetがユーザーによって変更されたことを記録するコールバック関数
    
    Args:
        key: wkeyで生成されたwidget key
    
    Note:
        st.form内ではon_changeが使えないため、この関数は使用されていません。
        代わりにset_touched_if_changedを使用してください。
    """
    touched_key = f"touched:{key}"
    # 既にtouched:trueなら何もしない（余計なrerunを避ける）
    if st.session_state.get(touched_key):
        return
    st.session_state[touched_key] = True


def _coerce_text_input_value(v) -> str:
    """st.text_input に渡す値/セッション値を必ず str に正規化する。"""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (list, tuple, set)):
        return ",".join(str(x) for x in v)
    if isinstance(v, dict):
        try:
            import json
            return json.dumps(v, ensure_ascii=False)
        except Exception:
            return str(v)
    return str(v)


def set_touched_if_changed(field: str, key: str, value, default_value=None, existing_value=None, scope="create"):
    """
    値の差分でtouchedフラグを立てるヘルパー関数（st.form内で使用）
    
    Args:
        field: フィールド名（例: "name_official", "category_main"）
        key: wkeyで生成されたwidget key
        value: ウィジェットの現在の値
        default_value: createモードでのデフォルト値（比較用）
        existing_value: editモードでの既存値（比較用）
        scope: スコープ（"create" or "edit"）
    """
    touched_key = f"touched:{key}"
    
    # name_official は非空なら touched 扱い（既存仕様に合わせる）
    if field == "name_official":
        if str(value or "").strip():
            st.session_state[touched_key] = True
        return
    
    # create: デフォルトと違うなら touched
    if scope == "create":
        if default_value is not None and value != default_value:
            st.session_state[touched_key] = True
        return
    
    # edit: existing と違うなら touched
    if scope == "edit":
        if existing_value is not None and value != existing_value:
            st.session_state[touched_key] = True
        return


def _find_existing_widget_key_for_field(field: str, scope: str, material_id=None):
    """
    session_state上に実在するwidget keyを探索して返す。
    suffixズレ（nosub/sub/new等）でpayloadが空になるのを防ぐ。
    """
    try:
        keys = list(st.session_state.keys())
    except Exception:
        return None

    candidates = []

    # material_id がある場合：mf:{scope}:{material_id}:...:{field} を優先
    if material_id is not None:
        prefix = f"mf:{scope}:{material_id}:"
        for k in keys:
            if isinstance(k, str) and k.startswith(prefix) and k.endswith(f":{field}"):
                candidates.append(k)

    # 見つからなければ scope のみで探す（create等）
    if not candidates:
        prefix = f"mf:{scope}:"
        for k in keys:
            if isinstance(k, str) and k.startswith(prefix) and k.endswith(f":{field}"):
                candidates.append(k)

    if not candidates:
        return None

    # suffix優先度: nosub > sub > その他
    def _score(k: str) -> int:
        if ":nosub:" in k:
            return 0
        if ":sub:" in k:
            return 1
        return 2

    candidates.sort(key=_score)
    return candidates[0]


def extract_payload(scope: str, material_id=None, submission_id=None) -> dict:
    """
    wkeyで生成されたwidget keyから値を収集してpayloadを構築する
    
    Args:
        scope: スコープ（"create", "edit", "approve"）
        material_id: 材料ID（編集モードの場合）
        submission_id: 投稿ID（承認画面の場合）
    
    Returns:
        dict: payload（CANONICAL_FIELDSのみ、見つからないキーは含めない）
    """
    # DEBUG_ENVチェック
    try:
        from utils.settings import get_flag
        debug_env_enabled = get_flag("DEBUG_ENV", False)
    except Exception:
        debug_env_enabled = os.getenv("DEBUG_ENV", "0") == "1"
    
    payload = {}
    legacy_keys_used = []
    
    # ---- name_official は必須: suffixズレに強い取得にする（touched gate 非依存） ----
    name_key = _find_existing_widget_key_for_field("name_official", scope, material_id)
    name_raw = st.session_state.get(name_key) if name_key else None
    name_val = _coerce_text_input_value(name_raw)
    name_val = str(name_val or "").strip()

    if os.getenv("DEBUG_ENV") == "1":
        logger.info(f"[EXTRACT_PAYLOAD] field=name_official key={name_key!r} touched=1 included={1 if name_val else 0} value={name_val[:120]!r}")

    if name_val:
        payload["name_official"] = name_val
    
    # suffixを計算（移行ブリッジ用）
    suffix = str(material_id) if material_id else "new"
    
    for field in CANONICAL_FIELDS:
        # name_official は既に処理済みなのでスキップ
        if field == "name_official":
            continue
        
        # まずwkeyから取得を試みる
        key = wkey(field, scope, material_id, submission_id)
        value = st.session_state.get(key)
        
        # wkeyが空の場合、旧suffixベースのキーから拾う（移行ブリッジ）
        if value is None:
            legacy_key = f"{field}_{suffix}"
            legacy_value = st.session_state.get(legacy_key)
            if legacy_value is not None:
                value = legacy_value
                legacy_keys_used.append(field)
                if debug_env_enabled:
                    logger.debug(f"[LEGACY_KEY_USED] field={field}, legacy_key={legacy_key}, wkey={key}")
        
        # 主要6項目については、touchedフラグをチェック
        is_touched = 0
        if field in CORE_FIELDS:
            touched_key = f"touched:{key}"
            is_touched_flag = st.session_state.get(touched_key, False)
            
            # その他の主要項目はtouchedフラグが立っていない場合は含めない
            if not is_touched_flag:
                if debug_env_enabled:
                    value_repr = repr(value) if value is not None else "None"
                    if len(value_repr) > 120:
                        value_repr = value_repr[:117] + "..."
                    logger.info(f"[EXTRACT_PAYLOAD] field={field} key={key} touched=0 included=0 value={value_repr}")
                continue
            
            is_touched = 1 if is_touched_flag else 0
        
        # None/空文字列/空配列は含めない（初期値で埋めない）
        if value is None:
            if debug_env_enabled:
                logger.info(f"[EXTRACT_PAYLOAD] field={field} key={key} touched={is_touched} included=0 value=None")
            continue
        if isinstance(value, str) and value.strip() == "":
            if debug_env_enabled:
                logger.info(f"[EXTRACT_PAYLOAD] field={field} key={key} touched={is_touched} included=0 value=''")
            continue
        if isinstance(value, list) and len(value) == 0:
            if debug_env_enabled:
                logger.info(f"[EXTRACT_PAYLOAD] field={field} key={key} touched={is_touched} included=0 value=[]")
            continue
        if isinstance(value, dict) and len(value) == 0:
            if debug_env_enabled:
                logger.info(f"[EXTRACT_PAYLOAD] field={field} key={key} touched={is_touched} included=0 value={{}}")
            continue
        
        # 数値の正規化（可能ならfloat/intへ）
        if isinstance(value, (int, float)):
            payload[field] = value
        elif isinstance(value, str):
            # 数値文字列の場合は変換を試みる（既存の挙動を壊さない範囲）
            try:
                if '.' in value:
                    payload[field] = float(value)
                else:
                    payload[field] = int(value)
            except ValueError:
                payload[field] = value
        else:
            payload[field] = value
        
        # payloadに含まれる場合のログ出力
        if debug_env_enabled:
            value_repr = repr(value) if value is not None else "None"
            if len(value_repr) > 120:
                value_repr = value_repr[:117] + "..."
            logger.info(f"[EXTRACT_PAYLOAD] field={field} key={key} touched={is_touched} included=1 value={value_repr}")
    
    # 移行ブリッジ使用時はログ出力（DEBUG_ENV=1のときのみ）
    if legacy_keys_used and debug_env_enabled:
        logger.info(f"[LEGACY_KEY_USED] Fields using legacy keys: {legacy_keys_used}")
    
    return payload


def _debug_dump_form_state(prefix: str = "mf:"):
    """
    フォーム状態をデバッグログに出力（DEBUG_ENV=1のときのみ）
    
    Args:
        prefix: キーのプレフィックス（デフォルト: "mf:"）
    """
    try:
        from utils.settings import get_flag
        debug_enabled = get_flag("DEBUG_ENV", False)
    except Exception:
        debug_enabled = os.getenv("DEBUG_ENV", "0") == "1"
    
    if not debug_enabled:
        return
    
    # mf: を含む session_state keys を収集
    mf_keys = [k for k in st.session_state.keys() if prefix in k]
    
    # 代表項目の値を取得
    representative_fields = ['name_official', 'category_main', 'origin_type', 'transparency', 'visibility']
    rep_values = {}
    for field in representative_fields:
        # 複数のscopeで探す
        for scope in ['create', 'edit', 'approve']:
            key = wkey(field, scope)
            if key in st.session_state:
                value = st.session_state[key]
                if isinstance(value, str) and len(value) > 200:
                    value = value[:200] + "..."
                rep_values[f"{scope}:{field}"] = value
                break
    
    # ログ出力
    logger.info(
        f"[DEBUG_DUMP] mf: keys_count={len(mf_keys)}, "
        f"keys_head={mf_keys[:10]}, "
        f"rep_values={rep_values}"
    )


def normalize_uploaded_files(v) -> list:
    """
    UploadedFile のリストを正規化（型揺れに強い）
    
    Args:
        v: None, 単一の UploadedFile, または list[UploadedFile]
    
    Returns:
        list[UploadedFile]: name属性を持つもののみを含むリスト
    """
    if v is None:
        return []
    items = v if isinstance(v, list) else [v]
    return [x for x in items if x is not None and getattr(x, "name", None) is not None]


def material_to_form_data(material: Material) -> dict:
    """
    Materialオブジェクトをフォームデータ（dict）に変換する
    
    Args:
        material: Materialオブジェクト（リレーションがロード済み）
    
    Returns:
        dict: フォームデータ（JSON配列フィールドはlistに正規化、NoneはNoneのまま）
    """
    import json
    
    form_data = {}
    
    # スカラー属性を取得
    for column in Material.__table__.columns:
        field_name = column.name
        if field_name in {"id", "created_at", "updated_at", "deleted_at", "uuid", "search_text"}:
            continue
        
        value = getattr(material, field_name, None)
        
        # JSON配列フィールドの場合はパース
        json_array_fields = [
            'name_aliases', 'material_forms', 'color_tags', 'processing_methods',
            'use_categories', 'safety_tags', 'question_templates', 'main_elements',
            'development_motives', 'tactile_tags', 'visual_tags', 'certifications'
        ]
        
        if field_name in json_array_fields:
            if isinstance(value, str):
                try:
                    form_data[field_name] = json.loads(value) if value else []
                except (json.JSONDecodeError, TypeError):
                    form_data[field_name] = []
            elif isinstance(value, list):
                form_data[field_name] = value
            else:
                form_data[field_name] = []
        else:
            # 通常フィールドはそのまま（Noneも保持）
            form_data[field_name] = value
    
    # リレーションをdictに変換
    if hasattr(material, 'reference_urls') and material.reference_urls:
        form_data['reference_urls'] = [
            {'url': ref.url, 'type': ref.url_type, 'desc': ref.description}
            for ref in material.reference_urls
        ]
    else:
        form_data['reference_urls'] = []
    
    if hasattr(material, 'use_examples') and material.use_examples:
        form_data['use_examples'] = [
            {'name': ex.example_name, 'url': ex.example_url, 'desc': ex.description}
            for ex in material.use_examples
        ]
    else:
        form_data['use_examples'] = []
    
    if hasattr(material, 'images') and material.images:
        form_data['existing_images'] = [
            {'kind': img.kind, 'public_url': img.public_url, 'r2_key': img.r2_key}
            for img in material.images
        ]
    else:
        form_data['existing_images'] = []
    
    return form_data


# 選択肢の定義
SUPPLIER_TYPES = [
    "企業", "大学/研究機関", "スタートアップ", "個人/アーティスト",
    "産学連携/コンソーシアム", "公的機関", "その他（自由記述）", "不明"
]

MATERIAL_CATEGORIES = [
    "高分子（樹脂・エラストマー等）", "金属・合金", "セラミックス・ガラス",
    "木材・紙・セルロース系", "繊維（天然/合成）", "ゴム",
    "複合材（FRP等）", "バイオマテリアル（菌糸・発酵・生体由来）",
    "ゲル・ハイドロゲル", "多孔質（フォーム・スポンジ・エアロゲル等）",
    "コーティング・表面処理材", "インク・塗料・顔料", "粉体・粒材",
    "電子/機能材料（電池・半導体・導電材等）", "その他（自由記述）", "不明"
]

MATERIAL_FORMS = [
    "シート/板材", "フィルム", "ロッド/棒材", "粒（ペレット）", "粉末",
    "繊維/糸", "フェルト/不織布", "液体（樹脂/溶液）", "ペースト/スラリー",
    "ゲル", "フォーム/スポンジ", "ブロック/バルク",
    "3Dプリント用フィラメント", "3Dプリント用レジン", "コーティング剤",
    "その他（自由記述）", "不明"
]

ORIGIN_TYPES = [
    "化石資源由来（石油等）", "植物由来", "動物由来", "鉱物由来",
    "微生物/発酵由来", "廃材/リサイクル由来", "混合/複合由来",
    "その他（自由記述）", "不明"
]

COLOR_OPTIONS = [
    "無色", "白系", "黒系", "グレー系", "透明", "半透明",
    "着色可能（任意色）", "その他（自由記述）", "不明"
]

TRANSPARENCY_OPTIONS = ["透明", "半透明", "不透明", "不明"]

HARDNESS_OPTIONS = ["とても柔らかい", "柔らかい", "中間", "硬い", "とても硬い", "不明"]

WEIGHT_OPTIONS = ["とても軽い", "軽い", "中間", "重い", "とても重い", "不明"]

WATER_RESISTANCE_OPTIONS = ["高い（屋外・水回りOK）", "中（条件付き）", "低い（水に弱い）", "不明"]

HEAT_RANGE_OPTIONS = ["低温域（〜60℃）", "中温域（60〜120℃）", "高温域（120℃〜）", "不明"]

WEATHER_RESISTANCE_OPTIONS = ["高い", "中", "低い", "不明"]

PROCESSING_METHODS = [
    "切削", "レーザー加工", "熱成形", "射出成形", "圧縮成形",
    "3Dプリント（FDM）", "3Dプリント（SLA/DLP）", "3Dプリント（SLS等粉体系）",
    "接着", "溶着/熱溶着", "縫製/編み", "積層/ラミネート",
    "塗装/コーティング", "焼成", "発泡", "鋳造", "その他（自由記述）", "不明"
]

EQUIPMENT_LEVELS = [
    "家庭/工房レベル", "ファブ施設レベル（FabLab等）",
    "工場設備が必要", "研究設備が必要", "不明"
]

DIFFICULTY_OPTIONS = ["低", "中", "高", "不明"]

USE_CATEGORIES = [
    "建築・内装", "家具", "生活用品/雑貨", "家電/機器筐体",
    "パッケージ/包装", "繊維/アパレル", "医療/ヘルスケア", "食品関連",
    "モビリティ", "エネルギー/電気電子", "教育/ホビー",
    "アート/展示", "その他（自由記述）", "不明",
    "産業設備・プラント",
    "インフラ・土木",
    "エネルギー（発電・蓄電・配電）",
    "防災・安全",
    "輸送・モビリティ",
    "海洋・港湾",
    "極環境",
    "研究・実験",
    "その他専門領域"
]

USE_ENVIRONMENT_OPTIONS = [
    "屋内", "屋外", "高温", "低温", "薬品", "塩害", "摩耗",
    "紫外線", "湿気", "乾燥", "振動", "衝撃", "圧力", "真空",
    "放射線", "電磁波", "静電気", "その他（自由記述）", "不明"
]

PROCUREMENT_OPTIONS = [
    "一般購入可", "法人のみ", "サンプル提供のみ",
    "共同研究/契約が必要", "入手困難", "不明"
]

COST_LEVELS = ["低", "中", "高", "変動大", "非公開", "不明"]

SAFETY_TAGS = [
    "食品接触OK", "食品接触不可", "皮膚接触OK", "皮膚接触注意",
    "揮発/臭気注意", "粉塵注意", "可燃性注意", "毒性/有害性懸念",
    "規制対象（要確認）", "不明", "その他（自由記述）"
]

VISIBILITY_OPTIONS = ["公開（誰でも閲覧可）", "限定公開（ログインユーザーのみ）", "非公開（登録者/管理者のみ）", "不明"]


# 必須フィールドのデフォルト値
REQUIRED_DEFAULTS = {
    "prototyping_difficulty": "中",
    "equipment_level": "家庭/工房レベル",
    "visibility": "公開（誰でも閲覧可）",
    "is_published": 1,
}


def _normalize_required(form_data: dict, existing=None) -> dict:
    """
    必須フィールドの補完（None/空文字列をデフォルト値で埋める）
    更新時は、既存値が埋まっているなら None/空文字で上書きしない
    """
    d = dict(form_data)

    for key, default in REQUIRED_DEFAULTS.items():
        v = d.get(key)

        # 未入力(None / 空文字)なら補完対象
        if v is None or (isinstance(v, str) and v.strip() == ""):
            # 更新時: 既存値が埋まっていれば維持（上書きしない）
            if existing is not None:
                cur = getattr(existing, key, None)
                if cur is not None:
                    if isinstance(cur, str):
                        if cur.strip() != "":
                            d.pop(key, None)
                            continue
                    else:
                        # int/float/bool などは None でなければ有効（0もOK）
                        d.pop(key, None)
                        continue

            # 新規 or 既存も空ならデフォルトを入れる
            d[key] = default

    if os.getenv("DEBUG", "0") == "1":
        print(f"[DEBUG] _normalize_required: {d}")

    return d


def show_detailed_material_form(material_id: int = None):
    """
    詳細仕様対応の材料登録フォーム（新規登録・編集対応）
    
    Args:
        material_id: 編集モードの場合、既存材料のID
    """
    # 編集モードかどうか判定
    is_edit_mode = material_id is not None
    existing_material = None
    existing_data = {}  # session 内で dict に変換したデータを保存
    
    # suffix を定義（widget key の統一用）
    suffix = material_id if material_id else "new"
    
    # material_id が変更されたらフォーム関連stateを掃除
    prev = st.session_state.get("active_edit_material_id")
    prev_suffix = prev if prev else "new"
    prev_is_edit = prev is not None
    current_is_edit = is_edit_mode
    
    # 編集→新規、新規→編集、編集→編集（別ID）のいずれかの場合にクリーンアップ
    if (prev_is_edit != current_is_edit) or (is_edit_mode and material_id and prev and prev != material_id):
        # wkey()で生成されたキーを削除（mf:プレフィックス）
        prev_scope = "edit" if prev_is_edit else "create"
        prev_mid_str = str(prev) if prev else "new"
        for k in list(st.session_state.keys()):
            if k.startswith(f"mf:{prev_scope}:{prev_mid_str}:"):
                del st.session_state[k]
        
        # 従来のsuffix付きキーも削除（後方互換性のため）
        for k in list(st.session_state.keys()):
            if k.endswith(f"_{prev_suffix}") and (
                k.startswith("name_") or k.startswith("supplier_") or k.startswith("category_") or
                k.startswith("material_forms_") or k.startswith("origin_") or k.startswith("recycle_bio_") or
                k.startswith("color_tags_") or k.startswith("transparency_") or k.startswith("hardness_") or
                k.startswith("weight_") or k.startswith("specific_gravity_") or k.startswith("water_resistance_") or
                k.startswith("heat_resistance_") or k.startswith("weather_resistance_") or k.startswith("processing_") or
                k.startswith("equipment_level_") or k.startswith("prototyping_difficulty_") or k.startswith("use_categories_") or
                k.startswith("use_other_") or k.startswith("procurement_status_") or k.startswith("cost_") or
                k.startswith("safety_") or k.startswith("restrictions_") or k.startswith("visibility_") or
                k.startswith("is_published_") or k.startswith("submitted_by_") or k.startswith("images_upload_") or
                k.startswith("existing_images_") or k.startswith("ref_url_") or k.startswith("ref_type_") or
                k.startswith("ref_desc_") or k.startswith("del_ref_") or k.startswith("ex_name_") or
                k.startswith("ex_url_") or k.startswith("ex_desc_") or k.startswith("del_ex_") or
                k.startswith("alias_") or k.startswith("del_alias_") or k.startswith("new_alias") or
                k.startswith("new_ref_") or k.startswith("new_ex_") or k.startswith("_seeded_") or
                k.startswith("delete_image_") or k.startswith("deleted_images_")
            ):
                del st.session_state[k]
        
        # suffix付きでないキーも削除（編集→新規の場合）
        if prev_is_edit and not current_is_edit:
            for name_key in ["name_official_input", "name_official_cached", "aliases", "ref_urls", "use_examples"]:
                if name_key in st.session_state:
                    del st.session_state[name_key]
        
        # 画像関連のキーも削除（suffix付きでないものも含む）
        for img_key in ["primary_image", "primary_image_cached"]:
            if img_key in st.session_state:
                del st.session_state[img_key]
        # suffix付きの画像キーも削除
        for k in list(st.session_state.keys()):
            if (k.startswith("primary_image_") or k.startswith("images_upload_") or 
                k.startswith("primary_image_cached_") or k.startswith("existing_images_")):
                if k.endswith(f"_{prev_suffix}") or (prev_suffix == "new" and not k.endswith("_" + str(material_id) if material_id else "_new")):
                    del st.session_state[k]
    
    st.session_state["active_edit_material_id"] = material_id
    
    if is_edit_mode:
        # 編集モード：既存材料を取得（eager load でリレーションを事前ロード）
        from utils.db import get_session
        from sqlalchemy.orm import selectinload
        from sqlalchemy import select
        
        with get_session() as db:
            # selectinload で必要なリレーションを事前ロード
            stmt = (
                select(Material)
                .where(Material.id == material_id)
                .options(
                    selectinload(Material.reference_urls),
                    selectinload(Material.use_examples),
                    selectinload(Material.images),
                )
            )
            existing_material = db.execute(stmt).scalar_one_or_none()
            
            if not existing_material:
                st.error(f"❌ 材料ID {material_id} が見つかりません")
                return
            
            st.markdown('<h2 class="gradient-text">✏️ 材料編集</h2>', unsafe_allow_html=True)
            st.info(f"📝 **編集対象**: {existing_material.name_official}")
            
            # session を閉じる前に、必要なリレーションにアクセスして dict に変換（DetachedInstanceError 防止）
            # ここでアクセスすることで、リレーションが確実にロードされる
            reference_urls_list = list(existing_material.reference_urls or [])
            use_examples_list = list(existing_material.use_examples or [])
            images_list = list(existing_material.images or [])
            
            # material_to_form_data を使って既存値をフォームデータに変換
            existing_form_data = material_to_form_data(existing_material)
            
            # session 内で dict に変換して保存（session を閉じた後でもアクセス可能にする）
            existing_data = {
                'reference_urls': existing_form_data.get('reference_urls', []),
                'use_examples': existing_form_data.get('use_examples', []),
            }
            # get_session()が自動でcloseするため、finallyは不要
            # existing_material は detached になるが、必要なデータは既に dict に変換済み
            
            # st.session_state に既存値を設定（suffixごとに初回のみseed）
            seeded_flag = f"_seeded_{suffix}"
            if seeded_flag not in st.session_state:
                # material_to_form_data で既存値をフォームデータに変換
                existing_form_data = material_to_form_data(existing_material)
                
                # wkey()を使ってwidget keyに値を投入（既にユーザーが入力中なら上書きしない）
                scope = "edit"
                def seed_widget(field_name: str, value):
                    """
                    Widget keyに値を設定（wkey()で生成、既に値がある場合は上書きしない）
                    
                    - editモード: 既存materialからseedしてOK（該当キーが存在しない場合のみ）
                    - createモード: CORE_FIELDSについてはseed禁止（UIのindex defaultに任せる）
                    """
                    widget_key = wkey(field_name, scope, material_id=material_id)
                    # createモードでCORE_FIELDSはseed禁止（ユーザーが触った時だけtouchedが立つ設計）
                    if scope == "create" and field_name in CORE_FIELDS:
                        return
                    # 既に値がある場合は上書きしない（ユーザーが入力中なら保護）
                    if widget_key not in st.session_state:
                        st.session_state[widget_key] = value
                
                # 主要6項目をseed（editモードのみ、createモードではseed_widget内でスキップ）
                for field_name in CORE_FIELDS:
                    if field_name in existing_form_data:
                        seed_widget(field_name, existing_form_data[field_name])
                
                # その他のフィールドもseed（後方互換性のため）
                for field_name in CANONICAL_FIELDS:
                    if field_name not in CORE_FIELDS and field_name in existing_form_data:
                        seed_widget(field_name, existing_form_data[field_name])
                
                # 画像（既存画像一覧を表示用に保存、従来のkeyを使用）
                st.session_state[f"existing_images_{suffix}"] = [
                    {'kind': img.kind, 'public_url': img.public_url, 'r2_key': img.r2_key}
                    for img in images_list
                ]
                
                # seed完了フラグを設定
                st.session_state[seeded_flag] = True
                
                # 既存フォームデータをsession_stateに保存（送信時にマージ用）
                st.session_state[f"existing_form_data_{suffix}"] = existing_form_data
                
                # DEBUG時のみログ出力
                if _show_debug_ui():
                    seeded_count = sum(1 for k in st.session_state.keys() if k.startswith(f"mf:{scope}:"))
                    logger.info(f"[SEED] material_id={material_id}, scope={scope}, seeded_wkeys_count={seeded_count}, images_count={len(existing_form_data.get('existing_images', []))}")
    else:
        st.markdown('<h2 class="gradient-text">➕ 材料登録（詳細版）</h2>', unsafe_allow_html=True)
        st.info("📝 **レイヤー①（必須）**: 約10分で入力可能な基本情報\n\n**レイヤー②（任意）**: 後から追記できる詳細情報")
        
        # 一括登録モードのチェック
        if st.session_state.get('bulk_import_mode', False):
            # 一括登録UIを表示
            from app import show_bulk_import
            show_bulk_import(embedded=True)
            return
    
    # 一括登録ボタン（編集モードでない場合のみ表示）
    if not existing_material:
        st.markdown("---")
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("📦 材料一括登録", key="bulk_import_button", use_container_width=True):
                st.session_state.bulk_import_mode = True
                st.rerun()
    
    # 編集モードの場合は既存値をform_dataに初期化（seed済みの場合はsession_stateから取得）
    if existing_material:
        # session_stateに既存フォームデータが保存されている場合はそれを使用
        existing_form_data_key = f"existing_form_data_{suffix}"
        if existing_form_data_key in st.session_state:
            form_data = dict(st.session_state[existing_form_data_key])
        else:
            # フォールバック：既存値からform_dataを初期化
            form_data = material_to_form_data(existing_material)
    else:
        form_data = {}
    
    # 材料名（正式）を st.form の外に配置して、submit時に値が消えないようにする
    scope = "edit" if is_edit_mode else "create"
    NAME_KEY = wkey("name_official", scope, material_id=material_id)
    
    st.markdown("### 1. 基本識別情報")
    col1, col2 = st.columns(2)
    with col1:
        # session_state に初期値を設定（seed で既に設定済みの場合はスキップ）
        # createモードでは主要6項目（CORE_FIELDS）のデフォルト値をsession_stateに設定しない
        if NAME_KEY not in st.session_state:
            if existing_material:
                default_name = (getattr(existing_material, "name_official", "") or "").strip()
                st.session_state[NAME_KEY] = _coerce_text_input_value(default_name)
            # else: createモードではsession_stateに設定しない（UIのデフォルトに任せる）
        else:
            # session_stateに既に値がある場合も正規化（list/dict等の不正な値に対応）
            st.session_state[NAME_KEY] = _coerce_text_input_value(st.session_state.get(NAME_KEY))
        
        # ★ text_input は必ず毎回呼ぶ（value= は削除、key だけで管理）
        name_val = st.text_input(
            "1-1 材料名（正式）*",
            key=NAME_KEY,
            help="材料の正式名称を入力してください",
        )
        # touched gate: 値の差分でtouchedを立てる（st.form内ではon_changeが使えない）
        set_touched_if_changed("name_official", NAME_KEY, name_val, scope=scope)
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        st.caption("材料IDは自動採番されます")
    
    # 画像アップロード（st.form の外に配置して、submit時に値が消えないようにする）
    # 画像は特別扱い（wkeyではなく従来のkeyを使用）
    PRIMARY_KEY = f"primary_image_{suffix}"
    CACHE_KEY = f"primary_image_cached_{suffix}"
    
    st.markdown("**1-5 画像（材料/サンプル/用途例）**")
    
    if is_edit_mode:
        # 編集モード：既存画像を表示
        existing_images = st.session_state.get(f"existing_images_{suffix}", [])
        
        if existing_images:
            st.markdown("**既存画像:**")
            for idx, img_info in enumerate(existing_images):
                if isinstance(img_info, dict):
                    kind = img_info.get('kind', 'primary')
                    public_url = img_info.get('public_url')
                    r2_key = img_info.get('r2_key')
                    
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        if public_url:
                            st.image(public_url, caption=f"{kind}画像", use_container_width=True)
                            st.markdown(f"URL: {public_url}")
                        elif r2_key:
                            st.write(f"**{kind}画像**: {r2_key}")
                        else:
                            st.write(f"**{kind}画像**: 情報なし")
                    with col2:
                        delete_key = f"delete_image_{suffix}_{idx}"
                        if st.checkbox("削除", key=delete_key, help="チェックして保存すると削除されます"):
                            # 削除フラグを session_state に保存
                            if f"deleted_images_{suffix}" not in st.session_state:
                                st.session_state[f"deleted_images_{suffix}"] = []
                            if idx not in st.session_state[f"deleted_images_{suffix}"]:
                                st.session_state[f"deleted_images_{suffix}"].append(idx)
            st.info("💡 既存画像は維持されます。新しい画像をアップロードする場合は下記から追加してください。")
        else:
            st.info("ℹ️ 既存画像はありません。")
        
        # 新規アップロード（任意）
        uploaded_files = st.file_uploader(
            "新しい画像をアップロード（任意・複数可）",
            type=['png', 'jpg', 'jpeg'],
            accept_multiple_files=True,
            key=PRIMARY_KEY,
            help="既存画像に追加する新しい画像をアップロードできます（空でも既存画像が維持されます）"
        )
    else:
        # 新規作成モード：通常のアップロード
        uploaded_files = st.file_uploader(
            "画像をアップロード（複数可）",
            type=['png', 'jpg', 'jpeg'],
            accept_multiple_files=True,
            key=PRIMARY_KEY,
            help="ドラッグ&ドロップで複数ファイルをアップロードできます"
        )
    
    # session_state にキャッシュ（submit時に値が消えないように）
    if uploaded_files:
        st.session_state[CACHE_KEY] = uploaded_files
    elif CACHE_KEY not in st.session_state:
        st.session_state[CACHE_KEY] = []
    
    # フォーム全体を st.form で囲む
    # 例外が発生しても submit ボタンに到達するよう、form ブロック全体を try/finally で囲む
    # finally ブロックで使用する変数を事前に定義（例外経路でも未定義にならないように）
    submitted = False
    button_text = "📤 投稿を送信（承認待ち）"  # デフォルト値（一般ユーザーモード）
    is_admin = os.getenv("DEBUG", "0") == "1" or os.getenv("ADMIN", "0") == "1"
    # is_edit_mode と suffix は既に188行目と194行目で定義済み（finally 内で参照可能）
    # layer1_data と layer2_data を事前に初期化（submitブロックで参照可能にするため）
    layer1_data = {}
    layer2_data = {}
    
    with st.form("material_form", clear_on_submit=False):
        try:
            # タブでレイヤー①とレイヤー②を分ける
            tab1, tab2 = st.tabs(["📋 レイヤー①：必須情報", "✨ レイヤー②：任意情報"])
            
            with tab1:
                try:
                    layer1_data = show_layer1_form(existing_material=existing_material, suffix=suffix)
                    if layer1_data:
                        # name_official/name が混ざるなら除去して上書きを防ぐ
                        layer1_data.pop("name_official", None)
                        layer1_data.pop("name", None)
                        form_data.update(layer1_data)
                except Exception as e:
                    # 例外が発生しても form を続行（ボタンは必ず表示される）
                    if _show_debug_ui():
                        st.error(f"⚠️ Layer1フォームでエラーが発生しました: {e}")
                        import traceback
                        st.code(traceback.format_exc(), language="python")
                    # エラー時は空のdictを返す（クラッシュを防ぐ）
                    layer1_data = {}
            
            with tab2:
                # show_layer2_form のシグネチャを実行時に確認して互換呼び出しに切り替える
                # form ブロック内では return を使わず、フラグ変数で制御
                layer2_data = {}
                try:
                    sig = inspect.signature(show_layer2_form)
                    params = sig.parameters
                    
                    if "existing_material" in params:
                        # existing_material パラメータが存在する場合
                        layer2_data = show_layer2_form(existing_material=existing_material, scope=scope, material_id_for_wkey=material_id)
                    else:
                        # existing_material パラメータが存在しない場合（古い実装）
                        if _show_debug_ui():
                            st.warning("⚠️ show_layer2_form が existing_material パラメータを受け取りません（古い実装）")
                            st.json({
                                "show_layer2_form.module": getattr(show_layer2_form, "__module__", None),
                                "show_layer2_form.file": inspect.getsourcefile(show_layer2_form),
                                "show_layer2_form.signature": str(sig),
                                "has_existing_material": False,
                                "parameters": list(params.keys()),
                            })
                        layer2_data = show_layer2_form(scope=scope, material_id_for_wkey=material_id)
                except TypeError as e:
                    # 念のため最終フォールバック（古い関数でも落ちない）
                    if _show_debug_ui():
                        try:
                            sig = inspect.signature(show_layer2_form)
                            params = sig.parameters
                            st.error(f"⚠️ Layer2呼び出しでTypeError: {e}")
                            st.json({
                                "show_layer2_form.module": getattr(show_layer2_form, "__module__", None),
                                "show_layer2_form.file": inspect.getsourcefile(show_layer2_form),
                                "show_layer2_form.signature": str(sig),
                                "has_existing_material": "existing_material" in params,
                                "parameters": list(params.keys()),
                                "error": str(e),
                            })
                        except Exception as diag_error:
                            st.error(f"⚠️ Layer2呼び出しでTypeError: {e}（診断情報の取得も失敗: {diag_error}）")
                    # フォールバック: existing_material なしで呼び出す
                    try:
                        layer2_data = show_layer2_form(scope=scope, material_id_for_wkey=material_id)
                    except Exception as fallback_error:
                        # それでも失敗する場合は空のdictを設定（クラッシュを防ぐ）
                        if _show_debug_ui():
                            st.error(f"⚠️ show_layer2_form() の呼び出しに失敗しました: {fallback_error}")
                        layer2_data = {}
                except Exception as e:
                    # その他の予期しない例外
                    if _show_debug_ui():
                        st.error(f"⚠️ show_layer2_form の呼び出しで予期しないエラー: {e}")
                        import traceback
                        st.code(traceback.format_exc(), language="python")
                    layer2_data = {}
                
                # layer2_data を form_data に反映
                if layer2_data:
                    # name_official/name が混ざるなら除去して上書きを防ぐ
                    layer2_data.pop("name_official", None)
                    layer2_data.pop("name", None)
                    form_data.update(layer2_data)
            
            # 掲載可否の設定
            st.markdown("---")
            st.markdown("### 📢 掲載設定")
            pub_key = wkey("is_published", scope, material_id=material_id)
            
            # 過去のsession_stateのゴミを吸収する正規化
            # 1) 旧key（is_published_<id> / is_published_new 等）で suffix と違うものが存在したら削除する（移行のため）
            for k in list(st.session_state.keys()):
                if k.startswith("is_published_") and k != pub_key:
                    del st.session_state[k]
            
            # 2) st.session_state[pub_key] の正規化（すべての古い値パターンに対応）
            if pub_key in st.session_state:
                pub_value = st.session_state[pub_key]
                normalized = None
                
                # 文字列 "公開"/"非公開" なら 1/0 に変換
                if pub_value == "公開":
                    normalized = 1
                elif pub_value == "非公開":
                    normalized = 0
                # True/False なら 1/0 に変換
                elif pub_value is True:
                    normalized = 1
                elif pub_value is False:
                    normalized = 0
                # 文字列 "1"/"0" なら int に変換
                elif isinstance(pub_value, str):
                    if pub_value.strip() == "1":
                        normalized = 1
                    elif pub_value.strip() == "0":
                        normalized = 0
                    else:
                        # その他の文字列は削除
                        normalized = None
                # int 1/0 はそのまま
                elif pub_value in (1, 0):
                    normalized = pub_value
                # None やその他の値は削除
                else:
                    normalized = None
                
                if normalized is not None:
                    st.session_state[pub_key] = normalized
                else:
                    # 正規化できない値は削除
                    del st.session_state[pub_key]
            
            # 3) default は existing_material.is_published があればそれを int化
            # createモードでは主要6項目（CORE_FIELDS）のデフォルト値をsession_stateに設定しない
            # editモード: touchedが立っていない限り代入しない（ユーザー操作を潰さないため）
            if pub_key not in st.session_state:
                if existing_material:
                    # 初回seedのみ許可（毎rerunで上書き禁止）
                    default_pub = int(getattr(existing_material, "is_published", 1) or 1)
                    st.session_state[pub_key] = default_pub
                # else: createモードではsession_stateに設定しない（UIのデフォルトに任せる）
            
            # 4) radio の options は int に統一して [1, 0] を使う
            # 5) 表示は format_func で "公開/非公開" に変換する
            is_published = st.radio(
                "掲載:",
                options=[1, 0],
                format_func=lambda v: "公開" if int(v) == 1 else "非公開",
                key=pub_key,
                horizontal=True,
            )
            
            # 6) form_data['is_published'] には必ず int を入れる
            form_data['is_published'] = int(is_published)
            
            # touched gate: 値の差分でtouchedを立てる（st.form内ではon_changeが使えない）
            default_pub = 1  # createモードのデフォルト
            existing_pub = int(getattr(existing_material, "is_published", 1) or 1) if existing_material else None
            set_touched_if_changed("is_published", pub_key, form_data['is_published'], 
                                 default_value=default_pub, existing_value=existing_pub, scope=scope)
            
            # 管理者モードかどうかを判定（finally ブロックでも使用するため、try ブロック内で更新）
            is_admin = os.getenv("DEBUG", "0") == "1" or os.getenv("ADMIN", "0") == "1"
            
            # 投稿者情報（一般ユーザー用、任意）
            submitted_by = None
            try:
                if not is_admin and not is_edit_mode:
                    st.markdown("---")
                    st.markdown("### 📝 投稿者情報（任意）")
                    submitted_by = st.text_input(
                        "ニックネーム / メールアドレス（任意）",
                        key=f"submitted_by_{suffix}",
                        help="承認連絡が必要な場合に使用します（任意入力）"
                    )
                    if submitted_by and submitted_by.strip() == "":
                        submitted_by = None
            except Exception as e:
                # 例外が発生しても form を続行（ボタンは必ず表示される）
                if _show_debug_ui():
                    st.error(f"⚠️ 投稿者情報でエラーが発生しました: {e}")
                submitted_by = None
        
        except Exception as e:
            # form ブロック全体で例外が発生した場合でも、submit ボタンに到達する
            if _show_debug_ui():
                st.error(f"⚠️ フォーム描画中にエラーが発生しました: {e}")
                import traceback
                st.code(traceback.format_exc(), language="python")
        
        finally:
            # フォーム送信ボタン（form ブロック内で必ず1個だけ存在、finally で必ず実行される）
            # 条件分岐で button_text を変えるが、ボタン自体は常に存在する
            # 注意: is_edit_mode と is_admin は form 開始前に定義済み（例外経路でも参照可能）
            if is_edit_mode or is_admin:
                # 管理者モードまたは編集モード：直接materialsに保存
                button_text = "✅ 材料を更新" if is_edit_mode else "✅ 材料を登録"
            else:
                # 一般ユーザーモード：submissionsに保存
                button_text = "📤 投稿を送信（承認待ち）"
            
            # 必ず form ブロック内で submit ボタンを定義（finally ブロックで必ず実行される）
            submitted = st.form_submit_button(button_text, type="primary", use_container_width=True)
            
            # DEBUG用（submitted が True のときだけ、管理者のみ表示）
            if submitted and _show_debug_ui():
                st.success("DEBUG: submitted=True (フォーム送信を検知)")
    
    # submitted 時は、extract_payloadでwkeyから値を収集
    if submitted:
        # DEBUG_ENV=1のときだけ、投稿直前に5項目のkeyと値をログ出力
        try:
            from utils.settings import get_flag
            debug_env_enabled = get_flag("DEBUG_ENV", False)
        except Exception:
            debug_env_enabled = os.getenv("DEBUG_ENV", "0") == "1"
        
        # CORE_FIELDS取得用ヘルパー関数（優先順位: layer1_data -> layer2_data -> form_data）
        def _pick_core_val(field: str, layer1_data, layer2_data, form_data):
            """CORE_FIELDSの値を優先順位で取得（widget返り値が必ず勝つ）"""
            if isinstance(layer1_data, dict) and field in layer1_data:
                return layer1_data.get(field)
            if isinstance(layer2_data, dict) and field in layer2_data:
                return layer2_data.get(field)
            if isinstance(form_data, dict):
                return form_data.get(field)
            return None
        
        # submit直前ログ: transparencyの優先順位確認（DEBUG_ENV=1時のみ）
        if debug_env_enabled:
            logger.warning(f"[SUBMIT_CORE_PICK] layer1={layer1_data.get('transparency') if isinstance(layer1_data, dict) else None!r} layer2={layer2_data.get('transparency') if isinstance(layer2_data, dict) else None!r} form_data={form_data.get('transparency') if isinstance(form_data, dict) else None!r}")
        
        # submit直前ログ: widget return値を確認（layer1_data/form_data）
        if debug_env_enabled:
            transparency_from_layer1 = layer1_data.get('transparency') if isinstance(layer1_data, dict) else None
            transparency_from_form_data = form_data.get('transparency') if isinstance(form_data, dict) else None
            logger.warning(f"[SUBMIT_SNAPSHOT] transparency_from_layer1={transparency_from_layer1!r} transparency_from_form_data={transparency_from_form_data!r}")
        
        # ---- name_official を直接取得（方式1: 最も堅牢） ----
        # st.text_input の返り値（name_val）から直接取得（session_state依存を排除）
        # name_val は widget の返り値なので、key不一致の影響を受けない
        coerced = _coerce_text_input_value(name_val)
        name_clean = str(coerced or "").strip()
        
        # payloadを初期化し、name_officialを最初に設定
        payload = {}
        if name_clean:
            payload["name_official"] = name_clean
        
        # ---- CORE_FIELDS を widget返り値dict（layer1_data優先）から取得 ----
        # widget返り値が必ず勝つように、優先順位: layer1_data -> layer2_data -> form_data
        
        # B) CORE_FIELDS（name_official以外）を優先順位で取得（touched gate付き）
        for field in CORE_FIELDS:
            # name_official は既に設定済みなのでスキップ
            if field == "name_official":
                continue
            
            # widget key を生成（ウィジェット生成時と同じ wkey を使用）
            key = wkey(field, scope, material_id=material_id if scope == "edit" else None, submission_id=None)
            touched = bool(st.session_state.get(f"touched:{key}", False))
            
            # 優先順位: layer1_data -> layer2_data -> form_data（widget返り値が必ず勝つ）
            val = _pick_core_val(field, layer1_data, layer2_data, form_data)
            
            # scope別の追加ロジック
            # - edit: touchedがTrueのときだけ追加（上書き事故防止）
            # - create: touchedを見ずに追加（デフォルト値も含めて保存）、ただしvalがNoneの場合は入れない
            included = 0
            reason = ""
            if scope == "edit":
                if touched:
                    payload[field] = val
                    included = 1
                    reason = "edit+touched"
                else:
                    reason = "edit+not_touched"
            else:  # scope == "create"
                if val is not None:
                    payload[field] = val
                    included = 1
                    reason = "create+always"
                else:
                    reason = "skipped_none"
            
        
        
        # D) extract_payloadでwkeyから値を収集（CANONICAL_FIELDSのみ）
        extracted = extract_payload(scope, material_id=material_id if is_edit_mode else None, submission_id=None)
        
        # extract_payloadの結果からCORE_FIELDSを全て削除してからマージ（widget返り値を優先）
        for core_field in CORE_FIELDS:
            extracted.pop(core_field, None)
        # name_official は上書きしない（既に設定済み）
        extracted.pop("name_official", None)
        payload.update(extracted)
        
        # DEBUG_ENV=1のときのみ、最終payloadのCORE_FIELDSを1行でログ出力
        if debug_env_enabled:
            core_fields_summary = {}
            for field in CORE_FIELDS:
                val = payload.get(field)
                if val is not None:
                    val_str = str(val)
                    if len(val_str) > 50:
                        val_str = val_str[:47] + "..."
                    core_fields_summary[field] = val_str
                else:
                    core_fields_summary[field] = "(missing)"
            logger.warning(f"[SUBMIT_PAYLOAD_CORE] scope={scope!r} {core_fields_summary}")
        
        # デバッグログ（送信直前）
        _debug_dump_form_state(prefix="mf:")
        
        # payloadをベースにform_dataを作成（extract_payload()のみから作成）
        form_data = payload.copy()
        
        # 通称の削除/追加処理（従来のkeyから取得）
        if '_alias_del_flags' in st.session_state:
            # 削除フラグが True のものを除外
            aliases_filtered = []
            for i, alias in enumerate(form_data.get('name_aliases', [])):
                if not form_data['_alias_del_flags'].get(i, False):
                    aliases_filtered.append(alias)
            form_data['name_aliases'] = aliases_filtered
            
            # 新しい通称を追加（重複チェック）
            new_alias = form_data.get('_new_alias', '').strip()
            if new_alias and new_alias not in form_data['name_aliases']:
                form_data['name_aliases'].append(new_alias)
            
            # 一時的なキーを削除
            form_data.pop('_alias_del_flags', None)
            form_data.pop('_new_alias', None)
        
        # 参照URLの削除/追加処理（従来のkeyから取得、payloadには含まれない）
        # 削除フラグの処理
        ref_urls_from_payload = form_data.get('reference_urls', [])
        ref_urls_filtered = []
        # 削除フラグはst.session_stateのdel_ref_{i}キーから取得
        for i, ref in enumerate(ref_urls_from_payload):
            if not st.session_state.get(f'del_ref_{i}', False):
                ref_urls_filtered.append(ref)
        
        # 使用例の削除/追加処理（従来のkeyから取得、payloadには含まれない）
        # 削除フラグの処理
        use_examples_from_payload = form_data.get('use_examples', [])
        use_examples_filtered = []
        # 削除フラグはst.session_stateのdel_ex_{i}キーから取得
        for i, ex in enumerate(use_examples_from_payload):
            if not st.session_state.get(f'del_ex_{i}', False):
                use_examples_filtered.append(ex)
        
        # 参照URLの追加処理（従来のkeyから取得、payloadには含まれない）
        if 'new_ref_url' in st.session_state:
            new_ref_url = st.session_state.get('new_ref_url', '').strip()
            if new_ref_url:
                new_ref = {
                    "url": new_ref_url,
                    "type": st.session_state.get('new_ref_type', ''),
                    "desc": st.session_state.get('new_ref_desc', '').strip()
                }
                if new_ref['url'] not in [r.get('url', '') for r in ref_urls_filtered]:
                    ref_urls_filtered.append(new_ref)
        
        # 使用例の追加処理（従来のkeyから取得、payloadには含まれない）
        if 'new_ex_name' in st.session_state:
            new_ex_name = st.session_state.get('new_ex_name', '').strip()
            if new_ex_name:
                new_ex = {
                    "name": new_ex_name,
                    "url": st.session_state.get('new_ex_url', '').strip(),
                    "desc": st.session_state.get('new_ex_desc', '').strip()
                }
                if new_ex['name'] not in [e.get('name', '') for e in use_examples_filtered]:
                    use_examples_filtered.append(new_ex)
        
        # フィルタ済みの参照URLと使用例をform_dataに設定
        form_data['reference_urls'] = ref_urls_filtered
        form_data['use_examples'] = use_examples_filtered
        
        # name_official は既にpayloadに設定済み（直接取得方式）
        # フォールバック処理は不要（方式1で確実に取得済み）
        
        # 画像を session_state のキャッシュから取得（submit時に確実に保持される）
        CACHE_KEY = f"primary_image_cached_{suffix}"
        cached_files = st.session_state.get(CACHE_KEY, [])
        uploaded_files = normalize_uploaded_files(cached_files)
        
        # 編集モード時の既存画像処理
        if is_edit_mode and material_id:
            # 削除フラグを取得
            deleted_indices = st.session_state.get(f"deleted_images_{suffix}", [])
            if deleted_indices:
                form_data['deleted_image_indices'] = deleted_indices
            else:
                form_data['deleted_image_indices'] = []
        
        # 画像枚数をログ出力
        cached_image_count = len(uploaded_files)
        logger.info(f"[MATERIAL FORM] cached_image_count={cached_image_count}, is_edit_mode={is_edit_mode}")
        
        # DEBUG=1 のときは UI にも表示
        if _show_debug_ui():
            st.info(f"📸 キャッシュ画像: {cached_image_count} 枚")
            for idx, img in enumerate(uploaded_files):
                if hasattr(img, 'name'):
                    logger.info(f"[MATERIAL FORM] Cached image {idx+1}: {img.name}")
        
        # form_data の images を設定（確実に取得）
        # 編集モードで新規アップロードが空の場合は None を設定（既存画像を維持）
        if is_edit_mode and material_id and not uploaded_files:
            form_data['images'] = None  # 既存画像を維持
        else:
            form_data['images'] = uploaded_files
        
        # 画像枚数をログ出力
        image_count = len(form_data.get('images', [])) if form_data.get('images') else 0
        logger.info(f"[MATERIAL FORM] Submitted: image_count={image_count}, is_edit_mode={is_edit_mode}")
        if image_count > 0:
            st.info(f"📸 選択された画像: {image_count} 枚")
            for idx, img in enumerate(form_data['images']):
                if hasattr(img, 'name'):
                    logger.info(f"[MATERIAL FORM] Image {idx+1}: {img.name}")
        else:
            if is_edit_mode:
                st.info("ℹ️ 新しい画像はアップロードされませんでした（既存画像が維持されます）")
            else:
                st.info("ℹ️ 画像は選択されていません")
            logger.info(f"[MATERIAL FORM] No images selected (is_edit_mode={is_edit_mode})")
        
        # name_official は extract_payload() から取得済み（キャッシュ上書きを削除）
        # 後方互換性のため name も設定
        if 'name_official' in form_data:
            form_data["name"] = form_data["name_official"]
        
        # 編集モードの場合、既存値とマージ（フォームで触ってないキーは既存値を保持）
        if is_edit_mode and material_id:
            existing_form_data_key = f"existing_form_data_{suffix}"
            if existing_form_data_key in st.session_state:
                existing_form_data = st.session_state[existing_form_data_key]
                
                # フォームで触ったキーを記録（form_dataに存在するキー）
                form_touched_keys = set(form_data.keys())
                
                # 既存値でマージ（フォームで触ってないキーは既存値を保持）
                for key, existing_value in existing_form_data.items():
                    # システムキーやリレーションは除外
                    if key in {"id", "created_at", "updated_at", "deleted_at", "uuid", "search_text", "existing_images"}:
                        continue
                    
                    # フォームで触ってないキーは既存値を保持
                    if key not in form_touched_keys:
                        form_data[key] = existing_value
                
                # DEBUG時のみログ出力
                if os.getenv("DEBUG", "0") == "1":
                    preserved_keys = [k for k in existing_form_data.keys() if k not in form_touched_keys and k not in {"id", "created_at", "updated_at", "deleted_at", "uuid", "search_text", "existing_images"}]
                    logger.info(f"[SUBMIT] is_edit_mode=True, material_id={material_id}, payload_keys_count={len(form_touched_keys)}, preserved_keys_count={len(preserved_keys)}")
        
        # save_material_submission() の直前に "最終値" をログに出す（DEBUG=0でも1行出す）
        logger.info(f"[SUBMIT] final name_official='{form_data.get('name_official')}' payload_keys_count={len(form_data)}")
        
        # フォーム送信処理
        if is_edit_mode or is_admin:
            # 管理者モードまたは編集モード：直接materialsに保存
            try:
                result = save_material(form_data, material_id=material_id if is_edit_mode else None)
                if _show_debug_ui():
                    st.success(f"DEBUG: save_material returned: {result}")
            except Exception as e:
                import traceback
                if _show_debug_ui():
                    st.error(f"DEBUG: save_material exception: {e}")
                    st.code(traceback.format_exc())
                else:
                    st.error("材料の保存中にエラーが発生しました。")
                st.stop()
            
            # 防御的にresult.get("ok")で分岐
            if result.get("ok"):
                # 成功時：result["action"]でcreated/updatedを判定してメッセージ表示
                if result.get("action") == 'created':
                    st.success("✅ 材料を新規登録しました！")
                else:
                    st.success("✅ 材料を更新しました！")
                    # 編集モードの場合は編集完了フラグを設定
                    if is_edit_mode:
                        st.session_state.edit_completed = True
                        # 編集ページから一覧に戻る（フォーム外なので st.button を使用可能）
                        if st.button("← 一覧に戻る", key="back_after_edit"):
                            st.session_state.edit_material_id = None
                            st.session_state.page = "材料一覧"
                            st.rerun()
            else:
                # 失敗時：st.error(result["error"])とst.expanderでtraceback表示
                error_msg = result.get('error', '不明なエラー')
                st.error(f"❌ エラーが発生しました: {error_msg}")
                # name_official が空の場合は特別なメッセージを表示
                if result.get("error_code") == "name_official_empty":
                    st.info("💡 材料名（正式）を入力してから再度送信してください。")
                if result.get("traceback"):
                    with st.expander("🔍 エラー詳細（デバッグ用）", expanded=False):
                        st.code(result["traceback"], language="python")
        else:
            # 一般ユーザーモード：submissionsに保存
            if form_data:
                # DEBUG_ENV=1のときだけ、投稿直前に5項目のkeyと値をログ出力
                try:
                    from utils.settings import get_flag
                    debug_env_enabled = get_flag("DEBUG_ENV", False)
                except Exception:
                    debug_env_enabled = os.getenv("DEBUG_ENV", "0") == "1"
                
                # submit直前ログ: transparencyの優先順位確認（DEBUG_ENV=1時のみ）
                if debug_env_enabled:
                    logger.warning(f"[SUBMIT_CORE_PICK] layer1={layer1_data.get('transparency') if isinstance(layer1_data, dict) else None!r} layer2={layer2_data.get('transparency') if isinstance(layer2_data, dict) else None!r} form_data={form_data.get('transparency') if isinstance(form_data, dict) else None!r}")
                
                # submit直前ログ: widget return値を確認（layer1_data/form_data）
                if debug_env_enabled:
                    transparency_from_layer1 = layer1_data.get('transparency') if isinstance(layer1_data, dict) else None
                    transparency_from_form_data = form_data.get('transparency') if isinstance(form_data, dict) else None
                    logger.warning(f"[SUBMIT_SNAPSHOT] transparency_from_layer1={transparency_from_layer1!r} transparency_from_form_data={transparency_from_form_data!r}")
                
                # ---- name_official を直接取得（方式1: 最も堅牢） ----
                # st.text_input の返り値（name_val）から直接取得（session_state依存を排除）
                # name_val は widget の返り値なので、key不一致の影響を受けない
                coerced = _coerce_text_input_value(name_val)
                name_clean = str(coerced or "").strip()
                
                # payloadを初期化し、name_officialを最初に設定
                payload = {}
                if name_clean:
                    payload["name_official"] = name_clean
                
                # ---- CORE_FIELDS を widget返り値dict（layer1_data優先）から取得 ----
                # widget返り値が必ず勝つように、優先順位: layer1_data -> layer2_data -> form_data
                
                # B) CORE_FIELDS（name_official以外）を優先順位で取得（一般ユーザーは常にcreate）
                scope_submit = "create"  # E) 変数の整合性チェック: submitのscopeをそのまま使う（外側のscopeを上書きしない）
                for field in CORE_FIELDS:
                    # name_official は既に設定済みなのでスキップ
                    if field == "name_official":
                        continue
                    
                    # widget key を生成（ウィジェット生成時と同じ wkey を使用）
                    key = wkey(field, scope_submit, material_id=None, submission_id=None)
                    touched = bool(st.session_state.get(f"touched:{key}", False))  # ログ用に保持
                    
                    # 優先順位: layer1_data -> layer2_data -> form_data（widget返り値が必ず勝つ）
                    val = _pick_core_val(field, layer1_data, layer2_data, form_data)
                    
                    # 一般ユーザーは常にcreateなので、touchedを見ずに常にpayloadに入れる（valがNoneの場合はスキップ）
                    included = 0
                    reason = ""
                    if val is not None:
                        payload[field] = val
                        included = 1
                        reason = "create+always"
                    else:
                        reason = "skipped_none"
                    
                
                
                # D) extract_payloadでwkeyから値を収集（CANONICAL_FIELDSのみ）
                extracted = extract_payload(scope_submit, material_id=None, submission_id=None)
                
                # extract_payloadの結果からCORE_FIELDSを全て削除してからマージ（widget返り値を優先）
                for core_field in CORE_FIELDS:
                    extracted.pop(core_field, None)
                # name_official は上書きしない（既に設定済み）
                extracted.pop("name_official", None)
                payload.update(extracted)
                
                # DEBUG_ENV=1のときのみ、最終payloadのCORE_FIELDSを1行でログ出力
                if debug_env_enabled:
                    core_fields_summary = {}
                    for field in CORE_FIELDS:
                        val = payload.get(field)
                        if val is not None:
                            val_str = str(val)
                            if len(val_str) > 50:
                                val_str = val_str[:47] + "..."
                            core_fields_summary[field] = val_str
                        else:
                            core_fields_summary[field] = "(missing)"
                    logger.warning(f"[SUBMIT_PAYLOAD_CORE] scope={scope_submit!r} {core_fields_summary}")
                
                # デバッグログ（送信直前）
                _debug_dump_form_state(prefix="mf:")
                
                # name_officialの必須チェック
                if not payload.get("name_official") or not payload["name_official"].strip():
                    st.error("❌ 材料名（正式）が空です。送信できません。")
                    logger.warning(f"[SUBMIT] blocked: name_official empty in payload")
                else:
                    # 画像を取得（従来のkeyを使用）
                    CACHE_KEY = f"primary_image_cached_{suffix}"
                    cached_files = st.session_state.get(CACHE_KEY, [])
                    uploaded_files = normalize_uploaded_files(cached_files)
                    
                    # DEBUG時のみログ出力
                    if os.getenv("DEBUG", "0") == "1":
                        logger.info(f"[SUBMIT] payload_keys={list(payload.keys())}, payload_sample={dict(list(payload.items())[:5])}")
                    
                    result = save_material_submission(payload, uploaded_files=uploaded_files, submitted_by=submitted_by)
                    
                    # 防御的にresult.get("ok")で分岐
                    if result.get("ok"):
                        submission_id = result.get("submission_id")
                        submission_uuid = result.get("uuid")
                        uploaded_images = result.get("uploaded_images", [])
                        
                        st.success("✅ 投稿を送信しました！管理者の承認をお待ちください。")
                        st.info("📝 承認後、材料一覧に表示されます。")
                        st.markdown("---")
                        st.markdown("### 📋 投稿控え")
                        st.code(f"投稿ID: {submission_id}\nUUID: {submission_uuid}", language="text")
                        st.info("💡 このIDを控えておくと、後で投稿ステータスを確認できます。")
                        
                        # アップロードされた画像のプレビュー
                        if uploaded_images:
                            st.markdown("---")
                            st.markdown("### 📷 アップロードされた画像")
                            for img_info in uploaded_images:
                                kind = img_info.get('kind', 'primary')
                                public_url = img_info.get('public_url')
                                if public_url:
                                    st.markdown(f"**{kind}画像:**")
                                    st.image(public_url, caption=f"{kind}画像", use_container_width=True)
                                    st.caption(f"URL: {public_url}")
                    else:
                        # 失敗時：st.error(result["error"])とst.expanderでtraceback表示
                        error_msg = result.get('error', '不明なエラー')
                        st.error(f"❌ エラーが発生しました: {error_msg}")
                        # name_official が空の場合は特別なメッセージを表示
                        if result.get("error_code") == "name_official_empty":
                            st.info("💡 材料名（正式）を入力してから再度送信してください。")
                        if result.get("traceback"):
                            with st.expander("🔍 エラー詳細（デバッグ用）", expanded=False):
                                st.code(result["traceback"], language="python")


def show_layer1_form(existing_material=None, suffix="new"):
    """
    レイヤー①：必須情報フォーム
    
    Args:
        existing_material: 編集モードの場合、既存のMaterialオブジェクト
        suffix: サフィックス（material_id or "new"）
    """
    form_data = {}
    
    # scopeとmaterial_idを決定（suffixから推測）
    scope = "edit" if existing_material else "create"
    material_id_for_wkey = existing_material.id if existing_material else None
    
    # name_official は st.form の外で処理されるため、ここでは何もしない
    # （show_detailed_material_form で form_data に設定済み）
    
    # 材料名（通称・略称）複数（st.form内で完結）
    st.markdown("**1-2 材料名（通称・略称）**")
    
    # session_state の初期化（初回のみ）
    if 'aliases' not in st.session_state:
        if existing_material:
            # 編集モード：既存値を初期化
            existing_aliases = getattr(existing_material, 'name_aliases', None)
            if existing_aliases:
                try:
                    import json
                    st.session_state.aliases = json.loads(existing_aliases) if isinstance(existing_aliases, str) else existing_aliases
                except:
                    st.session_state.aliases = [""]
            else:
                st.session_state.aliases = [""]
        else:
            st.session_state.aliases = [""]
    
    # 既存の通称を表示（削除チェックボックス付き）
    aliases = []
    for i, alias in enumerate(st.session_state.aliases):
        # session_state に初期値を設定（既に値がある場合は上書きしない）
        alias_key = f"alias_{i}"
        if alias_key not in st.session_state:
            st.session_state[alias_key] = alias
        
        col1, col2 = st.columns([5, 1])
        with col1:
            alias_val = st.text_input(f"通称 {i+1}", key=alias_key)
            if alias_val:
                aliases.append(alias_val)
        with col2:
            # 削除チェックボックス（フォーム内で使用可能）
            del_flag = st.checkbox("削除", key=f"del_alias_{i}", help="チェックして保存すると削除されます")
            if del_flag:
                # チェックされたものは除外（送信時に処理）
                pass
    
    # 追加する通称の入力
    new_alias = st.text_input("➕ 追加する通称（入力して保存すると追加されます）", key="new_alias", placeholder="新しい通称を入力")
    
    # 送信時に処理（ここでは form_data に反映するだけ）
    # 実際の削除/追加処理は submitted 時に実行
    form_data['name_aliases'] = [a for a in aliases if a]
    form_data['_alias_del_flags'] = {i: st.session_state.get(f"del_alias_{i}", False) for i in range(len(st.session_state.aliases))}
    form_data['_new_alias'] = new_alias.strip() if new_alias else ""
    
    # 供給元・開発主体
    st.markdown("**1-3 供給元・開発主体***")
    col1, col2 = st.columns([2, 1])
    with col1:
        # session_state に初期値を設定（seed で既に設定済みの場合はスキップ）
        supplier_org_key = wkey("supplier_org", scope, material_id=material_id_for_wkey)
        if supplier_org_key not in st.session_state:
            default_supplier_org = getattr(existing_material, 'supplier_org', '') if existing_material else ''
            st.session_state[supplier_org_key] = default_supplier_org
        form_data['supplier_org'] = st.text_input("組織名*", key=supplier_org_key)
    with col2:
        # selectbox の index を計算（session_state があればそれ優先）
        supplier_type_key = wkey("supplier_type", scope, material_id=material_id_for_wkey)
        if supplier_type_key in st.session_state:
            supplier_type_value = st.session_state[supplier_type_key]
            supplier_type_index = SUPPLIER_TYPES.index(supplier_type_value) if supplier_type_value in SUPPLIER_TYPES else 0
        else:
            default_supplier_type = getattr(existing_material, 'supplier_type', SUPPLIER_TYPES[0]) if existing_material else SUPPLIER_TYPES[0]
            supplier_type_index = SUPPLIER_TYPES.index(default_supplier_type) if default_supplier_type in SUPPLIER_TYPES else 0
            st.session_state[supplier_type_key] = SUPPLIER_TYPES[supplier_type_index]
        form_data['supplier_type'] = st.selectbox("種別*", SUPPLIER_TYPES, index=supplier_type_index, key=supplier_type_key)
        if form_data['supplier_type'] == "その他（自由記述）":
            supplier_other_key = wkey("supplier_other", scope, material_id=material_id_for_wkey)
            if supplier_other_key not in st.session_state:
                default_supplier_other = getattr(existing_material, 'supplier_other', '') if existing_material else ''
                st.session_state[supplier_other_key] = default_supplier_other
            form_data['supplier_other'] = st.text_input("その他（詳細）", key=supplier_other_key)
    
    # 参照URL（複数）（st.form内で完結）
    st.markdown("**1-4 参照URL（公式/製品/論文/プレス等）**")
    
    # session_state の初期化（初回のみ）
    if 'ref_urls' not in st.session_state:
        if existing_material and form_data.get('reference_urls'):
            # 編集モード：既存値を初期化（dict から取得、DetachedInstanceError 防止）
            st.session_state.ref_urls = form_data.get('reference_urls', [])
        else:
            st.session_state.ref_urls = [{"url": "", "type": "", "desc": ""}]
    
    ref_urls = []
    ref_type_options = ["公式", "製品", "論文", "プレス", "その他"]
    for i, ref in enumerate(st.session_state.ref_urls):
        # session_state に初期値を設定
        ref_url_key = f"ref_url_{i}"
        ref_type_key = f"ref_type_{i}"
        ref_desc_key = f"ref_desc_{i}"
        
        if ref_url_key not in st.session_state:
            st.session_state[ref_url_key] = ref.get('url', '')
        if ref_type_key not in st.session_state:
            ref_type_value = ref.get('type', '公式')
            ref_type_index = ref_type_options.index(ref_type_value) if ref_type_value in ref_type_options else 0
            st.session_state[ref_type_key] = ref_type_options[ref_type_index]
        if ref_desc_key not in st.session_state:
            st.session_state[ref_desc_key] = ref.get('desc', '')
        
        with st.expander(f"URL {i+1}", expanded=False):
            col1, col2 = st.columns([3, 1])
            with col1:
                url_val = st.text_input("URL", key=ref_url_key)
            with col2:
                # selectbox の index を計算（session_state があればそれ優先）
                if ref_type_key in st.session_state:
                    ref_type_value = st.session_state[ref_type_key]
                    ref_type_index = ref_type_options.index(ref_type_value) if ref_type_value in ref_type_options else 0
                else:
                    ref_type_index = 0
                url_type = st.selectbox("種別", ref_type_options, index=ref_type_index, key=ref_type_key)
            desc = st.text_input("メモ", key=ref_desc_key)
            if url_val:
                ref_urls.append({"url": url_val, "type": url_type, "desc": desc})
            # 削除チェックボックス（フォーム内で使用可能）
            del_flag = st.checkbox("削除", key=f"del_ref_{i}", help="チェックして保存すると削除されます")
    
    # 追加するURLの入力
    st.markdown("**➕ 新しいURLを追加**")
    new_url = st.text_input("URL", key="new_ref_url", placeholder="新しいURLを入力")
    new_url_type = st.selectbox("種別", ["公式", "製品", "論文", "プレス", "その他"], key="new_ref_type")
    new_url_desc = st.text_input("メモ", key="new_ref_desc", placeholder="メモ（任意）")
    
    # 送信時に処理（ここでは form_data に反映するだけ）
    form_data['reference_urls'] = ref_urls
    form_data['_ref_del_flags'] = {i: st.session_state.get(f"del_ref_{i}", False) for i in range(len(st.session_state.ref_urls))}
    form_data['_new_ref_url'] = new_url.strip() if new_url else ""
    form_data['_new_ref_type'] = new_url_type if new_url else ""
    form_data['_new_ref_desc'] = new_url_desc.strip() if new_url_desc else ""
    
    st.markdown("---")
    st.markdown("### 2. 分類")
    
    # scope と material_id_for_wkey は既に1142-1143行目で定義済み（重複定義を削除）
    
    # category_main selectbox の index を計算（UI表示と内部値の整合を保証）
    category_main_key = wkey("category_main", scope, material_id=material_id_for_wkey)
    options = MATERIAL_CATEGORIES
    
    # current_value を優先順で取得: 1) session_state 2) edit時のexisting_material 3) None
    current_value = st.session_state.get(category_main_key)
    if current_value is None or (isinstance(current_value, str) and current_value.strip() == ""):
        # session_stateに値が無い場合、editモードで既存materialから取得
        if scope == "edit" and existing_material:
            current_value = getattr(existing_material, 'category_main', None)
        else:
            current_value = None
    
    # index を計算（optionsに存在すればそのindex、なければ0にフォールバック）
    if current_value and current_value in options:
        category_main_index = options.index(current_value)
        # editモード: touchedが立っていない限り代入しない（ユーザー操作を潰さないため）
        # 初回seedのみ許可（毎rerunで上書き禁止）
        if scope == "edit" and existing_material and category_main_key not in st.session_state:
            st.session_state[category_main_key] = current_value
    else:
        # optionsに存在しない、またはcurrent_valueがNoneの場合は0にフォールバック
        category_main_index = 0
    form_data['category_main'] = st.selectbox(
        "2-1 材料カテゴリ（大分類）*",
        MATERIAL_CATEGORIES,
        index=category_main_index,
        key=category_main_key,
    )
    # touched gate: 値の差分でtouchedを立てる（st.form内ではon_changeが使えない）
    default_category = MATERIAL_CATEGORIES[0] if scope == "create" else None
    existing_category = getattr(existing_material, 'category_main', None) if existing_material else None
    set_touched_if_changed("category_main", category_main_key, form_data['category_main'],
                         default_value=default_category, existing_value=existing_category, scope=scope)
    if form_data['category_main'] == "その他（自由記述）":
        form_data['category_other'] = st.text_input("その他（詳細）", key=wkey("category_other", scope, material_id=material_id_for_wkey))
    
    form_data['material_forms'] = st.multiselect(
        "2-2 材料形態（供給形状）*",
        MATERIAL_FORMS,
        key=wkey("material_forms", scope, material_id=material_id_for_wkey)
    )
    if "その他（自由記述）" in form_data['material_forms']:
        form_data['material_forms_other'] = st.text_input("その他（詳細）", key=wkey("material_forms_other", scope, material_id=material_id_for_wkey))
    
    st.markdown("---")
    st.markdown("### 3. 由来・原料")
    
    # selectbox の index を計算（session_state があればそれ優先）
    origin_type_key = wkey("origin_type", scope, material_id=material_id_for_wkey)
    if origin_type_key in st.session_state:
        origin_type_value = st.session_state[origin_type_key]
        origin_type_index = ORIGIN_TYPES.index(origin_type_value) if origin_type_value in ORIGIN_TYPES else 0
    else:
        # createモードでは主要6項目（CORE_FIELDS）のデフォルト値をsession_stateに設定しない
        if existing_material:
            # editモード: touchedが立っていない限り代入しない（ユーザー操作を潰さないため）
            if origin_type_key not in st.session_state:
                # 初回seedのみ許可（毎rerunで上書き禁止）
                default_origin_type = getattr(existing_material, 'origin_type', ORIGIN_TYPES[0])
                origin_type_index = ORIGIN_TYPES.index(default_origin_type) if default_origin_type in ORIGIN_TYPES else 0
                st.session_state[origin_type_key] = ORIGIN_TYPES[origin_type_index]
            else:
                # session_stateに既に値がある場合は、その値からindexを計算
                origin_type_value = st.session_state[origin_type_key]
                origin_type_index = ORIGIN_TYPES.index(origin_type_value) if origin_type_value in ORIGIN_TYPES else 0
        else:
            # createモード: index=0（UIのデフォルトに任せる）で、session_stateには設定しない
            origin_type_index = 0
    form_data['origin_type'] = st.selectbox(
        "3-1 原料由来（一次分類）*",
        ORIGIN_TYPES,
        index=origin_type_index,
        key=origin_type_key,
    )
    # touched gate: 値の差分でtouchedを立てる（st.form内ではon_changeが使えない）
    default_origin = ORIGIN_TYPES[0] if scope == "create" else None
    existing_origin = getattr(existing_material, 'origin_type', None) if existing_material else None
    set_touched_if_changed("origin_type", origin_type_key, form_data['origin_type'],
                         default_value=default_origin, existing_value=existing_origin, scope=scope)
    if form_data['origin_type'] == "その他（自由記述）":
        origin_other_key = wkey("origin_other", scope, material_id=material_id_for_wkey)
        if origin_other_key not in st.session_state:
            default_origin_other = getattr(existing_material, 'origin_other', '') if existing_material else ''
            st.session_state[origin_other_key] = default_origin_other
        form_data['origin_other'] = st.text_input("その他（詳細）", key=origin_other_key)
    
    origin_detail_key = wkey("origin_detail", scope, material_id=material_id_for_wkey)
    if origin_detail_key not in st.session_state:
        default_origin_detail = getattr(existing_material, 'origin_detail', '') if existing_material else ''
        st.session_state[origin_detail_key] = default_origin_detail
    form_data['origin_detail'] = st.text_input(
        "3-2 原料詳細（具体名）*",
        placeholder="例：トウモロコシ由来PLA、木粉、ガラスカレット、菌糸体",
        key=origin_detail_key
    )
    
    col1, col2 = st.columns(2)
    with col1:
        form_data['recycle_bio_rate'] = st.number_input(
            "3-3 リサイクル/バイオ含有率（%）",
            min_value=0.0,
            max_value=100.0,
            value=None,
            key=wkey("recycle_bio_rate", scope, material_id=material_id_for_wkey)
        )
    with col2:
        # selectbox の index を計算（session_state があればそれ優先）
        recycle_basis_key = wkey("recycle_bio_basis", scope, material_id=material_id_for_wkey)
        recycle_basis_options = ["自己申告", "第三者認証", "文献", "不明"]
        if recycle_basis_key in st.session_state:
            recycle_basis_value = st.session_state[recycle_basis_key]
            recycle_basis_index = recycle_basis_options.index(recycle_basis_value) if recycle_basis_value in recycle_basis_options else 0
        else:
            default_recycle_basis = getattr(existing_material, 'recycle_bio_basis', recycle_basis_options[0]) if existing_material else recycle_basis_options[0]
            recycle_basis_index = recycle_basis_options.index(default_recycle_basis) if default_recycle_basis in recycle_basis_options else 0
            st.session_state[recycle_basis_key] = recycle_basis_options[recycle_basis_index]
        form_data['recycle_bio_basis'] = st.selectbox(
            "根拠",
            recycle_basis_options,
            index=recycle_basis_index,
            key=recycle_basis_key
        )
    
    st.markdown("---")
    st.markdown("### 4. 基本特性")
    
    form_data['color_tags'] = st.multiselect(
        "4-1 色*",
        COLOR_OPTIONS,
        key=wkey("color_tags", scope, material_id=material_id_for_wkey)
    )
    
    # selectbox の index を計算（session_state があればそれ優先）
    transparency_key = wkey("transparency", scope, material_id=material_id_for_wkey)
    if transparency_key in st.session_state:
        transparency_value = st.session_state[transparency_key]
        transparency_index = TRANSPARENCY_OPTIONS.index(transparency_value) if transparency_value in TRANSPARENCY_OPTIONS else 0
    else:
        # createモードでは主要6項目（CORE_FIELDS）のデフォルト値をsession_stateに設定しない
        if existing_material:
            # editモード: touchedが立っていない限り代入しない（ユーザー操作を潰さないため）
            # 初回seedのみ許可（毎rerunで上書き禁止）
            if transparency_key not in st.session_state:
                # 初回seedのみ許可（毎rerunで上書き禁止）
                default_transparency = getattr(existing_material, 'transparency', TRANSPARENCY_OPTIONS[0])
                transparency_index = TRANSPARENCY_OPTIONS.index(default_transparency) if default_transparency in TRANSPARENCY_OPTIONS else 0
                st.session_state[transparency_key] = TRANSPARENCY_OPTIONS[transparency_index]
            else:
                # session_stateに既に値がある場合は、その値からindexを計算
                transparency_value = st.session_state[transparency_key]
                transparency_index = TRANSPARENCY_OPTIONS.index(transparency_value) if transparency_value in TRANSPARENCY_OPTIONS else 0
        else:
            # createモード: index=0（UIのデフォルトに任せる）で、session_stateには設定しない
            transparency_index = 0
    form_data['transparency'] = st.selectbox(
        "透明性*",
        TRANSPARENCY_OPTIONS,
        index=transparency_index,
        key=transparency_key,
    )
    
    # DEBUG_ENV=1のときのみ、widget生成直後の値をログ出力（原因特定用）
    try:
        from utils.settings import get_flag
        debug_env_enabled = get_flag("DEBUG_ENV", False)
    except Exception:
        debug_env_enabled = os.getenv("DEBUG_ENV", "0") == "1"
    
    if debug_env_enabled:
        return_value = form_data['transparency']
        session_value = st.session_state.get(transparency_key)
        touched_key = f"touched:{transparency_key}"
        touched_value = st.session_state.get(touched_key, False)
        logger.warning(f"[WIDGET_VAL] field=transparency scope={scope!r} key={transparency_key!r} return={return_value!r} session={session_value!r}")
        logger.warning(f"[WIDGET_TOUCH] touched_key={touched_key!r} touched={touched_value!r}")
    
    # touched gate: 値の差分でtouchedを立てる（st.form内ではon_changeが使えない）
    default_transparency = TRANSPARENCY_OPTIONS[0] if scope == "create" else None
    existing_transparency = getattr(existing_material, 'transparency', None) if existing_material else None
    set_touched_if_changed("transparency", transparency_key, form_data['transparency'],
                         default_value=default_transparency, existing_value=existing_transparency, scope=scope)
    
    col1, col2 = st.columns(2)
    with col1:
        # selectbox の index を計算（session_state があればそれ優先）
        hardness_key = wkey("hardness_qualitative", scope, material_id=material_id_for_wkey)
        if hardness_key in st.session_state:
            hardness_value = st.session_state[hardness_key]
            hardness_index = HARDNESS_OPTIONS.index(hardness_value) if hardness_value in HARDNESS_OPTIONS else 0
        else:
            default_hardness = getattr(existing_material, 'hardness_qualitative', HARDNESS_OPTIONS[0]) if existing_material else HARDNESS_OPTIONS[0]
            hardness_index = HARDNESS_OPTIONS.index(default_hardness) if default_hardness in HARDNESS_OPTIONS else 0
            st.session_state[hardness_key] = HARDNESS_OPTIONS[hardness_index]
        form_data['hardness_qualitative'] = st.selectbox(
            "4-2 硬さ（定性）*",
            HARDNESS_OPTIONS,
            index=hardness_index,
            key=hardness_key
        )
    with col2:
        form_data['hardness_value'] = st.text_input(
            "硬さ（数値）",
            placeholder="例：Shore A 50, Mohs 3",
            key=wkey("hardness_value", scope, material_id=material_id_for_wkey)
        )
    
    col1, col2 = st.columns(2)
    with col1:
        # selectbox の index を計算（session_state があればそれ優先）
        weight_key = wkey("weight_qualitative", scope, material_id=material_id_for_wkey)
        if weight_key in st.session_state:
            weight_value = st.session_state[weight_key]
            weight_index = WEIGHT_OPTIONS.index(weight_value) if weight_value in WEIGHT_OPTIONS else 0
        else:
            default_weight = getattr(existing_material, 'weight_qualitative', WEIGHT_OPTIONS[0]) if existing_material else WEIGHT_OPTIONS[0]
            weight_index = WEIGHT_OPTIONS.index(default_weight) if default_weight in WEIGHT_OPTIONS else 0
            st.session_state[weight_key] = WEIGHT_OPTIONS[weight_index]
        form_data['weight_qualitative'] = st.selectbox(
            "4-3 重さ感（定性）*",
            WEIGHT_OPTIONS,
            index=weight_index,
            key=weight_key
        )
    with col2:
        form_data['specific_gravity'] = st.number_input(
            "比重",
            min_value=0.0,
            value=None,
            key=wkey("specific_gravity", scope, material_id=material_id_for_wkey)
        )
    
    # selectbox の index を計算（session_state があればそれ優先）
    water_resistance_key = wkey("water_resistance", scope, material_id=material_id_for_wkey)
    if water_resistance_key in st.session_state:
        water_resistance_value = st.session_state[water_resistance_key]
        water_resistance_index = WATER_RESISTANCE_OPTIONS.index(water_resistance_value) if water_resistance_value in WATER_RESISTANCE_OPTIONS else 0
    else:
        default_water_resistance = getattr(existing_material, 'water_resistance', WATER_RESISTANCE_OPTIONS[0]) if existing_material else WATER_RESISTANCE_OPTIONS[0]
        water_resistance_index = WATER_RESISTANCE_OPTIONS.index(default_water_resistance) if default_water_resistance in WATER_RESISTANCE_OPTIONS else 0
        st.session_state[water_resistance_key] = WATER_RESISTANCE_OPTIONS[water_resistance_index]
    form_data['water_resistance'] = st.selectbox(
        "4-4 耐水性・耐湿性*",
        WATER_RESISTANCE_OPTIONS,
        index=water_resistance_index,
        key=water_resistance_key
    )
    
    col1, col2 = st.columns(2)
    with col1:
        form_data['heat_resistance_temp'] = st.number_input(
            "4-5 耐熱性（温度℃）",
            min_value=-273.0,
            value=None,
            key=wkey("heat_resistance_temp", scope, material_id=material_id_for_wkey)
        )
    with col2:
        # selectbox の index を計算（session_state があればそれ優先）
        heat_range_key = wkey("heat_resistance_range", scope, material_id=material_id_for_wkey)
        if heat_range_key in st.session_state:
            heat_range_value = st.session_state[heat_range_key]
            heat_range_index = HEAT_RANGE_OPTIONS.index(heat_range_value) if heat_range_value in HEAT_RANGE_OPTIONS else 0
        else:
            default_heat_range = getattr(existing_material, 'heat_resistance_range', HEAT_RANGE_OPTIONS[0]) if existing_material else HEAT_RANGE_OPTIONS[0]
            heat_range_index = HEAT_RANGE_OPTIONS.index(default_heat_range) if default_heat_range in HEAT_RANGE_OPTIONS else 0
            st.session_state[heat_range_key] = HEAT_RANGE_OPTIONS[heat_range_index]
        form_data['heat_resistance_range'] = st.selectbox(
            "耐熱性（範囲）*",
            HEAT_RANGE_OPTIONS,
            index=heat_range_index,
            key=heat_range_key
        )
    
    # selectbox の index を計算（session_state があればそれ優先）
    weather_resistance_key = wkey("weather_resistance", scope, material_id=material_id_for_wkey)
    if weather_resistance_key in st.session_state:
        weather_resistance_value = st.session_state[weather_resistance_key]
        weather_resistance_index = WEATHER_RESISTANCE_OPTIONS.index(weather_resistance_value) if weather_resistance_value in WEATHER_RESISTANCE_OPTIONS else 0
    else:
        default_weather_resistance = getattr(existing_material, 'weather_resistance', WEATHER_RESISTANCE_OPTIONS[0]) if existing_material else WEATHER_RESISTANCE_OPTIONS[0]
        weather_resistance_index = WEATHER_RESISTANCE_OPTIONS.index(default_weather_resistance) if default_weather_resistance in WEATHER_RESISTANCE_OPTIONS else 0
        st.session_state[weather_resistance_key] = WEATHER_RESISTANCE_OPTIONS[weather_resistance_index]
    form_data['weather_resistance'] = st.selectbox(
        "4-6 耐候性（屋外耐久）*",
        WEATHER_RESISTANCE_OPTIONS,
        index=weather_resistance_index,
        key=weather_resistance_key
    )
    
    st.markdown("---")
    st.markdown("### 5. 加工・実装条件")
    
    form_data['processing_methods'] = st.multiselect(
        "5-1 加工方法（可能なもの）*",
        PROCESSING_METHODS,
        key=wkey("processing_methods", scope, material_id=material_id_for_wkey)
    )
    if "その他（自由記述）" in form_data['processing_methods']:
        form_data['processing_other'] = st.text_input("その他（詳細）", key=wkey("processing_other", scope, material_id=material_id_for_wkey))
    
    # selectbox の index を計算（session_state があればそれ優先）
    equipment_level_key = wkey("equipment_level", scope, material_id=material_id_for_wkey)
    if equipment_level_key in st.session_state:
        equipment_level_value = st.session_state[equipment_level_key]
        equipment_level_index = EQUIPMENT_LEVELS.index(equipment_level_value) if equipment_level_value in EQUIPMENT_LEVELS else 0
    else:
        equipment_level_index = 0  # デフォルトを "家庭/工房レベル"
        st.session_state[equipment_level_key] = EQUIPMENT_LEVELS[equipment_level_index]
    form_data['equipment_level'] = st.selectbox(
        "5-2 必要設備レベル*",
        EQUIPMENT_LEVELS,
        index=equipment_level_index,
        key=equipment_level_key
    )
    
    prototyping_difficulty_key = wkey("prototyping_difficulty", scope, material_id=material_id_for_wkey)
    if prototyping_difficulty_key in st.session_state:
        prototyping_difficulty_value = st.session_state[prototyping_difficulty_key]
        prototyping_difficulty_index = DIFFICULTY_OPTIONS.index(prototyping_difficulty_value) if prototyping_difficulty_value in DIFFICULTY_OPTIONS else 1
    else:
        prototyping_difficulty_index = 1  # デフォルトを "中"
        st.session_state[prototyping_difficulty_key] = DIFFICULTY_OPTIONS[prototyping_difficulty_index]
    form_data['prototyping_difficulty'] = st.selectbox(
        "5-3 試作難易度*",
        DIFFICULTY_OPTIONS,
        index=prototyping_difficulty_index,
        key=prototyping_difficulty_key
    )
    
    st.markdown("---")
    st.markdown("### 6. 用途・市場状態")
    
    # 使用環境（一時的にコメントアウト - DBにカラムが存在しない）
    # form_data['use_environment'] = st.multiselect(
    #     "6-1 使用環境",
    #     USE_ENVIRONMENT_OPTIONS,
    #     default=form_data.get('use_environment', []),
    #     key="use_environment"
    # )
    
    form_data['use_categories'] = st.multiselect(
        "6-2 主用途カテゴリ*",
        USE_CATEGORIES,
        default=form_data.get('use_categories', []),
        key=wkey("use_categories", scope, material_id=material_id_for_wkey)
    )
    if "その他（自由記述）" in form_data['use_categories']:
        form_data['use_other'] = st.text_input("その他（詳細）", key=wkey("use_other", scope, material_id=material_id_for_wkey))
    
    # 代表的使用例（複数）（st.form内で完結）
    st.markdown("**6-2 代表的使用例**")
    
    # session_state の初期化（初回のみ）
    if 'use_examples' not in st.session_state:
        if existing_material and form_data.get('use_examples'):
            # 編集モード：既存値を初期化（dict から取得、DetachedInstanceError 防止）
            st.session_state.use_examples = form_data.get('use_examples', [])
        else:
            st.session_state.use_examples = [{"name": "", "url": "", "desc": ""}]
    
    use_examples = []
    for i, ex in enumerate(st.session_state.use_examples):
        # session_state に初期値を設定
        ex_name_key = f"ex_name_{i}"
        ex_url_key = f"ex_url_{i}"
        ex_desc_key = f"ex_desc_{i}"
        
        if ex_name_key not in st.session_state:
            st.session_state[ex_name_key] = ex.get('name', '')
        if ex_url_key not in st.session_state:
            st.session_state[ex_url_key] = ex.get('url', '')
        if ex_desc_key not in st.session_state:
            st.session_state[ex_desc_key] = ex.get('desc', '')
        
        with st.expander(f"使用例 {i+1}", expanded=False):
            name = st.text_input("製品名/事例名", key=ex_name_key)
            url = st.text_input("リンク", key=ex_url_key)
            desc = st.text_area("説明", key=ex_desc_key)
            if name:
                use_examples.append({"name": name, "url": url, "desc": desc})
            # 削除チェックボックス（フォーム内で使用可能）
            del_flag = st.checkbox("削除", key=f"del_ex_{i}", help="チェックして保存すると削除されます")
    
    # 追加する使用例の入力
    st.markdown("**➕ 新しい使用例を追加**")
    new_ex_name = st.text_input("製品名/事例名", key="new_ex_name", placeholder="新しい使用例名を入力")
    new_ex_url = st.text_input("リンク", key="new_ex_url", placeholder="リンク（任意）")
    new_ex_desc = st.text_area("説明", key="new_ex_desc", placeholder="説明（任意）")
    
    # 送信時に処理（ここでは form_data に反映するだけ）
    form_data['use_examples'] = use_examples
    form_data['_ex_del_flags'] = {i: st.session_state.get(f"del_ex_{i}", False) for i in range(len(st.session_state.use_examples))}
    form_data['_new_ex_name'] = new_ex_name.strip() if new_ex_name else ""
    form_data['_new_ex_url'] = new_ex_url.strip() if new_ex_url else ""
    form_data['_new_ex_desc'] = new_ex_desc.strip() if new_ex_desc else ""
    
    # selectbox の index を計算（session_state があればそれ優先）
    procurement_key = wkey("procurement_status", scope, material_id=material_id_for_wkey)
    if procurement_key in st.session_state:
        procurement_value = st.session_state[procurement_key]
        procurement_index = PROCUREMENT_OPTIONS.index(procurement_value) if procurement_value in PROCUREMENT_OPTIONS else 0
    else:
        default_procurement = getattr(existing_material, 'procurement_status', PROCUREMENT_OPTIONS[0]) if existing_material else PROCUREMENT_OPTIONS[0]
        procurement_index = PROCUREMENT_OPTIONS.index(default_procurement) if default_procurement in PROCUREMENT_OPTIONS else 0
        st.session_state[procurement_key] = PROCUREMENT_OPTIONS[procurement_index]
    form_data['procurement_status'] = st.selectbox(
        "6-3 調達性（入手しやすさ）*",
        PROCUREMENT_OPTIONS,
        index=procurement_index,
        key=procurement_key
    )
    
    col1, col2, col3 = st.columns(3)
    with col1:
        # selectbox の index を計算（session_state があればそれ優先）
        cost_level_key = wkey("cost_level", scope, material_id=material_id_for_wkey)
        if cost_level_key in st.session_state:
            cost_level_value = st.session_state[cost_level_key]
            cost_level_index = COST_LEVELS.index(cost_level_value) if cost_level_value in COST_LEVELS else 0
        else:
            default_cost_level = getattr(existing_material, 'cost_level', COST_LEVELS[0]) if existing_material else COST_LEVELS[0]
            cost_level_index = COST_LEVELS.index(default_cost_level) if default_cost_level in COST_LEVELS else 0
            st.session_state[cost_level_key] = COST_LEVELS[cost_level_index]
        form_data['cost_level'] = st.selectbox(
            "6-4 コスト帯（目安）*",
            COST_LEVELS,
            index=cost_level_index,
            key=cost_level_key
        )
    with col2:
        form_data['cost_value'] = st.number_input(
            "価格情報（数値）",
            min_value=0.0,
            value=None,
            key=wkey("cost_value", scope, material_id=material_id_for_wkey)
        )
    with col3:
        form_data['cost_unit'] = st.text_input(
            "単位",
            placeholder="例：円/kg, 円/m²",
            key=wkey("cost_unit", scope, material_id=material_id_for_wkey)
        )
    
    st.markdown("---")
    st.markdown("### 7. 制約・安全・法規")
    
    form_data['safety_tags'] = st.multiselect(
        "7-1 安全区分（用途制限）*",
        SAFETY_TAGS,
        key=wkey("safety_tags", scope, material_id=material_id_for_wkey)
    )
    if "その他（自由記述）" in form_data['safety_tags']:
        form_data['safety_other'] = st.text_input("その他（詳細）", key=wkey("safety_other", scope, material_id=material_id_for_wkey))
    
    form_data['restrictions'] = st.text_area(
        "7-2 禁止・注意事項（自由記述）",
        placeholder="使用上の注意点、禁止事項などを記入してください",
        key=wkey("restrictions", scope, material_id=material_id_for_wkey)
    )
    
    st.markdown("---")
    st.markdown("### 8. 公開範囲")
    
    # selectbox の index を計算（session_state があればそれ優先）
    visibility_key = wkey("visibility", scope, material_id=material_id_for_wkey)
    if visibility_key in st.session_state:
        visibility_value = st.session_state[visibility_key]
        visibility_index = VISIBILITY_OPTIONS.index(visibility_value) if visibility_value in VISIBILITY_OPTIONS else 0
    else:
        # createモードでは主要6項目（CORE_FIELDS）のデフォルト値をsession_stateに設定しない
        if existing_material:
            # editモード: touchedが立っていない限り代入しない（ユーザー操作を潰さないため）
            if visibility_key not in st.session_state:
                # 初回seedのみ許可（毎rerunで上書き禁止）
                default_visibility = getattr(existing_material, 'visibility', VISIBILITY_OPTIONS[0])
                visibility_index = VISIBILITY_OPTIONS.index(default_visibility) if default_visibility in VISIBILITY_OPTIONS else 0
                st.session_state[visibility_key] = VISIBILITY_OPTIONS[visibility_index]
            else:
                # session_stateに既に値がある場合は、その値からindexを計算
                visibility_value = st.session_state[visibility_key]
                visibility_index = VISIBILITY_OPTIONS.index(visibility_value) if visibility_value in VISIBILITY_OPTIONS else 0
        else:
            # createモード: index=0（UIのデフォルトに任せる）で、session_stateには設定しない
            visibility_index = 0
    form_data['visibility'] = st.selectbox(
        "8-1 公開設定*",
        VISIBILITY_OPTIONS,
        index=visibility_index,
        key=visibility_key,
    )
    # touched gate: 値の差分でtouchedを立てる（st.form内ではon_changeが使えない）
    default_visibility = VISIBILITY_OPTIONS[0] if scope == "create" else None
    existing_visibility = getattr(existing_material, 'visibility', None) if existing_material else None
    set_touched_if_changed("visibility", visibility_key, form_data['visibility'],
                         default_value=default_visibility, existing_value=existing_visibility, scope=scope)
    
    st.markdown("---")
    st.markdown("### 9. 主要元素リスト（STEP 6: 材料×元素マッピング）")
    
    st.info("💡 **思考の補助**として、この材料に含まれる主要元素の原子番号を入力してください。\n\n例: 水 (H₂O) → `1, 8`、鉄 (Fe) → `26`、プラスチック (C, H, O) → `1, 6, 8`")
    
    main_elements_key = wkey("main_elements", scope, material_id=material_id_for_wkey)
    
    # --- safety: MUST happen before widget instantiation ---
    if main_elements_key in st.session_state:
        st.session_state[main_elements_key] = _coerce_text_input_value(st.session_state[main_elements_key])
    else:
        st.session_state[main_elements_key] = ""
    
    main_elements_input = st.text_input(
        "主要元素の原子番号（カンマ区切り）",
        placeholder="例: 1, 6, 8 または 26",
        help="1-118の範囲で、カンマ区切りで入力してください",
        key=main_elements_key
    )
    
    if main_elements_input:
        try:
            # カンマ区切りの文字列をパース
            elements_list = [int(e.strip()) for e in main_elements_input.split(",") if e.strip().isdigit()]
            # 1-118の範囲に制限
            elements_list = [e for e in elements_list if 1 <= e <= 118]
            if elements_list:
                # widget生成後はsession_stateを触らない（form_dataのみ設定）
                # extract_payloadはwidgetの戻り値（main_elements_input）から取得する
                form_data['main_elements'] = json.dumps(elements_list, ensure_ascii=False)
                st.success(f"✅ {len(elements_list)}個の元素を登録: {elements_list}")
            else:
                # widget生成後はsession_stateを触らない（form_dataのみ設定）
                form_data['main_elements'] = None
                st.warning("⚠️ 有効な原子番号（1-118）が見つかりませんでした。")
        except Exception as e:
            # widget生成後はsession_stateを触らない（form_dataのみ設定）
            form_data['main_elements'] = None
            st.warning(f"⚠️ 入力形式が正しくありません: {e}")
    else:
        # widget生成後はsession_stateを触らない（form_dataのみ設定）
        form_data['main_elements'] = None
    
    return form_data


def show_layer2_form(existing_material=None, scope="create", material_id_for_wkey=None):
    """
    レイヤー②：任意情報フォーム
    
    Args:
        existing_material: 編集モードの場合、既存のMaterialオブジェクト
        scope: スコープ（"create", "edit", "approve"）
        material_id_for_wkey: 材料ID（編集モードの場合）
    """
    form_data = {}
    
    # scopeとmaterial_id_for_wkeyが未指定の場合は推測
    if scope is None:
        scope = "edit" if existing_material else "create"
    if material_id_for_wkey is None and existing_material:
        material_id_for_wkey = existing_material.id
    
    st.markdown("### A. ストーリー・背景")
    
    DEVELOPMENT_MOTIVES = [
        "環境負荷低減", "コスト低減", "性能向上（強度/耐熱等）",
        "触感/意匠性の追求", "安全性向上", "地域資源活用",
        "廃棄物活用", "規制対応", "サプライチェーン事情",
        "研究的好奇心", "その他（自由記述）", "不明"
    ]
    
    form_data['development_motives'] = st.multiselect(
        "A-1 開発動機タイプ",
        DEVELOPMENT_MOTIVES,
        key=wkey("development_motives", scope, material_id=material_id_for_wkey)
    )
    if "その他（自由記述）" in form_data.get('development_motives', []):
        form_data['development_motive_other'] = st.text_input("その他（詳細）", key=wkey("development_motive_other", scope, material_id=material_id_for_wkey))
    
    form_data['development_background_short'] = st.text_input(
        "A-2 開発背景（短文）",
        key=wkey("development_background_short", scope, material_id=material_id_for_wkey)
    )
    
    form_data['development_story'] = st.text_area(
        "A-3 開発ストーリー（長文）",
        placeholder="課題、転機、学びなどを記入してください",
        height=150,
        key=wkey("development_story", scope, material_id=material_id_for_wkey)
    )
    
    st.markdown("---")
    st.markdown("### C. 感覚的特性")
    
    TACTILE_TAGS = [
        "さらさら", "しっとり", "ざらざら", "もちもち", "ねっとり",
        "ふわふわ", "つるつる", "べたつく", "ひんやり", "あたたかい",
        "かたい感触", "やわらかい感触", "その他（自由記述）"
    ]
    
    form_data['tactile_tags'] = st.multiselect(
        "C-1 触感タグ",
        TACTILE_TAGS,
        key=wkey("tactile_tags", scope, material_id=material_id_for_wkey)
    )
    if "その他（自由記述）" in form_data.get('tactile_tags', []):
        form_data['tactile_other'] = st.text_input("その他（詳細）", key=wkey("tactile_other", scope, material_id=material_id_for_wkey))
    
    VISUAL_TAGS = [
        "マット", "グロス", "パール/干渉", "透過散乱", "蛍光",
        "蓄光", "変色（温度/光）", "その他（自由記述）"
    ]
    
    form_data['visual_tags'] = st.multiselect(
        "C-2 視覚タグ（光の反応）",
        VISUAL_TAGS,
        key=wkey("visual_tags", scope, material_id=material_id_for_wkey)
    )
    if "その他（自由記述）" in form_data.get('visual_tags', []):
        form_data['visual_other'] = st.text_input("その他（詳細）", key=wkey("visual_other", scope, material_id=material_id_for_wkey))
    
    form_data['sound_smell'] = st.text_input(
        "C-3 音・匂い",
        placeholder="音や匂いの特徴を記入してください",
        key=wkey("sound_smell", scope, material_id=material_id_for_wkey)
    )
    
    st.markdown("---")
    st.markdown("### D. 物性値（任意）")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        density_value = st.number_input(
            "密度 (g/cm³)",
            min_value=0.0,
            value=None,
            step=0.01,
            format="%.2f",
            key="density",  # CANONICAL_FIELDSに含まれていないためwkey化しない
            help="材料の密度を入力してください（例: 1.38）"
        )
        if density_value is not None and density_value > 0:
            form_data['density'] = float(density_value)
    
    with col2:
        tensile_strength_value = st.number_input(
            "引張強度 (MPa)",
            min_value=0.0,
            value=None,
            step=0.1,
            format="%.1f",
            key="tensile_strength",  # CANONICAL_FIELDSに含まれていないためwkey化しない
            help="引張強度を入力してください（例: 50.0）"
        )
        if tensile_strength_value is not None and tensile_strength_value > 0:
            form_data['tensile_strength'] = float(tensile_strength_value)
    
    with col3:
        yield_strength_value = st.number_input(
            "降伏強度 (MPa)",
            min_value=0.0,
            value=None,
            step=0.1,
            format="%.1f",
            key="yield_strength",  # CANONICAL_FIELDSに含まれていないためwkey化しない
            help="降伏強度を入力してください（例: 45.0）"
        )
        if yield_strength_value is not None and yield_strength_value > 0:
            form_data['yield_strength'] = float(yield_strength_value)
    
    st.markdown("---")
    st.markdown("### F. 環境・倫理・未来")
    
    CIRCULARITY_OPTIONS = [
        "リサイクルしやすい", "条件付きで可能", "難しい",
        "生分解する", "焼却前提", "不明"
    ]
    
    form_data['circularity'] = st.selectbox(
        "F-1 循環性（ざっくり評価）",
        CIRCULARITY_OPTIONS,
        key=wkey("circularity", scope, material_id=material_id_for_wkey)
    )
    
    CERTIFICATIONS = [
        "ISO系", "FSC/PEFC", "GRS 等リサイクル系", "生分解規格",
        "食品接触規格", "その他（自由記述）", "不明"
    ]
    
    form_data['certifications'] = st.multiselect(
        "F-2 認証・規格（あれば）",
        CERTIFICATIONS,
        key=wkey("certifications", scope, material_id=material_id_for_wkey)
    )
    if "その他（自由記述）" in form_data.get('certifications', []):
        form_data['certifications_other'] = st.text_input("その他（詳細）", key=wkey("certifications_other", scope, material_id=material_id_for_wkey))
    
    return form_data


def handle_primary_image(material_id: int, uploaded_files: list) -> None:
    """
    主画像をR2にアップロードし、imagesテーブルへupsertする共通関数
    
    Args:
        material_id: 材料ID（確定済み）
        uploaded_files: UploadedFile のリスト（空の場合はスキップ）
    
    Returns:
        None（例外時はログとUI警告のみ、材料保存は継続）
    """
    if not uploaded_files or len(uploaded_files) == 0:
        logger.info("[R2] skip: no uploaded file")
        st.info("ℹ️ 画像が選択されていないため、R2アップロードをスキップします")
        return
    
    # 最初のファイルを primary として扱う
    primary_file = uploaded_files[0]
    if primary_file is None:
        logger.warning("[R2] WARNING: primary_file is None, skipping upload")
        st.warning("⚠️ 画像ファイルが無効です。R2アップロードをスキップします。")
        return
    
    # R2設定のチェック
    import utils.settings as settings
    
    # get_flag が無い場合に備えた二重化
    flag_fn = getattr(settings, "get_flag", None)
    if not callable(flag_fn):
        # フォールバック: os.getenv のみで判定
        def flag_fn(key, default=False):
            value = os.getenv(key)
            if value is None:
                return default
            value_str = str(value).lower().strip()
            return value_str in ("1", "true", "yes", "y", "on")
    
    enable_r2_upload = flag_fn("ENABLE_R2_UPLOAD", True)
    # INIT_SAMPLE_DATA の時は必ず False 扱い（seed中はR2アップロードしない）
    # 注意: SEED_SKIP_IMAGES は seed処理（init_sample_data.py等）のみで使用し、通常登録では参照しない
    if flag_fn("INIT_SAMPLE_DATA", False):
        enable_r2_upload = False
        logger.info("[R2] skip: INIT_SAMPLE_DATA=True (seed mode)")
        st.info("ℹ️ サンプルデータ生成中はR2アップロードをスキップします")
        return
    
    if not enable_r2_upload:
        logger.info("[R2] skip: ENABLE_R2_UPLOAD is False")
        st.info("ℹ️ R2アップロードが無効化されています")
        return
    
    # R2 アップロード処理
    try:
        # importを安定化（循環/欠落に強い）
        import utils.r2_storage as r2_storage
        from utils.image_repo import upsert_image
        
        # R2設定の確認（Missing keys を理由付きでUIにも出す）
        try:
            # get_r2_client を呼んで設定不足を検知
            _ = r2_storage.get_r2_client()
        except RuntimeError as r2_config_error:
            error_msg = str(r2_config_error)
            logger.warning(f"[R2] Configuration error: {error_msg}")
            st.warning(f"⚠️ R2設定が不足しています: {error_msg}")
            return
        
        # ファイル名を取得
        file_name = getattr(primary_file, 'name', 'unknown')
        logger.info(f"[R2] Upload start: material_id={material_id}, file={file_name}")
        
        # R2 にアップロード
        r2_result = r2_storage.upload_uploadedfile(primary_file, material_id, "primary")
        
        logger.info(f"[R2] Upload success: material_id={material_id}, r2_key={r2_result.get('r2_key')}, public_url={r2_result.get('public_url')}")
        
        # images テーブルへ upsert
        from utils.db import session_scope
        with session_scope() as db:
            upsert_image(
                db=db,
                material_id=material_id,
                kind="primary",
                r2_key=r2_result["r2_key"],
                public_url=r2_result["public_url"],
                bytes=None,  # Phase1: bytes列には書かない（BYTEA型の可能性があるため）
                mime=r2_result["mime"],
                sha256=r2_result["sha256"],
            )
            # commitはsession_scopeが自動で行う
            logger.info(f"[R2] Image saved to DB: material_id={material_id}, public_url={r2_result['public_url']}")
            st.success(f"✅ 画像をR2にアップロードしました: {r2_result.get('public_url', 'N/A')}")
            
    except Exception as r2_error:
        # R2 アップロード失敗はログとUI警告のみ（材料保存は成功させる）
        logger.exception(f"[R2] Upload failed: material_id={material_id}, error={r2_error}")
        st.warning(f"⚠️ R2アップロードに失敗しました: {str(r2_error)[:100]}")


def save_material(form_data, material_id: int = None):
    """
    材料データを保存（upsert対応）
    
    Args:
        form_data: フォームデータの辞書
        material_id: 編集モードの場合、既存材料のID（指定されていればIDで検索、なければname_officialで検索）
    """
    from utils.db import session_scope
    try:
        with session_scope() as db:
            # 編集モードの場合、material_idで既存レコードを検索
            existing_material = None
            if material_id:
                existing_material = db.query(Material).filter(Material.id == material_id).first()
            
            # material_idが指定されていない場合、name_officialで既存レコードを検索（upsert）
            if not existing_material and 'name_official' in form_data:
                existing_material = db.query(Material).filter(
                    Material.name_official == form_data['name_official']
                ).first()
        
        # 必須フィールドの補完（None/空文字列をデフォルト値で埋める）
        form_data = _normalize_required(form_data, existing=existing_material)
        
        # 必須フィールドのバリデーション
        required_fields = [
            'name_official', 'supplier_org', 'supplier_type',
            'category_main', 'material_forms', 'origin_type', 'origin_detail',
            'transparency', 'hardness_qualitative', 'weight_qualitative',
            'water_resistance', 'heat_resistance_range', 'weather_resistance',
            'processing_methods', 'equipment_level', 'prototyping_difficulty',
            'use_categories', 'procurement_status', 'cost_level',
            'safety_tags', 'visibility'
        ]
        
        for field in required_fields:
            if field not in form_data or not form_data[field]:
                raise ValueError(f"必須フィールド '{field}' が入力されていません")
        
        action = 'updated' if existing_material else 'created'
        
        # relationship を form_data から pop（setattr で触らない）
        ref_urls_payload = form_data.pop("reference_urls", None)
        use_examples_payload = form_data.pop("use_examples", None)
        
        if existing_material:
            # UPDATE（既存レコードを更新）
            # --- ensure material is bound to this session ---
            material = db.merge(existing_material)
            material_uuid = material.uuid  # UUIDは保持
            
            # VARCHARカラム用サニタイズ関数（dict/listをJSON文字列に変換）
            def _to_varchar(v):
                """VARCHARカラムに入れる値を正規化（文字列 or None）"""
                if v is None:
                    return None
                if isinstance(v, (dict, list)):
                    return json.dumps(v, ensure_ascii=False)
                if isinstance(v, (bool, int, float)):
                    return str(v)
                return v  # 文字列など
            
            # 編集モードでは、form_dataに存在するキーだけを更新（存在しないキーは既存値を保持）
            # ただし、None/空文字列/空配列は「ユーザーが意図的に空にした」とみなして更新する
            json_array_fields = ['name_aliases', 'material_forms', 'color_tags', 'processing_methods',
                                'use_categories', 'safety_tags', 'question_templates', 'main_elements',
                                'development_motives', 'tactile_tags', 'visual_tags', 'certifications']
            
            # VARCHARカラム（特にdict/listが混入しやすいフィールド）
            varchar_fields = {'question_templates', 'main_elements'}
            
            # システムキーやリレーションを除外
            system_keys = {"id", "created_at", "updated_at", "deleted_at", "uuid", "search_text"}
            relationship_keys = {"images", "uploaded_images", "reference_urls", "use_examples", "properties", "metadata_items", "process_example_images", "existing_images"}
            
            # form_dataに存在するキーだけを更新
            for k, v in form_data.items():
                if k in system_keys or k in relationship_keys:
                    continue
                
                # VARCHARカラムのサニタイズ（dict/listをJSON文字列に変換）
                if k in varchar_fields:
                    v = _to_varchar(v)
                
                # JSON配列フィールドの処理
                if k in json_array_fields:
                    if isinstance(v, list):
                        # リストの場合はJSON文字列に変換
                        setattr(material, k, json.dumps(v, ensure_ascii=False))
                    elif isinstance(v, dict):
                        # dictの場合はJSON文字列に変換（VARCHARカラム対策）
                        setattr(material, k, json.dumps(v, ensure_ascii=False))
                    elif v is not None:
                        # Noneでない場合はそのまま設定（既にJSON文字列の可能性）
                        setattr(material, k, v)
                    # vがNoneの場合は既存値を維持（更新しない）
                else:
                    # 通常フィールドはそのまま設定（None/空文字列も「ユーザーが意図的に空にした」とみなす）
                    if k in Material.__table__.columns:
                        setattr(material, k, v)
        else:
            # INSERT（新規レコード）
            material_uuid = str(uuid.uuid4())
            material = Material(
                uuid=material_uuid,
                id=None  # 新規作成
            )
            db.add(material)
            
            # VARCHARカラム用サニタイズ関数（dict/listをJSON文字列に変換）
            def _to_varchar(v):
                """VARCHARカラムに入れる値を正規化（文字列 or None）"""
                if v is None:
                    return None
                if isinstance(v, (dict, list)):
                    return json.dumps(v, ensure_ascii=False)
                if isinstance(v, (bool, int, float)):
                    return str(v)
                return v  # 文字列など
        
        # Materialデータを設定（新規/更新共通）
        # 注意：既存レコードの更新は上記のループで完了しているため、ここは新規のみ
        if not existing_material:
            material.name_official = form_data['name_official']
            material.name_aliases = json.dumps(form_data.get('name_aliases', []), ensure_ascii=False)
            material.supplier_org = form_data['supplier_org']
            material.supplier_type = form_data['supplier_type']
            material.supplier_other = form_data.get('supplier_other')
            material.category_main = form_data['category_main']
            material.category_other = form_data.get('category_other')
            material.material_forms = json.dumps(form_data['material_forms'], ensure_ascii=False)
            material.material_forms_other = form_data.get('material_forms_other')
            material.origin_type = form_data['origin_type']
            material.origin_other = form_data.get('origin_other')
            material.origin_detail = form_data['origin_detail']
            material.recycle_bio_rate = form_data.get('recycle_bio_rate')
            material.recycle_bio_basis = form_data.get('recycle_bio_basis')
            material.color_tags = json.dumps(form_data.get('color_tags', []), ensure_ascii=False)
            material.transparency = form_data['transparency']
            material.hardness_qualitative = form_data['hardness_qualitative']
            material.hardness_value = form_data.get('hardness_value')
            material.weight_qualitative = form_data['weight_qualitative']
            material.specific_gravity = form_data.get('specific_gravity')
            material.water_resistance = form_data['water_resistance']
            material.heat_resistance_temp = form_data.get('heat_resistance_temp')
            material.heat_resistance_range = form_data['heat_resistance_range']
            material.weather_resistance = form_data['weather_resistance']
            material.processing_methods = json.dumps(form_data['processing_methods'], ensure_ascii=False)
            material.processing_other = form_data.get('processing_other')
            material.equipment_level = form_data['equipment_level']
            material.prototyping_difficulty = form_data['prototyping_difficulty']  # typo修正
            # material.use_environment = json.dumps(form_data.get('use_environment', []), ensure_ascii=False)  # 一時的にコメントアウト（DBにカラムが存在しない）
            material.use_categories = json.dumps(form_data['use_categories'], ensure_ascii=False)
            material.use_other = form_data.get('use_other')
            material.procurement_status = form_data['procurement_status']
            material.cost_level = form_data['cost_level']
            material.cost_value = form_data.get('cost_value')
            material.cost_unit = form_data.get('cost_unit')
            material.safety_tags = json.dumps(form_data['safety_tags'], ensure_ascii=False)
            material.safety_other = form_data.get('safety_other')
            material.restrictions = form_data.get('restrictions')
            material.visibility = form_data['visibility']
            material.is_published = form_data.get('is_published', 1)  # デフォルトは公開
            # レイヤー②
            material.development_motives = json.dumps(form_data.get('development_motives', []), ensure_ascii=False)
            material.development_motive_other = form_data.get('development_motive_other')
            material.development_background_short = form_data.get('development_background_short')
            material.development_story = form_data.get('development_story')
            material.tactile_tags = json.dumps(form_data.get('tactile_tags', []), ensure_ascii=False)
            material.tactile_other = form_data.get('tactile_other')
            material.visual_tags = json.dumps(form_data.get('visual_tags', []), ensure_ascii=False)
            material.visual_other = form_data.get('visual_other')
            material.sound_smell = form_data.get('sound_smell')
            material.circularity = form_data.get('circularity')
            material.certifications = json.dumps(form_data.get('certifications', []), ensure_ascii=False)
            material.certifications_other = form_data.get('certifications_other')
            # STEP 6: 材料×元素マッピング
            # VARCHARカラムのサニタイズ（dict/listをJSON文字列に変換）
            main_elements_val = form_data.get('main_elements')
            material.main_elements = _to_varchar(main_elements_val)
            # question_templatesも同様にサニタイズ（存在する場合）
            question_templates_val = form_data.get('question_templates')
            if question_templates_val is not None:
                material.question_templates = _to_varchar(question_templates_val)
            # 後方互換性
            material.name = form_data['name_official']
            material.category = form_data['category_main']
        
        # search_textを生成して設定（新規/更新共通）
        from utils.search import generate_search_text, update_material_embedding
        material.search_text = generate_search_text(material)
        
        db.flush()
        
        # 埋め込みを更新（content_hashが変わった場合のみ）
        try:
            update_material_embedding(db, material)
        except Exception as e:
            # 埋め込み更新失敗は警告のみ（保存は継続）
            import logging
            logger.warning(f"[SAVE MATERIAL] Failed to update embedding for material_id={material.id}: {e}")
        
        # 参照URL保存（既存のものは削除してから再作成）
        # 編集モードでは、payload が None でない場合のみ更新（変更があった場合のみ）
        if ref_urls_payload is not None:
            db.query(ReferenceURL).filter(ReferenceURL.material_id == material.id).delete()
            for ref in ref_urls_payload:
                if ref.get('url'):
                    ref_url = ReferenceURL(
                        material_id=material.id,
                        url=ref['url'],
                        url_type=ref.get('type'),
                        description=ref.get('desc')
                    )
                    db.add(ref_url)
        
        # 使用例保存（既存のものは削除してから再作成）
        # 編集モードでは、payload が None でない場合のみ更新（変更があった場合のみ）
        if use_examples_payload is not None:
            db.query(UseExample).filter(UseExample.material_id == material.id).delete()
            for ex in use_examples_payload:
                if ex.get('name'):
                    use_ex = UseExample(
                        material_id=material.id,
                        example_name=ex['name'],
                        example_url=ex.get('url'),
                        description=ex.get('desc')
                    )
                    db.add(use_ex)
        
        # commitはsession_scopeが自動で行う
        
        # R2 アップロード処理（material.id 確定後）
        # form_data から画像を取得（submit時にform_data['images']に設定済み）
        uploaded_files = normalize_uploaded_files(form_data.get('images', []))
        
        # 画像枚数をログ出力
        cached_image_count = len(uploaded_files)
        logger.info(f"[SAVE MATERIAL] cached_image_count={cached_image_count}, material_id={material.id if material else None}, is_edit_mode={existing_material is not None}")
        
        # material.id と material.uuid をセッション内で取得（セッション外に持ち出さない）
        material_id = material.id
        material_uuid = material.uuid
        
        # 編集モードの場合、削除フラグが立っている画像を削除
        if existing_material and material_id:
            deleted_image_indices = form_data.get('deleted_image_indices', [])
            if deleted_image_indices:
                from database import Image
                # 既存画像を取得
                existing_images_list = db.query(Image).filter(Image.material_id == material_id).order_by(Image.id).all()
                for idx in deleted_image_indices:
                    if 0 <= idx < len(existing_images_list):
                        image_to_delete = existing_images_list[idx]
                        logger.info(f"[SAVE MATERIAL] Deleting image: material_id={material_id}, image_id={image_to_delete.id}, kind={image_to_delete.kind}")
                        db.delete(image_to_delete)
                db.flush()
        
        # 新規画像をアップロード（編集モードでも新規アップロードがあれば処理）
        if material_id and uploaded_files:
            if cached_image_count > 0:
                st.info(f"📸 保存する画像: {cached_image_count} 枚")
                for idx, img in enumerate(uploaded_files):
                    if hasattr(img, 'name'):
                        logger.info(f"[SAVE MATERIAL] Image {idx+1}: {img.name}")
            handle_primary_image(material_id, uploaded_files)
        else:
            if existing_material:
                logger.info(f"[SAVE MATERIAL] No new images to upload (existing images preserved)")
            else:
                logger.info(f"[SAVE MATERIAL] No images to upload (cached_image_count=0)")
                st.info("ℹ️ 画像が選択されていないため、R2アップロードをスキップします")
        
        # 成功時はdictを返す（セッション内で取得した値を使用）
        return {
            "ok": True,
            "action": action,
            "material_id": material_id,
            "uuid": material_uuid,
        }
    except Exception as e:
        # rollbackはsession_scopeが自動で行う
        import traceback
        # 失敗時はdictを返す（例外を再発生させない）
        return {
            "ok": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


def save_material_submission(form_data, uploaded_files=None, submitted_by=None):
    """
    投稿（MaterialSubmission）を保存して承認キューに積む。
    - ORMインスタンスをセッション外へ持ち出さない
    - 返すのは primitives のみ
    """
    import json, uuid, os
    from utils.db import session_scope
    from database import MaterialSubmission

    # 1) UUIDはセッション外で生成（R2 prefix等に使う）
    submission_uuid = str(uuid.uuid4())

    # 2) R2アップロード（セッション外で実行）
    uploaded_images = []
    try:
        import utils.settings as settings
        flag_fn = getattr(settings, "get_flag", None)
        if not callable(flag_fn):
            def flag_fn(key, default=False):
                v = os.getenv(key)
                if v is None:
                    return default
                return str(v).strip().lower() in ("1", "true", "yes", "y", "on")

        enable_r2_upload = flag_fn("ENABLE_R2_UPLOAD", True)
        if flag_fn("INIT_SAMPLE_DATA", False):
            enable_r2_upload = False

        if enable_r2_upload and uploaded_files:
            import utils.r2_storage as r2_storage
            prefix = f"submissions/{submission_uuid}"
            kind_map = ["primary", "space", "product"]
            for idx, f in enumerate(uploaded_files[:3]):
                if f is None:
                    continue
                kind = kind_map[idx] if idx < len(kind_map) else "primary"
                upload_fn = getattr(r2_storage, "upload_uploadedfile_to_prefix", None)
                if callable(upload_fn):
                    r2_result = upload_fn(f, prefix, kind)
                else:
                    # 既存の fallback 実装があなたのコードにあるならそれを呼ぶ。
                    # なければ R2 を諦めて warning だけ出す方が安全。
                    raise RuntimeError("upload_uploadedfile_to_prefix is not available")

                uploaded_images.append({
                    "kind": kind,
                    "r2_key": r2_result.get("r2_key"),
                    "public_url": r2_result.get("public_url"),
                    "bytes": r2_result.get("bytes"),
                    "mime": r2_result.get("mime"),
                    "sha256": r2_result.get("sha256"),
                })
    except Exception:
        # R2失敗は致命にしない（投稿保存は通す）
        pass

    # 3) payload_json を作る（uploaded_images はここで混ぜる）
    # form_dataは既にCANONICAL_FIELDSのみを含む（extract_payloadでフィルタ済み）
    payload_dict = dict(form_data)
    if uploaded_images:
        payload_dict["uploaded_images"] = uploaded_images
    payload_json = json.dumps(payload_dict, ensure_ascii=False, default=str)
    
    # DEBUG時のみログ出力（payload_jsonのkeys headを表示）
    if os.getenv("DEBUG", "0") == "1":
        import json as json_module
        try:
            payload_sample = json_module.loads(payload_json)
            logger.info(f"[SAVE_SUBMISSION] payload_json keys_head={list(payload_sample.keys())[:10]}, name_official='{payload_sample.get('name_official', '')[:50]}'")
        except Exception:
            pass

    # 4) DB保存（セッション内で完結）
    name_official = (payload_dict.get("name_official") or "").strip()
    submitted_by_value = submitted_by.strip() if (submitted_by and submitted_by.strip()) else None

    # session 内で必要な値を取得し、session 外では submission を参照しない
    submission_id = None
    submission_uuid_out = None
    
    try:
        with session_scope() as db:
            submission = MaterialSubmission(
                uuid=submission_uuid,
                status="pending",
                name_official=name_official if name_official else None,
                payload_json=payload_json,
                submitted_by=submitted_by_value,
            )
            db.add(submission)
            db.flush()  # ← id を確実に取るため
            # session 内で必要な値を取得（session 外では submission を参照しない）
            submission_id = submission.id
            submission_uuid_out = submission.uuid
            # session 内でのみ submission を使用（ここで終了）
    except Exception as e:
        # 例外時も session 外で submission を参照しない
        import traceback
        # ログやエラーメッセージには submission を使わず、値を使う
        error_msg = str(e)
        traceback_str = traceback.format_exc()
        # ログ出力（submission を使わない、既存の logger を使用）
        logger.error(f"[SUBMISSION] Failed to save submission (uuid={submission_uuid}): {error_msg}")
        logger.debug(f"[SUBMISSION] Traceback: {traceback_str}")
        
        return {
            "ok": False,
            "error": error_msg,
            "traceback": traceback_str,
            "uuid": submission_uuid,  # session 外で生成した値を使用
            "uploaded_images": uploaded_images,
        }

    # session 外での返り値（submission は使わず、取得した値のみ）
    return {
        "ok": True,
        "submission_id": submission_id,
        "uuid": submission_uuid_out,
        "uploaded_images": uploaded_images,
    }


