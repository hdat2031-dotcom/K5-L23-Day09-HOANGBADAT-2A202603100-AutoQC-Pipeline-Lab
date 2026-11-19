# Báo cáo Day 09 — Hoàng Bá Đạt, 2A202603100

## 1. Kết luận trước
Pipeline kết luận: **Hold** (mã thoát: 10). Lô dữ liệu ban đầu gồm **224 ảnh thô** trong `data/raw`. Qua bước Intake lọc đầu vào, máy tự loại bỏ **21 ảnh** (2 ảnh file bị hỏng không mở được, 3 ảnh kích thước quá nhỏ < 250px, 8 ảnh trùng lặp mã MD5, 5 ảnh rò rỉ từ tập test và 3 ảnh trùng góc chụp theo pHash). Tập dữ liệu sạch xuất ra ở `submission/export/clean_v1/` còn **203 ảnh**.

Lý do ra Hold: Máy đã tự động sửa hết toàn bộ các lỗi nghiêm trọng (ERROR còn lại = 0). Tuy nhiên, vì ngân sách duyệt của người chỉ có tối đa 80 ảnh nên sau khi duyệt xong vẫn còn tồn đọng **44/203 ảnh (chiếm 21.67%)** dính cảnh báo ngữ nghĩa. Tỉ lệ này vượt quá mốc an toàn 10% quy định (`warn_ratio_hold = 0.10`), nên lô dữ liệu tạm thời bị giữ lại (Hold) để chờ người duyệt nốt, chưa được phép phát hành chính thức (Release).

## 2. Lỗi và phân việc
Tổng hợp các lỗi phát hiện được từ `02_error_list_v1` (tổng cộng 224 vấn đề trên 203 ảnh):

| Mã lỗi | Số lượng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| `CORRUPT_IMAGE` | 2 ảnh | Máy (Intake) | File ảnh bị lỗi nhị phân, thư viện PIL không đọc được; máy xoá bỏ an toàn. |
| `BAD_SIZE` | 3 ảnh | Máy (Intake) | Ảnh có cạnh ngắn dưới 250px không đủ độ nét để train model; máy loại bỏ. |
| `DUP_IMAGE_EXACT` | 8 ảnh | Máy (Intake) | Trùng mã MD5 100% với ảnh đã có; máy tự xoá bản copy dư thừa. |
| `LEAK_TEST` | 5 ảnh | Máy (Intake) | Ảnh bị trùng với tập test/gold_val; nếu để lại train sẽ làm kết quả đo điểm bị gian lận; máy loại ngay. |
| `DUP_IMAGE_NEAR` | 3 ảnh | Máy (Intake) | Ảnh chụp liên tiếp hoặc nén lại (khoảng cách pHash <= 8); máy loại để tránh thiên vị dữ liệu. |
| `BAD_CLASS_NAME` | 2 dòng (data.yaml) | Máy (Autofix) | Tên lớp viết hoa sai quy chuẩn (ví dụ "Person"); máy sửa lại theo đúng `cfg["classes"]`. |
| `BAD_FORMAT` | 3 dòng | Máy (Autofix) | Dòng thiếu cột hoặc có ký tự lạ không đọc được toạ độ; máy xoá dòng (`drop_line`). |
| `BAD_CLASS_ID` | 6 dòng | Máy (Autofix) | Class ID bị gán số lạ ngoài khoảng 0..3 (vd: 93, 4); máy xoá dòng (`drop_line`). |
| `BOX_ZERO` | 4 dòng | Máy (Autofix) | Box có bề rộng hoặc bề cao <= 0; máy xoá dòng (`drop_line`). |
| `DUP_BOX` | 7 dòng | Máy (Autofix) | Hai box cùng lớp vẽ đè lên nhau (IoU > 0.9); máy giữ box trước, xoá box sau (`drop_line`). |
| `BOX_OUT_OF_IMAGE` | 8 dòng | Máy (Autofix) | Box vẽ lố ra ngoài mép ảnh; máy gọt mép box về trong khung hình [0, 1] (`clip_box`). |
| `MISSING_LABEL_FILE` | 6 ảnh | Người (Hàng đợi) | Ảnh không có file nhãn đi kèm; máy không thể tự bịa toạ độ, bắt buộc đẩy cho người vẽ nhãn. |
| `POSSIBLE_WRONG_CLASS` | 18 box | Người (Hàng đợi) | Model lớn nghi ngờ nhãn bị gán nhầm lớp (IoU >= 0.5); cần mắt người nhìn lại để phân xử. |
| `POSSIBLE_MISSING` | 68 box | Người (Hàng đợi) | Model lớn phát hiện vật thể rõ mà file nhãn không có; người xem để vẽ bù box. |
| `POSSIBLE_LOOSE_BOX` | 31 box | Người (Hàng đợi) | Box cùng lớp nhưng vẽ quá rộng hoặc lệch (IoU < 0.5); người kéo lại cạnh cho khít. |
| `POSSIBLE_FALSE_POS` | 25 box | Người (Hàng đợi) | Box nhãn nằm ở chỗ model lớn không thấy vật thể gì; người kiểm tra xem có phải nhãn rác không. |
| `EMPTY_LABEL` | 12 ảnh | Người (Hàng đợi) | File nhãn trống trơn 0 byte; người xem đây là ảnh nền (không có xe/người) thật hay do sót nhãn. |
| `BOX_TINY` | 6 box | Người (Hàng đợi) | Box quá bé (< 12px); người xem vật thể xa như vậy có đủ tiêu chuẩn dán nhãn không. |
| `BOX_HUGE` | 3 box | Người (Hàng đợi) | Box to chiếm hơn 95% ảnh; người xem có phải thợ dán nhãn vẽ trùm cả khung cảnh không. |
| `CLASS_RARE` | 4 lớp | Người / Quản lý | Cảnh báo lớp có ít mẫu; cần đi chụp thêm dữ liệu bổ sung. |

**Về hàng đợi duyệt (`05_review_queue.csv`):**
- Hàng đợi xếp thứ tự ưu tiên dựa trên điểm số tính gộp của các lỗi trên từng ảnh. Ảnh nào thiếu hẳn file nhãn hoặc có nhiều cảnh báo nghi ngờ sai lớp/sót box sẽ được cộng điểm cao và đẩy lên đầu (ví dụ ảnh `img_0020` có priority 14.5, `img_0185` có priority 10.0 đứng đầu danh sách).
- Với ngân sách cho phép duyệt 80 ảnh, người duyệt đã kịp xử lý xong 6 ảnh mất file nhãn (gán nhãn bổ sung, giải quyết dứt điểm lỗi ERROR) và gỡ được 128 cảnh báo ngữ nghĩa nặng nhất. Nhưng vì ban đầu có tới 124 ảnh dính cảnh báo nên sau khi người xem xong 80 ảnh, vẫn còn sót lại 44 ảnh chưa được ngó tới.

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **8** | Precision: 1.00 → 0.94<br>Recall: 0.40 → 0.90 | Mức 2 ban đầu quá chặt, chỉ bắt được ảnh giống hệt từng pixel, để lọt nhiều ảnh chỉ bị co giãn hoặc nén dung lượng (Recall thấp, chỉ 0.40). Nâng lên 8 thì bắt được 90% ảnh trùng, chấp nhận precision giảm nhẹ xuống 0.94. Nếu nâng tiếp lên 10 hay 12 thì precision tụt hẳn xuống 0.70 vì xoá nhầm cả ảnh chụp góc phố khác nhau. |
| `second_opinion.conf` | 0.25 | **0.50** | Precision: 0.52 → 0.78<br>Recall: 0.88 → 0.74 | Mức 0.25 ban đầu quá nhạy, model lớn sinh ra nhiều cảnh báo rác làm người duyệt bị quá tải (Precision chỉ 0.52). Nâng lên 0.50 giúp cảnh báo chất lượng hơn nhiều (Precision tăng lên 0.78), giảm bớt việc cho người xem, chấp nhận bỏ qua một số box quá mờ ở xa (Recall giảm từ 0.88 xuống 0.74). |

**Chỗ calibration có thể đánh lừa:**
Tập calib chỉ có 39 ảnh và các lỗi đều là do người cấy ghép có chủ đích, khác nhiều so với ảnh thực tế ở `data/raw`. Với lỗi trùng ảnh, nhiều ảnh đường phố chụp liên tiếp ở ngã tư (ví dụ cặp `img_0042` và `img_0043`) có góc nhà và vỉa hè phía sau gần giống nhau nhưng các xe cộ phía trước lại đang di chuyển khác nhau. Nếu chỉ nhìn bảng điểm F1 của 39 ảnh calib rồi ham chọn ngưỡng `phash_dist` lên 10 hay 12 thì sang dữ liệu raw sẽ bị máy xoá nhầm xe đang chạy. Em đã mở trực tiếp các cặp ảnh bị máy xoá ở ngưỡng 8 ra kiểm tra bằng mắt thì thấy các ảnh bị loại đúng là ảnh trùng góc thực sự.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được

**(a) Chứng minh cửa chặn Gate hoạt động đúng:**
Em chạy thử lệnh với ngân sách người duyệt bằng 0:
```powershell
python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb
```
- Khi không có người duyệt (budget = 0), 6 ảnh bị thiếu file nhãn (`MISSING_LABEL_FILE`) không được ai gán nhãn bù, nên lỗi nghiêm trọng (ERROR) vẫn còn nguyên khi đi vào cửa Gate.
- Kết quả: Pipeline lập tức ra quyết định **Rework**, mã thoát của lệnh trả về đúng **20** (`$LASTEXITCODE = 20`), và thư mục xuất dữ liệu `work/exp_nb` hoàn toàn không được tạo ra (chặn không cho xuất dữ liệu hỏng).

**(b) Các điểm mù pipeline không bắt được:**
1. **Box vẽ lỏng nhẹ (IoU lưng chừng 0.50 - 0.60):** 
   Nếu một box xe ô tô vẽ bị rộng, trùm luôn cả vệt bóng dưới lòng đường, nhưng diện tích trùng khớp IoU vẫn đạt khoảng 0.55 (lớn hơn ngưỡng `iou_loose = 0.50`), máy sẽ coi là đúng và im lặng. Em mở ảnh `img_0001` lên xem bằng mắt thấy rõ mép dưới box bị thừa một khoảng nhưng pipeline không gắn cờ.
2. **Vật thể bị che khuất hoặc quá nhỏ mà cả người lẫn model đều bỏ qua:** 
   Những vật thể bé hơn `min_area_px = 600` hoặc người đi bộ bị khuất sau tán cây khiến cả người gán nhãn ban đầu lẫn model yolo26l đều không phát hiện ra (confidence < 0.10). Cả hai bên đều bỏ sót thì máy không có căn cứ nào để gắn cờ `POSSIBLE_MISSING`.
3. **Ảnh trùng bị crop sâu hoặc lệch góc chụp:** 
   Thuật toán mã băm pHash chỉ kháng được việc co giãn tỉ lệ hoặc nén ảnh. Nếu ảnh chụp bị crop mất gần nửa hoặc người chụp bước sang một bên 45 độ, khoảng cách pHash sẽ vượt quá 8 và lọt qua khâu lọc trùng.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Em chưa chạy phần train so sánh do máy tính cá nhân chạy CPU, không có card đồ hoạ rời (bước này yêu cầu GPU T4 trên Google Colab theo tài liệu `docs/COLAB.md`).

**Phân tích giả thuyết học thuật:**
- Nếu train trên tập `raw`, trong đó có sẵn 5 ảnh bị rò rỉ từ tập test (`LEAK_TEST`) và 11 ảnh trùng lặp, mô hình sẽ học thuộc lòng các ảnh này khiến điểm số mAP khi test bị cao ảo. Đồng thời, 6 ảnh mất nhãn hoàn toàn trong `raw` sẽ phạt nhầm mô hình khi nó nhận diện đúng vật thể, kéo chỉ số Recall xuống.
- Nếu train trên tập `clean_v1`, ảnh rác và ảnh rò rỉ đã bị lọc sạch, 6 ảnh thiếu nhãn đã được người vẽ bổ sung đầy đủ, nên dữ liệu chuẩn hơn về mặt lý thuyết.
- Tuy nhiên, vì tập test chỉ có 100 ảnh và train vỏn vẹn 20 epoch, độ lệch ngẫu nhiên giữa các random seed (seed 0 và seed 1) có thể chênh nhau tầm 1–2% mAP50. Nếu mức chênh lệch giữa clean và raw chỉ nằm trong khoảng sai số này thì chưa thể vội kết luận là clean giúp model tốt hơn, mà bắt buộc phải chạy lặp lại ít nhất 5 seed và tăng kích thước tập test lên nhiều ảnh hơn thì mới dám khẳng định chắc chắn.

## 6. Quyết định và ghi chú AI

**(a) Quyết định cuối cùng:**
- Quyết định hiện tại của lô này là **Hold**.
- **Cách để chuyển thành Release:** Cần cấp thêm thời gian để người duyệt nốt **44 ảnh còn lại** đang dính cảnh báo. Khi số ảnh có cảnh báo chưa duyệt giảm xuống dưới 10% (tức còn dưới 20 ảnh) thì chạy lại pipeline sẽ tự động chuyển sang **Release**.

**(b) Ghi chú sử dụng AI:**
- **Prompt chính em dùng:** *"Viết hàm parse từng dòng nhãn YOLO và hàm clip_box cắt toạ độ về [0, 1] trong autofix.py, chú ý xử lý trường hợp toạ độ bị âm ra ngoài ảnh và giữ nguyên số dòng gốc khi file có dòng trống."*
- **Cách em kiểm tra code AI:** Em không dùng ngay mà chạy lệnh pytest (`pytest tests/test_*.py -q`) sau mỗi lần viết. Chỗ nào test báo đỏ là em mở file test ra xem nó test ca nào rồi tự vào sửa lại logic code; đồng thời em chạy `check_submission.py` để chắc chắn không bị AI sửa lén các file có sẵn của đề bài.
- **Một lần AI làm sai:** Khi viết hàm `clip_box` trong `autofix.py`, AI dùng lệnh kẹp giá trị về [0, 1]. Khi gặp box vẽ nằm hoàn toàn bên ngoài ảnh ở toạ độ âm ($x_2 < 0$), kẹp xong thì cả 2 mép đều bằng 0, dẫn tới box có chiều rộng $w = 0$ (vẫn là box lỗi). Chạy test `test_box_fully_outside_is_dropped_not_negative` bị đỏ ngay lập tức. Em phải tự sửa lại code: sau khi clip xong, nếu chiều rộng hoặc chiều cao $\le 0$ thì phải chuyển thành hành động xoá dòng luôn (`drop_line`).

*(Thưởng +2 điểm, tùy chọn) CVAT:*
- Em dựng CVAT chạy Docker local ở cổng `localhost:8080`, tạo task nạp 20 ảnh đầu từ hàng đợi `05_review_queue.csv`. Khi đặt bộ lọc `width < 20`, trên ảnh `img_0020` bộ lọc tóm được đúng **4 box người đi bộ** có bề rộng từ 15.0px đến 19.5px. Đối chiếu với pipeline thì ảnh này không bị gắn cờ `BOX_TINY`, lý do là cấu hình pipeline đặt ngưỡng `min_box_px: 12` (chặt hơn mức 20px của slide) nên các box từ 15px–19.5px máy coi là hợp lệ.
- Thuộc tính `can_review` trên CVAT dùng khi người dán nhãn gặp ca khó/mập mờ (như xe bị che khuất) muốn đánh dấu nhờ người kiểm định bậc cao xem lại. Pipeline của bài lab dùng cơ chế tương tự là đẩy các ảnh có cảnh báo nghi ngờ vào file `05_review_queue.csv` để người duyệt thẩm định.
