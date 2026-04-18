import argparse
import re
import time
import random
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urlencode

# selRANK options: RANK=0 → 1~300, RANK=1 → 301~600, ..., RANK=7 → 2101~2295
RANK_LABELS = {
    0: "1~300",
    1: "301~600",
    2: "601~900",
    3: "901~1200",
    4: "1201~1500",
    5: "1501~1800",
    6: "1801~2100",
    7: "2101~2295",
}

BASE_URL = "https://goodinfo.tw/tw/StockList.asp"
def make_common_params(year: str) -> dict:
    return {
        "SEARCH_WORD": "",
        "MARKET_CAT": "熱門排行",
        "INDUSTRY_CAT": "股票股利 (僅顯示去年資料)@@股票股利@@僅顯示去年資料",
        "SHEET": "股利政策發放年度",
        "SHEET2": "股利分派與除權/息價股利率",
        "RPT_TIME": year,
        "STOCK_CODE": "",
        "SORT_FIELD": "",
        "SORT": "",
    }

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
    "Referer": BASE_URL,
}

TZ_OFFSET = -480


def make_client_key() -> str:
    ts = time.time() * 1000 / 86400000 - TZ_OFFSET / 1440
    return f"2.3|43100.1033238637|46433.436657197|{TZ_OFFSET}|{ts}|{ts}"


def init_session(year: str = "2025") -> tuple[requests.Session, str]:
    session = requests.Session()
    session.headers.update(HEADERS)

    # Load main page to trigger cookie handshake and get REINIT
    init_params = make_common_params(year)
    init_params["RANK_RANGE"] = "300"
    r = session.get(BASE_URL + "?" + urlencode(init_params), timeout=30)
    r.encoding = "utf-8"

    m = re.search(r"REINIT=([0-9.]+)", r.text)
    reinit = m.group(1) if m else ""
    session.cookies.set("CLIENT_KEY", make_client_key(), domain="goodinfo.tw", path="/")
    return session, reinit


def fetch_rank_page(session: requests.Session, reinit: str, rank_idx: int, year: str = "2025") -> str:
    params = make_common_params(year)
    params["STEP"] = "DATA"
    params["RANK"] = str(rank_idx)
    if reinit:
        params["REINIT"] = reinit

    url = BASE_URL + "?" + urlencode(params)
    time.sleep(random.uniform(3.0, 5.0))
    r = session.get(url, timeout=30)
    r.encoding = "utf-8"
    r.raise_for_status()
    return r.text


def parse_table(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="tblStockList")
    if table is None:
        return []

    # Build headers from <th> rows
    col_texts: dict[int, list[str]] = {}
    data_rows = []
    parsing_headers = True

    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if not cells:
            continue

        if parsing_headers and any(c.name == "th" for c in cells):
            col = 0
            for cell in cells:
                colspan = int(cell.get("colspan", 1))
                text = cell.get_text(strip=True)
                for _ in range(colspan):
                    col_texts.setdefault(col, []).append(text)
                    col += 1
        else:
            parsing_headers = False
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            data_rows.append(tds)

    # Deduplicate header parts
    headers: list[str] = []
    for idx in sorted(col_texts):
        parts = col_texts[idx]
        unique: list[str] = []
        seen: set[str] = set()
        for p in parts:
            if p and p not in seen:
                unique.append(p)
                seen.add(p)
        headers.append(" ".join(unique) if unique else f"col{idx}")

    rows = []
    for tds in data_rows:
        row = {}
        for i, td in enumerate(tds):
            key = headers[i] if i < len(headers) else f"col{i}"
            row[key] = td.get_text(strip=True)
        if any(v for v in row.values()):
            rows.append(row)

    return rows


def detect_total_pages(session: requests.Session, reinit: str) -> int:
    """Check RANK=0 page to read selRANK options and determine total pages."""
    html = fetch_rank_page(session, reinit, 0)
    soup = BeautifulSoup(html, "lxml")
    sel = soup.find("select", id="selRANK")
    if sel:
        options = sel.find_all("option")
        return len(options)
    return len(RANK_LABELS)


def build_json(year: str) -> None:
    import os
    prev_year = str(int(year) - 1)
    csv_4digit = f"data/stock_dividend_{year}_4digit.csv"
    prev_csv   = f"data/stock_dividend_{prev_year}_4digit.csv"

    if not os.path.exists(csv_4digit):
        print(f"找不到 {csv_4digit}，請先執行爬蟲")
        return

    df = pd.read_csv(csv_4digit, encoding="utf-8-sig")

    # 排除當年未發股利
    df["合計股利"] = pd.to_numeric(df["合計股利"], errors="coerce").fillna(0)
    before = len(df)
    df = df[df["合計股利"] > 0].copy()
    print(f"排除 {year} 未發股利 {before - len(df)} 檔，剩 {len(df)} 筆")

    # 排除合計殖利率 < 1%
    df["除權息合計殖利率"] = pd.to_numeric(df["除權息合計殖利率"], errors="coerce").fillna(0)
    before = len(df)
    df = df[df["除權息合計殖利率"] >= 1].copy()
    print(f"排除合計殖利率 < 1% 共 {before - len(df)} 檔，剩 {len(df)} 筆")

    # 排除前一年未發股利
    if os.path.exists(prev_csv):
        df_prev = pd.read_csv(prev_csv, encoding="utf-8-sig")
        df_prev["合計股利"] = pd.to_numeric(df_prev["合計股利"], errors="coerce").fillna(0)
        no_div = set(df_prev[df_prev["合計股利"] == 0]["代號"].astype(str))
        df = df[~df["代號"].astype(str).isin(no_div)].copy()
        print(f"排除 {prev_year} 未發股利 {len(no_div)} 檔，剩 {len(df)} 筆")
    else:
        print(f"找不到 {prev_csv}，不過濾前年資料")

    num_cols = [
        "成交", "漲跌價", "漲跌幅",
        "現金股利", "股票股利", "合計股利",
        "除息價", "除息價現金殖利率",
        "除權價", "除權價股票殖利率", "除權息合計殖利率",
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 依殖利率降冪重排，排名重設為 1..N
    df = df.sort_values("除權息合計殖利率", ascending=False).reset_index(drop=True)
    df["排名"] = df.index + 1

    out_json = "data/index.json"
    df.to_json(out_json, orient="records", force_ascii=False)
    print(f"JSON {len(df)} 筆，已存至 {out_json}")


def main():
    parser = argparse.ArgumentParser(description="爬取 Goodinfo 股票股利資料")
    parser.add_argument("--year", default="2025", help="資料年度，例如 2024 或 2025")
    parser.add_argument("--json-only", action="store_true", help="只從現有 CSV 產生 JSON，不爬網站")
    args = parser.parse_args()
    year = args.year

    if args.json_only:
        build_json(year)
        return

    print(f"初始化 session（年度：{year}）...")
    session, reinit = init_session(year)
    print(f"REINIT: {reinit}")

    all_rows: list[dict] = []

    for rank_idx, label in RANK_LABELS.items():
        print(f"取得排名 {label}（RANK={rank_idx}）...")
        html = fetch_rank_page(session, reinit, rank_idx, year)
        rows = parse_table(html)
        print(f"  取得 {len(rows)} 筆")
        all_rows.extend(rows)

        if len(rows) == 0:
            print("  (無資料，停止)")
            break

    if not all_rows:
        print("未取得任何資料")
        return

    import os
    os.makedirs("data", exist_ok=True)

    df = pd.DataFrame(all_rows)
    out_all = f"data/stock_dividend_{year}.csv"
    out_4digit = f"data/stock_dividend_{year}_4digit.csv"

    df.to_csv(out_all, index=False, encoding="utf-8-sig")
    print(f"\n完成！共 {len(df)} 筆，已存至 {out_all}")

    df_4digit = df[df["代號"].astype(str).str.match(r"^\d{4}$")].copy()
    df_4digit.to_csv(out_4digit, index=False, encoding="utf-8-sig")
    print(f"四碼股票 {len(df_4digit)} 筆，已存至 {out_4digit}")

    # JSON：排除前一年未發股利的股票
    prev_year = str(int(year) - 1)
    prev_csv = f"data/stock_dividend_{prev_year}_4digit.csv"
    df_json = df_4digit.copy()
    if os.path.exists(prev_csv):
        df_prev = pd.read_csv(prev_csv, encoding="utf-8-sig")
        df_prev["合計股利"] = pd.to_numeric(df_prev["合計股利"], errors="coerce").fillna(0)
        no_div = set(df_prev[df_prev["合計股利"] == 0]["代號"].astype(str))
        df_json = df_json[~df_json["代號"].astype(str).isin(no_div)]
        print(f"排除 {prev_year} 未發股利 {len(no_div)} 檔，剩 {len(df_json)} 筆")

    num_cols = [
        "排名", "成交", "漲跌價", "漲跌幅",
        "現金股利", "股票股利", "合計股利",
        "除息價", "除息價現金殖利率",
        "除權價", "除權價股票殖利率", "除權息合計殖利率",
    ]
    for col in num_cols:
        if col in df_json.columns:
            df_json[col] = pd.to_numeric(df_json[col], errors="coerce")

    out_json = "data/index.json"
    df_json.to_json(out_json, orient="records", force_ascii=False)
    print(f"JSON {len(df_json)} 筆，已存至 {out_json}")


if __name__ == "__main__":
    main()
