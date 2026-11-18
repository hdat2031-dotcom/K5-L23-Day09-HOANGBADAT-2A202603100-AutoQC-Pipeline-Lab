"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.
"""
from __future__ import annotations

from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..model_cache import get_preds


def run(ds, cfg, preds=None) -> list[Issue]:
    if preds is None:
        preds = get_preds(ds, cfg, "checker")
    if preds is None:
        preds = {}

    so_cfg = cfg.get("second_opinion", {})
    conf_thresh = so_cfg.get("conf", 0.5)
    min_area_px = so_cfg.get("min_area_px", 600)
    fp_conf = so_cfg.get("fp_conf", 0.25)
    iou_missing = so_cfg.get("iou_missing", 0.3)
    iou_match = so_cfg.get("iou_match", 0.5)
    iou_loose = so_cfg.get("iou_loose", 0.6)

    issues: list[Issue] = []

    # Thứ tự theo ds.image_files()
    for img_path in ds.image_files():
        stem = img_path.stem

        # Bỏ qua ảnh không có trong preds hoặc không có file nhãn
        if stem not in preds:
            continue
        if not ds.label_path(stem).exists():
            continue

        img_size = ds.image_size(stem)
        if img_size is None:
            continue
        img_w, img_h = img_size

        img_preds = preds.get(stem, [])
        valid_boxes = ds.valid_boxes(stem)

        # 1. P: dự đoán có conf >= conf VÀ diện tích px >= min_area_px
        P = [
            r for r in img_preds
            if r[1] >= conf_thresh and (r[4] * img_w * r[5] * img_h) >= min_area_px
        ]

        # Kiểm tra từng dự đoán trong P theo thứ tự
        for r in P:
            r_cls = int(r[0])
            r_conf = float(r[1])
            r_box = (float(r[2]), float(r[3]), float(r[4]), float(r[5]))

            # Lấy các nhãn có IoU(r, nhãn) >= iou_missing
            cands: list[tuple[int, float]] = []
            for lbl in valid_boxes:
                lbl_cls = int(lbl[0])
                lbl_box = (float(lbl[1]), float(lbl[2]), float(lbl[3]), float(lbl[4]))
                iou = iou_xywh(r_box, lbl_box)
                if iou >= iou_missing:
                    cands.append((lbl_cls, iou))

            if not cands:
                # Không có cands -> POSSIBLE_MISSING
                issues.append(
                    Issue(
                        "second_opinion",
                        WARN,
                        "POSSIBLE_MISSING",
                        stem,
                        f"model phát hiện lớp {r_cls} (conf={r_conf:.2f}) nhưng nhãn không có box tương ứng",
                        line=None,
                        extra={"conf": r_conf},
                    )
                )
            else:
                same_class_cands = [c for c in cands if c[0] == r_cls]
                if same_class_cands:
                    best_same_iou = max(c[1] for c in same_class_cands)
                    if best_same_iou < iou_loose:
                        # Có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX
                        issues.append(
                            Issue(
                                "second_opinion",
                                WARN,
                                "POSSIBLE_LOOSE_BOX",
                                stem,
                                f"box nhãn cùng lớp {r_cls} nhưng bị lỏng (IoU={best_same_iou:.2f} < {iou_loose})",
                                line=None,
                                extra={"conf": r_conf, "iou": round(best_same_iou, 3)},
                            )
                        )
                    # Nếu best_same_iou >= iou_loose: nhãn đúng lớp đã phủ vật này, không cờ gì
                else:
                    # Không có cands cùng lớp
                    diff_class_cands = [c for c in cands if c[0] != r_cls]
                    if diff_class_cands:
                        best_diff_iou = max(c[1] for c in diff_class_cands)
                        if best_diff_iou >= iou_match:
                            # Không có cands cùng lớp, nhưng cands khác lớp tốt nhất IoU >= iou_match -> POSSIBLE_WRONG_CLASS
                            issues.append(
                                Issue(
                                    "second_opinion",
                                    WARN,
                                    "POSSIBLE_WRONG_CLASS",
                                    stem,
                                    f"model phát hiện lớp {r_cls} (conf={r_conf:.2f}) nhưng nhãn gán lớp khác (IoU={best_diff_iou:.2f} >= {iou_match})",
                                    line=None,
                                    extra={"conf": r_conf, "iou": round(best_diff_iou, 3)},
                                )
                            )
                        # Nếu best_diff_iou < iou_match: mơ hồ trong [iou_missing, iou_match), không cờ gì

        # 2. Kiểm tra POSSIBLE_FALSE_POS cho từng dòng nhãn hợp lệ
        # Dự đoán để xét FP: conf >= fp_conf, KHÔNG lọc diện tích
        fp_preds = [r for r in img_preds if r[1] >= fp_conf]

        for line_num, ln in ds.read_label_lines(stem) or []:
            try:
                c, cx, cy, w, h = parse_yolo_line(ln)
            except ValueError:
                continue

            if c < 0 or c >= len(ds.classes):
                continue
            if w <= 0 or h <= 0:
                continue

            lbl_box = (cx, cy, w, h)
            matched = any(
                iou_xywh(lbl_box, (r[2], r[3], r[4], r[5])) >= iou_missing
                for r in fp_preds
            )
            if not matched:
                issues.append(
                    Issue(
                        "second_opinion",
                        WARN,
                        "POSSIBLE_FALSE_POS",
                        stem,
                        f"box nhãn không khớp với dự đoán nào của model (conf >= {fp_conf})",
                        line=line_num,
                    )
                )

    return issues
