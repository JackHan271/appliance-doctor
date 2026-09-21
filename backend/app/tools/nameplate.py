"""读铭牌工具：用视觉模型识别照片中的品牌与型号。"""
from ..json_utils import parse_json
from ..llm import chat_with_image

NAMEPLATE_SYSTEM = "你是家电铭牌识别助手，只输出 JSON，不要输出其他文字。"


def read_nameplate(image_base64: str, media_type: str = "image/jpeg") -> dict:
    """识别照片中铭牌的品牌、型号与品类。

    返回形如 {"brand": "海尔", "model": "BCD-470WDPG", "category": "refrigerator"}
    """
    prompt = (
        "请识别照片中家电铭牌上的品牌(brand)与型号(model)，并判断品类(category)。\n"
        'category 取值：refrigerator（冰箱）/ washing_machine（洗衣机），无法判断时留空字符串。\n'
        '严格输出 JSON：{"brand": "", "model": "", "category": ""}'
    )
    raw = chat_with_image(prompt, image_base64, media_type, system=NAMEPLATE_SYSTEM)
    return parse_json(raw)
