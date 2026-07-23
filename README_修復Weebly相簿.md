# 一鍵修復所有 Weebly slideshow

把以下兩個檔案放到網站根目錄，與 `index.html` 同一層：

```text
NTU_Chem_JSYLab/
├── fix_all_weebly_slideshows.py
├── run_fix_all_slideshows.command
├── index.html
├── photograph.html
├── publications.html
├── files/
└── uploads/
```

Mac 第一次執行：

```bash
chmod +x run_fix_all_slideshows.command
```

執行：

```bash
./run_fix_all_slideshows.command
```

也可直接執行：

```bash
python3 fix_all_weebly_slideshows.py --root .
```

程式會：

- 掃描同層所有 `.html` 和 `.htm`
- 在網站資料夾外建立 `網站名稱_slideshow_backup_日期時間` 備份，避免被一起 commit
- 偵測 `window.wSlideshow.render(...)`
- 將 `1/2/2/8/...` 改成 `uploads/1/2/2/8/...`
- 改成不依賴 Weebly 的原生相簿
- 保留左右按鈕、縮圖與鍵盤方向鍵
- 不修改已修好的頂端導覽列

更新 GitHub：

```bash
git add .
git commit -m "Fix Weebly slideshows"
git pull --rebase origin main
git push origin main
```
