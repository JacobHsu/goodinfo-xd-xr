"""決策節點打分的共用規則（純 Python，無第三方套件）。

fetch_stock_dividend.py（產生 JSON 時算全部節點）與 update_prices.py（GitHub Actions 每週更新股價後，
只重算受股價影響的「殖利率」「紀念品」節點與總分）共用這裡的權重與分級，確保兩邊結果一致。
詳見 README「排名依據」。
"""
import re

# 決策節點權重（目標：穩健存股）
NODE_WEIGHTS = {
    "殖利率": 0.30,
    "配息安全": 0.20,
    "本業穩定": 0.15,
    "獲利能力": 0.10,
    "財報體質": 0.10,
    "股利不衰退": 0.10,
    "紀念品": 0.05,
}

LEVELS = [0, 1 / 3, 2 / 3, 1]  # Score 題 4 級 rubric 正規化為 0~1
MISSING = 0.5                  # 缺資料的節點分數


def interp(x, xs, ys=LEVELS):
    """分段線性內插（超出範圍取端點值）；x 為 None 時回傳 None。"""
    if x is None:
        return None
    if x <= xs[0]:
        return ys[0]
    for (x0, y0), (x1, y1) in zip(zip(xs, ys), zip(xs[1:], ys[1:])):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return ys[-1]


def _num(v):
    """轉 float；None / NaN / 無法轉換 → None。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def gift_value(text) -> float:
    """紀念品文字 → 估計價值（元）：取「NN元」最大值；其他實物記 30 元；無紀念品 = 0。"""
    if not isinstance(text, str) or not text.strip():
        return 0.0
    nums = [int(n) for n in re.findall(r"(\d+)\s*元", text)]
    return float(max(nums)) if nums else 30.0


SPLIT_RATIO = 0.5  # 現價 < 除息（權）價 × 此比例 → 視為可能股票分割 / 面額變更


def current_yield(stock: dict):
    """現價殖利率(%) = 合計股利 ÷ 現在股價。

    若現價跌破除息（權）價的一半，多半是分割或面額變更（股利仍為分割前金額，會嚴重高估，
    例如寶雅 677 → 74），此時退回使用 Goodinfo 的除權息合計殖利率。
    """
    d, p = _num(stock.get("合計股利")), _num(stock.get("成交"))
    if d is None or not p or p <= 0:
        return _num(stock.get("除權息合計殖利率"))
    base = _num(stock.get("除息價")) or _num(stock.get("除權價"))
    if base and p < base * SPLIT_RATIO:
        return _num(stock.get("除權息合計殖利率"))
    return round(d / p * 100, 2)


def yield_score(cur_yield) -> float:
    s = interp(_num(cur_yield), [2, 4, 6, 8])
    return MISSING if s is None else round(s, 2)


def gift_score(text, price) -> float:
    p = _num(price)
    if not p or p <= 0:
        return MISSING
    return round(interp(gift_value(text) / p, [0, 0.5, 1, 2]), 2)


def total_score(stock: dict) -> float:
    """依各 `分_<節點>` 加權成 0~100 總分。"""
    total = 0.0
    for name, weight in NODE_WEIGHTS.items():
        s = _num(stock.get(f"分_{name}"))
        total += weight * (MISSING if s is None else s)
    return round(total * 100, 1)


def rescore_price_nodes(stock: dict) -> None:
    """股價變動後，就地更新 現價殖利率、分_殖利率、分_紀念品、總分。"""
    stock["現價殖利率"] = current_yield(stock)
    stock["分_殖利率"] = yield_score(stock["現價殖利率"])
    stock["分_紀念品"] = gift_score(stock.get("紀念品"), stock.get("成交"))
    stock["總分"] = total_score(stock)


def rerank(stocks: list[dict]) -> None:
    """依總分降冪排序並重編排名 1..N（就地）。"""
    stocks.sort(key=lambda s: _num(s.get("總分")) or 0, reverse=True)
    for i, s in enumerate(stocks, 1):
        s["排名"] = i
