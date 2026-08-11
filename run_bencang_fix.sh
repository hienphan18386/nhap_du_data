#!/bin/zsh
# Repair pass for TH Bến Cảng: re-run one student at a time so each gets a fresh
# form. Every student is logged separately because clinical_results.json is
# overwritten by every run, so the logs are the only durable record.
cd "/Users/hienphantrong/Desktop/Project/AI_PROJECT/NHAP_DATA_LONG" || exit 1

FILE="data/TH BEN CANG-AI NHẬP LIỆU KQ.xlsx"

while read -r cccd tt name; do
  [ -z "$cccd" ] && continue
  echo "=== TT$tt $name ($cccd) ==="
  python3 -u -m app.clinical --file "$FILE" \
      --from 01/07/2026 --to 11/08/2026 --only-cccd "$cccd" \
      > "logs_bencang/fix_TT${tt}.log" 2>&1
  grep -E "=>|^ +!" "logs_bencang/fix_TT${tt}.log"
done <<'LIST'
079219022652 3 DƯƠNG HIẾU NGHĨA
079219017419 4 ĐOÀN MINH QUÂN
079318042909 16 LÊ PHẠM NGỌC LAN CHI
079218026385 17 HÀ NGUYỄN MINH TUẤN
079217001524 18 UÔNG ĐÌNH GIA BẢO
079217033870 19 VÕ ĐỨC DUY
079317043047 20 TRẦN ĐOÀN NGỌC HOÀI
079217040682 21 NGUYỄN HUY HOÀNG
079316041031 23 LÊ MINH THIỆN TÂM
079217003907 24 HUỲNH PHÚC THỊNH
031217016182 26 NGUYỄN THÀNH TRUNG
079316006413 28 BÙI NGỌC TUYẾT MAI
079317031335 29 CAO HỒNG NGỌC
LIST

echo "=== XONG DOT VA ==="
