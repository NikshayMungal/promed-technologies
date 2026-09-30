"""Validation and proposal generation. Never posts accounting entries."""
import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation

SCHEMAS = {
    'customers': ['customer_id', 'customer_name', 'email', 'credit_terms_days', 'credit_limit'],
    'invoices': ['invoice_id', 'customer_id', 'invoice_date', 'due_date', 'original_amount', 'outstanding_amount'],
    'receipts': ['receipt_id', 'payment_date', 'customer_id', 'reference', 'amount'],
    'remittances': ['receipt_id', 'invoice_id', 'amount'],
}

def money(value):
    try:
        d = Decimal(str(value))
        if not d.is_finite() or d < 0 or d != d.quantize(Decimal('0.01')):
            raise ValueError()
        return d
    except (InvalidOperation, ValueError):
        raise ValueError(f'Invalid non-negative currency amount: {value!r}') from None

def parse_csv(kind, content):
    reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff')))
    if reader.fieldnames != SCHEMAS[kind]:
        raise ValueError('Required headers, in order: ' + ','.join(SCHEMAS[kind]))
    rows, seen = [], set()
    for line, raw in enumerate(reader, 2):
        if None in raw or any(v is None for v in raw.values()):
            raise ValueError(f'Row {line}: wrong number of fields')
        row = {k: v.strip() for k, v in raw.items()}
        try:
            optional = {'email'} if kind == 'customers' else {'customer_id', 'reference'} if kind == 'receipts' else set()
            if any(not v for k, v in row.items() if k not in optional):
                raise ValueError('Required field is blank')
            if any(len(v) > 500 for v in row.values()):
                raise ValueError('Field exceeds 500 characters')
            key = tuple(row[k] for k in SCHEMAS[kind][:2]) if kind == 'remittances' else row[SCHEMAS[kind][0]]
            if key in seen:
                raise ValueError(f'Duplicate identifier: {key}')
            seen.add(key)
            for k, v in row.items():
                if k.endswith('_date'):
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', v):
                        raise ValueError('Dates must use YYYY-MM-DD')
                    date.fromisoformat(v)
                if k.endswith('amount') or k == 'credit_limit':
                    row[k] = str(money(v))
            if kind == 'customers':
                terms = int(row['credit_terms_days'])
                if not 0 <= terms <= 365:
                    raise ValueError('Credit terms must be 0–365 days')
                if row['email'] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', row['email']):
                    raise ValueError('Invalid email')
            if kind == 'invoices':
                if row['due_date'] < row['invoice_date']:
                    raise ValueError('Due date precedes invoice date')
                if money(row['outstanding_amount']) > money(row['original_amount']):
                    raise ValueError('Outstanding exceeds original amount')
            if kind in ('receipts', 'remittances') and money(row['amount']) == 0:
                raise ValueError('Amount must be positive')
        except ValueError as e:
            raise ValueError(f'Row {line}: {e}') from None
        rows.append(row)
    return rows

def validate_links(data):
    customers = {r['customer_id'] for r in data['customers']}
    invoices = {r['invoice_id'] for r in data['invoices']}
    receipts = {r['receipt_id'] for r in data['receipts']}
    for kind in ('invoices', 'receipts'):
        for r in data[kind]:
            if r['customer_id'] and r['customer_id'] not in customers:
                raise ValueError(f"Unknown customer {r['customer_id']} in {kind}")
    for r in data['remittances']:
        if r['receipt_id'] not in receipts or r['invoice_id'] not in invoices:
            raise ValueError('Remittance refers to an unknown receipt or invoice')

def ageing(invoices, as_of):
    result = []
    for inv in invoices:
        if date.fromisoformat(inv['invoice_date']) > as_of:
            raise ValueError('Report date precedes an invoice date')
        if money(inv['outstanding_amount']) == 0:
            continue
        days = max(0, (as_of - date.fromisoformat(inv['due_date'])).days)
        bucket = 'Current' if days == 0 else '1–30' if days <= 30 else '31–60' if days <= 60 else '61–90' if days <= 90 else '90+'
        result.append(dict(inv, days_overdue=days, ageing_bucket=bucket))
    return result

def match_receipts(data):
    """Conservative proposals; reserve invoice balances to prevent over-allocation."""
    validate_links(data)
    invoices = {i['invoice_id']: i for i in data['invoices']}
    remaining = {k: money(i['outstanding_amount']) for k, i in invoices.items()}
    output = []
    for r in sorted(data['receipts'], key=lambda x: (x['payment_date'], x['receipt_id'])):
        amount = money(r['amount'])
        rem = [x for x in data['remittances'] if x['receipt_id'] == r['receipt_id']]
        allocations, reason = [], ''
        if rem:
            if sum((money(x['amount']) for x in rem), Decimal(0)) != amount:
                reason = 'Remittance total differs from receipt'
            else:
                allocations = [(x['invoice_id'], money(x['amount'])) for x in rem]
        elif r['reference'] in invoices:
            allocations = [(r['reference'], amount)]
        else:
            reason = 'No exact invoice reference or remittance; manual investigation'
        if allocations:
            if not r['customer_id']:
                reason = 'Missing receipt customer; identity requires confirmation'
            elif any(invoices[k]['customer_id'] != r['customer_id'] for k, _ in allocations):
                reason = 'Customer mismatch'
            elif any(r['payment_date'] < invoices[k]['invoice_date'] for k, _ in allocations):
                reason = 'Receipt predates invoice'
            elif any(a > remaining[k] for k, a in allocations):
                reason = 'Amount exceeds remaining balance; check duplicate, overpayment or previous posting'
        if reason:
            output.append(dict(receipt_id=r['receipt_id'], invoice_id='', proposed_amount=str(amount), status='Review', reason=reason))
        else:
            for k, a in allocations:
                remaining[k] -= a
                output.append(dict(receipt_id=r['receipt_id'], invoice_id=k, proposed_amount=str(a), status='Proposed', reason='Remittance match' if rem else 'Exact invoice reference'))
    return output

def export_csv(rows, headers=None):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=headers or (list(rows[0]) if rows else []))
    writer.writeheader()
    for row in rows:
        # Neutralise spreadsheet formulas in downloaded text fields.
        writer.writerow({k: "'" + str(v) if str(v).lstrip().startswith(('=', '+', '-', '@')) else v for k, v in row.items()})
    return out.getvalue().encode('utf-8-sig')

def statement(customer, invoices, as_of):
    rows = ageing([i for i in invoices if i['customer_id'] == customer['customer_id']], as_of)
    total = sum((money(r['outstanding_amount']) for r in rows), Decimal(0))
    overdue = sum((money(r['outstanding_amount']) for r in rows if r['days_overdue']), Decimal(0))
    lines = [f"CUSTOMER STATEMENT — {customer['customer_name']}", f"Account: {customer['customer_id']}", f'As of: {as_of}', 'Currency: ZAR', '']
    for r in rows:
        lines.append(f"{r['invoice_id']} | Due {r['due_date']} | R {money(r['outstanding_amount']):,.2f} | {r['ageing_bucket']}")
    lines.extend(['', f'Total outstanding: R {total:,.2f}', f'Overdue: R {overdue:,.2f}', 'Based on the imported open-invoice snapshot; allocation proposals are not posted.'])
    draft = f"To: {customer['email']}\nSubject: Account {customer['customer_id']} — outstanding balance\n\nDear {customer['customer_name']},\n\nOur records as of {as_of} show an overdue balance of R {overdue:,.2f}. Please confirm payment status and provide remittance advice where payment has been made. If you dispute a balance, please identify the relevant invoice so we can investigate.\n\nKind regards,\nAccounts team\n"
    return '\n'.join(lines), draft, overdue
