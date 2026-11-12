#!/usr/bin/env python3
"""Exploratory Binance SPOT aggTrades trade-flow study. NOT an execution-ready backtest."""
import argparse, csv, io, json, urllib.request, zipfile
from collections import defaultdict, deque
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

p=argparse.ArgumentParser()
p.add_argument('--start',default='2026-11-08');p.add_argument('--days',type=int,default=3)
p.add_argument('--symbol',default='BTCUSDT');p.add_argument('--out',default='orderflow_results')
p.add_argument('--fee-bps-side',type=float,default=5);p.add_argument('--slippage-bps-side',type=float,default=2)
a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
if a.days<3: raise ValueError('Use >=3 days to allow a separate test day')
rows=[]; counts={}
for i in range(a.days):
 d=(date.fromisoformat(a.start)+timedelta(days=i)).isoformat()
 url=f'https://data.binance.vision/data/spot/daily/aggTrades/{a.symbol}/{a.symbol}-aggTrades-{d}.zip'
 print('Downloading',url,flush=True)
 try:
  with urllib.request.urlopen(url,timeout=90) as response: data=response.read()
 except Exception as exc: raise RuntimeError(f'Unable to download {url}: {exc}') from exc
 n=0
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  with z.open(z.namelist()[0]) as f:
   for chunk in pd.read_csv(f,header=None,chunksize=300000):
    # Binance aggTrades: id,price,quantity,firstId,lastId,timestamp,isBuyerMaker,isBestMatch
    chunk=chunk.iloc[:,:7].copy();chunk.columns=['id','price','qty','first','last','ts','buyer_maker']
    chunk['price']=pd.to_numeric(chunk.price);chunk['qty']=pd.to_numeric(chunk.qty)
    ts=pd.to_numeric(chunk.ts);chunk['sec']=(ts//(1000000 if ts.max()>1e16 else 1000)).astype('int64')
    chunk['signed_quote']=np.where(chunk.buyer_maker.astype(str).str.lower().isin(['true','1']),-1,1)*chunk.price*chunk.qty
    chunk['quote']=chunk.price*chunk.qty
    agg=chunk.groupby('sec',sort=True).agg(last_price=('price','last'),signed=('signed_quote','sum'),quote=('quote','sum'),trades=('id','size'))
    rows.append(agg);n+=len(chunk)
 counts[d]=n
 print(d,'aggTrades',n,flush=True)
raw=pd.concat(rows).groupby(level=0,sort=True).agg(last_price=('last_price','last'),signed=('signed','sum'),quote=('quote','sum'),trades=('trades','sum'))
# Calendar-second bars; no trades -> zero flow, price forward-filled for indicative marks.
idx=pd.RangeIndex(raw.index.min(),raw.index.max()+1)
s=raw.reindex(idx);s['last_price']=s.last_price.ffill();s[['signed','quote','trades']]=s[['signed','quote','trades']].fillna(0)
# Past 10 seconds flow only, never current/future price for signal.
s['imbalance']=s.signed.rolling(10,min_periods=10).sum()/s.quote.rolling(10,min_periods=10).sum().replace(0,np.nan)
s['rolling_quote']=s.quote.rolling(10,min_periods=10).sum()
# Use last trade price of NEXT second as an optimistic proxy; actual bid/ask not present.
prices=s.last_price.to_numpy(); im=s.imbalance.to_numpy();volume=s.rolling_quote.to_numpy();seconds=np.asarray(s.index)
results=[];trades=[]
# Predeclared small grid; tune on first days only, hold last day as test.
for lookback in [10]:
 for threshold in [0.3,0.5,0.7]:
  for min_quote in [10000,50000]:
   for direction in ['momentum','reversal']:
    for hold in [20,30,60]:
     selected=[]; last_exit=-1
     for j in range(lookback+1,len(s)-hold-2):
      if j<=last_exit:continue
      if not np.isfinite(im[j]) or abs(im[j])<threshold or volume[j]<min_quote:continue
      side=(1 if im[j]>0 else -1)*(1 if direction=='momentum' else -1)
      entry=prices[j+1]; exitp=prices[j+1+hold]
      if entry<=0 or exitp<=0:continue
      gross=side*(exitp/entry-1)*10000
      cost=2*(a.fee_bps_side+a.slippage_bps_side)
      pnl=(gross-cost)*20/10000
      row={'entry_utc':pd.to_datetime(seconds[j+1],unit='s',utc=True).isoformat(),'symbol':a.symbol,'model':direction,'threshold':threshold,'min_10s_quote':min_quote,'hold_s':hold,'side':'LONG' if side==1 else 'SHORT','entry_proxy':entry,'exit_proxy':exitp,'gross_bps':round(gross,5),'cost_bps':cost,'net_usdt_20':round(pnl,8)}
      selected.append(row);last_exit=j+1+hold
     for part in ['train','test']:
      # Last calendar day reserved for test; do not tune based on it.
      boundary=pd.Timestamp(date.fromisoformat(a.start)+timedelta(days=a.days-1),tz='UTC')
      subset=[r for r in selected if (pd.Timestamp(r['entry_utc'])<boundary)==(part=='train')]
      net=sum(r['net_usdt_20'] for r in subset)
      results.append({'symbol':a.symbol,'model':direction,'threshold':threshold,'min_10s_quote':min_quote,'hold_s':hold,'split':part,'trades':len(subset),'net_usdt_20':round(net,5),'avg_net_bps':round(sum(r['net_usdt_20'] for r in subset)/len(subset)/20*10000,5) if subset else None,'win_rate':round(sum(r['net_usdt_20']>0 for r in subset)/len(subset),5) if subset else None})
     trades.extend(selected)
pd.DataFrame(results).to_csv(out/'comparison.csv',index=False)
pd.DataFrame(trades).to_csv(out/'trades.csv',index=False)
report={'status':'EXPLORATORY_NOT_LIVE_READY','symbol':a.symbol,'start':a.start,'days':a.days,'raw_aggTrades_per_day':counts,'fee_bps_per_side':a.fee_bps_side,'slippage_bps_per_side':a.slippage_bps_side,'notes':['SPOT aggTrades are historical executed trades, NOT order book or bid/ask quotes.','Last traded price as entry/exit is an optimistic proxy; no market impact or latency modeled.','Short trades are hypothetical; SPOT cannot short without borrowing.','Do not treat the last test day as untouched after repeated strategy selection.','Same-second timestamps aggregated; fills not validated.','Funding and liquidation excluded.']}
(out/'report.json').write_text(json.dumps(report,indent=2))
print('Wrote results to',out,flush=True)
