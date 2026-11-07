import argparse
import json
import os
import re
import time
import random
from bs4 import BeautifulSoup
from curl_cffi import requests as cf_requests
import pandas as pd
from urllib.parse import urlencode

import scoring

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

def _chrome_major_version() -> int | None:
    """從 Windows registry 讀本機 Chrome 主版本；讀不到就回傳 None（交給 uc 自行判斷）。"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon") as key:
            return int(winreg.QueryValueEx(key, "version")[0].split(".")[0])
    except Exception:
        return None


def solve_cloudflare(year: str, timeout: int = 180) -> tuple[dict, str, str]:
    """開一個有畫面的 Chrome（undetected_chromedriver）通過 Cloudflare JS 驗證，
    取得 cf_clearance 等 cookie，並回傳驗證頁本身的 HTML（即 RANK=0 那一頁）。

    若跳出需要手動點擊的驗證方塊，視窗會保持開啟，請直接在畫面上完成即可，
    腳本會持續等待直到 timeout 秒。
    """
    params = make_common_params(year)
    params["RANK_RANGE"] = "300"
    return solve_cloudflare_url(BASE_URL + "?" + urlencode(params), timeout)


def solve_cloudflare_url(url: str, timeout: int = 180) -> tuple[dict, str, str]:
    """solve_cloudflare 的通用版：對任意 Goodinfo StockList 網址通過驗證，回傳 (cookies, user_agent, html)。"""
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    opts = uc.ChromeOptions()
    opts.add_argument("--lang=zh-TW")
    # uc 預設下載最新版 chromedriver；本機 Chrome 尚未更新時會版本不合，故指定本機主版本
    driver = uc.Chrome(options=opts, headless=False, version_main=_chrome_major_version())
    try:
        driver.get(url)
        print("等待 Cloudflare 驗證通過...（若跳出驗證方塊，請於視窗中手動完成）")
        WebDriverWait(driver, timeout).until(
            lambda d: "稍候" not in d.title and "Just a moment" not in d.title
        )
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.ID, "tblStockList")))
        html = driver.page_source
        user_agent = driver.execute_script("return navigator.userAgent")
        cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
        return cookies, user_agent, html
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def init_session(cookies: dict, user_agent: str) -> cf_requests.Session:
    """用驗證頁取得的 cookie + User-Agent 建立 session，供後續分頁請求重複使用。"""
    session = cf_requests.Session(impersonate="chrome")
    session.headers.update(HEADERS)
    session.headers["User-Agent"] = user_agent
    session.cookies.update(cookies)
    return session


def fetch_rank_page(session: cf_requests.Session, rank_idx: int, year: str = "2025") -> str:
    params = make_common_params(year)
    params["STEP"] = "DATA"
    params["RANK"] = str(rank_idx)

    url = BASE_URL + "?" + urlencode(params)
    time.sleep(random.uniform(3.0, 5.0))
    r = session.get(url, timeout=30)
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


def detect_total_pages(session: cf_requests.Session, year: str = "2025") -> int:
    """Check RANK=0 page to read selRANK options and determine total pages."""
    html = fetch_rank_page(session, 0, year)
    soup = BeautifulSoup(html, "lxml")
    sel = soup.find("select", id="selRANK")
    if sel:
        options = sel.find_all("option")
        return len(options)
    return len(RANK_LABELS)


def update_years_manifest(year: str) -> list[str]:
    """更新 data/years.json，記錄目前有哪些年度的 index_<year>.json 可供網頁切換。"""
    years_file = "data/years.json"
    years: list[str] = []
    if os.path.exists(years_file):
        try:
            years = json.load(open(years_file, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            years = []
    years_sorted = sorted({str(y) for y in years} | {str(year)}, key=int, reverse=True)
    with open(years_file, "w", encoding="utf-8") as fp:
        json.dump(years_sorted, fp, ensure_ascii=False)
    return years_sorted


def score_nodes(df: pd.DataFrame) -> pd.DataFrame:
    """每個節點輸出 0~1 分數（缺值 0.5），加權成 0~100 的總分。規則與權重見 scoring.py。

    Score 題：有序 rubric，落在錨點之間線性內插（= 期望等級 / (N-1)）。
    Noul 題：是/否條件的 0~1 分數。
    """
    def node(values, anchors=None, levels=scoring.LEVELS):
        v = pd.to_numeric(values, errors="coerce")
        if anchors is not None:
            v = v.map(lambda x: scoring.interp(None if pd.isna(x) else x, anchors, levels))
        return pd.to_numeric(v, errors="coerce").fillna(scoring.MISSING).round(2)

    nan = pd.Series(float("nan"), index=df.index)
    df["分_配息安全"] = node(df["合計股利"] / df["EPS"].where(df["EPS"] > 0), [0.8, 1.0, 1.5], [1, 0.5, 0])
    df["分_本業穩定"] = node(df["_本業穩定"] if "_本業穩定" in df else nan)
    df["分_獲利能力"] = node(df["ROE(%)"], [5, 10, 15, 20])
    df["分_財報體質"] = node(df["財報評分"], [40, 50, 60, 70])
    df["分_股利不衰退"] = node((df["合計股利"] / df["_前年股利"].where(df["_前年股利"] > 0)).clip(upper=1)
                            if "_前年股利" in df else nan)

    # 受股價影響的節點（現價殖利率、紀念品）與總分：與 update_prices.py 共用同一函式
    records = df.to_dict("records")
    for r in records:
        scoring.rescore_price_nodes(r)
    for col in ["現價殖利率", "分_殖利率", "分_紀念品", "總分"]:
        df[col] = [r[col] for r in records]
    return df


def build_json(year: str) -> None:
    prev_year = str(int(year) - 1)
    csv_4digit = f"data/stock_dividend_{year}_4digit.csv"
    prev_csv   = f"data/stock_dividend_{prev_year}_4digit.csv"

    if not os.path.exists(csv_4digit):
        print(f"找不到 {csv_4digit}，請先執行爬蟲")
        return

    df = pd.read_csv(csv_4digit, encoding="utf-8-sig")
    dr_count = df["名稱"].str.contains(r"-DR", na=False).sum()
    df = df[~df["名稱"].str.contains(r"-DR", na=False)].copy()
    print(f"排除 DR 存託憑證 {dr_count} 筆，剩 {len(df)} 筆")

    # 排除當年未發股利
    df["合計股利"] = pd.to_numeric(df["合計股利"], errors="coerce").fillna(0)
    before = len(df)
    df = df[df["合計股利"] > 0].copy()
    print(f"排除 {year} 未發股利 {before - len(df)} 檔，剩 {len(df)} 筆")

    # 排除現價殖利率 < 1%（規則見 scoring.current_yield）
    df["除權息合計殖利率"] = pd.to_numeric(df["除權息合計殖利率"], errors="coerce").fillna(0)
    cur_yield = pd.Series([scoring.current_yield(r) for r in df.to_dict("records")], index=df.index, dtype=float).fillna(0)
    before = len(df)
    df = df[cur_yield >= 1].copy()
    print(f"排除現價殖利率 < 1% 共 {before - len(df)} 檔，剩 {len(df)} 筆")

    # 排除前一年未發股利
    if os.path.exists(prev_csv):
        df_prev = pd.read_csv(prev_csv, encoding="utf-8-sig")
        df_prev["合計股利"] = pd.to_numeric(df_prev["合計股利"], errors="coerce").fillna(0)
        no_div = set(df_prev[df_prev["合計股利"] == 0]["代號"].astype(str))
        df = df[~df["代號"].astype(str).isin(no_div)].copy()
        print(f"排除 {prev_year} 未發股利 {len(no_div)} 檔，剩 {len(df)} 筆")
        # 股利不衰退節點用：前一年合計股利
        prev_div = df_prev.assign(代號=df_prev["代號"].astype(str)).drop_duplicates("代號").set_index("代號")["合計股利"]
        df["_前年股利"] = df["代號"].astype(str).map(prev_div)
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

    df["代號"] = df["代號"].astype(str)

    # Join ROE 與財報評分
    roe_csv = "data/stock_roe.csv"
    if os.path.exists(roe_csv):
        df_roe = pd.read_csv(roe_csv, encoding="utf-8-sig")[["代號", "ROE(%)", "財報評分"]]
        df_roe["代號"] = df_roe["代號"].astype(str)
        df_roe["ROE(%)"] = pd.to_numeric(df_roe["ROE(%)"], errors="coerce")
        df_roe["財報評分"] = pd.to_numeric(df_roe["財報評分"], errors="coerce")
        df = df.merge(df_roe, on="代號", how="left")
        print(f"Join ROE：{df['ROE(%)'].notna().sum()}/{len(df)} 筆有資料")
    else:
        print(f"找不到 {roe_csv}，跳過 ROE join")

    # Join EPS
    eps_csv = "data/stock_eps.csv"
    if os.path.exists(eps_csv):
        df_eps = pd.read_csv(eps_csv, encoding="utf-8-sig")[["代號", "EPS(元)"]]
        df_eps["代號"] = df_eps["代號"].astype(str)
        df_eps = df_eps.rename(columns={"EPS(元)": "EPS"})
        df_eps["EPS"] = pd.to_numeric(df_eps["EPS"], errors="coerce")
        df = df.merge(df_eps, on="代號", how="left")
        print(f"Join EPS：{df['EPS'].notna().sum()}/{len(df)} 筆有資料")
    else:
        print(f"找不到 {eps_csv}，跳過 EPS join")

    # Join OI（平均營業利益）
    oi_csv = "data/stock_operating_profit.csv"
    if os.path.exists(oi_csv):
        df_oi = pd.read_csv(oi_csv, encoding="utf-8-sig")[["代號", "平均營益(億)"]]
        df_oi["代號"] = df_oi["代號"].astype(str)
        df_oi = df_oi.rename(columns={"平均營益(億)": "OI(億)"})
        df_oi["OI(億)"] = pd.to_numeric(df_oi["OI(億)"], errors="coerce")
        # 本業穩定節點：各季營益中 > 0 的比例（只取比例，不把季欄寫進 JSON）
        df_q = pd.read_csv(oi_csv, encoding="utf-8-sig")
        q_cols = [c for c in df_q.columns if re.fullmatch(r"\d\dQ\d營益\(億\)", c)]
        q = df_q[q_cols].apply(lambda s: pd.to_numeric(s.astype(str).str.replace(",", ""), errors="coerce"))
        df_oi["_本業穩定"] = (q > 0).sum(axis=1) / q.notna().sum(axis=1).replace(0, float("nan"))
        df = df.merge(df_oi, on="代號", how="left")
        print(f"Join OI：{df['OI(億)'].notna().sum()}/{len(df)} 筆有資料")
    else:
        print(f"找不到 {oi_csv}，跳過 OI join")

    # Join 紀念品
    gifts_tsv = f"data/stock_gifts_{year}.tsv"
    if os.path.exists(gifts_tsv):
        df_gifts = pd.read_csv(gifts_tsv, encoding="utf-8", sep="\t", on_bad_lines="skip")[["股號", "紀念品"]]
        df_gifts = df_gifts.rename(columns={"股號": "代號"})
        df_gifts["代號"] = df_gifts["代號"].astype(str)
        df_gifts = df_gifts.groupby("代號")["紀念品"].apply(lambda x: "、".join(x.dropna().unique())).reset_index()
        df = df.merge(df_gifts, on="代號", how="left")
        print(f"Join 紀念品：{df['紀念品'].notna().sum()}/{len(df)} 筆有資料")
    else:
        print(f"找不到 {gifts_tsv}，跳過紀念品 join")

    # 排除 EPS 或 ROE 為負值
    before = len(df)
    df = df[~((df["EPS"] < 0) | (df["ROE(%)"] < 0))].copy()
    print(f"排除 EPS/ROE 負值 {before - len(df)} 檔，剩 {len(df)} 筆")

    # 排除 OI 為負值（本業虧損，股利不可持續）
    if "OI(億)" in df.columns:
        before = len(df)
        df = df[~(df["OI(億)"] < 0)].copy()
        print(f"排除 OI 負值 {before - len(df)} 檔，剩 {len(df)} 筆")

    # 決策節點打分（Jev System One 概念），依總分降冪重排，排名重設為 1..N
    df = score_nodes(df)
    df = df.drop(columns=[c for c in df.columns if c.startswith("_")])
    df = df.sort_values("總分", ascending=False).reset_index(drop=True)
    df["排名"] = df.index + 1
    show = ["排名", "代號", "名稱", "現價殖利率", "總分"] + [f"分_{n}" for n in scoring.NODE_WEIGHTS]
    print("\n前 20 名：")
    print(df[show].head(20).to_string(index=False))
    print()

    out_json = f"data/index_{year}.json"
    df.to_json(out_json, orient="records", force_ascii=False)
    print(f"JSON {len(df)} 筆，已存至 {out_json}")
    update_years_manifest(year)


def main():
    parser = argparse.ArgumentParser(description="爬取 Goodinfo 股票股利資料")
    parser.add_argument("--year", default="2025", help="資料年度，例如 2024 或 2025")
    parser.add_argument("--json-only", action="store_true", help="只從現有 CSV 產生 JSON，不爬網站")
    args = parser.parse_args()
    year = args.year

    if args.json_only:
        build_json(year)
        return

    print(f"啟動瀏覽器並通過 Cloudflare 驗證（年度：{year}）...")
    cookies, user_agent, first_html = solve_cloudflare(year)
    print("驗證通過，建立 session...")
    session = init_session(cookies, user_agent)

    all_rows: list[dict] = []

    first_rows = parse_table(first_html)
    print(f"取得排名 {RANK_LABELS[0]}（RANK=0，隨驗證頁一併取得）...")
    print(f"  取得 {len(first_rows)} 筆")
    all_rows.extend(first_rows)

    for rank_idx in range(1, len(RANK_LABELS)):
        label = RANK_LABELS[rank_idx]
        print(f"取得排名 {label}（RANK={rank_idx}）...")
        html = fetch_rank_page(session, rank_idx, year)
        rows = parse_table(html)
        print(f"  取得 {len(rows)} 筆")
        all_rows.extend(rows)

        if len(rows) == 0:
            print("  (無資料，停止)")
            break

    if not all_rows:
        print("未取得任何資料")
        return

    os.makedirs("data", exist_ok=True)

    df = pd.DataFrame(all_rows)
    out_all = f"data/stock_dividend_{year}.csv"
    out_4digit = f"data/stock_dividend_{year}_4digit.csv"

    df.to_csv(out_all, index=False, encoding="utf-8-sig")
    print(f"\n完成！共 {len(df)} 筆，已存至 {out_all}")

    df_4digit = df[df["代號"].astype(str).str.match(r"^\d{4}$")].copy()
    df_4digit = df_4digit[~df_4digit["名稱"].str.contains(r"-DR", na=False)].copy()
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

    out_json = f"data/index_{year}.json"
    df_json.to_json(out_json, orient="records", force_ascii=False)
    print(f"JSON {len(df_json)} 筆，已存至 {out_json}")
    update_years_manifest(year)


if __name__ == "__main__":
    main()
