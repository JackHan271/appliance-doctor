"""识别故障现象工具：用视觉模型描述照片中的故障现象与可能原因。"""
from ..json_utils import parse_json
from ..llm import chat_with_image

SYMPTOM_SYSTEM = "你是家电故障现象识别助手，只输出 JSON，不要输出其他文字。"


def identify_symptom(image_base64: str, media_type: str = "image/jpeg") -> dict:
    """识别照片中的故障现象，给出涉及部件与可能原因。

    返回形如 {"symptom": "排水不畅", "parts": ["排水管"], "possible_causes": ["堵塞"]}
    """
    prompt = (
        "请描述照片中的家电故障现象（如漏水、不制冷、异响、屏幕显示故障码等），"
        "并判断涉及的部件与可能原因。\n"
        '严格输出 JSON：{"symptom": "现象描述", "parts": ["涉及部件"], "possible_causes": ["可能原因"]}'
    )
    raw = chat_with_image(prompt, image_base64, media_type, system=SYMPTOM_SYSTEM)
    return parse_json(raw)
