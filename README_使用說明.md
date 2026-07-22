# Weebly 圖片路徑修復工具

這個工具是依照你提供的 HTML 結構製作，會處理：

- `uploads/1/2/2/8/122804110/...`
- `/uploads/1/2/2/8/122804110/...`
- Weebly slideshow 的 `"url":"1/2/2/8/122804110/..."`
- JavaScript 跳脫格式 `1\/2\/2\/8\/122804110\/...`
- CSS 的 `background-image: url(...)`
- URL 後方的 `?1723011726` 快取參數

它會掃描同一個網站資料夾下的所有圖片，找到正確位置後，把 HTML/CSS/JS 改成可用的相對路徑。

## 最建議的資料夾放法

把這三個檔案放進網站根目錄：

```text
你的網站資料夾/
├── repair_weebly_images.py
├── run_repair.command
├── index(1).html
├── research(1).html
├── members(1).html
├── uploads/
└── 其他圖片資料夾/
```

## Mac 最簡單執行方式

1. 解壓縮。
2. 把 `repair_weebly_images.py` 與 `run_repair.command` 放進網站根目錄。
3. 第一次執行前，開啟「終端機」，輸入：

```bash
chmod +x run_repair.command
```

4. 將 `run_repair.command` 拖進終端機後按 Enter。

預設會從原始 Weebly 網站下載缺少的圖片：

```text
https://jsylab1218.weebly.com
```

完成後會產生：

```text
repaired_site/
├── 修正後的 HTML
├── 下載或原有的圖片
└── image_path_report.csv
```

## 手動執行

只使用本機現有圖片：

```bash
python3 repair_weebly_images.py --root .
```

本機缺圖時，從原始 Weebly 網站下載：

```bash
python3 repair_weebly_images.py \
  --root . \
  --source-url https://jsylab1218.weebly.com \
  --download-missing
```

指定輸出資料夾：

```bash
python3 repair_weebly_images.py \
  --root . \
  --output ./my_fixed_site \
  --source-url https://jsylab1218.weebly.com \
  --download-missing
```

## 不要直接修改原檔的原因

預設會建立新的 `repaired_site`，不會覆蓋原始資料。網站修好前，保留原檔比較安全；路徑修復最怕「修了一半，原本能看的也一起走失」。

## 報告判讀

開啟 `repaired_site/image_path_report.csv`：

- `repaired`：已改成正確的本機相對路徑。
- `already-valid`：原本路徑已能找到圖片。
- `unresolved`：找不到或有多個同名圖片，程式沒有亂猜。
- `matched_file`：實際配對到的圖片。
- `download_url`：若有下載，顯示來源網址。
- `note`：配對方法或錯誤訊息。

## 重要提醒

目前提供給 ChatGPT 的是 HTML，沒有一起附上所有圖片資料夾，因此無法在這裡直接產生完整修正網站。將工具放到含有圖片的網站根目錄執行即可；若本機圖片不存在，使用 `--download-missing` 從仍可存取的 Weebly 網站抓回。
