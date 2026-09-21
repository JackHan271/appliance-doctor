"""测试视觉识别：python test_vision.py 图片路径

例：python test_vision.py C:\\Users\\ASUS\\Desktop\\photo.jpg
"""
import base64
import sys

from app.llm import chat_with_image

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python test_vision.py <图片路径>")
        sys.exit(1)
    path = sys.argv[1]
    with open(path, "rb") as f:
        img = base64.b64encode(f.read()).decode()
    # 根据扩展名猜 media_type
    ext = path.rsplit(".", 1)[-1].lower()
    media = {"png": "image/png", "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/jpeg")
    print(chat_with_image("请描述这张图片的内容，并识别其中的文字（如家电品牌、型号、铭牌信息）。", img, media_type=media))
