"""Research-only 1-second OHLC scalping experiment; NOT a live trading system.
Download recent complete daily 1s Binance Spot kline archives, test non-overlapping
20s/30s momentum and reversal LONG/SHORT, with explicit fee/spread/slippage.
Limitations: no bid/ask quotes, Futures funding or liquidation model; short is hypothetical.
"""
import argparse, io, json, urllib.request, zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path('seconds_results');ROOT.mkdir(exist_ok=True)
BASE='https://data.binance.vision/data/spot/daily/klines'
COLS=['open_time','open','high','low','close','volume','close_time','quote_volume','trades','taker_base','taker_quote','ignore']

def download(symbol,day):
    date=day.strftime('%Y-%m-%d'); path=ROOT/f'{symbol}_{date}_1s.csv'
    if path.exists():return path
    url=f'{BASE}/{symbol}/1s/{symbol}-1s-{date}.zip'
    print('Downloading',url,flush=True)
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'research-backtest/1.0'})
        with urllib.request.urlopen(req,timeout=120) as r: blob=r.read()
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            fname=next(x for x in z.namelist() if x.endswith('.csv'))
            raw=pd.read_csv(z.open(fname),header=None)
    except Exception as exc:
        print('SKIP unavailable',date,symbol,repr(exc),flush=True);return None
    if raw.shape[1]!=12:raise ValueError('Unexpected Binance CSV format')
    raw.columns=COLS
    # Archive timestamps may be milliseconds or microseconds depending on year.
    ts=pd.to_numeric(raw['open_time'],errors='coerce')
    unit='us' if ts.dropna().median()>1e14 else 'ms'
    raw['time']=pd.to_datetime(ts,unit=unit,utc=True)
    raw=raw[['time','open','high','low','close','volume']]
    raw.to_csv(path,index=False)
    return path

def test_day(path,symbol,fee_bps,spread_bps,slip_bps):
    df=pd.read_csv(path,parse_dates=['time']);df=df.sort_values('time').drop_duplicates('time')
    for c in ['open','high','low','close','volume']:df[c]=pd.to_numeric(df[c],errors='coerce')
    df=df.dropna(subset=['close','open'])
    # Restrict to genuine adjacent 1s observations; don't silently fill missing prices.
    t=df.time.astype('int64').to_numpy()//10**9
    p=df['close'].to_numpy(float)
    opens=df['open'].to_numpy(float)
    rows=[]
    for lookback in (5,10,20):
      for hold in (20,30):
       for mode in ('momentum','reversal'):
        for side in ('LONG','SHORT'):
         # One signal per 60 seconds per strategy, no overlap for this strategy.
         for i in range(max(lookback,1),len(p)-hold,60):
          if t[i]-t[i-lookback]!=lookback or t[i+hold]-t[i]!=hold:continue
          prior=(p[i]/p[i-lookback]-1)*10000
          if abs(prior)<2:continue # signal threshold 2 bps, fixed in advance
          direction=np.sign(prior)*(1 if mode=='momentum' else -1)
          if (direction>0)!=(side=='LONG'):continue
          # Signal formed at second i, enter next second OPEN, exit at next second after holding.
          entry=opens[i+1] if t[i+1]-t[i]==1 else np.nan
          exit_=p[i+hold] # close after hold; approximate fill
          if not np.isfinite(entry) or entry<=0:continue
          gross=(exit_/entry-1)*direction*10000
          # two-sided fees + crossing half spread twice + two-sided slippage
          cost=2*fee_bps+spread_bps+2*slip_bps
          rows.append(dict(symbol=symbol,date=str(df.time.iloc[i].date()),signal_time=df.time.iloc[i].isoformat(),lookback_s=lookback,hold_s=hold,mode=mode,side=side,entry=entry,exit=exit_,gross_bps=gross,cost_bps=cost,net_bps=gross-cost,net_usdt=20*(gross-cost)/10000))
    return rows

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--days',type=int,default=3);ap.add_argument('--end-date',help='YYYY-MM-DD last completed UTC day, default yesterday');ap.add_argument('--fee-bps',type=float,default=10,help='per side; default Spot 0.1%');ap.add_argument('--spread-bps',type=float,default=1);ap.add_argument('--slippage-bps',type=float,default=1);args=ap.parse_args()
 if not 1<=args.days<=14:ap.error('days must be 1..14')
 today=datetime.now(timezone.utc).date();end=datetime.strptime(args.end_date,'%Y-%m-%d').date() if args.end_date else today-timedelta(days=2)
 if end>=today:ap.error('end-date must be before current UTC day')
 allrows=[];missing=[]
 for symbol in ('BTCUSDT','ETHUSDT'):
  for n in range(args.days):
   day=end-timedelta(days=n);file=download(symbol,day)
   if file is None:missing.append(f'{symbol} {day}');continue
   allrows.extend(test_day(file,symbol,args.fee_bps,args.spread_bps,args.slippage_bps))
 if not allrows:
  print('NO RESULTS: archives unavailable or insufficient data. Missing:',missing);return
 trades=pd.DataFrame(allrows);trades.to_csv(ROOT/'seconds_trades.csv',index=False)
 group=['symbol','lookback_s','hold_s','mode','side']
 summary=trades.groupby(group).agg(trades=('net_bps','size'),win_rate=('net_bps',lambda s:float((s>0).mean())),gross_bps_avg=('gross_bps','mean'),net_bps_avg=('net_bps','mean'),net_usdt=('net_usdt','sum')).reset_index().sort_values('net_usdt',ascending=False)
 summary.to_csv(ROOT/'seconds_summary.csv',index=False)
 report={'note':'Exploratory research, in-sample. Not proof of profitable execution. Spot candles used for hypothetical SHORT; not Futures execution.', 'parameters':vars(args),'available_dates':sorted(trades.date.unique().tolist()),'missing_archives':missing,'total_simulated_trades':len(trades),'best_in_sample':summary.head(5).to_dict('records')}
 (ROOT/'report.json').write_text(json.dumps(report,indent=2,default=str))
 print(summary.to_string(index=False));print('Saved results in seconds_results/')
if __name__=='__main__':main()
