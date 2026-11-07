"""從零股屋（stockroomtw.com）首頁的「預計發放的紀念品」表抓股東會紀念品，
輸出 data/stock_gifts_<year>.tsv（欄位：股號、股名、年份、紀念品），供 fetch_stock_dividend.py join。
"""
import argparse
import os
import requests
from bs4 import BeautifulSoup
import pandas as pd

URL = "https://www.stockroomtw.com/"


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取股東會紀念品清單")
    parser.add_argument("--year", default="2026", help="寫入「年份」欄與輸出檔名的年度")
    args = parser.parse_args()

    r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    r.raise_for_status()
    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "lxml")

    # 紀念品表是表頭含「預計發放的」且有資料列的那一張
    table = max(
        (t for t in soup.find_all("table") if "預計發放的" in t.get_text()),
        key=lambda t: len(t.find_all("tr")),
    )

    rows = []
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all(["th", "td"])
        if len(cells) < 4:
            continue
        code = cells[0].get_text(strip=True)
        name = cells[1].get_text(" ", strip=True)
        gift = cells[3].get_text(" ", strip=True)
        if not code or not gift:
            continue
        name = name.replace(" 臨時會", "(臨)")
        rows.append({"股號": code, "股名": name, "年份": args.year, "紀念品": gift})

    df = pd.DataFrame(rows)
    # 「(不開)」= 股東會不開 / 不發，不算有紀念品
    skipped = df["紀念品"].str.startswith("(不開)")
    df = df[~skipped]

    os.makedirs("data", exist_ok=True)
    out = f"data/stock_gifts_{args.year}.tsv"
    df.to_csv(out, sep="\t", index=False, encoding="utf-8")
    print(f"共 {len(df)} 筆（排除「不開」{int(skipped.sum())} 筆），已存至 {out}")


if __name__ == "__main__":
    main()
