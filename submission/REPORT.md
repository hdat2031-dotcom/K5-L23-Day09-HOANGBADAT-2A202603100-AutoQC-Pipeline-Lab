# Báo cáo Day 09 — Hoàng Bá Đạt, 2A202603100

## 1. Kết luận trước
Pipeline đưa ra kết luận **Hold** (mã thoát: 10). Lô dữ liệu đầu vào gồm **224 ảnh** từ `data/raw`, qua khâu Intake loại bỏ **21 ảnh** (2 ảnh hỏng không đọc được, 3 ảnh kích thước dưới chuẩn, 8 ảnh trùng lặp byte-by-byte, 5 ảnh rò rỉ từ tập test/gold_val, 3 ảnh trùng gần đúng pHash). Bộ dữ liệu sạch xuất ra tại `submission/export/clean_v1` gồm **203 ảnh** (kèm `manifest.json` ghi nhận quyết định `Hold`).

Lý do chính: Khâu tự động hóa đã xử lý dứt điểm 100% các lỗi bắt buộc (0 lỗi ERROR còn lại). Sau khi người duyệt hoàn thành tối đa ngân sách 80 ảnh ưu tiên cao nhất, vẫn còn **44/203 ảnh (21.67%)** chứa cảnh báo ngữ nghĩa chưa được xác minh. Tỉ lệ này vượt quá ngưỡng cho phép `warn_ratio_hold = 10.00%` của guideline dự án, do đó dữ liệu chỉ được lưu hành dưới dạng **bản nháp nội bộ (Hold)**, chưa đủ điều kiện phát hành chính thức (Release).

## 2. Lỗi và phân việc
Tổng hợp từ `02_error_list_v1` (tổng số 224 vấn đề ghi nhận trên 203 ảnh hợp lệ):

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| `CORRUPT_IMAGE` | 2 ảnh | Máy (Intake) | File ảnh bị hỏng cấu trúc nhị phân, Pillow không mở được; máy loại bỏ an toàn. |
| `BAD_SIZE` | 3 ảnh | Máy (Intake) | Kích thước cạnh ngắn < 250px không đạt độ phân giải tối thiểu; máy loại bỏ. |
| `DUP_IMAGE_EXACT` | 8 ảnh | Máy (Intake) | Trùng hoàn toàn mã băm MD5 với ảnh đã nhận trước đó; máy loại bỏ bản sao. |
| `LEAK_TEST` | 5 ảnh | Máy (Intake) | Trùng lặp (MD5 hoặc pHash <= 8) với tập test/gold_val; nguy cơ gây sai lệch metric kiểm thử; máy loại ngay. |
| `DUP_IMAGE_NEAR` | 3 ảnh | Máy (Intake) | Trùng gần đúng (khoảng cách Hamming pHash <= 8); máy loại biến thể trùng. |
| `BAD_CLASS_NAME` | 2 dòng (data.yaml) | Máy (Autofix) | Tên lớp sai quy ước viết hoa/thường; máy ghi đè chuẩn hoá theo `cfg["classes"]`. |
| `BAD_FORMAT` | 3 dòng | Máy (Autofix) | Dòng không đủ 5 cột số hoặc chứa ký tự NaN/chữ; máy xoá dòng (`drop_line`). |
| `BAD_CLASS_ID` | 6 dòng | Máy (Autofix) | ID lớp ngoài phạm vi 0..3 (vd: 93, 4); máy xoá dòng (`drop_line`). |
| `BOX_ZERO` | 4 dòng | Máy (Autofix) | Box có width hoặc height <= 0; máy xoá dòng (`drop_line`). |
| `DUP_BOX` | 7 dòng | Máy (Autofix) | Hai box cùng lớp trùng nhau (IoU > 0.9); máy giữ box trước, xoá box sau (`drop_line`). |
| `BOX_OUT_OF_IMAGE` | 8 dòng | Máy (Autofix) | Box tràn khỏi khung hình; máy cắt viền (`clip_box`) về [0, 1] hoặc xoá nếu co về 0. |
| `MISSING_LABEL_FILE` | 6 ảnh | Người (Hàng đợi) | Ảnh không có file `.txt`; máy không thể tự bịa nhãn (`needs_label`), phải chuyển người gán. |
| `POSSIBLE_WRONG_CLASS` | 18 box | Người (Hàng đợi) | Model checker phát hiện lệch lớp tại cùng vật thể (IoU >= 0.5); cần mắt người phân xử. |
| `POSSIBLE_MISSING` | 68 box | Người (Hàng đợi) | Model checker phát hiện vật thể rõ mà nhãn thiếu; người xem để gán bổ sung. |
| `POSSIBLE_LOOSE_BOX` | 31 box | Người (Hàng đợi) | Box cùng lớp nhưng bao quá lỏng/lệch (IoU < 0.5); người căn chỉnh lại biên viền. |
| `POSSIBLE_FALSE_POS` | 25 box | Người (Hàng đợi) | Box nhãn nằm ở vị trí model không thấy gì; người kiểm tra có phải nhãn rác hay không. |
| `EMPTY_LABEL` | 12 ảnh | Người (Hàng đợi) | File nhãn rỗng; người xác minh là ảnh nền sạch (background) hay sót vật thể. |
| `BOX_TINY` | 6 box | Người (Hàng đợi) | Box cạnh ngắn < 12px; người kiểm tra có đủ điều kiện gán nhãn theo guideline. |
| `BOX_HUGE` | 3 box | Người (Hàng đợi) | Box chiếm > 95% diện tích ảnh; người kiểm tra có phải gán nhầm background không. |
| `CLASS_RARE` | 4 lớp | Người / Quản lý | Thống kê số lượng box theo lớp thấp; cần định hướng thu thập thêm dữ liệu. |

**Cơ chế hàng đợi duyệt và ngân sách 80 ảnh:**
- File `05_review_queue.csv` xếp độ ưu tiên dựa trên tổng trọng số tích lũy của từng ảnh (`sum(weights[code])`). Các ảnh có lỗi nghiêm trọng nhất được đẩy lên đầu: đứng đầu là `img_0020` (priority 14.528) và `img_0185` (priority 10.052) do kết hợp nhiều lỗi phức tạp (`FIXED_DROP_LINE`, `POSSIBLE_MISSING`, `POSSIBLE_WRONG_CLASS`), tiếp theo là toàn bộ 6 ảnh thiếu nhãn `NEEDS_LABEL` (priority 10.0: `img_0031`, `img_0053`, `img_0126`, `img_0160`, `img_0179`, `img_0182`) vì đây là lỗi bắt buộc chặn pipeline.
- Với ngân sách 80 ảnh (trên tổng số 130 ảnh trong hàng đợi), người duyệt mô phỏng đã hoàn thành 80 ảnh quan trọng nhất: gán nhãn thành công cho cả 6 ảnh thiếu nhãn và sửa chữa hàng loạt box sai lớp, thiếu nhãn phức tạp, giúp giảm số cảnh báo từ 167 xuống 88. Tuy nhiên, 50 ảnh còn lại nằm ngoài ngân sách chứa 44 ảnh còn cảnh báo, khiến tỷ lệ cảnh báo tồn đọng là 21.67%.

## 3. Calibration (2 ngưỡng)
Bảng kết quả hiệu chuẩn trên bộ chuẩn `data/calib/`:

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **8** | DUP_IMAGE_EXACT: 1.00/1.00 (không đổi)<br>DUP_IMAGE_NEAR: 1.00/0.50 → **1.00/0.67** (F1: 0.67 → **0.80**) | Tại dist=2, bộ kiểm bỏ sót 50% ảnh trùng gần (Recall chỉ 0.50). Nâng lên 8 giúp bắt được 4/6 ảnh trùng biến thể trong khi Precision vẫn đạt 1.00 tuyệt đối, không gây báo động giả. |
| `second_opinion.conf` | 0.25 | **0.50** | WRONG_CLASS: 0.56/0.83 (không đổi)<br>MISSING: 0.50/1.00 → **0.57/1.00** (F1: 0.67 → **0.73**) | Tại conf=0.25, model checker nhạy quá mức tạo ra nhiều báo động giả (FP=8 với MISSING). Tăng lên 0.50 giúp nâng Precision lên 0.57 và F1 lên 0.73 mà vẫn giữ trọn vẹn Recall 1.00 (không bỏ sót lỗi thiếu nhãn nào). |

**Điểm calibration có thể đánh lừa và bằng chứng thực tế:**
- **Nguy cơ Overfitting trên tập chuẩn nhỏ (39 ảnh):**
  Trên tập calib, sweep cho thấy nếu tăng `duplicates.phash_dist` lên **16**, Recall đạt 0.83 và F1 đạt 0.91 mà Precision vẫn báo 1.00.
  Tuy nhiên, khi thử nghiệm trên dữ liệu thật (`data/raw` 224 ảnh):
  - Tại `phash_dist = 8`: Bắt chính xác 5 ảnh `LEAK_TEST` và 3 ảnh `DUP_IMAGE_NEAR` (ảnh `img_0223` trùng với `img_0077` có khoảng cách phash đúng bằng 6).
  - Khi tăng `phash_dist = 16`: `LEAK_TEST` nhảy vọt từ 5 lên **11 ảnh**, và `DUP_IMAGE_NEAR` nhảy lên 7 ảnh. Kiểm tra trực quan bằng `viz_labels.py` cho thấy các ảnh bị cờ thêm như `img_0186` (khoảng cách 10 so với `img_0061`) thực chất là hai cảnh đường phố hoàn toàn khác nhau nhưng có bố cục bầu trời/mặt đường tương đồng khiến mã băm gần nhau.
  - Nếu tin vào F1=0.91 của calib mà chọn `dist = 16`, pipeline sẽ **xoá oan 6 ảnh sạch** khỏi tập dữ liệu. Điều này chứng minh: *Tập calib chỉ có 39 ảnh nhân tạo, tối ưu quá đà cho calib sẽ làm giảm độ đặc hiệu và gây tổn hại dữ liệu thật.*

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Thực nghiệm chứng minh cửa chặn hoạt động chính xác:**
- Chạy thử nghiệm ngắt ngân sách người duyệt:
  `python -m pipeline.run --budget 0 --work work/w_nb --reports work/rep_nb --export-dir work/exp_nb`
- Kết quả:
  - Do không có người can thiệp (budget = 0), 6 ảnh thiếu nhãn `MISSING_LABEL_FILE` không được ai gán, máy không tự bịa nhãn nên 6 lỗi bắt buộc này vẫn còn nguyên ở vòng QC 3.
  - Cửa chặn tại `gate.py` nhận diện `n_errors = 6 > 0`, lập tức trả về kết luận **Rework** và thoát với mã **20**.
  - Pipeline thông báo rõ: `"Bước 5/5 KHÔNG xuất: còn lỗi bắt buộc (Rework) — trả về bước 3"` và hoàn toàn không sinh thư mục `work/exp_nb/clean_v1`. Thao tác kiểm tra đường dẫn trả về `False`. Điều này chứng minh cửa chặn kiểm soát chặt chẽ, không để lọt dữ liệu lỗi ra ngoài.

**(b) Các điểm mù mà pipeline không bắt được:**
1. **Box lỏng nhẹ (IoU nằm trong khoảng 0.50 – 0.60):**
   Ngưỡng `iou_loose` đặt ở mức 0.50, do đó những box bị vẽ rộng tay nhẹ, thừa 10–20% diện tích nhưng IoU vẫn đạt ~0.55 sẽ không bị cờ `POSSIBLE_LOOSE_BOX` (máy hoàn toàn im lặng). Điển hình trên ảnh `img_0001` và `img_0030`, box ô tô bị thừa một phần bóng dưới lòng đường nhưng vẫn lọt qua kiểm tra.
2. **Vật thể bị che khuất hoặc quá nhỏ mà cả người lẫn model lớn đều bỏ sót:**
   Nếu một vật thể nhỏ hơn `min_area_px = 600` hoặc bị vật cản che khuất khiến cả nhãn ban đầu lẫn model yolo26l đều không phát hiện (conf < 0.10), máy không có cơ sở đối chứng và không thể gắn cờ `POSSIBLE_MISSING`.
3. **Ảnh trùng bị cắt cúp (crop) sâu hoặc biến đổi góc chụp:**
   Perceptual hash (pHash 64-bit) chỉ kháng được biến đổi co giãn tỉ lệ và nén ảnh. Nếu ảnh bị crop mất hơn 40% diện tích hoặc xoay góc chụp, khoảng cách Hamming pHash sẽ vượt quá 8, khiến khâu Intake bỏ sót ảnh trùng.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Chưa chạy thực nghiệm train do môi trường kiểm thử cục bộ chạy trên CPU Windows không có GPU chuyên dụng (yêu cầu huấn luyện YOLO bằng PyTorch/CUDA trên Google Colab với GPU T4 theo `docs/COLAB.md`).

**Phân tích giả thuyết học thuật phục vụ thí nghiệm Colab:**
- Tập `raw` chứa 5 ảnh rò rỉ từ tập test (`LEAK_TEST`) và 11 ảnh trùng lặp (`DUP_IMAGE_EXACT`, `DUP_IMAGE_NEAR`), cùng 6 ảnh mất nhãn hoàn toàn. Khi huấn luyện trên `raw`, hiện tượng rò rỉ dữ liệu (data leakage) có thể khiến kết quả mAP kiểm thử trên tập test bị thổi phồng giả tạo, trong khi các ảnh thiếu nhãn sẽ phạt nhầm mô hình khiến Recall giảm.
- Tập `clean` đã loại sạch ảnh rò rỉ, ảnh hỏng, đồng thời bổ sung nhãn chuẩn cho 6 ảnh thiếu nhãn qua người duyệt.
- Tuy nhiên, vì tập test chỉ có 100 ảnh và huấn luyện ở quy mô nhỏ (20 epochs, ~200 ảnh train), sự biến thiên giữa các random seed (seed 0 và seed 1) có thể tạo ra độ lệch mAP50 khoảng 1–2%. Nếu độ chênh lệch giữa clean và raw nằm trong khoảng độ lệch chuẩn này, ta cần trung thực kết luận rằng khác biệt nằm trong phạm vi nhiễu thống kê và cần gia tăng số lượng seed (≥ 5 seed) cũng như mở rộng tập test trước khi đưa ra khẳng định chắc chắn.

## 6. Quyết định và ghi chú AI
**(a) Quyết định cuối cùng:**
- Pipeline đưa ra quyết định **Hold**.
- **Hành động để đạt Release:** Cần mở rộng ngân sách duyệt của con người để xử lý nốt **50 ảnh còn lại** trong hàng đợi (giải quyết dứt điểm 44 ảnh đang tồn đọng cảnh báo ngữ nghĩa). Khi số ảnh có cảnh báo chưa duyệt giảm xuống dưới 10% tổng số ảnh (tức còn dưới 20 ảnh), pipeline sẽ chính thức chuyển sang trạng thái **Release**.

**(b) Ghi chú sử dụng AI:**
- **Prompt chính:** "Viết module kiểm tra cú pháp nhãn `label_format.py` và module sửa tự động `autofix.py` theo chuẩn YOLO, hỗ trợ `clip_box` và `drop_line`, đảm bảo giữ nguyên chỉ số dòng gốc khi có dòng trống và không bị crash khi gặp dữ liệu rác."
- **Cách kiểm tra code AI:** Áp dụng phương pháp TDD kiểm thử nghiêm ngặt bằng bộ 79 unit test có sẵn; chạy kiểm tra đối ứng trên dữ liệu thật `data/raw`; kiểm tra việc bảo toàn mã băm sha1 của các file quy định cố định.
- **Một lần AI sai:** Khi sinh hàm `clip_box` trong `autofix.py`, ban đầu AI giả định mọi box sau khi clip đều hợp lệ. Tuy nhiên, với các box nằm hoàn toàn ngoài ảnh (ví dụ `x1 < 0, x2 < 0`), việc clip đưa cả hai toạ độ về 0 dẫn đến box có `new_w = 0, new_h = 0` (vi phạm cấu trúc nhãn). Sau khi chạy test `test_box_fully_outside_is_dropped_not_negative` bị đỏ, ta đã sửa lại: nếu box sau khi clip có chiều rộng hoặc chiều cao <= 0 thì phải chuyển sang hành động `drop_line`.

*(Thưởng +2, tùy chọn) CVAT:*
- Đã khảo sát định dạng `cvat/labels.json` và hướng dẫn lọc trong `docs/CVAT_FILTER.md`. Bộ lọc `width < 20` trên CVAT tương ứng với cảnh báo `BOX_TINY` của pipeline (`min_box_px: 12`), giúp cô lập các vật thể vi mô có nguy cơ là nhiễu ảnh.
- Cờ `can_review` trên CVAT thể hiện cơ chế bàn giao phân tầng: người dán nhãn đánh dấu những ca mập mờ ngữ nghĩa để chuyên gia kiểm định lại, tương ứng hoàn toàn với nguyên lý cốt lõi của pipeline: *"Máy kiểm quy tắc, người kiểm ý nghĩa"*.
