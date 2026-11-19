# Báo cáo Day 09 — Nguyễn Đức Anh, 2A202603209

## 1. Kết luận trước
Pipeline kết luận **Release**: intake giữ 203/224 ảnh và loại 21 ảnh; dataset xuất có 203 ảnh/nhãn. Sau mô phỏng duyệt 80 ảnh còn 0 lỗi bắt buộc và 16/203 ảnh còn cảnh báo (7,9%), thấp hơn ngưỡng Hold 10%.

## 2. Lỗi và phân việc
Số liệu từ `02_error_list_v1.csv`; các số là lượt cảnh báo/lỗi, không nhất thiết là số ảnh duy nhất.

| Mã lỗi (số lượt) | Ai xử lý | Cách xử lý |
|---|---|---|
| `BAD_SIZE` (3), `CORRUPT_IMAGE` (2), `DUP_IMAGE_EXACT` (8), `DUP_IMAGE_NEAR` (3), `LEAK_TEST` (5) | Máy | Loại ảnh ở intake để ảnh lỗi/trùng/rò rỉ không vào dataset. |
| `BAD_CLASS_ID` (6), `BAD_FORMAT` (3), `BOX_ZERO` (4), `DUP_BOX` (7) | Máy | Xóa dòng lỗi; autofix gộp lỗi cùng dòng để chỉ xóa một lần. |
| `BOX_OUT_OF_IMAGE` (8) | Máy | Cắt box về biên ảnh; người có thể kiểm lại log trước/sau. |
| `BAD_CLASS_NAME` (2) | Máy | Chuẩn hóa `names` trong `data.yaml`. |
| `MISSING_LABEL_FILE` (6) | Người | Không tạo nhãn giả; chuyển ảnh cho người gán. |
| `BOX_TINY` (6), `BOX_HUGE` (3), `EMPTY_LABEL` (12), `POSSIBLE_FALSE_POS` (29), `POSSIBLE_LOOSE_BOX` (12), `POSSIBLE_MISSING` (32), `POSSIBLE_WRONG_CLASS` (14) | Người | Đây là cảnh báo cần xem ảnh; ý kiến model không phải đáp án. |
| `CLASS_RARE` (4) | Người | Cảnh báo ở mức thống kê tập dữ liệu, cần kiểm tra phân bố lớp. |

`img_0020` đứng đầu hàng đợi (priority 11.524) vì có đồng thời `FIXED_DROP_LINE`, `POSSIBLE_MISSING` và `POSSIBLE_WRONG_CLASS`; điểm ưu tiên cộng trọng số cảnh báo với điểm của autofix. Hàng đợi có 102 ảnh, nhưng ngân sách chỉ cho duyệt 80. Trong 80 ảnh đầu có 77 lượt gắn mã cảnh báo ngữ nghĩa (`MISSING`, `WRONG_CLASS`, `FALSE_POS`, `LOOSE_BOX`); một ảnh có thể mang nhiều mã và đây không phải 77 lỗi đã được xác nhận.

## 3. Calibration
| Tham số | Khởi đầu | Đã chọn | Precision / Recall trước → sau | Lý do |
|---|---:|---:|---|---|
| `duplicates.phash_dist` | 2 | 6 | `DUP_IMAGE_NEAR`: 1.00/0.50 → 1.00/0.67 | Tăng recall trên calib nhưng giữ ngưỡng thấp để tránh gộp nhầm ảnh raw. |
| `second_opinion.conf` | 0.25 | 0.8 | `WRONG_CLASS`: 0.56/0.83 → 1.00/0.83 | Precision nhầm lớp tăng; chấp nhận giảm recall ở một số loại cảnh báo. |

Với `conf` 0.25 → 0.8, các chỉ số khác đổi như sau: `MISSING` P/R 0.50/1.00 → 0.67/0.75; `LOOSE_BOX` 0.29/0.40 → 0.50/0.20; `FALSE_POS` giữ 0.31/1.00 vì dùng ngưỡng `fp_conf` riêng. Calibration có thể gây hiểu nhầm: chỉ có 39 ảnh, và sweep trùng gần không đo được mọi kiểu ảnh raw hay rò rỉ test. Ở `phash_dist=16`, calib đạt P=1.00/R=0.83, nhưng raw ghép nhầm `img_0011` (sân tennis) với `img_0008` (trượt tuyết). Tôi chọn 6: các cặp raw bị phát hiện ở khoảng cách 0, 0 và 6 là cùng cảnh/ảnh biến đổi khi mở xem; kết quả loại 3 ảnh trùng gần thay vì 7 ở ngưỡng 16. Ngưỡng thấp vẫn có thể bỏ sót ảnh bị biến đổi mạnh; tập calib không có ca `LEAK_TEST`, nên không thể suy ra recall rò rỉ từ sweep này.

## 4. Cửa chặn và điểm mù
Chạy thử `--budget 0 --reports work/rep_nb --export-dir work/exp_nb` cho kết luận **Rework**, mã thoát **20**, còn 6 lỗi bắt buộc và không tạo `work/exp_nb/clean_v1`. Đây là hành vi đúng: ảnh thiếu nhãn không được máy tự bịa nhãn, và không người duyệt thì không thể phát hành.

Tôi đã xem 10 ảnh đã vẽ nhãn. Ba lỗi quan sát được: `img_0050` có box người chiều rộng 0 (dòng 1); `img_0100` có box lớp car rộng 98,5% ảnh và cao 88,8% ảnh nhưng diện tích 87,5% vẫn thấp hơn ngưỡng BOX_HUGE cố định 95%; `img_0030` có box người tràn mép trái (dòng 9) giữa cảnh đông người. Đây là điểm mù: ngưỡng diện tích không bắt mọi box quá rộng về mặt ngữ nghĩa, còn ảnh đông người làm box chồng lấn khó phân xử. Thêm nữa, second opinion chỉ tạo cảnh báo chứ không chứng minh nhãn đúng; trên calib, recall `LOOSE_BOX` giảm từ 0.40 xuống 0.20 khi nâng `conf` lên 0.8. Các trường hợp này cần người xem ảnh gốc.

## 5. Train: raw vs clean
**Chưa chạy**: train Colab là tùy chọn chấm riêng; lượt này hoàn thành phần lõi và không chạy huấn luyện.

## 6. Quyết định và ghi chú AI
Quyết định là **Release** theo gate của lab; vẫn cần người xử lý các cảnh báo còn lại trước khi dùng nhãn cho mục đích khác.

- Prompt chính: triển khai bốn module theo docstring/test, giữ nguyên các file dữ liệu, test và quy tắc cố định.
- Kiểm tra: chạy 79 unit test, calibration sweep, pipeline; mở 10 ảnh vẽ nhãn và xem lại các cặp near-duplicate.
- Một lần AI sai: ban đầu chọn `phash_dist=16` chỉ từ calib; kiểm tra trực quan raw phát hiện cặp sân tennis/trượt tuyết bị ghép nhầm, nên hạ ngưỡng xuống 6.
