"""
承認待ち一覧ページの表示ロジック
"""
import streamlit as st
import os
import logging
from datetime import datetime
from features.approval_actions import approve_submission, reject_submission, reopen_submission, calculate_submission_diff

# ロガーを設定
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('[%(name)s] %(levelname)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def show_approval_queue():
    """承認待ち一覧ページ（管理者のみ）"""
    # パフォーマンス計測（DEBUG=1のみ）
    import time
    
    # 画面デバッグは管理者認証後のみ（ログ用 is_debug とは分離）
    try:
        from utils.settings import is_debug as is_debug_flag, show_debug_ui
    except Exception:
        def is_debug_flag():
            return os.getenv("DEBUG", "0") == "1"
        def show_debug_ui():
            return False
    
    debug_enabled = show_debug_ui()
    t0 = time.perf_counter() if is_debug_flag() else None
    is_debug = debug_enabled
    
    # ヘッダー表示
    try:
        from utils.logo import render_site_header
        st.markdown(render_site_header(debug=debug_enabled), unsafe_allow_html=True)
    except Exception:
        st.markdown('<h1>承認待ち一覧</h1>', unsafe_allow_html=True)
    
    st.markdown('<h2 class="section-title">📋 承認待ち一覧</h2>', unsafe_allow_html=True)
    
    # フィルタ：rejectedも表示するか
    # 初期化はwidget作成前にのみ行う
    if "approval_show_rejected" not in st.session_state:
        st.session_state["approval_show_rejected"] = False
    
    show_rejected = st.checkbox(
        "却下済みも表示",
        key="approval_show_rejected"
    )
    
    # 検索：name_official部分一致
    # 初期化はwidget作成前にのみ行う
    if "approval_search" not in st.session_state:
        st.session_state["approval_search"] = ""
    
    search_query = st.text_input(
        "材料名で検索（部分一致）",
        key="approval_search"
    )
    
    # DBからsubmissionsを取得
    from utils.db import session_scope
    from database import MaterialSubmission
    
    with session_scope() as s:
        submissions = s.query(MaterialSubmission).order_by(MaterialSubmission.id.desc()).limit(200).all()
    
    # DB上でのstatus別件数とpending最新5件を確認
    with session_scope() as s:
        from sqlalchemy import text
        rows = s.execute(text("""
            select status, count(*) 
            from material_submissions 
            group by status 
            order by status
        """)).all()
        pend = s.execute(text("""
            select id, status, created_at 
            from material_submissions 
            where status='pending'
            order by id desc
            limit 5
        """)).all()
    
    st.caption(f"DB status counts: {rows}")
    st.caption(f"DB pending latest: {pend}")
    
    # ステータス別の件数表示
    pending_count = len([sub for sub in submissions if sub.status == "pending"])
    rejected_count = len([sub for sub in submissions if sub.status == "rejected"])
    approved_count = len([sub for sub in submissions if sub.status == "approved"])
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("承認待ち", pending_count)
    with col2:
        st.metric("却下済み", rejected_count)
    with col3:
        st.metric("承認済み", approved_count)
    
    if not submissions:
        st.info("✅ 該当する投稿はありません。")
        return
    
    # 各submissionの表示
    for submission in submissions:
        # ステータスに応じたアイコンと色
        status_icon = {
            "pending": "⏳",
            "approved": "✅",
            "rejected": "❌"
        }.get(getattr(submission, "status", "pending"), "📄")
        
        status_color = {
            "pending": "#FFA500",
            "approved": "#28A745",
            "rejected": "#DC3545"
        }.get(getattr(submission, "status", "pending"), "#666")
        
        # モックデータ用の表示
        submission_key = getattr(submission, "uuid", None) or submission.id
        created_at_obj = getattr(submission, "created_at", None)
        if created_at_obj:
            if hasattr(created_at_obj, "strftime"):
                # datetimeオブジェクトの場合
                created_at_display = created_at_obj.strftime('%Y-%m-%d %H:%M')
            elif isinstance(created_at_obj, (int, float)):
                # タイムスタンプの場合
                try:
                    created_at_display = datetime.fromtimestamp(created_at_obj).strftime('%Y-%m-%d %H:%M')
                except (ValueError, OSError):
                    created_at_display = "unknown"
            else:
                created_at_display = "unknown"
        else:
            created_at_display = "N/A"
        
        submitted_by = getattr(submission, "submitted_by", None) or "匿名"
        submission_status = getattr(submission, "status", "pending")
        
        with st.expander(
            f"{status_icon} {created_at_display} - {submitted_by} - {submission_status}",
            expanded=False
        ):
            # payload_jsonをパースして表示
            import json
            
            # DEBUG_ENV=1のときのみログ出力
            try:
                from utils.settings import get_flag
                debug_enabled = get_flag("DEBUG_ENV", False)
            except Exception:
                debug_enabled = os.getenv("DEBUG_ENV", "0") == "1"
            
            # payload_jsonを取得してパース
            payload_json_raw = getattr(submission, "payload_json", None)
            payload_dict = None
            
            if payload_json_raw:
                try:
                    # payload_jsonがstrの場合はjson.loadsしてdict化
                    if isinstance(payload_json_raw, str):
                        payload_dict = json.loads(payload_json_raw)
                    elif isinstance(payload_json_raw, dict):
                        payload_dict = payload_json_raw
                    else:
                        logger.warning(f"[APPROVAL_VIEW] payload_json is neither str nor dict: {type(payload_json_raw)}")
                except json.JSONDecodeError as e:
                    logger.warning(f"[APPROVAL_VIEW] Failed to parse payload_json: {e}")
                    payload_dict = None
                except Exception as e:
                    logger.warning(f"[APPROVAL_VIEW] Unexpected error parsing payload_json: {e}")
                    payload_dict = None
            
            # DEBUG_ENV=1のときのみログ出力
            if debug_enabled:
                if payload_dict:
                    payload_keys = list(payload_dict.keys())
                    payload_keys_head = payload_keys[:30]
                    
                    # 主要項目の値を取得
                    core_fields = {
                        'name_official': payload_dict.get('name_official'),
                        'category_main': payload_dict.get('category_main'),
                        'origin_type': payload_dict.get('origin_type'),
                        'transparency': payload_dict.get('transparency'),
                        'visibility': payload_dict.get('visibility'),
                        'is_published': payload_dict.get('is_published'),
                    }
                    
                    logger.info(
                        f"[APPROVAL_VIEW] submission_id={submission.id}, "
                        f"status={submission_status}, "
                        f"payload_keys_count={len(payload_keys)}, "
                        f"payload_keys_head={payload_keys_head}, "
                        f"core_fields={core_fields}"
                    )
                else:
                    logger.info(
                        f"[APPROVAL_VIEW] submission_id={submission.id}, "
                        f"status={submission_status}, "
                        f"payload_json=None or parse failed"
                    )
            
            st.markdown("### 投稿内容")
            
            # 主要フィールドを表示
            col1, col2 = st.columns(2)
            with col1:
                # payload_dictから主要項目を取得して表示
                name_official = payload_dict.get('name_official', 'N/A') if payload_dict else 'N/A'
                category_main = payload_dict.get('category_main', 'N/A') if payload_dict else 'N/A'
                origin_type = payload_dict.get('origin_type', 'N/A') if payload_dict else 'N/A'
                
                st.write(f"**材料名（正式）**: {name_official}")
                st.write(f"**カテゴリ**: {category_main}")
                st.write(f"**由来タイプ**: {origin_type}")
                
                # 透明性、公開設定、掲載可否も表示
                transparency = payload_dict.get('transparency', 'N/A') if payload_dict else 'N/A'
                visibility = payload_dict.get('visibility', 'N/A') if payload_dict else 'N/A'
                is_published = payload_dict.get('is_published', 'N/A') if payload_dict else 'N/A'
                
                # is_publishedの表示を整形
                if is_published == 1 or is_published == "1" or is_published is True:
                    is_published_display = "公開"
                elif is_published == 0 or is_published == "0" or is_published is False:
                    is_published_display = "非公開"
                else:
                    is_published_display = str(is_published)
                
                st.write(f"**透明性**: {transparency}")
                st.write(f"**公開設定**: {visibility}")
                st.write(f"**掲載可否**: {is_published_display}")
            
            with col2:
                st.write(f"**投稿者**: {submitted_by}")
                st.write(f"**投稿日時**: {created_at_display}")
                st.markdown(f"**ステータス**: <span style='color: {status_color}'>{submission_status}</span>", unsafe_allow_html=True)
                if hasattr(submission, "approved_material_id") and submission.approved_material_id:
                    st.write(f"**承認済み材料ID**: {submission.approved_material_id}")
            
            # editor_noteを表示・編集
            st.markdown("---")
            st.markdown("### 編集者メモ")
            editor_note_key = f"editor_note_edit_{submission_key}"
            editor_note_value = st.text_area(
                "編集者メモ（いつでも編集可能）",
                value=getattr(submission, "editor_note", "") or "",
                key=editor_note_key,
                placeholder="編集者メモを入力・編集できます"
            )
            if st.button("💾 メモを保存", key=f"save_note_{submission_key}"):
                st.info("TODO: メモ保存機能を実装")
                # TODO: DB保存処理を実装
                # st.success("✅ メモを保存しました")
                # st.rerun()
            
            # 却下理由を表示（rejectedの場合）
            if submission_status == "rejected" and hasattr(submission, "reject_reason") and submission.reject_reason:
                st.markdown("---")
                st.markdown("### 却下理由")
                st.warning(submission.reject_reason)
            
            # 差分表示（既存materialsとの比較）
            st.markdown("---")
            st.markdown("### 差分表示（既存材料との比較）")
            st.info("TODO: 差分表示機能を実装")
            
            # アップロードされた画像のプレビュー
            st.markdown("---")
            st.markdown("### 📷 アップロードされた画像")
            st.info("TODO: 画像プレビュー機能を実装")
            
            # プレビュー（簡易表示）
            st.markdown("---")
            st.markdown("### プレビュー（全データ）")
            with st.expander("JSONデータ", expanded=False):
                st.info("TODO: JSONデータ表示を実装")
            
            # アクション（ステータスに応じて表示）
            st.markdown("---")
            st.markdown("### アクション")
            
            if submission_status == "pending":
                # 承認モード選択（新規作成 or 既存更新）
                approval_mode_key = f"approval_mode_{submission_key}"
                approval_mode = st.radio(
                    "承認モード",
                    ["既存へ反映（同名素材がある場合）", "新規作成"],
                    index=0,  # デフォルトは「既存へ反映」
                    key=approval_mode_key,
                    help="同名の材料が既に存在する場合の動作を選択します"
                )
                update_existing = (approval_mode == "既存へ反映（同名素材がある場合）")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("✅ 承認", key=f"approve_{submission_key}", type="primary"):
                        if is_debug:
                            import inspect
                            with st.expander("DEBUG: approve_submission full source", expanded=False):
                                st.write("module:", getattr(approve_submission, "__module__", None))
                                st.write("file:", getattr(getattr(approve_submission, "__code__", None), "co_filename", None))
                                st.write("firstlineno:", getattr(getattr(approve_submission, "__code__", None), "co_firstlineno", None))
                                try:
                                    st.code(inspect.getsource(approve_submission), language="python")
                                except Exception as e:
                                    st.write("source unavailable:", e)
                            st.caption(f"DEBUG UI submission_key={submission_key} type={type(submission_key)}")
                        result = approve_submission(
                            submission_key,
                            editor_note=editor_note_value,
                            update_existing=update_existing,
                            db=None,
                        )

                        if result is None:
                            st.error("❌ approve_submission() が None を返しました（想定外）")
                            st.stop()

                        if not isinstance(result, dict):
                            st.error(f"❌ approve_submission() returned non-dict: {repr(result)}")
                            st.stop()

                        if result.get("ok"):
                            st.success("✅ 承認しました！（非公開状態で保存されました）")
                            st.info("💡 承認後、材料一覧で公開トグルをONにしてください。")
                            if result.get("image_warning"):
                                st.warning(f"⚠️ {result['image_warning']}")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            error_msg = result.get("error", "不明なエラー")
                            st.error(f"❌ エラー: {error_msg}")
                            if result.get("traceback"):
                                with st.expander("🔍 エラー詳細", expanded=False):
                                    st.code(result["traceback"], language="python")
                
                with col2:
                    reject_reason_key = f"reject_reason_{submission_key}"
                    reject_reason = st.text_input(
                        "却下理由（任意）",
                        key=reject_reason_key,
                        placeholder="却下理由を入力してください"
                    )
                    if st.button("❌ 却下", key=f"reject_{submission_key}"):
                        if is_debug:
                            st.caption(f"reject_submission module={getattr(reject_submission, '__module__', None)} file={getattr(reject_submission, '__code__', None).co_filename if getattr(reject_submission, '__code__', None) else None}")
                        result = reject_submission(submission_key, reject_reason=reject_reason, db=None)

                        if result is None:
                            st.error("❌ reject_submission() が None を返しました（想定外）")
                            st.stop()

                        if not isinstance(result, dict):
                            st.error(f"❌ reject_submission() returned non-dict: {repr(result)}")
                            st.stop()

                        if result.get("ok"):
                            st.success("❌ 却下しました。")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            error_msg = result.get("error", "不明なエラー")
                            st.error(f"❌ エラー: {error_msg}")
                            if result.get("traceback"):
                                with st.expander("🔍 エラー詳細", expanded=False):
                                    st.code(result["traceback"], language="python")
            
            elif submission_status == "rejected":
                if st.button("🔄 再審査（pendingに戻す）", key=f"reopen_{submission_key}", type="primary"):
                    if is_debug:
                        st.caption(f"reopen_submission module={getattr(reopen_submission, '__module__', None)} file={getattr(reopen_submission, '__code__', None).co_filename if getattr(reopen_submission, '__code__', None) else None}")
                    result = reopen_submission(submission_key, db=None)

                    if result is None:
                        st.error("❌ reopen_submission() が None を返しました（想定外）")
                        st.stop()

                    if not isinstance(result, dict):
                        st.error(f"❌ reopen_submission() returned non-dict: {repr(result)}")
                        st.stop()

                    if result.get("ok"):
                        st.success("🔄 再審査に戻しました。")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        error_msg = result.get("error", "不明なエラー")
                        st.error(f"❌ エラー: {error_msg}")
                        if result.get("traceback"):
                            with st.expander("🔍 エラー詳細", expanded=False):
                                st.code(result["traceback"], language="python")
            
            elif submission_status == "approved":
                if hasattr(submission, "approved_material_id") and submission.approved_material_id:
                    st.info(f"✅ 承認済み材料ID: {submission.approved_material_id}")
                    if st.button("📝 材料詳細を見る", key=f"view_material_{submission_key}"):
                        st.info("TODO: 材料詳細ページへの遷移を実装")
                        # TODO: 材料詳細ページへの遷移
                        # st.session_state.selected_material_id = submission.approved_material_id
                        # st.session_state.page = "材料一覧"
                        # st.rerun()
