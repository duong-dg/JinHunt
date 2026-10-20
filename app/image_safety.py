"""Optional local detector. Failure never implies an image is safe."""
import os
from functools import lru_cache
from PIL import Image, ImageFilter

@lru_cache(maxsize=1)
def detector():
    from nudenet import NudeDetector
    return NudeDetector()

def scan_image(path):
    result = {"state":"unavailable", "faces_blurred":0, "sensitive":False,
              "plate_detection":"manual_review", "warnings":["Cần người kiểm duyệt kiểm tra ảnh, khuôn mặt và biển số."]}
    if os.getenv("IMAGE_SCANNER", "off") != "nudenet":
        return result
    try:
        detections = detector().detect(str(path))
        sensitive = {"FEMALE_GENITALIA_EXPOSED","MALE_GENITALIA_EXPOSED","ANUS_EXPOSED","FEMALE_BREAST_EXPOSED","BUTTOCKS_EXPOSED"}
        with Image.open(path) as source:
            image = source.convert("RGB")
        for item in detections:
            if float(item["score"]) < .5:
                continue
            if item["class"] in sensitive:
                result["sensitive"] = True
            if item["class"] not in {"FACE_FEMALE","FACE_MALE"}:
                continue
            x,y,w,h = item["box"]
            box = (max(0,int(x-w*.15)),max(0,int(y-h*.15)),min(image.width,int(x+w*1.15)),min(image.height,int(y+h*1.15)))
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            region = image.crop(box)
            # Pixelate then blur: overwrite the only stored image; no public original.
            region = region.resize((4,4)).resize(region.size).filter(ImageFilter.GaussianBlur(12))
            image.paste(region,box)
            result["faces_blurred"] += 1
        if result["faces_blurred"]:
            image.save(path,"JPEG",quality=88)
        result["state"] = "scanned"
        if result["sensitive"]:
            result["warnings"].append("Phát hiện vùng ảnh có thể nhạy cảm; cần người duyệt.")
    except Exception:
        result["state"] = "error"
        result["warnings"].append("Bộ quét không hoàn tất; ảnh vẫn chờ duyệt.")
    return result
