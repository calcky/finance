"""Population stocks, census households and UN historical fertility estimates."""

import csv
from datetime import date
import gzip
from html import unescape
import io
import json
from pathlib import Path
import re
import unicodedata

from bs4 import BeautifulSoup

from macro_common import add, fetch, number
from macro_nbs_annual import collect_group
from macro_render import periods_between

GROUPS = [
    ("6331ad868e8b4f55b8e9b6e765609ce1", {
        "806083491dbe46a08995783945a30b9d": ("population_china", "年末总人口(万人)", "万人"),
    }),
    ("ffed4267bba24830beea5991d4c9bcfc", {
        "3d4006d356d94bdd9d75700b9788e230": ("population_birth_rate", "人口出生率(‰)", "‰"),
        "ee4b8be1ad68498e81d9ecddf4d4f2de": ("population_death_rate", "人口死亡率(‰)", "‰"),
        "3969129b26a846968a7dddff5f326f55": ("population_natural_rate", "人口自然增长率(‰)", "‰"),
    }),
    ("0746af8973394b7b86b4468859a42c56", {
        "1d19561de3d24b078fe0aeae34b7c057": ("household_size_census", "人口普查家庭户规模(人/户)", "人/户"),
    }),
]
UN_URL = "https://population.un.org/wpp/assets/Excel%20Files/1_Indicator%20%28Standard%29/CSV_FILES/WPP2024_Demographic_Indicators_Medium.csv.gz"
UN_PAGE = "https://population.un.org/wpp/"
HOUSEHOLDS = Path(__file__).resolve().parents[1] / "data/reference/population-households.json"


def parse_fertility(data):
    rows, seen = [], set()
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
        for raw in csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig")):
            if raw["ISO3_code"] != "CHN":
                continue
            if raw["LocID"] != "156" or raw["Location"] != "China" or raw["Variant"] != "Medium":
                raise ValueError("UN China geography/variant changed")
            year = raw["Time"]
            if not re.fullmatch(r"\d{4}", year) or year in seen:
                raise ValueError("UN duplicate/invalid year")
            seen.add(year)
            # The Medium file contains BOTH estimates and projections. WPP2024
            # defines 2024 onward as projections, including years now in the past.
            if not "1950" <= year <= "2023":
                continue
            value = number(raw["TFR"])
            if value is None or not 0 < value < 15:
                raise ValueError("UN fertility missing/out of bounds")
            add(rows, "fertility_china_un", year, value, UN_URL,
                note="WPP2024历史人口学估计；1950—2023；排除2024起预测；中国不含香港、澳门和台湾；不是中国官方出生率")
    if sorted(r["period"] for r in rows) != periods_between("1950", "2023", "A"):
        raise ValueError("UN historical fertility incomplete")
    return rows


def normalize(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", unescape(text)))


def parse_household_evidence(data, record):
    soup = BeautifulSoup(data, "html.parser")
    text = normalize(soup.get_text())
    if normalize(record["quotation"]) not in text:
        raise ValueError(f"Audited household source quotation changed: {record['year']}")
    # The 1987 report gives only the number of sampled households. Keep that
    # discovery in the audit manifest, never turn it into a national total.
    if record["kind"] == "survey_sample":
        return []
    if record["kind"] not in ("census", "survey_estimate"):
        raise ValueError("Unknown household statistical scope")
    unit = record["count_original_unit"]
    if unit not in ("户", "万户"):
        raise ValueError("Household source unit changed")
    raw_count = number(record["count_original"])
    count = raw_count / (10000 if unit == "户" else 1)
    if count != number(record["count_wanhu"]) or not 0 < count < 100000:
        raise ValueError("Household conversion changed")
    if record["count_original"]+unit not in normalize(record["quotation"]):
        raise ValueError("Household count not in source quotation")
    mean = number(record["mean_size"])
    if not 1 < mean < 10 or record["mean_size"] not in record["quotation"]:
        raise ValueError("Household size not in source quotation")
    segment = "census" if record["kind"] == "census" else "survey"
    rows = []
    note = "全国人口普查时点数" if segment == "census" else "1%调查官方全国推算值，非样本实际户数"
    add(rows, "households_"+segment, record["year"], count, record["source_url"], note=note+"；家庭户不含集体户；保留原公告精度")
    if segment == "survey":
        add(rows, "household_size_survey", record["year"], mean, record["source_url"], note=note)
    return rows


def collect(backfill=False):
    rows, metadata = [], {}
    for cid, members in GROUPS:
        batch, details = collect_group(cid, members)
        for key, _, _ in members.values():
            years = sorted(r["period"] for r in batch if r["series_id"] == key)
            if key.startswith("population_") and (years[0] != "1949" or years != periods_between(years[0], years[-1], "A")):
                raise ValueError("National population history truncated")
        rows.extend(batch)
        metadata.update(details)
    key = "fertility_china_un"
    rows.extend(parse_fertility(fetch(UN_URL)))
    metadata[key] = dict(source_url=UN_URL, release="WPP2024", field="TFR", geography="CHN/156",
        estimate_end="2023", excluded_projection_start="2024", source_page=UN_PAGE,
        coverage="联合国WPP2024完整1950—2023历史估计；2024年起预测不收录；新版本发布后需核对估计边界再升级，不能自动把过去的预测改叫观测",
        definition_notes=["2026年1月联合国公告：下一次完整修订推迟到2027年7月；2026临时更新仅涉及多哥"],
        requested_window_complete=True, refresh_ranges=[dict(start="1950", end="2023")])
    records = json.loads(HOUSEHOLDS.read_text(encoding="utf-8"))
    for record in records:
        batch = parse_household_evidence(fetch(record["source_url"]), record)
        rows.extend(batch)
        for row in batch:
            metadata.setdefault(row["series_id"], dict(source_records=[],
                coverage="普查及1%调查原始公报点；仅真实调查年有值，缺年不插值；新增普查/调查须核验后更新证据清单，不是逐年自动估算",
                requested_window_complete=True, refresh_ranges=[dict(start="1949", end=str(date.today().year))]))["source_records"].append(record)
    print("Population:", len(rows), "observations", flush=True)
    return rows, metadata
