# fetch_stock_dividend.py 技術文檔

## 概述

從 [Goodinfo! 台灣股市資訊網](https://goodinfo.tw) 爬取「熱門排行 – 股票股利（僅顯示去年資料）– 股利政策發放年度 – 股利分派與除權/息價殖利率 – 2025」全部資料，共 **2295 筆**，輸出為 CSV。

---

## 執行方式

```bash
pip install requests beautifulsoup4 lxml pandas
python fetch_stock_dividend.py
```

輸出：`stock_dividend_2025.csv`（UTF-8 BOM 編碼，可直接用 Excel 開啟）

執行時間約 **2~3 分鐘**（含每頁 3~5 秒隨機延遲，共 8 頁）。

---

## 輸出欄位

| 欄位 | 說明 |
|------|------|
| 排名 | 除權息合計殖利率排名 |
| 代號 | 股票代碼 |
| 名稱 | 股票名稱 |
| 股價日期 | 最新股價日期 |
| 成交 | 成交價 |
| 漲跌價 | 當日漲跌金額 |
| 漲跌幅 | 當日漲跌幅（%）|
| 股利發放年度 | 股利發放年度（此表為 2025）|
| 股利發放頻率 | 年、半年、季、月 |
| 現金股利 | 現金股利（元）|
| 股票股利 | 股票股利（元）|
| 合計股利 | 現金 + 股票股利合計（元）|
| 除息價 | 除息參考價 |
| 除息價現金殖利率 | 現金股利 / 除息價（%）|
| 除權價 | 除權參考價 |
| 除權價股票殖利率 | 股票股利 / 除權價（%）|
| 除權息合計殖利率 | 合計殖利率（%）|
| 除息交易日 | 除息日期 |
| 除權交易日 | 除權日期 |
| 現金股利發放日 | 現金股利入帳日 |

---

## 網站請求機制（逆向工程結果）

### 1. Cookie 驗證握手

Goodinfo 對第一次請求回傳一個「驗證頁」而非資料，該頁包含：

```javascript
// 設定含時區與時間戳的 cookie
setCookie('CLIENT_KEY',
  '2.3|43100.x|46433.x|' + GetTimezoneOffset() + '|' + Date.now()/86400000 + '|...',
  7, '/');

// 用 setTimeout 重導向回原 URL 並附加 REINIT 參數
setTimeout(function(){
  window.location.replace('StockList.asp?...&REINIT=46130.xxx');
}, 500);
```

Python 不執行 JS，因此必須手動：
1. 從第一次回應的 HTML 用 regex 擷取 `REINIT` 值
2. 用 Python 計算等效的 `CLIENT_KEY` 值並寫入 session cookie

`CLIENT_KEY` 格式：
```
2.3|<固定值A>|<固定值B>|<TZ_OFFSET>|<timestamp>|<timestamp>
```
- `TZ_OFFSET`：台灣 UTC+8 → JS `GetTimezoneOffset()` 回傳 `-480`
- `timestamp`：`Date.now() / 86400000 - TZ_OFFSET / 1440`（JS 日曆天數）

### 2. 資料 AJAX 端點

實際資料透過獨立的 AJAX fragment 端點提供，由 `StockList_Func.js` 中的 `ReloadStockList()` 呼叫：

```javascript
function ReloadStockList(sLink) {
    var href = 'StockList.asp?STEP=DATA' + '&' + sLink;
    ReloadReport(href, txtStockListData, StockListDataLoading);
}
```

請求格式：
```
GET https://goodinfo.tw/tw/StockList.asp?STEP=DATA&MARKET_CAT=...&RANK=0&REINIT=xxx
```

回應為純 HTML fragment，包含 `<table id="tblStockList">` 與 `<select id="selRANK">`。

### 3. 分頁參數 RANK

每頁固定顯示 300 筆，透過 `RANK` 參數切換頁面。
分頁資訊藏在回應 HTML 的 `<select id="selRANK">` 下拉選單中：

```html
<select id="selRANK" onchange="ReloadStockList('...&RANK='+encodeURIComponent(selRANK.value))">
  <option value="0">1~300</option>
  <option value="1">301~600</option>
  <option value="2">601~900</option>
  ...
  <option value="7">2101~2295</option>
</select>
```

| `RANK` | 名次範圍 | 筆數 |
|--------|---------|------|
| 0 | 1 ~ 300 | 300 |
| 1 | 301 ~ 600 | 300 |
| 2 | 601 ~ 900 | 300 |
| 3 | 901 ~ 1200 | 300 |
| 4 | 1201 ~ 1500 | 300 |
| 5 | 1501 ~ 1800 | 300 |
| 6 | 1801 ~ 2100 | 300 |
| 7 | 2101 ~ 2295 | 195 |

---

## 全量取得流程

```
[Step 1] init_session()
         └─ GET StockList.asp?...&RANK_RANGE=300   ← 不帶 STEP=DATA，觸發驗證頁
              ├─ 從 HTML 擷取 REINIT 時間戳
              └─ 注入 CLIENT_KEY cookie

[Step 2] for RANK = 0, 1, 2 ... 7              ← 對應 selRANK 下拉的 option value
         │
         ├─ GET StockList.asp?STEP=DATA&RANK={N}&REINIT={ts}
         │   └─ 回傳 HTML fragment（含 tblStockList + selRANK）
         │
         ├─ parse_table()
         │   ├─ 找 <table id="tblStockList">
         │   ├─ 掃 <th> 行 → 建構欄位名稱（處理 colspan）
         │   └─ 掃 <td> 行 → 每行轉為 dict，append 到 all_rows
         │
         └─ sleep(3~5 秒)                        ← 隨機延遲，避免被封

[Step 3] pd.DataFrame(all_rows)
         └─ to_csv("stock_dividend_2025.csv", encoding="utf-8-sig")
```

**為什麼需要 RANK 迴圈？**
伺服器每次只回傳 300 筆，`RANK` 參數決定從哪個區段開始。
`RANK_LABELS` dict 為硬編碼對應表（由 `selRANK` 的 HTML options 推導），
迴圈跑完 8 次（RANK 0~7）後累積全部 2295 筆再一次寫入 CSV。

---

## 程式架構

```
main()
 ├── init_session()          # cookie 握手，取得 REINIT
 ├── for rank_idx in 0..7:
 │    ├── fetch_rank_page()  # 帶 STEP=DATA&RANK=N 的 AJAX 請求
 │    └── parse_table()      # 解析 tblStockList，建構 header + rows
 └── pd.DataFrame → CSV
```

### `init_session() → (Session, reinit)`

1. 送出不帶 `STEP=DATA` 的初始請求（觸發 cookie 驗證頁）
2. 從回應 HTML 用 regex 擷取 `REINIT` 時間戳
3. 手動計算並注入 `CLIENT_KEY` cookie

### `fetch_rank_page(session, reinit, rank_idx) → str`

- 帶 `STEP=DATA`、`RANK=rank_idx`、`REINIT=reinit` 送出 GET
- 每頁前隨機延遲 3.0 ~ 5.0 秒（避免觸發速率限制）

### `parse_table(html) → list[dict]`

- 找到 `<table id="tblStockList">`
- 掃描所有 `<th>` 行建構欄位名稱（處理多層 header + colspan）
- 掃描 `<td>` 行提取資料
- 去除空白行

---

## 開發過程記錄

### 問題一：第一次請求拿不到資料（1295 bytes 空頁）

**現象**：直接 `requests.get(URL)` 只得到 1295 bytes 的 HTML，內容只有 JS，沒有任何資料。

**原因**：Goodinfo 的防爬機制——第一次請求回傳「驗證頁」，該頁用 JS 設 `CLIENT_KEY` cookie 後重導向。由於 Python 不執行 JS，拿到的永遠是驗證頁。

**破解方式**：
- 分析驗證頁 JS，了解 `CLIENT_KEY` 的計算邏輯
- 從 `setTimeout` 的 `window.location.replace` 字串中 regex 擷取 `REINIT` 值
- 用 Python 複製相同的時間戳計算，手動呼叫 `session.cookies.set()`

---

### 問題二：每次只拿到 300 筆，分頁參數找不到

**現象**：成功取得資料後，每次請求固定只回傳 300 筆，`divPager` 不存在，`pg=2` 與 `RANK_RANGE=600` 都回傳相同的 rank 1~300。

**嘗試失敗的方法**：
| 嘗試 | 結果 |
|------|------|
| `?pg=2` | 回傳同一批 rank 1~300 |
| `RANK_RANGE=600` | caption 仍顯示 `名次範圍:1~300` |
| 搜尋 `divPager` | HTML 中不存在 |

**破解方式**：

解析 AJAX 回應 HTML 的 `<select id="selRANK">` 元素，其 `onchange` 屬性揭露真正的分頁參數：

```html
onchange="ReloadStockList('...&RANK='+encodeURIComponent(selRANK.value))"
```

`selRANK` 的 option value（0~7）就是分頁索引，對應 `RANK=0` 到 `RANK=7`。

**誤導點**：
- URL 上的 `RANK_RANGE=300` 是初始請求用的 hint，不是分頁控制
- `pg=` 是其他報表用的，Stock List 不用
- 分頁控制完全藏在 HTML fragment 的下拉選單 `onchange` 事件裡

---

### 問題三：`RPT_TIME` 切換年度無效，2024 與 2025 回傳相同資料

**現象**：將 `RPT_TIME` 從 `2025` 改為 `2024` 後，爬回的資料完全相同（欄位值一致，6219 富旺兩年均顯示現金股利 0.7、殖利率 5.57%）。

**原因**：`SHEET=股利政策發放年度_去年` 中的 `_去年` 後綴讓伺服器永遠回傳「最近一年」資料，忽略 `RPT_TIME` 的值。

**嘗試失敗的方法**：
| 嘗試 | 結果 |
|------|------|
| 僅修改 `RPT_TIME=2024` | 資料與 2025 完全相同 |
| `SHEET=股利政策發放年度` + `RPT_TIME=2025` | 回傳 10321 bytes（疑似不對的 INDUSTRY_CAT） |

**破解方式**：

保持 `INDUSTRY_CAT=股票股利 (僅顯示去年資料)@@股票股利@@僅顯示去年資料` 不變，將 `SHEET` 改為：

```
股利政策發放年度_去年  →  股利政策發放年度
```

確認：同樣是 6219 富旺，修正後 2024 年正確回傳現金股利 0、股票股利 0；2025 年回傳現金股利 0.7、股票股利 0.5，與網站手動選年一致。

**誤導點**：
- `INDUSTRY_CAT` 裡的「僅顯示去年資料」是分類路徑標籤，不影響年度篩選
- 真正鎖年度的是 `SHEET` 參數的 `_去年` 後綴，而非 `RPT_TIME`
- `RPT_TIME` 只有在 `SHEET` 不帶 `_去年` 時才實際生效

---

## 注意事項

- **請求間隔**：每頁隨機延遲 3~5 秒，避免對伺服器造成壓力
- **REINIT 時效**：`REINIT` 為當日時間戳，跨日重新執行需重新 init_session
- **年度切換**：透過 `--year <年份>` 指定年度（如 `--year 2024`），預設 2025。`SHEET` 必須用 `股利政策發放年度`（不帶 `_去年`），`RPT_TIME` 才會生效
- **編碼**：回應為 UTF-8，但 HTTP header 沒有 charset，需手動設定 `resp.encoding = 'utf-8'`；輸出 CSV 使用 `utf-8-sig`（帶 BOM），Excel 可直接正確開啟
