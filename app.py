import json
from datetime import date
from decimal import Decimal
from pathlib import Path
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from core import SCHEMAS, parse_csv, validate_links, ageing, match_receipts, export_csv, statement, money
from storage import connect, load, save, history

load_dotenv()
st.set_page_config(page_title='Debtors Desk', page_icon='📊', layout='wide')
st.title('Debtors Desk')
st.caption('Receipts • ageing • reconciliations • customer statements')
st.info('Local review workspace. Imports are snapshots; proposals do not update balances or post to Sage. No emails are sent.')
try:
    engine, table = connect()
    current = load(engine, table)
except Exception:
    st.error('Database unavailable. Check your .env settings, database service and user permissions.')
    st.stop()
page = st.sidebar.radio('Workspace', ['Overview', 'Import data', 'Receipt matching', 'Statements & reminders', 'Import history'])

if page == 'Import data':
    st.subheader('Import a complete snapshot')
    st.write('Upload customers and current open invoices exported from Sage, plus an unposted bank-receipt batch. Remittances are optional. Use the exact sample column names. All values are ZAR.')
    uploads = {}
    for kind in SCHEMAS:
        st.caption(f"{kind}: {', '.join(SCHEMAS[kind])}")
        uploads[kind] = st.file_uploader(kind.title(), type=['csv'], key=kind)
    snapshot_date = st.date_input('Balance snapshot date', value=date.today())
    label = st.text_input('Import description', value='Sage export and bank batch')
    if st.button('Validate and save snapshot'):
        try:
            data = {}
            for kind, file in uploads.items():
                if file is None and kind != 'remittances':
                    raise ValueError(f'Upload {kind}.csv')
                data[kind] = parse_csv(kind, file.getvalue().decode('utf-8-sig')) if file else []
            validate_links(data)
            ageing(data['invoices'], snapshot_date)
            save(engine, table, data, snapshot_date, label)
            st.success('Snapshot saved. Open Overview or Receipt matching.')
        except (ValueError, UnicodeError) as e:
            st.error(str(e))
        except Exception:
            st.error('Could not save snapshot; check database availability. No partial import was saved.')
    if st.button('Load fictional demonstration data'):
        folder = Path(__file__).parent / 'sample_data'
        data = {k: parse_csv(k, (folder / f'{k}.csv').read_text()) for k in SCHEMAS}
        validate_links(data)
        save(engine, table, data, '2026-09-30', 'Fictional demo — September 2026')
        st.success('Demo saved. Open Overview.')
    st.stop()

if page == 'Import history':
    st.dataframe(pd.DataFrame(history(engine, table)), width='stretch')
    st.caption('Append-only import history in this app; not a tamper-proof accounting audit log.')
    st.stop()
if not current:
    st.warning('Open Import data to load the sample data or your CSV files.')
    st.stop()
data = json.loads(current['payload'])
as_of = date.fromisoformat(current['snapshot_date'])
st.sidebar.caption(f"Snapshot #{current['id']} • {as_of}\n{current['label']}")
aged = ageing(data['invoices'], as_of)
if page == 'Overview':
    total = sum((money(i['outstanding_amount']) for i in aged), Decimal(0))
    overdue = sum((money(i['outstanding_amount']) for i in aged if i['days_overdue']), Decimal(0))
    a, b, c = st.columns(3)
    a.metric('Outstanding', f'R {total:,.2f}')
    b.metric('Overdue', f'R {overdue:,.2f}')
    c.metric('Open invoices', len(aged))
    st.subheader('Age analysis by days past due')
    df = pd.DataFrame(aged)
    st.dataframe(df, width='stretch')
    if aged:
        chart = df.assign(outstanding_amount=df.outstanding_amount.astype(float)).groupby('ageing_bucket')['outstanding_amount'].sum().reindex(['Current', '1–30', '31–60', '61–90', '90+'], fill_value=0)
        st.bar_chart(chart)
        st.download_button('Download age analysis CSV', export_csv(aged), 'age_analysis.csv', 'text/csv')
    st.subheader('Customer exposure')
    exposure = []
    for customer in data['customers']:
        balance = sum((money(i['outstanding_amount']) for i in aged if i['customer_id'] == customer['customer_id']), Decimal(0))
        exposure.append({'customer': customer['customer_name'], 'balance': str(balance), 'credit_limit': customer['credit_limit'], 'over_limit': balance > money(customer['credit_limit'])})
    st.dataframe(pd.DataFrame(exposure), width='stretch')
elif page == 'Receipt matching':
    proposals = match_receipts(data)
    st.subheader('Allocation proposals and exceptions')
    st.write('Exact invoice references or balanced remittance splits can produce proposals. Missing identity, ambiguous references and excess amounts require review. Review every proposal before entering it in Sage.')
    st.dataframe(pd.DataFrame(proposals), width='stretch')
    bank_total = sum((money(r['amount']) for r in data['receipts']), Decimal(0))
    proposed = sum((money(r['proposed_amount']) for r in proposals if r['status'] == 'Proposed'), Decimal(0))
    a, b, c = st.columns(3)
    a.metric('Imported receipts', f'R {bank_total:,.2f}')
    b.metric('Proposed allocations', f'R {proposed:,.2f}')
    c.metric('Requires review', f'R {bank_total-proposed:,.2f}')
    st.download_button('Download review worksheet', export_csv(proposals, ['receipt_id', 'invoice_id', 'proposed_amount', 'status', 'reason']), 'allocation_review.csv', 'text/csv')
    st.caption('This is a review worksheet, not a Sage-compatible import file or a full bank reconciliation.')
elif page == 'Statements & reminders':
    customers = {c['customer_id']: c for c in data['customers']}
    if not customers:
        st.info('No customers in this snapshot.')
        st.stop()
    selected = st.selectbox('Customer', list(customers), format_func=lambda k: f"{k} — {customers[k]['customer_name']}")
    text, draft, overdue = statement(customers[selected], data['invoices'], as_of)
    st.text(text)
    st.download_button('Download statement', text, 'customer_statement.txt', 'text/plain')
    if overdue:
        st.text_area('Reminder draft — review before sending', draft, height=250)
        st.download_button('Download reminder draft', draft, 'reminder_draft.txt', 'text/plain')
    else:
        st.success('No overdue balance; no collection reminder needed.')
