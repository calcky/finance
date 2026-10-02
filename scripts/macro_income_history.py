"""Historical national household-income releases discovered via NBS public search."""

from datetime import date
import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from macro_common import add, fetch
from macro_nbs_history import collect_income_api

SEARCH = "https://api.so-gov.cn/query/s"


def search(query, *, start=None, end=None, title_only=True):
    """The public search form linked by stats.gov.cn; exhaust its pagination."""
    page, total, seen = 1, None, set()
    while total is None or page <= (total + 19) // 20:
        params = dict(siteCode="bm36000002", qt=query, adv=1, keyPlace=int(title_only),
                      sort="dateDesc", page=page, pageSize=20)
        if start and end:
            params.update(timeOption=2, startDateStr=start, endDateStr=end)
        payload = json.loads(fetch(SEARCH, form=params))
        if payload.get("ok") is not True:
            raise ValueError("NBS public search failed")
        documents = payload["resultDocs"]
        total = payload["totalHits"]
        if not documents and total:
            raise ValueError("Incomplete NBS search pagination")
        for entry in documents:
            if entry["id"] in seen:
                raise ValueError("NBS search repeated a page")
            seen.add(entry["id"])
            item = entry["data"]
            if urlparse(item["url"]).hostname == "www.stats.gov.cn":
                yield dict(url=item["url"].replace("http://", "https://", 1),
                           title=item["titleO"], published=item["docDate"])
        page += 1


def parse_release(html, item):
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one(".txt-content") or soup.select_one(".TRS_Editor")
    if body is None:
        raise ValueError("Income release body not found")
    text = re.sub(r"\s+", "", body.get_text()).replace("％", "%").replace(",", "，")
    title, published = item["title"], item["published"]
    match = re.search(r"(20\d{2})年", title)
    year = int(match[1]) if match else int(published[:4])
    if "一季度" in title:
        quarter = 1
    elif "上半年" in title:
        quarter = 2
    elif "前三季度" in title:
        quarter = 3
    elif match and ("年居民收入" in title or "年全国居民收入" in title or "国民经济" in title):
        quarter = 4
    else:
        return []  # Not a clearly identified reporting period, never infer from numbers.
    # Explicit national amount + nominal + real growth in the same sentence.
    pattern = (r"全国居民人均可支配收入([\d.]+)元，?(?:比上年(?:同期)?|同比)(?:名义)?"
               r"(增长|下降)([\d.]+)%[，、]?扣除价格因素[，、]?实际(增长|下降)([\d.]+)%")
    found = re.search(pattern, text)
    if not found:
        return []
    rows = []
    nominal = ("-" if found[2] == "下降" else "") + found[3]
    real = ("-" if found[4] == "下降" else "") + found[5]
    for key, value in [("income_ytd", found[1]), ("income_nominal_ytd_yoy", nominal), ("income_real_ytd_yoy", real)]:
        add(rows, key, f"{year}-Q{quarter}", value, item["url"], published,
            "官方发布正文明确的全国居民年内累计值；非独立单季；发布日期来自统计局检索索引")
    return rows


def collect(backfill=False):
    rows, details = collect_income_api()
    found = list(search('("居民收入和消费支出情况")',
                        **({} if backfill else dict(start=f"{date.today().year-1}-01-01", end=date.today().isoformat()))))
    if backfill:
        found.extend(search('("全国居民人均可支配收入")', start="2013-01-01", end="2017-01-31", title_only=False))
        # This earlier integrated household survey release is indexed under
        # the national-economy title, not the later income-release title.
        found.extend(search('("国民经济")', start="2014-07-01", end="2014-07-31"))
    by_key = {(r["series_id"], r["period"]): r for r in rows}
    rejected = []
    for item in sorted({i["url"]: i for i in found}.values(), key=lambda i: (i["published"], i["url"])):
        batch = parse_release(fetch(item["url"]), item)
        if not batch:
            rejected.append(item["url"])
            continue
        for row in batch:
            key = row["series_id"], row["period"]
            # API latest history takes priority for amount/real; releases supply
            # nominal and any clearly verified missing early real observations.
            if key not in by_key or row["series_id"] == "income_nominal_ytd_yoy":
                by_key[key] = row
        print("Income release:", batch[0]["period"], item["url"], flush=True)
    rows = list(by_key.values())
    for key in ("income_ytd", "income_nominal_ytd_yoy", "income_real_ytd_yoy"):
        selected = [r for r in rows if r["series_id"] == key]
        if not selected:
            raise ValueError(f"Missing income history {key}")
        details.setdefault(key, {}).update(
            search_url="https://www.stats.gov.cn/search/s", search_api=SEARCH,
            coverage="全国一体化住户调查；金额自2013年，增速仅保留官方明确且可核验期间，不推算缺失增速",
            first_observation=min(r["period"] for r in selected),
            refresh_ranges=[{"start": ("2013-Q1" if backfill or key == "income_ytd" else
                                        "2014-Q1" if key == "income_real_ytd_yoy" else f"{date.today().year-1}-Q1"),
                             "end": f"{date.today().year}-Q4"}],
        )
    details["income_nominal_ytd_yoy"]["discovery_unparsed"] = rejected if backfill else []
    return rows, details
