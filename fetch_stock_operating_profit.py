import os
import re
import time
import random
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urlencode

BASE_URL = "https://goodinfo.tw/tw/StockList.asp"

COMMON_PARAMS = {
    "SEARCH_WORD": "",
    "MARKET_CAT": "熱門排行",
    "INDUSTRY_CAT": "單季營業利益最低@@營業利益@@單季營業利益最低",
    "RPT_TIME": "",
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


def init_session() -> tuple[requests.Session, str]:
    session = requests.Session()
    session.headers.update(HEADERS)

    params = {**COMMON_PARAMS, "RANK_RANGE": "300"}
    r = session.get(BASE_URL + "?" + urlencode(params), timeout=30)
    r.encoding = "utf-8"

    m = re.search(r"REINIT=([0-9.]+)", r.text)
    reinit = m.group(1) if m else ""
    session.cookies.set("CLIENT_KEY", make_client_key(), domain="goodinfo.tw", path="/")
    return session, reinit


def count_pages(session: requests.Session, reinit: str) -> int:
    params = {**COMMON_PARAMS, "STEP": "DATA", "RANK": "0"}
    if reinit:
        params["REINIT"] = reinit
    r = session.get(BASE_URL + "?" + urlencode(params), timeout=30)
    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "lxml")
    sel = soup.find("select", id="selRANK")
    if sel:
        return len(sel.find_all("option"))
    return 1


def fetch_page(session: requests.Session, reinit: str, rank_idx: int) -> str:
    params = {**COMMON_PARAMS, "STEP": "DATA", "RANK": str(rank_idx)}
    if reinit:
        params["REINIT"] = reinit
    time.sleep(random.uniform(3.0, 5.0))
    r = session.get(BASE_URL + "?" + urlencode(params), timeout=30)
    r.encoding = "utf-8"
    r.raise_for_status()
    return r.text


def parse_table(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="tblStockList")
    if table is None:
        return []

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


def report(df: pd.DataFrame) -> None:
    avg_col = next((c for c in df.columns if c.startswith("平均營益")), None)
    quarter_cols = [c for c in df.columns if "營益" in c and not c.startswith("平均")]

    if not avg_col and not quarter_cols:
        print(f"找不到營益欄位，現有欄位：{list(df.columns)}")
        return

    for col in ([avg_col] if avg_col else []) + quarter_cols:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce")

    if not avg_col and quarter_cols:
        df["平均營益(億)"] = df[quarter_cols].mean(axis=1)
        avg_col = "平均營益(億)"

    df4 = df[df["代號"].astype(str).str.match(r"^\d{4}$")].copy()
    df4 = df4[~df4["名稱"].str.contains(r"-DR", na=False)]

    overall_avg = df4[avg_col].mean()
    print(f"\n全體四碼股票{avg_col}：{overall_avg:,.2f} 億")
    print(f"樣本數：{df4[avg_col].notna().sum()} 檔\n")

    show_cols = ["代號", "名稱"] + quarter_cols + [avg_col]
    show_cols = [c for c in show_cols if c in df4.columns]
    print(df4[show_cols].sort_values(avg_col).to_string(index=False))

    out_csv = "data/stock_operating_profit.csv"
    df4.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"\n已存至 {out_csv}")


def main() -> None:
    os.makedirs("data", exist_ok=True)

    print("初始化 session...")
    session, reinit = init_session()
    print(f"REINIT: {reinit}")

    total_pages = count_pages(session, reinit)
    print(f"共 {total_pages} 頁")

    all_rows: list[dict] = []
    for rank_idx in range(total_pages):
        print(f"取得第 {rank_idx + 1}/{total_pages} 頁（RANK={rank_idx}）...")
        html = fetch_page(session, reinit, rank_idx)
        rows = parse_table(html)
        print(f"  取得 {len(rows)} 筆")
        if not rows:
            print("  (無資料，停止)")
            break
        all_rows.extend(rows)

    if not all_rows:
        print("未取得任何資料")
        return

    df = pd.DataFrame(all_rows)
    print(f"\n欄位：{list(df.columns)}")

    report(df)


if __name__ == "__main__":
    main()
