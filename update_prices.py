# 更新報價的備援：每週從 TPEX（上櫃）與 TWSE（上市）Open API 抓取收盤價，
# 反查 index.json 的股票代號並更新成交價與股價日期，
# 供前端在 TPEX API 失敗時使用 index.json 作為靜態備援資料源。
#
# 本地測試 API 失敗情境：
#   Chrome DevTools → Network tab → 右鍵 TWSE/TPEX 請求(/openapi/v1/tpex_mainboard_quotes) → Block request URL
#   再按「更新報價」，表格維持顯示 index.json 的成交值（備援生效）
import json
import sys
import requests
from datetime import datetime, timezone, timedelta

TW_TZ = timezone(timedelta(hours=8))
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def roc_date_to_mmdd(roc_date: str) -> str:
    """'1150420' → '04/20'"""
    return f"{roc_date[3:5]}/{roc_date[5:7]}"


def fetch_json(url: str) -> list[dict]:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def build_price_map(tpex_data: list[dict], twse_data: list[dict]) -> tuple[dict[str, float], str]:
    price_map: dict[str, float] = {}
    price_date = ""

    for item in tpex_data:
        code = item.get("SecuritiesCompanyCode", "").strip()
        close = item.get("Close", "").strip()
        if code and close and close not in ("--", ""):
            try:
                price_map[code] = float(close)
            except ValueError:
                pass
        if not price_date and item.get("Date"):
            price_date = roc_date_to_mmdd(item["Date"])

    for item in twse_data:
        code = item.get("Code", "").strip()
        close = item.get("ClosingPrice", "").strip()
        if code and close and close not in ("--", ""):
            try:
                price_map[code] = float(close)
            except ValueError:
                pass
        if not price_date and item.get("Date"):
            price_date = roc_date_to_mmdd(item["Date"])

    return price_map, price_date


def update_index_json(price_map: dict[str, float], price_date: str) -> int:
    with open("data/index.json", "rb") as f:
        stocks: list[dict] = json.loads(f.read().decode("utf-8"))

    updated = 0
    for stock in stocks:
        code = str(stock.get("代號", "")).strip()
        if code in price_map:
            stock["成交"] = price_map[code]
            stock["股價日期"] = price_date
            updated += 1

    with open("data/index.json", "w", encoding="utf-8") as f:
        json.dump(stocks, f, ensure_ascii=False, separators=(",", ":"))

    return updated


def main() -> None:
    now_tw = datetime.now(TW_TZ)
    print(f"Taiwan time: {now_tw.strftime('%Y-%m-%d %H:%M:%S')}")

    print("Fetching TPEX quotes (上櫃)...")
    try:
        tpex_data = fetch_json(TPEX_URL)
        print(f"  TPEX: {len(tpex_data)} records")
    except Exception as e:
        print(f"TPEX API error: {e}", file=sys.stderr)
        tpex_data = []

    print("Fetching TWSE quotes (上市)...")
    try:
        twse_data = fetch_json(TWSE_URL)
        print(f"  TWSE: {len(twse_data)} records")
    except Exception as e:
        print(f"TWSE API error: {e}", file=sys.stderr)
        twse_data = []

    if not tpex_data and not twse_data:
        print("Both APIs failed", file=sys.stderr)
        sys.exit(1)

    price_map, price_date = build_price_map(tpex_data, twse_data)
    print(f"Price date: {price_date}, total stocks with price: {len(price_map)}")

    updated = update_index_json(price_map, price_date)
    print(f"Updated {updated} stocks in index.json")

    if updated == 0:
        print("Warning: no stocks matched", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
