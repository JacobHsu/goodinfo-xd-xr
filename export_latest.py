"""產生 data/latest.json：最新年度過濾好的股票名單（精簡欄位），供外部以固定網址取用。

https://jacobhsu.github.io/goodinfo-xd-xr/data/latest.json
由 fetch_stock_dividend.py（--json-only）與 update_prices.py（每週）在更新後呼叫。純 Python，無第三方套件。
"""
import json
from datetime import datetime, timezone, timedelta

# index_<year>.json 欄位 → 對外 API 欄位（英文 key，方便其他系統串接）
FIELDS = {
    "排名": "rank",
    "代號": "code",
    "名稱": "name",
    "總分": "score",
    "成交": "price",
    "現價殖利率": "yield",
    "現金股利": "cash_div",
    "股票股利": "stock_div",
    "合計股利": "total_div",
    "股利發放頻率": "freq",
    "除息交易日": "ex_div_date",
    "紀念品": "gift",
}
FREQ = {"年": "annual", "半年": "semiannual", "季": "quarterly"}


def _iso_date(v):
    """Goodinfo 的 "'26/09/21" → "2026-09-21"；空值 → None。"""
    if not v:
        return None
    yy, mm, dd = str(v).lstrip("'").split("/")
    return f"20{yy}-{mm}-{dd}"


def _to_api(s: dict) -> dict:
    out = {api: s.get(src) for src, api in FIELDS.items()}
    out["freq"] = FREQ.get(out["freq"], out["freq"])
    out["ex_div_date"] = _iso_date(out["ex_div_date"])
    return out


def write_latest() -> str:
    with open("data/years.json", encoding="utf-8") as f:
        year = max(json.load(f), key=int)
    with open(f"data/index_{year}.json", encoding="utf-8") as f:
        stocks = json.load(f)

    today = datetime.now(timezone(timedelta(hours=8)))
    # 股價日期只有 "MM/DD"：補上年份（月份大於本月代表是去年，例如 1 月初更新時拿到 12/31 的價格）
    price_date = None
    mmdd = next((s["股價日期"] for s in stocks if s.get("股價日期")), "")
    if mmdd:
        mm, dd = mmdd.split("/")
        y = today.year - 1 if int(mm) > today.month else today.year
        price_date = f"{y}-{mm}-{dd}"
    out = {
        "year": str(year),
        "updated": today.strftime("%Y-%m-%d"),
        "price_date": price_date,
        "count": len(stocks),
        "stocks": [_to_api(s) for s in stocks],
    }
    path = "data/latest.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    return path


if __name__ == "__main__":
    print(f"已存至 {write_latest()}")
