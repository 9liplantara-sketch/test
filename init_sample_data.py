"""
サンプルデータの初期化スクリプト（詳細仕様対応版）
JIS規格に準拠したベーシックな材料データを作成
べき等性を保証（何回実行しても重複投入されない）
"""
import json
import uuid
from database import SessionLocal, Material, Property, Image, MaterialMetadata, ReferenceURL, UseExample, init_db
from image_generator import ensure_material_image
from datetime import datetime
from utils.material_seed import get_or_create_material, get_or_create_property, get_or_create_use_example


def init_sample_data():
    """
    サンプルデータをデータベースに追加（idempotent）
    重複投入を防ぐため、既存の材料名をチェックして差分のみ投入
    """
    # データベース初期化
    init_db()
    
    db = SessionLocal()
    
    try:
        # 統計情報の初期化
        stats = {"created": 0, "skipped": 0, "updated": 0}
        
        # 既存の材料数を取得（情報表示用）
        existing_count = db.query(Material).count()
        
        materials_data = []
        print("サンプルデータの生成を開始します...")
        print("=" * 60)
        print(f"既存材料数: {existing_count}件")
        print("=" * 60)
        
        # ========== 木材 ==========
        
        # 1. カリン材（get-or-createパターン）
        material1, created = get_or_create_material(
            db,
            name_official="カリン材",
            name="カリン材",
            uuid=str(uuid.uuid4()),
            name_aliases=json.dumps(["花梨", "カリン"], ensure_ascii=False),
            supplier_org="一般流通",
            supplier_type="企業",
            category_main="木材・紙・セルロース系",
            material_forms=json.dumps(["シート/板材", "ロッド/棒材", "ブロック/バルク"], ensure_ascii=False),
            origin_type="植物由来",
            origin_detail="カリン（花梨）の木",
            color_tags=json.dumps(["グレー系", "着色可能（任意色）"], ensure_ascii=False),
            transparency="不透明",
            hardness_qualitative="硬い",
            hardness_value="Janka硬度: 約1200 lbf",
            weight_qualitative="中間",
            specific_gravity=0.75,
            water_resistance="中（条件付き）",
            heat_resistance_range="中温域（60〜120℃）",
            weather_resistance="中",
            processing_methods=json.dumps(["切削", "レーザー加工", "接着", "塗装/コーティング"], ensure_ascii=False),
            equipment_level="家庭/工房レベル",
            prototyping_difficulty="低",
            use_categories=json.dumps(["建築・内装", "家具", "生活用品/雑貨"], ensure_ascii=False),
            procurement_status="一般購入可",
            cost_level="中",
            safety_tags=json.dumps(["皮膚接触OK"], ensure_ascii=False),
            visibility="公開（誰でも閲覧可）",
            category="木材・紙・セルロース系",
            description="カリン（花梨）の木材。美しい木目と高い硬度が特徴。"
        )
        
        if created:
            db.flush()
            print(f"  ✓ 作成: カリン材 (ID: {material1.id})")
            stats["created"] += 1
            
            # 物性データを追加（get-or-create）
            get_or_create_property(db, material1.id, "密度", value=0.75, unit="g/cm³")
            get_or_create_property(db, material1.id, "JIS規格", value=None, unit="JAS（日本農林規格）")
            get_or_create_property(db, material1.id, "引張強度", value=85, unit="MPa")
            get_or_create_property(db, material1.id, "圧縮強度", value=50, unit="MPa")
            
            # 画像生成
            ensure_material_image("カリン材", "木材・紙・セルロース系", material1.id, db)
            materials_data.append(material1)
        else:
            print(f"  ⏭️  スキップ: カリン材 (ID: {material1.id})（既に登録されています）")
            stats["skipped"] += 1
        
        # 2. 栗材（get-or-createパターン）
        material2, created = get_or_create_material(
            db,
            name_official="栗材",
            name="栗材",
            uuid=str(uuid.uuid4()),
            name_aliases=json.dumps(["クリ", "チェスナット"], ensure_ascii=False),
            supplier_org="一般流通",
            supplier_type="企業",
            category_main="木材・紙・セルロース系",
            material_forms=json.dumps(["シート/板材", "ロッド/棒材", "ブロック/バルク"], ensure_ascii=False),
            origin_type="植物由来",
            origin_detail="クリ（栗）の木",
            color_tags=json.dumps(["グレー系", "着色可能（任意色）"], ensure_ascii=False),
            transparency="不透明",
            hardness_qualitative="中間",
            hardness_value="Janka硬度: 約540 lbf",
            weight_qualitative="軽い",
            specific_gravity=0.56,
            water_resistance="低い（水に弱い）",
            heat_resistance_range="中温域（60〜120℃）",
            weather_resistance="低い",
            processing_methods=json.dumps(["切削", "接着", "塗装/コーティング"], ensure_ascii=False),
            equipment_level="家庭/工房レベル",
            prototyping_difficulty="低",
            use_categories=json.dumps(["建築・内装", "家具", "生活用品/雑貨"], ensure_ascii=False),
            procurement_status="一般購入可",
            cost_level="低",
            safety_tags=json.dumps(["皮膚接触OK"], ensure_ascii=False),
            visibility="公開（誰でも閲覧可）",
            category="木材・紙・セルロース系",
            description="クリ（栗）の木材。軽量で加工しやすい。"
        )
        
        if created:
            db.flush()
            print(f"  ✓ 作成: 栗材 (ID: {material2.id})")
            stats["created"] += 1
            
            # 物性データを追加（get-or-create）
            get_or_create_property(db, material2.id, "密度", value=0.56, unit="g/cm³")
            get_or_create_property(db, material2.id, "引張強度", value=65, unit="MPa")
            get_or_create_property(db, material2.id, "圧縮強度", value=35, unit="MPa")
            
            # 画像生成
            ensure_material_image("栗材", "木材・紙・セルロース系", material2.id, db)
            materials_data.append(material2)
        else:
            print(f"  ⏭️  スキップ: 栗材 (ID: {material2.id})（既に登録されています）")
            stats["skipped"] += 1
        
        # 3. 樫材（get-or-createパターン）
        material3, created = get_or_create_material(
            db,
            name_official="樫材",
            name="樫材",
            uuid=str(uuid.uuid4()),
            name_aliases=json.dumps(["カシ", "オーク"], ensure_ascii=False),
            supplier_org="一般流通",
            supplier_type="企業",
            category_main="木材・紙・セルロース系",
            material_forms=json.dumps(["シート/板材", "ロッド/棒材", "ブロック/バルク"], ensure_ascii=False),
            origin_type="植物由来",
            origin_detail="カシ（樫）の木",
            color_tags=json.dumps(["グレー系", "着色可能（任意色）"], ensure_ascii=False),
            transparency="不透明",
            hardness_qualitative="とても硬い",
            hardness_value="Janka硬度: 約1360 lbf",
            weight_qualitative="重い",
            specific_gravity=0.75,
            water_resistance="中（条件付き）",
            heat_resistance_range="中温域（60〜120℃）",
            weather_resistance="中",
            processing_methods=json.dumps(["切削", "レーザー加工", "接着", "塗装/コーティング"], ensure_ascii=False),
            equipment_level="家庭/工房レベル",
            prototyping_difficulty="中",
            use_categories=json.dumps(["建築・内装", "家具", "生活用品/雑貨"], ensure_ascii=False),
            procurement_status="一般購入可",
            cost_level="中",
            safety_tags=json.dumps(["皮膚接触OK"], ensure_ascii=False),
            visibility="公開（誰でも閲覧可）",
            category="木材・紙・セルロース系",
            description="カシ（樫）の木材。非常に硬く、耐久性に優れる。"
        )
        
        if created:
            db.flush()
            print(f"  ✓ 作成: 樫材 (ID: {material3.id})")
            stats["created"] += 1
            
            # 物性データを追加（get-or-create）
            get_or_create_property(db, material3.id, "密度", value=0.75, unit="g/cm³")
            get_or_create_property(db, material3.id, "引張強度", value=95, unit="MPa")
            get_or_create_property(db, material3.id, "圧縮強度", value=55, unit="MPa")
            
            # 画像生成
            ensure_material_image("樫材", "木材・紙・セルロース系", material3.id, db)
            materials_data.append(material3)
        else:
            print(f"  ⏭️  スキップ: 樫材 (ID: {material3.id})（既に登録されています）")
            stats["skipped"] += 1
        
        # ========== 金属 ==========
        print("\n【金属】")
        
        # 4. アルミニウム（純アルミ）（get-or-createパターン）
        material4, created = get_or_create_material(
            db,
            name_official="アルミニウム（純アルミ）",
            name="アルミニウム（純アルミ）",
            uuid=str(uuid.uuid4()),
            name_aliases=json.dumps(["Al", "アルミ", "A1050"], ensure_ascii=False),
            supplier_org="一般流通",
            supplier_type="企業",
            category_main="金属・合金",
            material_forms=json.dumps(["シート/板材", "フィルム", "ロッド/棒材", "粉末"], ensure_ascii=False),
            origin_type="鉱物由来",
            origin_detail="ボーキサイト由来",
            color_tags=json.dumps(["グレー系", "白系"], ensure_ascii=False),
            transparency="不透明",
            hardness_qualitative="柔らかい",
            hardness_value="ビッカース硬度: 約25 HV",
            weight_qualitative="とても軽い",
            specific_gravity=2.70,
            water_resistance="高い（屋外・水回りOK）",
            heat_resistance_temp=660,
            heat_resistance_range="高温域（120℃〜）",
            weather_resistance="高い",
            processing_methods=json.dumps(["切削", "レーザー加工", "熱成形", "鋳造", "接着"], ensure_ascii=False),
            equipment_level="家庭/工房レベル",
            prototyping_difficulty="低",
            use_categories=json.dumps(["建築・内装", "家具", "家電/機器筐体", "パッケージ/包装", "モビリティ"], ensure_ascii=False),
            procurement_status="一般購入可",
            cost_level="低",
            safety_tags=json.dumps(["食品接触OK", "皮膚接触OK"], ensure_ascii=False),
            visibility="公開（誰でも閲覧可）",
            category="金属・合金",
            description="純アルミニウム。軽量で加工性が良く、耐食性に優れる。JIS H 4000準拠。"
        )
        
        if created:
            db.flush()
            print(f"  ✓ 作成: アルミニウム（純アルミ） (ID: {material4.id})")
            stats["created"] += 1
            
            # 物性データを追加（get-or-create）
            get_or_create_property(db, material4.id, "密度", value=2.70, unit="g/cm³")
            get_or_create_property(db, material4.id, "引張強度", value=70, unit="MPa")
            get_or_create_property(db, material4.id, "降伏強度", value=20, unit="MPa")
            get_or_create_property(db, material4.id, "融点", value=660, unit="°C")
            get_or_create_property(db, material4.id, "熱伝導率", value=237, unit="W/(m·K)")
            get_or_create_property(db, material4.id, "JIS規格", value=None, unit="JIS H 4000")
            
            # 画像生成
            ensure_material_image("アルミニウム", "金属・合金", material4.id, db)
            
            # 用途例を追加（画像付き、get-or-create）
            from utils.use_example_image_generator import ensure_use_example_image
            use1_img = ensure_use_example_image("アルミニウム", "アルミ鍋", "キッチン")
            use2_img = ensure_use_example_image("アルミニウム", "アルミサッシ", "建築")
            
            get_or_create_use_example(
                db,
                material4.id,
                "アルミ鍋",
                domain="キッチン",
                description="調理器具として広く使用される。熱伝導性が良く、軽量。",
                image_path=use1_img or "",
                source_name="Generated",
                source_url="",
                license_note="自前生成"
            )
            get_or_create_use_example(
                db,
                material4.id,
                "アルミサッシ/外装材",
                domain="建築",
                description="建築外装材として使用。軽量で耐候性に優れる。",
                image_path=use2_img or "",
                source_name="Generated",
                source_url="",
                license_note="自前生成"
            )
            
            materials_data.append(material4)
        else:
            print(f"  ⏭️  スキップ: アルミニウム（純アルミ） (ID: {material4.id})（既に登録されています）")
            stats["skipped"] += 1
        
        # 5. ステンレス鋼 SUS304（get-or-createパターン）
        material5, created = get_or_create_material(
            db,
            name_official="ステンレス鋼 SUS304",
            name="ステンレス鋼 SUS304",
            uuid=str(uuid.uuid4()),
            name_aliases=json.dumps(["SUS304", "18-8ステンレス", "オーステナイト系ステンレス"], ensure_ascii=False),
            supplier_org="一般流通",
            supplier_type="企業",
            category_main="金属・合金",
            material_forms=json.dumps(["シート/板材", "フィルム", "ロッド/棒材", "粉末"], ensure_ascii=False),
            origin_type="鉱物由来",
            origin_detail="鉄鉱石、クロム、ニッケル",
            color_tags=json.dumps(["白系", "グレー系"], ensure_ascii=False),
            transparency="不透明",
            hardness_qualitative="硬い",
            hardness_value="ビッカース硬度: 約200 HV",
            weight_qualitative="重い",
            specific_gravity=7.93,
            water_resistance="高い（屋外・水回りOK）",
            heat_resistance_temp=800,
            heat_resistance_range="高温域（120℃〜）",
            weather_resistance="高い",
            processing_methods=json.dumps(["切削", "レーザー加工", "熱成形", "溶接", "接着"], ensure_ascii=False),
            equipment_level="ファブ施設レベル（FabLab等）",
            prototyping_difficulty="中",
            use_categories=json.dumps(["建築・内装", "家具", "家電/機器筐体", "食品関連", "医療/ヘルスケア"], ensure_ascii=False),
            procurement_status="一般購入可",
            cost_level="中",
            safety_tags=json.dumps(["食品接触OK", "皮膚接触OK"], ensure_ascii=False),
            visibility="公開（誰でも閲覧可）",
            category="金属・合金",
            description="オーステナイト系ステンレス鋼。優れた耐食性と加工性を持つ。JIS G 4305準拠。"
        )
        
        if created:
            db.flush()
            print(f"  ✓ 作成: ステンレス鋼 SUS304 (ID: {material5.id})")
            stats["created"] += 1
            
            # 物性データを追加（get-or-create）
            get_or_create_property(db, material5.id, "密度", value=7.93, unit="g/cm³")
            get_or_create_property(db, material5.id, "引張強度", value=520, unit="MPa")
            get_or_create_property(db, material5.id, "降伏強度", value=205, unit="MPa")
            get_or_create_property(db, material5.id, "融点", value=1400, unit="°C")
            get_or_create_property(db, material5.id, "熱伝導率", value=16.3, unit="W/(m·K)")
            get_or_create_property(db, material5.id, "JIS規格", value=None, unit="JIS G 4305")
            get_or_create_property(db, material5.id, "主成分", value=None, unit="Fe, Cr 18%, Ni 8%")
            
            # 画像生成
            ensure_material_image("ステンレス鋼", "金属・合金", material5.id, db)
            
            # 用途例を追加（画像付き、get-or-create）
            from utils.use_example_image_generator import ensure_use_example_image
            use1_img = ensure_use_example_image("ステンレス鋼", "調理台/流し台", "キッチン")
            
            get_or_create_use_example(
                db,
                material5.id,
                "調理台/流し台",
                domain="キッチン",
                description="キッチン設備として使用。耐食性と清潔性に優れる。",
                image_path=use1_img or "",
                source_name="Generated",
                source_url="",
                license_note="自前生成"
            )
            
            materials_data.append(material5)
        else:
            print(f"  ⏭️  スキップ: ステンレス鋼 SUS304 (ID: {material5.id})（既に登録されています）")
            stats["skipped"] += 1
        
        # 6. 真鍮（黄銅）（get-or-createパターン）
        material6, created = get_or_create_material(
            db,
            name_official="真鍮（黄銅）",
            name="真鍮（黄銅）",
            uuid=str(uuid.uuid4()),
            name_aliases=json.dumps(["ブラス", "C2600", "黄銅"], ensure_ascii=False),
            supplier_org="一般流通",
            supplier_type="企業",
            category_main="金属・合金",
            material_forms=json.dumps(["シート/板材", "ロッド/棒材", "粉末"], ensure_ascii=False),
            origin_type="鉱物由来",
            origin_detail="銅、亜鉛",
            color_tags=json.dumps(["着色可能（任意色）"], ensure_ascii=False),
            transparency="不透明",
            hardness_qualitative="中間",
            hardness_value="ビッカース硬度: 約100 HV",
            weight_qualitative="重い",
            specific_gravity=8.53,
            water_resistance="中（条件付き）",
            heat_resistance_temp=900,
            heat_resistance_range="高温域（120℃〜）",
            weather_resistance="中",
            processing_methods=json.dumps(["切削", "レーザー加工", "熱成形", "鋳造", "接着"], ensure_ascii=False),
            equipment_level="家庭/工房レベル",
            prototyping_difficulty="低",
            use_categories=json.dumps(["建築・内装", "家具", "生活用品/雑貨", "アート/展示"], ensure_ascii=False),
            procurement_status="一般購入可",
            cost_level="中",
            safety_tags=json.dumps(["皮膚接触OK"], ensure_ascii=False),
            visibility="公開（誰でも閲覧可）",
            category="金属・合金",
            description="銅と亜鉛の合金。美しい黄金色と優れた加工性を持つ。JIS H 3100準拠。"
        )
        
        if created:
            db.flush()
            print(f"  ✓ 作成: 真鍮（黄銅） (ID: {material6.id})")
            stats["created"] += 1
            
            # 物性データを追加（get-or-create）
            get_or_create_property(db, material6.id, "密度", value=8.53, unit="g/cm³")
            get_or_create_property(db, material6.id, "引張強度", value=350, unit="MPa")
            get_or_create_property(db, material6.id, "降伏強度", value=100, unit="MPa")
            get_or_create_property(db, material6.id, "融点", value=900, unit="°C")
            get_or_create_property(db, material6.id, "熱伝導率", value=120, unit="W/(m·K)")
            get_or_create_property(db, material6.id, "JIS規格", value=None, unit="JIS H 3100")
            get_or_create_property(db, material6.id, "主成分", value=None, unit="Cu 70%, Zn 30%")
            
            # 画像生成
            ensure_material_image("真鍮", "金属・合金", material6.id, db)
            
            # 用途例を追加（画像付き、get-or-create）
            from utils.use_example_image_generator import ensure_use_example_image
            use1_img = ensure_use_example_image("真鍮", "ドアノブ/金物", "内装")
            
            get_or_create_use_example(
                db,
                material6.id,
                "ドアノブ/金物",
                domain="内装",
                description="内装金物として使用。美しい黄金色と優れた加工性。",
                image_path=use1_img or "",
                source_name="Generated",
                source_url="",
                license_note="自前生成"
            )
            
            materials_data.append(material6)
        else:
            print(f"  ⏭️  スキップ: 真鍮（黄銅） (ID: {material6.id})（既に登録されています）")
            stats["skipped"] += 1
        
        # ========== プラスチック ==========
        print("\n【プラスチック】")
        
        # 7. ポリプロピレン（PP）（get-or-createパターン）
        material7, created = get_or_create_material(
            db,
            name_official="ポリプロピレン（PP）",
            name="ポリプロピレン（PP）",
            uuid=str(uuid.uuid4()),
            name_aliases=json.dumps(["PP", "ポリプロ", "ポリプロピレン樹脂"], ensure_ascii=False),
            supplier_org="一般流通",
            supplier_type="企業",
            category_main="高分子（樹脂・エラストマー等）",
            material_forms=json.dumps(["シート/板材", "フィルム", "粒（ペレット）", "3Dプリント用フィラメント"], ensure_ascii=False),
            origin_type="化石資源由来（石油等）",
            origin_detail="プロピレン由来",
            color_tags=json.dumps(["無色", "白系", "着色可能（任意色）"], ensure_ascii=False),
            transparency="不透明",
            hardness_qualitative="中間",
            hardness_value="Shore D: 約70",
            weight_qualitative="とても軽い",
            specific_gravity=0.90,
            water_resistance="高い（屋外・水回りOK）",
            heat_resistance_temp=130,
            heat_resistance_range="中温域（60〜120℃）",
            weather_resistance="中",
            processing_methods=json.dumps(["射出成形", "圧縮成形", "3Dプリント（FDM）", "熱成形", "接着"], ensure_ascii=False),
            equipment_level="ファブ施設レベル（FabLab等）",
            prototyping_difficulty="低",
            use_categories=json.dumps(["パッケージ/包装", "生活用品/雑貨", "家電/機器筐体", "自動車部品"], ensure_ascii=False),
            procurement_status="一般購入可",
            cost_level="低",
            safety_tags=json.dumps(["食品接触OK", "皮膚接触OK"], ensure_ascii=False),
            visibility="公開（誰でも閲覧可）",
            category="高分子（樹脂・エラストマー等）",
            description="ポリプロピレン樹脂。軽量で耐薬品性に優れ、食品容器などに広く使用される。JIS K 6922準拠。"
        )
        
        if created:
            db.flush()
            print(f"  ✓ 作成: ポリプロピレン（PP） (ID: {material7.id})")
            stats["created"] += 1
            
            # 物性データを追加（get-or-create）
            get_or_create_property(db, material7.id, "密度", value=0.90, unit="g/cm³")
            get_or_create_property(db, material7.id, "引張強度", value=35, unit="MPa")
            get_or_create_property(db, material7.id, "降伏強度", value=30, unit="MPa")
            get_or_create_property(db, material7.id, "融点", value=165, unit="°C")
            get_or_create_property(db, material7.id, "ガラス転移温度", value=-10, unit="°C")
            get_or_create_property(db, material7.id, "JIS規格", value=None, unit="JIS K 6922")
            
            # 画像生成
            ensure_material_image("ポリプロピレン", "高分子（樹脂・エラストマー等）", material7.id, db)
            
            # 用途例を追加（画像付き、get-or-create）
            from utils.use_example_image_generator import ensure_use_example_image
            use1_img = ensure_use_example_image("ポリプロピレン", "収納ケース", "生活")
            use2_img = ensure_use_example_image("ポリプロピレン", "配管", "建築")
            
            get_or_create_use_example(
                db,
                material7.id,
                "収納ケース",
                domain="生活",
                description="生活用品として使用。軽量で耐薬品性に優れる。",
                image_path=use1_img or "",
                source_name="Generated",
                source_url="",
                license_note="自前生成"
            )
            get_or_create_use_example(
                db,
                material7.id,
                "配管",
                domain="建築",
                description="建築配管材として使用。耐薬品性と軽量性。",
                image_path=use2_img or "",
                source_name="Generated",
                source_url="",
                license_note="自前生成"
            )
            
            materials_data.append(material7)
        else:
            print(f"  ⏭️  スキップ: ポリプロピレン（PP） (ID: {material7.id})（既に登録されています）")
            stats["skipped"] += 1
        
        # 8. ポリエチレン（PE）（get-or-createパターン）
        material8, created = get_or_create_material(
            db,
            name_official="ポリエチレン（PE）",
            name="ポリエチレン（PE）",
            uuid=str(uuid.uuid4()),
            name_aliases=json.dumps(["PE", "ポリエチレン樹脂"], ensure_ascii=False),
            supplier_org="一般流通",
            supplier_type="企業",
            category_main="高分子（樹脂・エラストマー等）",
            material_forms=json.dumps(["シート/板材", "フィルム", "粒（ペレット）", "3Dプリント用フィラメント"], ensure_ascii=False),
            origin_type="化石資源由来（石油等）",
            origin_detail="エチレン由来",
            color_tags=json.dumps(["無色", "白系", "着色可能（任意色）"], ensure_ascii=False),
            transparency="半透明",
            hardness_qualitative="柔らかい",
            hardness_value="Shore D: 約50",
            weight_qualitative="とても軽い",
            specific_gravity=0.92,
            water_resistance="高い（屋外・水回りOK）",
            heat_resistance_temp=120,
            heat_resistance_range="中温域（60〜120℃）",
            weather_resistance="中",
            processing_methods=json.dumps(["射出成形", "圧縮成形", "3Dプリント（FDM）", "熱成形", "接着"], ensure_ascii=False),
            equipment_level="ファブ施設レベル（FabLab等）",
            prototyping_difficulty="低",
            use_categories=json.dumps(["パッケージ/包装", "生活用品/雑貨", "家電/機器筐体"], ensure_ascii=False),
            procurement_status="一般購入可",
            cost_level="低",
            safety_tags=json.dumps(["食品接触OK", "皮膚接触OK"], ensure_ascii=False),
            visibility="公開（誰でも閲覧可）",
            category="高分子（樹脂・エラストマー等）",
            description="ポリエチレン樹脂。最も一般的な熱可塑性樹脂。優れた化学的安定性と電気絶縁性を持つ。JIS K 6760準拠。"
        )
        
        if created:
            db.flush()
            print(f"  ✓ 作成: ポリエチレン（PE） (ID: {material8.id})")
            stats["created"] += 1
            
            # 物性データを追加（get-or-create）
            get_or_create_property(db, material8.id, "密度", value=0.92, unit="g/cm³")
            get_or_create_property(db, material8.id, "引張強度", value=20, unit="MPa")
            get_or_create_property(db, material8.id, "降伏強度", value=15, unit="MPa")
            get_or_create_property(db, material8.id, "融点", value=130, unit="°C")
            get_or_create_property(db, material8.id, "ガラス転移温度", value=-120, unit="°C")
            get_or_create_property(db, material8.id, "JIS規格", value=None, unit="JIS K 6760")
            
            # 画像生成
            ensure_material_image("ポリエチレン", "高分子（樹脂・エラストマー等）", material8.id, db)
            
            # 用途例を追加（画像付き、get-or-create）
            from utils.use_example_image_generator import ensure_use_example_image
            use1_img = ensure_use_example_image("ポリエチレン", "シート/包装材", "生活")
            
            get_or_create_use_example(
                db,
                material8.id,
                "シート/包装材",
                domain="生活",
                description="包装材として広く使用される。柔軟性と化学的安定性。",
                image_path=use1_img or "",
                source_name="Generated",
                source_url="",
                license_note="自前生成"
            )
            
            materials_data.append(material8)
        else:
            print(f"  ⏭️  スキップ: ポリエチレン（PE） (ID: {material8.id})（既に登録されています）")
            stats["skipped"] += 1
        
        # 9. ポリ塩化ビニル（PVC）（get-or-createパターン）
        material9, created = get_or_create_material(
            db,
            name_official="ポリ塩化ビニル（PVC）",
            name="ポリ塩化ビニル（PVC）",
            uuid=str(uuid.uuid4()),
            name_aliases=json.dumps(["PVC", "塩ビ", "ポリ塩化ビニル樹脂"], ensure_ascii=False),
            supplier_org="一般流通",
            supplier_type="企業",
            category_main="高分子（樹脂・エラストマー等）",
            material_forms=json.dumps(["シート/板材", "フィルム", "粒（ペレット）", "3Dプリント用フィラメント"], ensure_ascii=False),
            origin_type="化石資源由来（石油等）",
            origin_detail="塩化ビニル由来",
            color_tags=json.dumps(["無色", "白系", "着色可能（任意色）"], ensure_ascii=False),
            transparency="不透明",
            hardness_qualitative="硬い",
            hardness_value="Shore D: 約80",
            weight_qualitative="軽い",
            specific_gravity=1.38,
            water_resistance="高い（屋外・水回りOK）",
            heat_resistance_temp=80,
            heat_resistance_range="中温域（60〜120℃）",
            weather_resistance="高い",
            processing_methods=json.dumps(["射出成形", "圧縮成形", "3Dプリント（FDM）", "熱成形", "接着"], ensure_ascii=False),
            equipment_level="ファブ施設レベル（FabLab等）",
            prototyping_difficulty="中",
            use_categories=json.dumps(["建築・内装", "パッケージ/包装", "生活用品/雑貨", "医療/ヘルスケア"], ensure_ascii=False),
            procurement_status="一般購入可",
            cost_level="低",
            safety_tags=json.dumps(["皮膚接触OK"], ensure_ascii=False),
            restrictions="高温での使用は避ける。食品接触用途では食品衛生法に準拠したグレードを使用。",
            visibility="公開（誰でも閲覧可）",
            category="高分子（樹脂・エラストマー等）",
            description="ポリ塩化ビニル樹脂。硬質と軟質があり、建築材料やパイプなどに広く使用される。JIS K 6723準拠。"
        )
        
        if created:
            db.flush()
            print(f"  ✓ 作成: ポリ塩化ビニル（PVC） (ID: {material9.id})")
            stats["created"] += 1
            
            # 物性データを追加（get-or-create）
            get_or_create_property(db, material9.id, "密度", value=1.38, unit="g/cm³")
            get_or_create_property(db, material9.id, "引張強度", value=50, unit="MPa")
            get_or_create_property(db, material9.id, "降伏強度", value=45, unit="MPa")
            get_or_create_property(db, material9.id, "ガラス転移温度", value=87, unit="°C")
            get_or_create_property(db, material9.id, "JIS規格", value=None, unit="JIS K 6723")
            
            # 画像生成
            ensure_material_image("ポリ塩化ビニル", "高分子（樹脂・エラストマー等）", material9.id, db)
            
            # 用途例を追加（画像付き、get-or-create）
            from utils.use_example_image_generator import ensure_use_example_image
            use1_img = ensure_use_example_image("ポリ塩化ビニル", "シート/内装材", "建築")
            
            get_or_create_use_example(
                db,
                material9.id,
                "シート/内装材",
                domain="建築",
                description="建築内装材として使用。耐候性と加工性に優れる。",
                image_path=use1_img or "",
                source_name="Generated",
                source_url="",
                license_note="自前生成"
            )
            
            materials_data.append(material9)
        else:
            print(f"  ⏭️  スキップ: ポリ塩化ビニル（PVC） (ID: {material9.id})（既に登録されています）")
            stats["skipped"] += 1
        
        db.commit()
        print("\n" + "=" * 60)
        print("✅ サンプルデータの追加が完了しました！")
        print("=" * 60)
        print(f"\n📊 処理結果:")
        print(f"  ✅ 作成: {stats['created']}件")
        print(f"  ⏭️  スキップ: {stats['skipped']}件")
        print(f"  📝 更新: {stats['updated']}件")
        print(f"\n📊 登録された材料一覧:\n")
        for i, mat in enumerate(materials_data, 1):
            print(f"  {i}. {mat.name_official}")
            print(f"     カテゴリ: {mat.category_main}")
            print(f"     ID: {mat.id}, UUID: {mat.uuid[:8]}...")
            print()
        print(f"合計 {len(materials_data)} 件の材料を処理しました。")
        print("=" * 60)
        
    except Exception as e:
        db.rollback()
        print(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    init_sample_data()
