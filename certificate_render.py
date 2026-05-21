"""Render certificates by painting student data into regions on the admin template image."""
import json
import os
from datetime import datetime

CERTIFICATE_FIELD_KEYS = (
    "studentName",
    "courseName",
    "completionDate",
    "instructorName",
    "founderName",
    "certificateId",
)

DEFAULT_FIELD_CONFIG = {
    "studentName": {
        "label": "Student name",
        "placeholder": "Your Name Here",
        "top": 51,
        "left": 50,
        "width": 44,
        "height": 7,
        "fontSizePercent": 3.2,
        "align": "center",
        "color": "#111111",
    },
    "courseName": {
        "label": "Course name",
        "placeholder": "Course Title",
        "top": 64,
        "left": 50,
        "width": 40,
        "height": 5,
        "fontSizePercent": 1.2,
        "align": "center",
        "color": "#111111",
    },
    "completionDate": {
        "label": "Completion date",
        "placeholder": "01/01/2026",
        "top": 75,
        "left": 68.5,
        "width": 22,
        "height": 4,
        "fontSizePercent": 1.1,
        "align": "center",
        "color": "#111111",
    },
    "instructorName": {
        "label": "Instructor name",
        "placeholder": "Instructor Name",
        "top": 75,
        "left": 31.5,
        "width": 22,
        "height": 4,
        "fontSizePercent": 1.1,
        "align": "center",
        "color": "#111111",
    },
    "founderName": {
        "label": "Founder / director name",
        "placeholder": "Founder Name",
        "top": 75,
        "left": 50,
        "width": 22,
        "height": 4,
        "fontSizePercent": 1.1,
        "align": "center",
        "color": "#111111",
    },
    "certificateId": {
        "label": "Certificate ID",
        "placeholder": "CERT-000000",
        "top": 87,
        "left": 50,
        "width": 30,
        "height": 3,
        "fontSizePercent": 0.65,
        "align": "center",
        "color": "#555555",
    },
}


def parse_field_config(settings):
    """Merge saved admin field config with defaults."""
    merged = {k: dict(v) for k, v in DEFAULT_FIELD_CONFIG.items()}
    raw = settings.get("certificate_field_config")
    if raw:
        try:
            data = json.loads(raw)
            fields = data.get("fields", data)
            for key in CERTIFICATE_FIELD_KEYS:
                if key in fields and isinstance(fields[key], dict):
                    merged[key].update(fields[key])
        except (json.JSONDecodeError, TypeError):
            pass
    legacy = settings.get("certificate_field_positions")
    if legacy and not raw:
        try:
            old = json.loads(legacy)
            for key in CERTIFICATE_FIELD_KEYS:
                if key in old:
                    o = old[key]
                    if "top" in o:
                        merged[key]["top"] = o["top"]
                    if "left" in o:
                        merged[key]["left"] = o["left"]
                    merged[key]["width"] = merged[key].get("width", 30)
                    merged[key]["height"] = merged[key].get("height", 5)
        except (json.JSONDecodeError, TypeError):
            pass
    return merged


def certificate_values(cert_row, settings):
    """Map database values for each certificate field."""
    issued = cert_row.get("issued_at") or cert_row["issued_at"]
    if isinstance(issued, str) and len(issued) >= 10:
        completion_date = issued[:10]
    else:
        completion_date = (
            str(issued)[:10] if issued else datetime.now().strftime("%Y-%m-%d")
        )
    course = cert_row.get("course_title") or cert_row["course_title"]
    return {
        "studentName": cert_row.get("username") or cert_row["username"],
        "courseName": str(course).upper() if course else "",
        "completionDate": completion_date,
        "instructorName": settings.get("instructor_name", "Course Instructor"),
        "founderName": settings.get("director_name", "Academic Director"),
        "certificateId": cert_row.get("certificate_code") or cert_row["certificate_code"],
    }


def _load_font(size):
    from PIL import ImageFont

    size = max(12, int(size))
    candidates = [
        os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "times.ttf"),
        os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "georgia.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/System/Library/Fonts/Times.ttc",
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _region_pixels(img_size, field):
    w, h = img_size
    width_pct = float(field.get("width", 30))
    height_pct = float(field.get("height", 5))
    left_pct = float(field.get("left", 50))
    top_pct = float(field.get("top", 50))

    rw = max(10, int(w * width_pct / 100))
    rh = max(8, int(h * height_pct / 100))
    cx = int(w * left_pct / 100)
    cy = int(h * top_pct / 100)
    x0 = max(0, cx - rw // 2)
    y0 = max(0, cy - rh // 2)
    x1 = min(w, x0 + rw)
    y1 = min(h, y0 + rh)
    return x0, y0, x1, y1


def _sample_background(image, box):
    from PIL import ImageStat

    x0, y0, x1, y1 = box
    patch = image.crop((x0, y0, x1, y1)).convert("RGB")
    stat = ImageStat.Stat(patch)
    return tuple(int(v) for v in stat.median)


def _fit_font(draw, text, font_path_size, max_w, max_h):
    from PIL import ImageFont

    size = font_path_size
    font = _load_font(size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    while (tw > max_w or th > max_h) and size > 10:
        size -= 2
        font = _load_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    return font, tw, th


def render_certificate_image(template_path, output_path, cert_row, settings, field_config=None):
    """
    Paint certificate data onto the admin template and save as JPEG/PNG.
    Erases each field region (covers placeholder text) then draws the real value.
    """
    from PIL import Image, ImageDraw

    if field_config is None:
        field_config = parse_field_config(settings)

    values = certificate_values(cert_row, settings)
    img = Image.open(template_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size

    for key in CERTIFICATE_FIELD_KEYS:
        field = field_config.get(key)
        if not field:
            continue
        text = (values.get(key) or "").strip()
        if not text:
            continue

        box = _region_pixels((w, h), field)
        x0, y0, x1, y1 = box
        bg = _sample_background(img, box)
        draw.rectangle([x0, y0, x1, y1], fill=bg)

        font_pct = float(field.get("fontSizePercent", 2))
        font, tw, th = _fit_font(
            draw,
            text,
            int(h * font_pct / 100),
            x1 - x0 - 6,
            y1 - y0 - 4,
        )

        align = field.get("align", "center")
        if align == "center":
            tx = x0 + ((x1 - x0) - tw) // 2
        elif align == "right":
            tx = x1 - tw - 3
        else:
            tx = x0 + 3
        ty = y0 + ((y1 - y0) - th) // 2

        color = field.get("color", "#111111")
        if isinstance(color, str) and color.startswith("#"):
            color = tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))
        draw.text((tx, ty), text, fill=color, font=font)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    ext = os.path.splitext(output_path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        img.save(output_path, "JPEG", quality=95)
    else:
        img.save(output_path, "PNG")
    return output_path


def config_from_admin_form(form, settings=None):
    """Build field config JSON from admin POST + region editor."""
    base = parse_field_config(settings or {})
    regions_raw = form.get("certificate_field_regions", "").strip()
    if regions_raw:
        try:
            regions = json.loads(regions_raw)
            for key in CERTIFICATE_FIELD_KEYS:
                if key in regions:
                    base[key].update(regions[key])
        except json.JSONDecodeError:
            pass

    for key in CERTIFICATE_FIELD_KEYS:
        ph = form.get(f"placeholder_{key}", "").strip()
        if ph:
            base[key]["placeholder"] = ph
    return {"fields": base}
