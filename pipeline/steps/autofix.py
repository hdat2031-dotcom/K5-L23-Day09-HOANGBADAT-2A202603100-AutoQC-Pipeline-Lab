"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import yaml

from ..common import ERROR, parse_yolo_line

REMOVE_IMAGE_CODES = {
    "DUP_IMAGE_EXACT",
    "DUP_IMAGE_NEAR",
    "LEAK_TEST",
    "CORRUPT_IMAGE",
    "BAD_SIZE",
}
DROP_LINE_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}


def fix(ds, issues, cfg) -> list[dict]:
    err_issues = [i for i in issues if i.severity == ERROR or i.severity == "error"]
    if not err_issues:
        return []

    fixes: list[dict] = []
    removed_images: set[str] = set()

    # 1. Xoá ảnh hỏng / trùng / rò rỉ (ưu tiên xử lý trước để không sửa nhãn của ảnh bị xoá)
    for iss in err_issues:
        if iss.code in REMOVE_IMAGE_CODES:
            stem = iss.image
            if stem in removed_images:
                continue
            removed_images.add(stem)

            # Xoá ảnh
            if ds.images_dir.exists():
                for p in list(ds.images_dir.glob(f"{stem}.*")):
                    try:
                        p.unlink()
                    except OSError:
                        pass

            # Xoá nhãn
            lbl_p = ds.label_path(stem)
            if lbl_p.exists():
                try:
                    lbl_p.unlink()
                except OSError:
                    pass

            fixes.append({
                "image": stem,
                "line": "",
                "action": "remove_image",
                "before": stem,
                "after": "(đã xoá)",
            })

    # 2. Sửa BAD_CLASS_NAME trong data.yaml
    if any(i.code == "BAD_CLASS_NAME" for i in err_issues):
        yaml_path = ds.yaml_path
        if yaml_path.exists():
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            before = str(data.get("names", []))
            data["names"] = list(cfg["classes"])
            yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
            fixes.append({
                "image": "data.yaml",
                "line": "",
                "action": "rename_classes",
                "before": before,
                "after": str(cfg["classes"]),
            })

    # 3. Ghi nhận MISSING_LABEL_FILE (không tự ý tạo file nhãn)
    seen_missing: set[str] = set()
    for iss in err_issues:
        if iss.code == "MISSING_LABEL_FILE":
            stem = iss.image
            if stem in removed_images or stem in seen_missing:
                continue
            seen_missing.add(stem)
            fixes.append({
                "image": stem,
                "line": "",
                "action": "needs_label",
                "before": "(không có file)",
                "after": "chuyển người gán",
            })

    # 4. Gom lỗi cấp dòng cho từng file nhãn
    line_issues_by_image: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for iss in err_issues:
        if iss.image in removed_images:
            continue
        if iss.code in DROP_LINE_CODES or iss.code == "BOX_OUT_OF_IMAGE":
            if iss.line is not None:
                line_issues_by_image[iss.image][iss.line].append(iss)

    for stem in sorted(line_issues_by_image):
        lbl_p = ds.label_path(stem)
        if not lbl_p.exists():
            continue

        raw_lines = lbl_p.read_text(encoding="utf-8", errors="replace").splitlines()
        new_lines: list[str] = []
        file_issues = line_issues_by_image[stem]

        for idx, line_str in enumerate(raw_lines):
            line_num = idx + 1
            if line_num not in file_issues:
                new_lines.append(line_str)
                continue

            current_issues = file_issues[line_num]
            has_drop = any(i.code in DROP_LINE_CODES for i in current_issues)

            if has_drop:
                # Xoá dòng
                fixes.append({
                    "image": stem,
                    "line": line_num,
                    "action": "drop_line",
                    "before": line_str,
                    "after": "(đã xoá)",
                })
            else:
                # Chỉ có BOX_OUT_OF_IMAGE -> thử cắt box về [0, 1]
                try:
                    c, cx, cy, w, h = parse_yolo_line(line_str)
                    x1 = cx - w / 2.0
                    x2 = cx + w / 2.0
                    y1 = cy - h / 2.0
                    y2 = cy + h / 2.0

                    cx1 = max(0.0, min(1.0, x1))
                    cx2 = max(0.0, min(1.0, x2))
                    cy1 = max(0.0, min(1.0, y1))
                    cy2 = max(0.0, min(1.0, y2))

                    new_w = cx2 - cx1
                    new_h = cy2 - cy1
                    new_cx = (cx1 + cx2) / 2.0
                    new_cy = (cy1 + cy2) / 2.0

                    if new_w <= 0.0 or new_h <= 0.0:
                        # Sau khi cắt không còn diện tích -> xoá dòng
                        fixes.append({
                            "image": stem,
                            "line": line_num,
                            "action": "drop_line",
                            "before": line_str,
                            "after": "(đã xoá)",
                        })
                    else:
                        clipped_str = f"{int(c)} {new_cx:.6f} {new_cy:.6f} {new_w:.6f} {new_h:.6f}"
                        fixes.append({
                            "image": stem,
                            "line": line_num,
                            "action": "clip_box",
                            "before": line_str,
                            "after": clipped_str,
                        })
                        new_lines.append(clipped_str)
                except ValueError:
                    # Dòng không parse được -> xoá dòng
                    fixes.append({
                        "image": stem,
                        "line": line_num,
                        "action": "drop_line",
                        "before": line_str,
                        "after": "(đã xoá)",
                    })

        new_content = "\n".join(new_lines) + ("\n" if new_lines else "")
        lbl_p.write_text(new_content, encoding="utf-8")

    return fixes
