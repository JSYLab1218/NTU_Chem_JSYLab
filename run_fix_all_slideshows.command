#!/bin/bash
cd "$(dirname "$0")"

echo "============================================"
echo " 批次修復所有 Weebly slideshow 相簿"
echo "============================================"
echo

python3 fix_all_weebly_slideshows.py --root .
status=$?

echo
if [ "$status" -eq 0 ]; then
  echo "處理完成。請將修改後的 HTML commit 到 GitHub。"
else
  echo "處理時發生錯誤，請查看上方訊息。"
fi

echo
read -n 1 -s -r -p "按任意鍵關閉..."
echo
exit "$status"
