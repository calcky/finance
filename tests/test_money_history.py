"""Historical PBC definition, revision, frequency, and unit regressions."""

from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from macro_money_history import parse_table, authoritative_ranges

URL = "https://www.pbc.gov.cn/official-history.htm"


def html(rows):
    return ('<meta charset="utf-8"><table>' + ''.join(
        '<tr>' + ''.join(f'<td>{value}</td>' for value in row) + '</tr>'
        for row in rows) + '</table>').encode()


class MonetaryHistoryContracts(unittest.TestCase):
    def test_old_m1_is_separate_and_money_converts_to_trillions(self):
        data = html([
            ['单位：亿元人民币'], ['项目', '1999.12'],
            ['货币和准货币', '117638.10'], ['货币（狭义货币 M1）', '45837.30'],
        ])
        rows = parse_table(data, 'money', 1999, URL)
        values = {r['series_id']: Decimal(r['value']) for r in rows}
        self.assertEqual(values, {'m2': Decimal('11.763810'), 'm1_old': Decimal('4.583730')})
        self.assertEqual({r['period'] for r in rows}, {'1999-12'})

    def test_transposed_2012_flow_is_monthly_not_cumulative(self):
        rows = [['社会融资规模统计表'], ['单位：亿元人民币'],
                ['项目'] + [f'2012.{month:02}' for month in range(1, 13)],
                ['社会融资规模 Aggregate Financing to the Real Economy'] +
                [9754, 10431, 18703, 9637, 11432, 17802, 10522, 12475, 16462, 12906, 11225, 16282]]
        parsed = parse_table(html(rows), 'flow', 2012, URL)
        self.assertEqual(len(parsed), 12)
        self.assertEqual(parsed[2]['value'], '18703')
        self.assertEqual(parsed[2]['period'], '2012-03')

    def test_percentage_share_appendix_is_not_financing_amount(self):
        rows = [['社会融资规模增量统计表'], ['单位：亿元人民币'],
                ['2019.01', 46791], ['2019.10', -10],
                ['表1：2017年以来各月完善后的社会融资规模增量数据'], ['单位：亿元人民币'],
                ['2017.01', 37720], ['2019.01', 46791],
                ['表2：2017年以来各月完善后的社会融资规模增量占比数据'], ['单位：%'],
                ['2017.01', 100], ['2019.01', 100]]
        parsed = parse_table(html(rows), 'flow', 2019, URL)
        values = {r['period']: r['value'] for r in parsed}
        self.assertEqual(values, {'2019-01': '46791', '2019-10': '-10', '2017-01': '37720'})

    def test_quarter_end_stocks_remain_sparse(self):
        rows = [['社会融资规模存量统计表'], ['单位：万亿元人民币'],
                ['', '2015.Q1', '', '2015.Q2', '', '2015.Q3', '', '2015.Q4', ''],
                ['社会融资规模存量', 127.68, 13.1, 131.70, 12.0, 134.70, 12.5, 138.28, 12.5]]
        parsed = parse_table(html(rows), 'stock', 2015, URL)
        self.assertEqual(len(parsed), 8)
        self.assertEqual({r['period'] for r in parsed}, {'2015-03', '2015-06', '2015-09', '2015-12'})

    def test_revised_stock_appendix_has_different_unit(self):
        rows = [['社会融资规模存量统计表'], ['单位：万亿元人民币'],
                ['', '2019.1', ''], ['社会融资规模存量', 231.55, 10.9],
                ['', '表1：2017年以来各月完善后的社会融资规模存量数据'],
                ['', '单位：亿元人民币'], ['', '2017.01', 1841433], ['', '2019.01', 2315500],
                ['', '表2：2017年以来各月完善后的社会融资规模增速数据'],
                ['', '单位：%'], ['', '2017.01', 14.4]]
        parsed = parse_table(html(rows), 'stock', 2019, URL)
        values = {(r['series_id'], r['period']): Decimal(r['value']) for r in parsed}
        self.assertEqual(values['tsf_stock', '2017-01'], Decimal('184.1433'))
        self.assertEqual(values['tsf_stock_yoy', '2017-01'], Decimal('14.4'))
        self.assertEqual(values['tsf_stock', '2019-01'], Decimal('231.55'))

    def test_unit_drift_fails_closed(self):
        data = html([['社会融资规模增量统计表'], ['单位：万元人民币'], ['2012.01', 9754]])
        with self.assertRaises(ValueError):
            parse_table(data, 'flow', 2012, URL)

    def test_refresh_scope_includes_withdrawn_cells_and_restatement(self):
        self.assertEqual(authoritative_ranges('money', 1999, 'm2'), [{'start': '1999-12', 'end': '1999-12'}])
        self.assertEqual(authoritative_ranges('money', 2026, 'm2'), [{'start': '2026-01', 'end': '2026-12'}])
        self.assertEqual(authoritative_ranges('flow', 2019, 'tsf_flow'), [{'start': '2017-01', 'end': '2019-12'}])
        self.assertEqual(authoritative_ranges('money', 2025, 'm1'), [{'start': '2024-01', 'end': '2025-12'}])

    def test_new_m1_uses_explicit_backcast_and_october_position(self):
        rows = [['单位：亿元人民币'], ['项目', '', ''] + [float(f'2025.{m:02}') for m in range(1, 13)],
                ['货币和准货币（M2）', '', ''] + [3185247.18] * 12,
                ['', '货币（M1）', ''] + [1124457.45] * 12,
                ['2024 年 M1 按可比口径回溯'],
                ['', '', ''] + [float(f'2024.{m:02}') for m in range(1, 13)],
                ['', '', '余额（亿元）'] + [1120120] * 12,
                ['', '', '同比增速'] + ['3.3%'] * 12]
        parsed = parse_table(html(rows), 'money', 2025, URL)
        lookup = {(r['series_id'], r['period']): Decimal(r['value']) for r in parsed}
        self.assertEqual(lookup['m1', '2024-01'], Decimal('112.012'))
        self.assertEqual(lookup['m1_yoy', '2024-01'], Decimal('3.3'))
        self.assertEqual(lookup['m1', '2025-10'], Decimal('112.445745'))
        self.assertNotIn(('m1_old', '2024-01'), lookup)


if __name__ == '__main__':
    unittest.main()
