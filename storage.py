import json
import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, Text, String, select
from sqlalchemy.engine import URL
from sqlalchemy.dialects.mysql import LONGTEXT


def connect():
    if os.getenv('DB_MODE', 'sqlite').lower() == 'mysql':
        url = URL.create('mysql+pymysql', username=os.environ['MYSQL_USER'], password=os.environ['MYSQL_PASSWORD'], host=os.getenv('MYSQL_HOST', 'localhost'), port=int(os.getenv('MYSQL_PORT', '3306')), database=os.getenv('MYSQL_DATABASE', 'debtors_automation'))
    else:
        url = os.getenv('DATABASE_URL', 'sqlite:///debtors_demo.db')
    engine = create_engine(url, pool_pre_ping=True)
    meta = MetaData()
    snapshots = Table('debtors_snapshots', meta, Column('id', Integer, primary_key=True), Column('created_at', String(40)), Column('snapshot_date', String(10)), Column('label', String(200)), Column('payload', Text().with_variant(LONGTEXT(), 'mysql')))
    meta.create_all(engine)
    return engine, snapshots


def save(engine, table, data, snapshot_date, label):
    with engine.begin() as conn:
        conn.execute(table.insert().values(created_at=datetime.now(timezone.utc).isoformat(), snapshot_date=str(snapshot_date), label=label[:200], payload=json.dumps(data)))


def load(engine, table):
    with engine.connect() as conn:
        row = conn.execute(select(table).order_by(table.c.id.desc()).limit(1)).mappings().first()
    return dict(row) if row else None


def history(engine, table):
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(select(table.c.id, table.c.created_at, table.c.snapshot_date, table.c.label).order_by(table.c.id.desc())).mappings()]
