"""Shared Supabase (Postgres) connection. URL comes from SUPABASE_DB_URL (env var or .env)."""
import os
from decimal import Decimal
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


def connect(**kw):
    return psycopg.connect(os.environ["SUPABASE_DB_URL"], **kw)


def query_df(sql, params=None, con=None):
    """Run a query and return a DataFrame (numeric columns come back as float)."""
    own = con is None
    con = con or connect()
    try:
        cur = con.execute(sql, params)
        df = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
    finally:
        if own:
            con.close()
    for c in df.columns:
        if df[c].dtype == object and df[c].map(lambda x: isinstance(x, Decimal)).any():
            df[c] = df[c].astype(float)
    return df
