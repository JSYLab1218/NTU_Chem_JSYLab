#!/bin/bash
cd "$(dirname "$0")"

echo "開始掃描並修復 Weebly 圖片路徑..."
echo

python3 repair_weebly_images.py \
  --root . \
  --source-url "https://jsylab1218.weebly.com" \
  --download-missing

status=$?
echo
if [ "$status" -eq 0 ]; then
  echo "完成。請打開 repaired_site 資料夾。"
else
  echo "處理完成，但仍有部分圖片未配對。"
  echo "請查看 repaired_site/image_path_report.csv。"
fi
echo
read -n 1 -s -r -p "按任意鍵關閉..."
echo
