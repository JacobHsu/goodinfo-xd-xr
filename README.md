# goodinfo-xd-xr

台灣股票股利排行瀏覽器 — 從 Goodinfo 抓取 2025 年股利資料，並以互動式網頁呈現除息 / 除權資訊與即時報價。

## 功能

- **資料爬蟲** (`fetch_stock_dividend.py`)：批次抓取 Goodinfo 股利排行（共約 2,295 支），輸出 CSV
- **互動網頁** (`index.html`)：讀取 JSON 資料，依股價 50 元分成兩個 Tab 顯示，支援：
  - 欄位排序（點擊表頭）
  - 代號 / 股名搜尋
  - 股利發放頻率篩選（年 / 半年 / 季）
  - 有除權篩選
  - 即時報價更新（TWSE + TPEX Open API，盤中 30 分鐘快取）

## 快速開始

### 1. 安裝相依套件

```bash
pip install requests beautifulsoup4 lxml pandas
```

### 2. 抓取股利資料

```bash
python fetch_stock_dividend.py
```

輸出至 `data/` 目錄：

| 檔案 | 說明 |
|------|------|
| `stock_dividend_2025.csv` | 全部股票（約 2,000+ 筆） |
| `stock_dividend_2025_4digit.csv` | 僅四碼股票 |

### 3. 轉換為 JSON（供網頁使用）

```bash
python -c "
import pandas as pd, json
df = pd.read_csv('data/stock_dividend_2025_4digit.csv')
df.to_json('data/stock_dividend_2025_4digit.json', orient='records', force_ascii=False)
"
```

### 4. 開啟網頁

用本機 HTTP server 開啟（直接開 file:// 會因 CORS 無法載入 JSON）：

```bash
python -m http.server 8080
# 瀏覽 http://localhost:8080
```

## 專案結構

```
goodinfo-xd-xr/
├── fetch_stock_dividend.py   # 爬蟲腳本
├── index.html                # 前端瀏覽器
├── data/
│   ├── stock_dividend_2025.csv
│   ├── stock_dividend_2025_4digit.csv
│   └── stock_dividend_2025_4digit.json
└── TECHNICAL_NOTES.md
```

## 注意事項

- 爬蟲每頁請求間隔 3～5 秒，請勿縮短以避免對伺服器造成負擔
- 資料來源為 [Goodinfo 台灣股市資訊網](https://goodinfo.tw)，僅供個人學習參考
- 即時報價來自 [TWSE Open API](https://openapi.twse.com.tw) 及 [TPEX Open API](https://www.tpex.org.tw/openapi)

## License

[MIT](LICENSE)
