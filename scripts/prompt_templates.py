"""
画像生成プロンプトテンプレート集
カテゴリ別に写真風の高品質プロンプトを生成
"""
from typing import List, Optional
import json


def slugify(text: str) -> str:
    """テキストをスラッグ形式に変換"""
    import re
    # 日本語・英数字・ハイフン・アンダースコアのみ許可
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.lower().strip('-')


def build_texture_prompt(material_name: str, category: str, description: Optional[str] = None) -> str:
    """
    テクスチャ画像用プロンプトを生成（1024x1024）
    
    Args:
        material_name: 材料名
        category: カテゴリ
        description: 説明
    
    Returns:
        プロンプト文字列
    """
    category_prompts = {
        "木材・紙・セルロース系": f"high-quality close-up texture photograph of {material_name} wood grain, natural lighting, detailed surface texture, macro photography, 1024x1024, professional product photography",
        "金属・合金": f"high-quality close-up texture photograph of {material_name} metal surface, reflective surface, industrial lighting, detailed metallic texture, macro photography, 1024x1024, professional product photography",
        "高分子（樹脂・エラストマー等）": f"high-quality close-up texture photograph of {material_name} plastic material surface, smooth or textured, studio lighting, detailed material texture, macro photography, 1024x1024, professional product photography",
        "セラミックス・ガラス": f"high-quality close-up texture photograph of {material_name} ceramic or glass surface, glossy or matte finish, natural lighting, detailed surface texture, macro photography, 1024x1024, professional product photography",
        "繊維（天然/合成）": f"high-quality close-up texture photograph of {material_name} fabric or fiber texture, woven or knitted pattern, natural lighting, detailed textile texture, macro photography, 1024x1024, professional product photography",
    }
    
    base_prompt = category_prompts.get(category, f"high-quality close-up texture photograph of {material_name} material surface, detailed texture, natural lighting, macro photography, 1024x1024, professional product photography")
    
    if description:
        # 説明からキーワードを抽出して追加
        base_prompt += f", {description[:100]}"
    
    return base_prompt


def build_use_case_prompt(
    material_name: str,
    category: str,
    use_case: str,
    domain: Optional[str] = None
) -> str:
    """
    用途写真用プロンプトを生成（1280x720）
    
    Args:
        material_name: 材料名
        category: カテゴリ
        use_case: 用途例（例: "調理鍋", "収納ケース"）
        domain: 領域（内装/プロダクト/建築/キッチン等）
    
    Returns:
        プロンプト文字列
    """
    # カテゴリ別の用途例マッピング
    category_use_cases = {
        "金属・合金": {
            "調理器具": f"professional product photography of {material_name} cooking pot or pan, kitchen setting, natural lighting, 1280x720, high quality",
            "建材": f"professional architectural photography of {material_name} building panel or facade, modern architecture, natural lighting, 1280x720, high quality",
            "自動車部品": f"professional product photography of {material_name} automotive part, industrial setting, studio lighting, 1280x720, high quality",
        },
        "高分子（樹脂・エラストマー等）": {
            "収納ケース": f"professional product photography of {material_name} storage container or box, home interior, natural lighting, 1280x720, high quality",
            "射出成形品": f"professional product photography of {material_name} injection molded product, industrial design, studio lighting, 1280x720, high quality",
            "包装材": f"professional product photography of {material_name} packaging material, commercial setting, natural lighting, 1280x720, high quality",
        },
        "木材・紙・セルロース系": {
            "家具": f"professional interior photography of {material_name} furniture, modern home interior, natural lighting, 1280x720, high quality",
            "内装材": f"professional architectural photography of {material_name} interior wall or ceiling, modern architecture, natural lighting, 1280x720, high quality",
            "工芸品": f"professional product photography of {material_name} craft or art piece, cultural setting, natural lighting, 1280x720, high quality",
        },
    }
    
    # カテゴリと用途からプロンプトを選択
    if category in category_use_cases:
        for key, prompt_template in category_use_cases[category].items():
            if key in use_case or use_case in key:
                return prompt_template.replace("{material_name}", material_name)
    
    # デフォルトプロンプト
    domain_context = f"in {domain} setting" if domain else "in real-world application"
    return f"professional product photography of {material_name} {use_case}, {domain_context}, natural lighting, 1280x720, high quality, detailed"


def build_process_prompt(
    material_name: str,
    process_method: str,
    category: Optional[str] = None
) -> str:
    """
    加工例画像用プロンプトを生成（1280x720）
    
    Args:
        material_name: 材料名
        process_method: 加工方法（例: "射出成形", "レーザー加工"）
        category: カテゴリ
    
    Returns:
        プロンプト文字列
    """
    process_prompts = {
        "射出成形": f"professional industrial photography of {material_name} injection molding process, plastic pellets and molded product, factory setting, industrial lighting, 1280x720, high quality",
        "圧縮成形": f"professional industrial photography of {material_name} compression molding process, material and molded product, factory setting, industrial lighting, 1280x720, high quality",
        "3Dプリント（FDM）": f"professional product photography of {material_name} 3D printed object using FDM printer, 3D printer in background, modern workspace, natural lighting, 1280x720, high quality",
        "熱成形": f"professional industrial photography of {material_name} thermoforming process, heated sheet and formed product, factory setting, industrial lighting, 1280x720, high quality",
        "レーザー加工": f"professional industrial photography of {material_name} laser cutting or engraving process, laser machine and cut material, factory setting, industrial lighting, 1280x720, high quality",
        "切削": f"professional industrial photography of {material_name} machining process, CNC machine or lathe, factory setting, industrial lighting, 1280x720, high quality",
        "接着": f"professional product photography of {material_name} bonding or adhesive application, materials being joined, workshop setting, natural lighting, 1280x720, high quality",
        "溶接": f"professional industrial photography of {material_name} welding process, welding equipment and welded joint, factory setting, industrial lighting, 1280x720, high quality",
        "鋳造": f"professional industrial photography of {material_name} casting process, molten material and cast product, foundry setting, industrial lighting, 1280x720, high quality",
        "塗装/コーティング": f"professional product photography of {material_name} painting or coating process, spray gun or brush, workshop setting, natural lighting, 1280x720, high quality",
    }
    
    # 直接マッチ
    if process_method in process_prompts:
        return process_prompts[process_method].replace("{material_name}", material_name)
    
    # 部分マッチ
    for key, prompt_template in process_prompts.items():
        if key in process_method or process_method in key:
            return prompt_template.replace("{material_name}", material_name)
    
    # デフォルト
    return f"professional industrial photography of {material_name} {process_method} process, factory or workshop setting, industrial lighting, 1280x720, high quality"


def get_material_slug(material_name: str, material_id: int) -> str:
    """材料のスラッグを生成"""
    slug = slugify(material_name)
    if not slug:
        slug = f"material_{material_id}"
    return slug


def get_use_case_slug(use_case: str) -> str:
    """用途例のスラッグを生成"""
    return slugify(use_case) or "use_case"


def get_process_slug(process_method: str) -> str:
    """加工方法のスラッグを生成"""
    return slugify(process_method) or "process"

