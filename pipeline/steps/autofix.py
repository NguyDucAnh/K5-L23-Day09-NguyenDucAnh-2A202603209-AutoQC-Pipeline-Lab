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

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


def fix(ds, issues, cfg):
    drop_codes = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
    remove_prefixes = ("DUP_IMAGE_",)
    remove_codes = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
    errors = [issue for issue in issues if issue.severity == ERROR]
    fixes = []
    removed = {
        issue.image for issue in errors
        if issue.code in remove_codes or issue.code.startswith(remove_prefixes)
    }

    for stem in sorted(removed):
        image = ds.image_path(stem)
        label = ds.label_path(stem)
        if image is None and not label.exists():
            continue
        if image is not None:
            image.unlink()
        if label.exists():
            label.unlink()
        fixes.append({
            "image": stem, "line": "", "action": "remove_image",
            "before": "ảnh và nhãn", "after": "đã xoá khỏi dataset",
        })

    grouped = defaultdict(list)
    for issue in errors:
        if issue.image in removed or issue.line is None:
            continue
        grouped[issue.image].append(issue)

    for stem, image_issues in grouped.items():
        path = ds.label_path(stem)
        if not path.exists():
            for issue in image_issues:
                if issue.code == "MISSING_LABEL_FILE":
                    fixes.append({
                        "image": stem, "line": "", "action": "needs_label",
                        "before": "(không có file)", "after": "chuyển người gán",
                    })
            continue
        original = path.read_text(encoding="utf-8", errors="replace").splitlines()
        by_line = defaultdict(list)
        for issue in image_issues:
            by_line[issue.line].append(issue)

        updated = []
        for line_no, text in enumerate(original, 1):
            line_issues = by_line.get(line_no, [])
            codes = {issue.code for issue in line_issues}
            dropping = bool(codes & drop_codes)
            if dropping:
                fixes.append({
                    "image": stem, "line": line_no, "action": "drop_line",
                    "before": text, "after": "",
                })
                continue
            if "BOX_OUT_OF_IMAGE" in codes:
                try:
                    cls, cx, cy, w, h = parse_yolo_line(text)
                except ValueError:
                    updated.append(text)
                    continue
                x1, y1 = max(0.0, cx - w / 2), max(0.0, cy - h / 2)
                x2, y2 = min(1.0, cx + w / 2), min(1.0, cy + h / 2)
                if x2 <= x1 or y2 <= y1:
                    fixes.append({
                        "image": stem, "line": line_no, "action": "drop_line",
                        "before": text, "after": "",
                    })
                    continue
                clipped = (cls, (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1)
                after = f"{clipped[0]} " + " ".join(f"{value:.10g}" for value in clipped[1:])
                updated.append(after)
                fixes.append({
                    "image": stem, "line": line_no, "action": "clip_box",
                    "before": text, "after": after,
                })
                continue
            updated.append(text)

        if updated != original:
            path.write_text("\n".join(updated) + ("\n" if updated else ""), encoding="utf-8")

    for issue in errors:
        if issue.code == "MISSING_LABEL_FILE" and issue.image not in removed:
            if not ds.label_path(issue.image).exists():
                fixes.append({
                    "image": issue.image, "line": "", "action": "needs_label",
                    "before": "(không có file)", "after": "chuyển người gán",
                })

    if any(issue.code == "BAD_CLASS_NAME" for issue in errors):
        path = ds.yaml_path
        before = path.read_text(encoding="utf-8") if path.exists() else ""
        data = yaml.safe_load(before) or {}
        data["names"] = {index: name for index, name in enumerate(cfg["classes"])}
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        fixes.append({
            "image": "data.yaml", "line": "", "action": "rename_classes",
            "before": before, "after": str(cfg["classes"]),
        })

    return fixes
