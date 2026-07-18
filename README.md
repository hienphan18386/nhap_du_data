# Medinet Health-Check Importer

Nhập danh sách khám sức khỏe trẻ em vào
[quanlyskcd.medinet.org.vn](https://quanlyskcd.medinet.org.vn/) một cách tự động.
Chỉ **thêm mới**, bỏ qua trẻ đã có; không sửa/xóa bất kỳ hồ sơ nào.

Ứng dụng lái một trình duyệt **Firefox** (qua Playwright). Khi đóng gói, Firefox được
nhúng sẵn vào file chạy nên máy đích **không cần cài gì**.

---

## 1. Dùng bản đã đóng gói (người dùng cuối)

Tải file chạy cho hệ điều hành của bạn:

| HĐH     | File                      |
|---------|---------------------------|
| Windows | `medinet-importer.exe`    |
| macOS   | `medinet-importer`        |
| Linux   | `medinet-importer`        |

Các bước:

1. Đặt file chạy vào một thư mục trống.
2. Chạy nó (Windows: bấm đúp; macOS/Linux: `./medinet-importer` trong Terminal).
   - Lần đầu chạy sẽ tự tạo file **`children.json`** ngay cạnh file chạy (dữ liệu mẫu).
3. Mở `children.json`, thay bằng danh sách trẻ của bạn (cùng định dạng), lưu lại.
4. Chạy lại. Cửa sổ Firefox mở lên — **đăng nhập medinet** và vào
   *Khám sức khỏe trẻ em → Thông tin hành chính*. Việc nhập bắt đầu tự động khi lưới hiện ra.
   - Đăng nhập được ghi nhớ trong thư mục `firefox-profile/` (cạnh file chạy), lần sau khỏi đăng nhập lại.
5. Kết quả ghi vào **`import_results.json`**.

Tùy chọn dòng lệnh:

```
medinet-importer --dry-run   # điền form nhưng KHÔNG lưu, để kiểm tra
medinet-importer --limit 3   # chỉ xử lý 3 hồ sơ đầu
```

> **macOS**: lần đầu có thể bị chặn "unidentified developer" → chuột phải → *Open*,
> hoặc *System Settings → Privacy & Security → Open Anyway*.

---

## 2. Chạy từ mã nguồn (lập trình viên)

```bash
pip install -r requirements.txt
python -m playwright install firefox
python -m app.importer            # nhập
python -m app.importer --dry-run  # kiểm tra, không lưu
```

Chuyển PDF → `children.json`: sửa văn bản nguồn trong
[tools/parse_mn12_pdf.py](tools/parse_mn12_pdf.py) rồi chạy nó (ghi ra `scripts/parsed_children_mn12.json`).

---

## 3. Tự đóng gói file chạy

PyInstaller **không build chéo** — mỗi HĐH phải build trên chính nó.

```bash
pip install -r requirements.txt pyinstaller
PLAYWRIGHT_BROWSERS_PATH=0 python -m playwright install firefox   # Windows: đặt biến rồi chạy
pyinstaller packaging/importer.spec
# → dist/medinet-importer  (hoặc .exe)
```

`PLAYWRIGHT_BROWSERS_PATH=0` cài Firefox *vào trong* gói playwright để spec nhúng được.

### Build cả 3 HĐH cùng lúc (khuyến nghị)

Đẩy repo lên GitHub. Workflow [.github/workflows/build.yml](.github/workflows/build.yml)
tự build Windows + macOS + Linux:

- **Actions** → *Build standalone importer* → *Run workflow*, hoặc
- gắn tag: `git tag v1.0 && git push --tags`

Tải file chạy từ mục **Artifacts** của lần chạy đó.

---

## Cấu trúc dự án

```
app/importer.py         # ứng dụng chính (Playwright, đa nền tảng)
app/data/children.json  # dữ liệu mẫu, được nhúng vào gói
tools/parse_mn12_pdf.py # công cụ chuyển PDF → JSON
packaging/importer.spec # cấu hình PyInstaller (+ runtime hook nhúng Firefox)
.github/workflows/      # build tự động 3 HĐH
scripts/_archive/       # script chẩn đoán cũ (không dùng khi đóng gói)
```
