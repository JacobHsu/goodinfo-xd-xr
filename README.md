# goodinfo-xd-xr

台灣股票股利排行瀏覽器 — 從 Goodinfo 抓取指定年度股利資料，過濾出連續兩年均有發股利的四碼股票，以互動式網頁呈現除息 / 除權資訊與即時報價。

## 功能

- **資料爬蟲** (`fetch_stock_dividend.py`)：批次抓取 Goodinfo 股利排行（共約 2,295 支），輸出 CSV 與 JSON
- **互動網頁** (`index.html`)：讀取 `data/index_<year>.json`，依股價 50 元分成兩個 Tab，支援：
  - 年度切換（右上角下拉選單，資料來自 `data/years.json`）
  - 欄位排序（點擊表頭）
  - 代號 / 股名搜尋
  - 股利發放頻率篩選（年 / 半年 / 季）
  - 有除權篩選
  - 即時報價更新（TWSE + TPEX Open API，盤中 30 分鐘快取）

## 快速開始

### 1. 安裝相依套件

```bash
pip install beautifulsoup4 lxml pandas curl_cffi undetected-chromedriver selenium
```

> Goodinfo 目前在爬蟲防護前多加了一層 Cloudflare JS 驗證，純 `requests` 已無法通過。
> 爬蟲改用 `undetected_chromedriver` 開一個**有畫面**的 Chrome 通過驗證（過程全自動，
> 通常不需要手動操作），拿到 `cf_clearance` cookie 後再用 `curl_cffi` 模擬瀏覽器
> 快速抓完剩下的分頁。因此執行爬蟲時本機需要能跳出瀏覽器視窗，不能在純 headless / 無顯示的環境執行。

### 2. 抓取兩年股利資料

先抓前一年（用來過濾），再抓當年：

```bash
python fetch_stock_dividend.py --year 2025
python fetch_stock_dividend.py --year 2026
```

輸出至 `data/` 目錄（每個年度各一組）：

| 檔案 | 說明 |
|------|------|
| `stock_dividend_<year>.csv` | 全部股票（約 2,295 筆） |
| `stock_dividend_<year>_4digit.csv` | 僅四碼股票（約 1,957 筆） |

### 3. 產生網頁用 JSON

```bash
python fetch_stock_dividend.py --year 2026 --json-only
```

邏輯：從 2026 四碼資料中，排除 2025 年合計股利為 0 的股票，輸出至 `data/index_2026.json`，
並更新 `data/years.json`（記錄目前有哪些年度可在網頁上切換）。

> 若 `data/stock_dividend_2025_4digit.csv` 不存在，則不做過濾直接輸出。

### 4. 開啟網頁

用本機 HTTP server 開啟（直接開 file:// 會因 CORS 無法載入 JSON）：

```bash
python -m http.server 8080
# 瀏覽 http://localhost:8080
```

網頁預設載入 `data/years.json` 中最新的年度，右上角下拉選單可切換其他已抓取的年度。

## 專案結構

```
goodinfo-xd-xr/
├── fetch_stock_dividend.py     # 爬蟲 + JSON 產生腳本
├── update_prices.py            # 每週更新所有 index_<year>.json 的即時股價
├── index.html                  # 前端瀏覽器
├── docs/TECHNICAL_NOTES.md     # 爬蟲逆向工程筆記與踩坑記錄
└── data/
    ├── stock_dividend_2025.csv
    ├── stock_dividend_2025_4digit.csv
    ├── stock_dividend_2026.csv
    ├── stock_dividend_2026_4digit.csv
    ├── index_2025.json         # 2025 年度網頁資料（兩年均有發股利）
    ├── index_2026.json         # 2026 年度網頁資料
    └── years.json              # 網頁年度下拉選單的可選年度清單
```

## 注意事項

- 爬蟲每頁請求間隔 3～5 秒，請勿縮短以避免對伺服器造成負擔
- `SHEET` 必須用 `股利政策發放年度`（不帶 `_去年`），`RPT_TIME` 才能正確切換年度，詳見 `docs/TECHNICAL_NOTES.md`
- Goodinfo 前面掛了 Cloudflare JS 驗證，爬蟲需要能開啟有畫面的 Chrome（見上方安裝說明）
- 資料來源為 [Goodinfo 台灣股市資訊網](https://goodinfo.tw)，僅供個人學習參考
- 即時報價來自 [TWSE Open API](https://openapi.twse.com.tw) 及 [TPEX Open API](https://www.tpex.org.tw/openapi)

## References

### Goodinfo 資料來源頁面

| 說明 | 網址 |
|------|------|
| 股票股利排行（年度） | [StockList – 股票股利](https://goodinfo.tw/tw/StockList.asp?MARKET_CAT=%E7%86%B1%E9%96%80%E6%8E%92%E8%A1%8C&INDUSTRY_CAT=%E8%82%A1%E7%A5%A8%E8%82%A1%E5%88%A9+%28%E5%83%85%E9%A1%AF%E7%A4%BA%E5%8E%BB%E5%B9%B4%E8%B3%87%E6%96%99%29%40%40%E8%82%A1%E7%A5%A8%E8%82%A1%E5%88%A9%40%40%E5%83%85%E9%A1%AF%E7%A4%BA%E5%8E%BB%E5%B9%B4%E8%B3%87%E6%96%99) |
| 年度 EPS 最高排行 | [StockList – 年度EPS最高](https://goodinfo.tw/tw/StockList.asp?MARKET_CAT=%E7%86%B1%E9%96%80%E6%8E%92%E8%A1%8C&INDUSTRY_CAT=%E5%B9%B4%E5%BA%A6EPS%E6%9C%80%E9%AB%98) |

### Open API

| 說明 | 網址 |
|------|------|
| TWSE 即時報價 | https://openapi.twse.com.tw |
| TPEX 即時報價 | https://www.tpex.org.tw/openapi |

## License

[MIT](LICENSE)
