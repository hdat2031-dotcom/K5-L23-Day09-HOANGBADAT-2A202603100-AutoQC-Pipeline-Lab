"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |
"""
from __future__ import annotations

from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line


def run(ds, cfg) -> list[Issue]:
    issues: list[Issue] = []
    fmt_cfg = cfg.get("label_format", {})
    overflow_tol = fmt_cfg.get("overflow_tol", 0.002)
    min_box_px = fmt_cfg.get("min_box_px", 12)
    max_box_frac = fmt_cfg.get("max_box_frac", 0.95)
    dup_box_iou = fmt_cfg.get("dup_box_iou", 0.9)
    num_classes = len(ds.classes)

    for label_path in ds.label_files():
        stem = label_path.stem
        lines = ds.read_label_lines(stem)
        if lines is None:
            continue

        valid_boxes: list[tuple[int, tuple[float, float, float, float]]] = []

        for line_num, ln in lines:
            try:
                c, cx, cy, w, h = parse_yolo_line(ln)
            except ValueError as e:
                issues.append(
                    Issue("label_format", ERROR, "BAD_FORMAT", stem, f"sai định dạng dòng YOLO: {e}", line=line_num)
                )
                continue

            if c < 0 or c >= num_classes:
                issues.append(
                    Issue(
                        "label_format",
                        ERROR,
                        "BAD_CLASS_ID",
                        stem,
                        f"ID lớp {c} không hợp lệ (hợp lệ: 0..{num_classes - 1})",
                        line=line_num,
                    )
                )
                continue

            if w <= 0 or h <= 0:
                issues.append(
                    Issue("label_format", ERROR, "BOX_ZERO", stem, f"box có kích thước <= 0: w={w}, h={h}", line=line_num)
                )
                continue

            # Mép box: [cx - w/2, cx + w/2] x [cy - h/2, cy + h/2]
            x1 = cx - w / 2.0
            x2 = cx + w / 2.0
            y1 = cy - h / 2.0
            y2 = cy + h / 2.0
            overflow = max(0.0, -x1, x2 - 1.0, -y1, y2 - 1.0)
            if overflow > overflow_tol:
                issues.append(
                    Issue(
                        "label_format",
                        ERROR,
                        "BOX_OUT_OF_IMAGE",
                        stem,
                        f"box tràn ra ngoài ảnh: overflow={overflow:.4f} > tol={overflow_tol}",
                        line=line_num,
                        extra={"overflow": round(overflow, 4)},
                    )
                )

            # DUP_BOX: cùng lớp với một dòng trước đó và IoU > dup_box_iou
            box_tuple = (cx, cy, w, h)
            is_dup = False
            for prev_c, prev_box in valid_boxes:
                if prev_c == c and iou_xywh(box_tuple, prev_box) > dup_box_iou:
                    is_dup = True
                    break
            if is_dup:
                issues.append(
                    Issue(
                        "label_format",
                        ERROR,
                        "DUP_BOX",
                        stem,
                        f"trùng box với dòng trước đó cùng lớp (IoU > {dup_box_iou})",
                        line=line_num,
                    )
                )
            valid_boxes.append((c, box_tuple))

            # BOX_TINY (cạnh ngắn của box theo px < min_box_px)
            img_size = ds.image_size(stem)
            if img_size is not None:
                img_w, img_h = img_size
                short_side_px = min(w * img_w, h * img_h)
                if short_side_px < min_box_px:
                    issues.append(
                        Issue(
                            "label_format",
                            WARN,
                            "BOX_TINY",
                            stem,
                            f"cạnh ngắn của box ({short_side_px:.1f}px) < {min_box_px}px",
                            line=line_num,
                        )
                    )

            # BOX_HUGE (w * h > max_box_frac)
            if w * h > max_box_frac:
                issues.append(
                    Issue(
                        "label_format",
                        WARN,
                        "BOX_HUGE",
                        stem,
                        f"box quá lớn: diện tích {w * h:.2f} > {max_box_frac}",
                        line=line_num,
                    )
                )

    return issues
