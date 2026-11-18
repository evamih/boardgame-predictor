import pandas as pd

import config

log = pd.read_csv(config.FETCH_LOG_CSV)
files = sorted(config.XML_DIR.glob("batch_*.xml.gz"))
leftovers = list(config.XML_DIR.glob("*.tmp"))
expected = len(pd.read_csv(config.SELECTED_IDS_CSV))

print(f"batch files on disk:   {len(files)}  (expected {-(-expected // config.BATCH_SIZE)})")
print(f"leftover .tmp files:   {len(leftovers)}")
print(f"log rows / unique:     {len(log)} / {log['batch'].nunique()}")
print(f"games requested:       {log['n_requested'].sum():,}  (selected: {expected:,})")
print(f"games returned:        {log['n_returned'].sum():,}")
print(f"games missing:         {(log['n_requested'] - log['n_returned']).sum():,}")
print(f"batches that retried:  {(log['attempts'] > 1).sum()}")
print(f"total size:            {sum(f.stat().st_size for f in files) / 1e6:.1f} MB")
print(f"collected (UTC):       {log['fetched_at_utc'].min()}  ->  {log['fetched_at_utc'].max()}")