# Medinet Health-Check Importer

Nhập danh sách khám sức khỏe trẻ em vào
[quanlyskcd.medinet.org.vn](https://quanlyskcd.medinet.org.vn/) một cách tự động.
Chỉ **thêm mới**, bỏ qua trẻ đã có; không sửa/xóa bất kỳ hồ sơ nào.

Công cụ điều khiển **trình duyệt bạn dùng hằng ngày, với phiên đăng nhập sẵn có**:

| Chế độ | Trình duyệt | Phiên đăng nhập | HĐH |
|---|---|---|---|
| `--browser chrome` (mặc định) | **Chrome thật của bạn** (qua AppleScript) | Dùng luôn phiên medinet đang có | macOS |
| `--browser firefox` | **Firefox thật của bạn** (profile mặc định, qua Marionette) | Dùng luôn phiên đang có | Mọi HĐH (phải đóng Firefox trước) |
| `--separate-profile` | Chrome/Edge qua Playwright, hồ sơ riêng | Đăng nhập 1 lần, tự nhớ | Mọi HĐH |

> **Yêu cầu:** máy đích cần có sẵn **Google Chrome** (hoặc Edge) **hoặc Firefox**.
> Ứng dụng không tải trình duyệt về.
>
> **Lưu ý Windows/Linux + Chrome:** Google chặn tự động hóa profile thật của Chrome
> (từ Chrome 136), nên trên Windows/Linux chế độ Chrome luôn dùng hồ sơ riêng;
> muốn dùng phiên thật sẵn có thì chọn `--browser firefox`.

---

## 1. Dùng bản đã đóng gói (người dùng cuối)

Tải file chạy cho hệ điều hành của bạn:

| HĐH     | File                      |
|---------|---------------------------|
| Windows | `medinet-importer.exe`    |
| macOS   | `medinet-importer`        |
| Linux   | `medinet-importer`        |

Các bước — **chỉ cần bấm đúp, không cần gõ lệnh**:

1. Đặt file chạy vào một thư mục trống rồi **bấm đúp**.
2. Menu hiện ra. Lần đầu chọn **[2] Tạo file Excel mẫu** → được `mau_danh_sach.xlsx`
   cạnh file chạy. Mở nó, điền danh sách trẻ (mỗi dòng một bé), lưu lại.
3. Bấm đúp chạy lại, chọn **[1] Nhập danh sách từ file** → **hộp thoại chọn file**
   mở ra, chọn file **Excel / PDF / JSON** của bạn.
4. Chọn trình duyệt trong menu — công cụ mở **đúng trình duyệt bạn dùng hằng ngày**:
   - **macOS + Chrome**: dùng luôn Chrome đang có, phiên medinet sẵn đăng nhập.
     Lần đầu Chrome sẽ yêu cầu bật một lần: menu **View → Developer →
     "Allow JavaScript from Apple Events"** (công cụ sẽ hướng dẫn ngay trên màn hình).
   - **Firefox**: thoát hẳn Firefox trước khi chạy; công cụ mở lại Firefox với
     profile thật của bạn (đăng nhập sẵn có).
   - Nếu chưa đăng nhập medinet, đăng nhập rồi vào *Khám sức khỏe trẻ em →
     Thông tin hành chính* — việc nhập tự chạy khi lưới hiện ra.
5. Kết quả ghi vào **`import_results.json`**.

### File dữ liệu hỗ trợ

| Định dạng | Ghi chú |
|---|---|
| **Excel (.xlsx)** | Khuyến nghị — dùng file mẫu tạo từ menu [2], cột tiếng Việt tự nhận |
| **PDF** | Đọc bảng danh sách dạng chuẩn (TT, họ tên, giới tính, ngày sinh, CCCD, BHYT, địa chỉ, mẹ, SĐT, lớp); nếu PDF không đọc được sẽ báo và hướng sang Excel |
| **JSON** | Định dạng nội bộ như `children.json` |

### Chạy bằng dòng lệnh (tùy chọn, không bắt buộc)

```
medinet-importer                            # bấm đúp = menu + hộp thoại chọn file
medinet-importer --file danhsach.xlsx       # chỉ định file, Chrome thật (macOS)
medinet-importer --file ds.pdf --browser firefox
medinet-importer --age-group m2             # nhập luồng Trẻ 6–17 tuổi (M2)
medinet-importer --make-template            # tạo mau_danh_sach.xlsx rồi thoát
medinet-importer --separate-profile         # hồ sơ riêng biệt, đăng nhập 1 lần
medinet-importer --dry-run --limit 3        # chạy thử 3 hồ sơ, KHÔNG lưu
medinet-importer --check-file ds.xlsx       # kiểm tra đọc file (không mở trình duyệt)
medinet-importer --selftest                 # kiểm tra máy (không mở trình duyệt)
```

> `--check-file` và `--selftest` không mở cửa sổ nào — dùng để kiểm tra nhanh
> file dữ liệu / môi trường trước khi nhập thật.

### Đối tượng khám: M1 và M2

Khi bấm đúp, menu đầu tiên cho chọn đối tượng khám:

- **[1] Trẻ dưới 6 tuổi (M1)** — luồng mầm non.
- **[2] TRẺ TỪ 6–17 TUỔI (M2)** — luồng tiểu học/THCS/THPT (form khác của medinet).

> **M2 luôn chạy "bản thử" trước:** công cụ nhập **1 học sinh đầu tiên**, hiện kết
> quả (tên, CCCD, trường, lớp) rồi hỏi *"Tiếp tục nhập hết? (y/n)"*. Bấm `y` mới
> chạy tiếp phần còn lại, `n` để dừng. Đây là bước bắt buộc để bạn kiểm tra form
> M2 điền đúng trước khi nhập hàng loạt.

> **macOS**: lần đầu có thể bị chặn "unidentified developer" → chuột phải → *Open*,
> hoặc *System Settings → Privacy & Security → Open Anyway*.

---

## 2. Chạy từ mã nguồn (lập trình viên)

```bash
pip install -r requirements.txt   # playwright (cho Chrome); Firefox chỉ cần stdlib
python -m app.importer                      # Chrome
python -m app.importer --browser firefox    # Firefox
python -m app.importer --dry-run            # kiểm tra, không lưu
```

Chuyển PDF → `children.json`: sửa văn bản nguồn trong
[tools/parse_mn12_pdf.py](tools/parse_mn12_pdf.py) rồi chạy nó.

---

## 3. Tự đóng gói file chạy

PyInstaller **không build chéo** — mỗi HĐH phải build trên chính nó.

```bash
pip install -r requirements.txt pyinstaller
pyinstaller packaging/importer.spec
# → dist/medinet-importer  (hoặc .exe)
```

Không có trình duyệt nào bị nhúng nên file chạy nhỏ và build nhanh.

### Build cả 3 HĐH cùng lúc (khuyến nghị)

Đẩy repo lên GitHub. Workflow [.github/workflows/build.yml](.github/workflows/build.yml)
tự build Windows + macOS + Linux:

- **Actions** → *Build standalone importer* → *Run workflow*, hoặc
- gắn tag: `git tag v1.0 && git push --tags`

Tải file chạy từ mục **Artifacts** của lần chạy đó.

---

## Cấu trúc dự án

```
app/importer.py         # ứng dụng chính (chọn Chrome/Firefox)
app/marionette.py       # client Marionette thuần stdlib (lái Firefox thật)
app/data/children.json  # dữ liệu mẫu, được nhúng vào gói
tools/parse_mn12_pdf.py # công cụ chuyển PDF → JSON
packaging/importer.spec # cấu hình PyInstaller
.github/workflows/      # build tự động 3 HĐH
scripts/_archive/       # script chẩn đoán cũ (không dùng khi đóng gói)
```

### Cách hoạt động (kỹ thuật)

- **Chrome thật (macOS)**: AppleScript `execute javascript` vào tab medinet của
  Chrome đang dùng — cách duy nhất còn lại vì Chrome 136+ chặn CDP trên profile
  mặc định. Kết quả JS bọc qua `JSON.stringify` để trả về đúng kiểu dữ liệu.
- **Firefox thật (mọi HĐH)**: khởi động Firefox với cờ `--marionette` trên profile
  mặc định của người dùng, điều khiển qua giao thức Marionette của Mozilla
  (thuần stdlib, không cần thư viện ngoài).
- **Hồ sơ riêng (`--separate-profile`)**: Playwright `channel="chrome"` (thử tiếp
  `msedge`, `chromium`) với thư mục profile cạnh app; Firefox riêng tương tự qua
  Marionette + `-profile`.
- Cùng một lớp `Importer` (selector, thao tác DevExtreme) dùng chung; chỉ lớp vận
  chuyển (`page.evaluate` ↔ AppleScript ↔ Marionette) là khác.
