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
├── fetch_stock_gifts.py        # 股東會紀念品（零股屋）
├── scoring.py                  # 排名決策節點的權重與分級（共用）
├── export_latest.py            # 產生外部 API 用的 data/latest.json
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

## 外部 API

最新年度過濾好的完整名單（固定網址，已開放 CORS，可直接 `fetch`）：

```
https://jacobhsu.github.io/goodinfo-xd-xr/data/latest.json
```

```json
{
  "year": "2026",
  "updated": "2026-11-07",
  "price_date": "2026-11-06",
  "count": 1162,
  "stocks": [
    {"rank": 1, "code": "5314", "name": "世紀*", "score": 98.1, "price": 20.85, "yield": 7.8,
     "cash_div": 0.049, "stock_div": 1.579, "total_div": 1.627, "freq": "annual",
     "ex_div_date": "2026-09-21", "gift": "德國KD頂級魚油(30粒/盒)"}
  ]
}
```

| key | 說明 |
|-----|------|
| `rank` | 排名（依 `score` 降冪，1 起算） |
| `code` / `name` | 股票代號（字串）/ 名稱 |
| `score` | 決策節點加權總分 0~100（見下方「排名依據」） |
| `price` | 收盤價（日期見頂層 `price_date`） |
| `yield` | 現價殖利率 %（合計股利 ÷ 現價，含分割保護） |
| `cash_div` / `stock_div` / `total_div` | 現金 / 股票 / 合計股利（元） |
| `freq` | 配息頻率：`annual` / `semiannual` / `quarterly` |
| `ex_div_date` | 除息交易日（`YYYY-MM-DD`） |
| `gift` | 股東會紀念品 |

- `stocks` 已依 `rank` 排序；缺值為 `null`。
- 由 `export_latest.py` 產生，`fetch_stock_dividend.py --json-only` 與每週 `update_prices.py` 會自動更新。
- 需要全部欄位或特定年度，可改抓 `data/index_<year>.json`（年度清單見 `data/years.json`）。

## 排名依據

`排名` 依 **總分**（0~100）降冪排列，網頁預設也依總分排序。總分借用 TypeSafe System One（Jev）
決策模型的概念：每個指標是一個只問一件事的「決策節點」，以 **Score**（有序分級，落在級距之間線性內插成小數）
或 **Noul**（是/否條件的 0~1 分數）題型打分，再加權加總。目標設定為「穩健存股」。
權重與分級在 `scoring.py`（`fetch_stock_dividend.py` 與 `update_prices.py` 共用）。

| 節點 | 題型 | 依據 | 分級（0 → 1） | 權重 |
|------|------|------|----------------|------|
| 殖利率 | Score | **現價殖利率** = 合計股利 ÷ 現在股價 | 2% / 4% / 6% / 8% | 30% |
| 配息安全 | Noul | 配發率 = 合計股利 ÷ EPS | ≤ 80% 滿分、100% 半分、≥ 150% 零分 | 20% |
| 本業穩定 | Noul | 近 12 季營業利益 | 為正的季數比例 | 15% |
| 獲利能力 | Score | ROE | 5% / 10% / 15% / 20% | 10% |
| 財報體質 | Score | Goodinfo 財報評分 | 40 / 50 / 60 / 70 | 10% |
| 股利不衰退 | Noul | 當年 ÷ 前一年合計股利 | 比值，上限 1 | 10% |
| 紀念品 CP | Score | 紀念品價值 ÷ 股價 | 0 / 0.5 / 1 / 2（價值取文字中「NN元」，其他實物估 30 元） | 5% |

- 缺資料的節點以 0.5 分計。各節點分數另存於 JSON 的 `分_<節點>` 欄位（網頁不顯示），可用來檢查為何某檔排在那裡。
- EPS、OI 不直接比絕對值（EPS 與股價高度相關、OI 反映公司規模），改用配發率與本業穩定度。
- 既有硬篩選（DR、未發股利、殖利率 < 1%、前一年未發、EPS/ROE/OI 為負）仍先執行，相當於否決節點。
- 權重與分級改動後需重跑 `python fetch_stock_dividend.py --year <year> --json-only`。

### 兩種殖利率

| 欄位 | 算法 | 何時更新 | 用途 |
|------|------|----------|------|
| 合計殖利率%（Goodinfo） | 股利 ÷ **除權息當時**股價 | 只有手動重抓股利時 | 對照 Goodinfo |
| 現價殖利率% | 合計股利 ÷ **現在**股價 | `update_prices.py` 每週自動；網頁按「更新報價」即時 | 排名、< 1% 篩選 |

- 股利資料久久才手動更新一次，但股價每週自動更新；改用現價讓殖利率與排名能自動跟上。
  `update_prices.py` 更新股價後會重算 `現價殖利率`、`分_殖利率`、`分_紀念品`、`總分` 並重新排名，其餘節點不變。
- 網頁按「更新報價」只會即時更新現價殖利率的顯示，總分仍是 JSON 裡每週算的值。
- 「現價殖利率 < 1%」篩選只在 `--json-only` 時執行；每週股價更新不會把股票加入或移出名單。
- **分割保護**：現價跌破除息（權）價的一半時，多半是股票分割或面額變更（名稱帶 `*` 的常見），
  股利仍是分割前金額、現價殖利率會嚴重高估（例：寶雅 677 → 74 元，會算成 34%），此時改用 Goodinfo 的合計殖利率。
  門檻為 `scoring.SPLIT_RATIO`。真的腰斬的股票也會被這條規則改用 Goodinfo 數字。
- **已知限制**：半年配 / 季配的股票在重抓股利前只算到已公布的部分股利，殖利率會偏低（例如國巨 2026 只算到上半年）。

## 資料來源

`index_<year>.json` 由以下資料合併而成（`fetch_stock_dividend.py --json-only` 負責 join 與篩選）：

| 資料檔 | 來源 | 產生方式 | 何時該更新 |
|--------|------|----------|------------|
| `stock_dividend_<year>.csv` | Goodinfo「股票股利」排行 | `python fetch_stock_dividend.py --year <year>` | 除權息季（約 6～9 月）期間 |
| `stock_eps.csv`（EPS） | Goodinfo「年度EPS最高」排行 | `python fetch_stock_eps.py` | 每年 4 月（前一年年報 3/31 前公布） |
| `stock_roe.csv`（ROE） | Goodinfo「年度ROE最高」排行 | `python fetch_stock_roe.py` | 同上 |
| `stock_operating_profit.csv`（OI 營業利益） | Goodinfo「單季營業利益最低」排行 | `python fetch_stock_operating_profit.py` | 每季財報公布後（5/15、8/14、11/14、3/31） |
| `stock_gifts_<year>.tsv`（紀念品） | [零股屋](https://www.stockroomtw.com/) 首頁的「預計發放的紀念品」表 | `python fetch_stock_gifts.py --year <year>` | 股東會季（約 3～6 月）期間 |
| 股價（寫回 `index_<year>.json`） | TWSE / TPEX Open API | `python update_prices.py`（GitHub Actions 每週一自動執行） | 自動 |

> - `fetch_stock_eps.py`、`fetch_stock_roe.py` 仍是舊的純 `requests` 寫法，Goodinfo 加上 Cloudflare 後應該已無法執行，
>   下次要更新時需比照 `fetch_stock_operating_profit.py` 改用 `solve_cloudflare_url()`。
> - 零股屋網站上的「下載推薦清單（Excel / PDF）」是**買股參考清單**（內容為前一年及更早的紀念品），不是當年實際發放的紀念品，不要用錯。
> - `stock_gifts_2025.tsv` 是早期手動整理的，來源未記錄（格式與零股屋相同）。

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
