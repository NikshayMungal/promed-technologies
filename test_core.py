import unittest
from copy import deepcopy
from datetime import date
from pathlib import Path
from core import parse_csv, SCHEMAS, validate_links, match_receipts, ageing, money, export_csv, statement

class CoreTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / 'sample_data'
        self.data = {k: parse_csv(k, (root / f'{k}.csv').read_text()) for k in SCHEMAS}
    def test_sample_totals_and_proposals(self):
        validate_links(self.data)
        rows = match_receipts(self.data)
        self.assertEqual(sum(money(r['proposed_amount']) for r in rows if r['status'] == 'Proposed'), 19000)
        self.assertEqual(sum(r['status'] == 'Review' for r in rows), 3)
    def test_ageing(self):
        rows = ageing(self.data['invoices'], date(2026,9,30))
        self.assertEqual(sum(money(r['outstanding_amount']) for r in rows), 27500)
        self.assertEqual(sum(money(r['outstanding_amount']) for r in rows if r['days_overdue']), 15500)
        self.assertEqual([r['ageing_bucket'] for r in rows], ['61–90','1–30','Current','90+','1–30'])
    def test_duplicate_id_rejected(self):
        header = ','.join(SCHEMAS['receipts']) + '\n'
        line = 'P1,2026-09-30,C001,INV001,1.00\n'
        with self.assertRaises(ValueError): parse_csv('receipts', header + line + line)
    def test_bad_money(self):
        for value in ['NaN','Infinity','-1','1.001']:
            with self.assertRaises(ValueError): money(value)
    def test_unknown_customer(self):
        self.data['invoices'][0]['customer_id'] = 'UNKNOWN'
        with self.assertRaises(ValueError): validate_links(self.data)
    def test_remittance_mismatch(self):
        self.data['remittances'][0]['amount'] = '11000'
        rows = match_receipts(self.data)
        self.assertEqual(next(r['status'] for r in rows if r['receipt_id']=='PAY002'), 'Review')
    def test_does_not_modify_ledger(self):
        before = deepcopy(self.data)
        match_receipts(self.data)
        self.assertEqual(before, self.data)
    def test_formula_export(self):
        self.assertIn("'=SUM", export_csv([{'name':'=SUM(1,2)'}]).decode('utf-8-sig'))
    def test_statement_uses_imported_balance(self):
        text, draft, overdue = statement(self.data['customers'][0], self.data['invoices'], date(2026,9,30))
        self.assertEqual(overdue, 8000)
        self.assertIn('8,000.00', text)
    def test_no_cross_customer_allocation(self):
        rows = match_receipts(self.data)
        self.assertEqual(next(r['reason'] for r in rows if r['receipt_id']=='PAY006'), 'Customer mismatch')
    def test_no_overallocation(self):
        rows = match_receipts(self.data)
        self.assertEqual(next(r['status'] for r in rows if r['receipt_id']=='PAY005'), 'Review')

if __name__ == '__main__': unittest.main()
