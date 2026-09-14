from __future__ import annotations

import base64
import json
import math
import os
import random
import sqlite3
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("TRADER_DB", ROOT / "trader.db"))
HOST = os.getenv("TRADER_HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

DEFAULT_UNIVERSE = (
    "NASD:AAPL,NASD:MSFT,NASD:NVDA,NASD:AMZN,NASD:META,NASD:GOOGL,"
    "NASD:AVGO,NASD:AMD,NASD:COST,NASD:NFLX,NASD:TSLA,NASD:QQQ,"
    "NYSE:SPY,NYSE:JPM,NYSE:LLY"
)

INDEX_HTML = r'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#101727"><title>사장님 자동매매</title><link rel="stylesheet" href="/style.css"></head><body><main>
<header><div><small id="mode">-</small><h1>사장님 자동매매</h1></div><span id="status" class="pill">정지</span></header>
<section class="hero"><div><small>추정 총 평가금액</small><h2 id="equity">$0.00</h2><span id="profit">$0.00 (0.00%)</span></div><button id="toggle">자동매매 시작</button></section>
<section class="grid"><article><small>매수가능금액</small><b id="cash">-</b></article><article><small>보유 종목</small><b id="holdingCount">0개</b></article><article><small>최근 판단</small><b id="signal">대기</b></article><article><small>오늘 손익률</small><b id="daypnl">0.00%</b></article></section>
<section class="card"><div class="title"><h3>자동 선정 후보</h3><button id="scan" class="link">1회 분석</button></div><div id="candidates"></div></section>
<section class="card"><div class="title"><h3>현재 보유</h3><span>최대 <b id="maxpos">3</b>종목</span></div><div id="positions"></div></section>
<section class="card"><div class="title"><h3>자동매매 설정</h3><span>저장 즉시 적용</span></div><form id="settings">
<label>감시 종목<input name="universe" placeholder="NASD:AAPL,NASD:MSFT,..."></label>
<div class="row"><label>최대 보유종목<input name="max_positions" type="number" min="1" max="5"></label><label>종목당 투자비중 %<input name="position_pct" type="number" step="1" min="1" max="20"></label></div>
<div class="row"><label>손절 %<input name="stop_loss_pct" type="number" step="0.5"></label><label>익절 %<input name="take_profit_pct" type="number" step="0.5"></label></div>
<div class="row"><label>최소 점수<input name="min_score" type="number" step="0.05"></label><label>판단 주기(초)<input name="poll_seconds" type="number" min="30"></label></div>
<button class="secondary">설정 저장</button></form></section>
<section class="card"><div class="title"><h3>최근 거래</h3><span>실제 주문 기록</span></div><div id="trades"></div></section>
<p class="notice">⚠️ 자동 종목선정은 수익을 보장하지 않습니다. 점수 기반으로 유동성 높은 종목을 비교하고, 손절·익절·일손실 제한을 적용합니다.</p>
</main><div id="toast"></div><script src="/app.js"></script></body></html>'''

STYLE_CSS = r''':root{font-family:system-ui,-apple-system,sans-serif;color:#edf2ff;background:#0a0f1c;color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:linear-gradient(160deg,#111a30,#080c16 55%);min-height:100vh}main{max-width:760px;margin:auto;padding:24px 16px 60px}header,.title,.hero,.row{display:flex;align-items:center;justify-content:space-between;gap:12px}h1{font-size:23px;margin:4px 0}h2{font-size:36px;margin:8px 0}h3{margin:0;font-size:17px}small,.title span,label,.notice,.muted{color:#93a1bd}.pill{background:#33405b;padding:7px 12px;border-radius:999px;font-size:13px}.pill.on{background:#123f32;color:#52e3aa}.hero,.card{background:rgba(20,29,49,.94);border:1px solid #26334d;border-radius:20px;padding:20px;margin-top:16px;box-shadow:0 14px 40px #0004}.hero button,form button{border:0;border-radius:14px;background:#4777ff;color:#fff;font-weight:800;padding:15px 18px}.hero button.stop{background:#ef5b68}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}.grid article{background:#121b2e;border:1px solid #23304a;border-radius:16px;padding:15px;min-width:0}.grid b{display:block;margin-top:7px;overflow:hidden;text-overflow:ellipsis}.title{margin-bottom:14px}.row label{width:50%}label{display:block;font-size:13px;margin:10px 0}input{display:block;width:100%;margin-top:7px;padding:13px;border-radius:12px;border:1px solid #34415a;background:#0d1424;color:#fff;font-size:15px}.secondary{width:100%;margin-top:10px}.link{background:transparent;border:0;color:#79a0ff;font-weight:700}.item{display:flex;justify-content:space-between;gap:12px;padding:12px 0;border-top:1px solid #29344a}.item:first-child{border-top:0}.buy{color:#ff6b76}.sell{color:#5b9dff}.score{font-weight:800}.good{color:#52e3aa}.bad{color:#ff6b76}.notice{text-align:center;line-height:1.6;font-size:13px}#toast{position:fixed;left:50%;bottom:28px;transform:translateX(-50%) translateY(90px);background:#edf2ff;color:#111827;padding:12px 18px;border-radius:12px;font-weight:700;transition:.25s;z-index:3;max-width:90%}#toast.show{transform:translateX(-50%) translateY(0)}@media(max-width:520px){.hero{align-items:flex-start}.hero button{padding:13px}.grid{grid-template-columns:1fr 1fr}.row{align-items:flex-start}}'''

APP_JS = r'''const $=s=>document.querySelector(s);let state=null;const money=n=>'$'+Number(n||0).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):null});const d=await r.json();if(!r.ok)throw Error(d.error||'요청 실패');return d.state||d}
function toast(t){$('#toast').textContent=t;$('#toast').classList.add('show');setTimeout(()=>$('#toast').classList.remove('show'),2200)}
function render(s){state=s;$('#mode').textContent=s.mode;$('#status').textContent=s.running?'자동 실행 중':'정지';$('#status').classList.toggle('on',s.running);$('#toggle').textContent=s.running?'자동매매 정지':'자동매매 시작';$('#toggle').classList.toggle('stop',s.running);$('#equity').textContent=money(s.equity);$('#profit').textContent=`${s.profit>=0?'+':''}${money(s.profit)} (${s.profit_pct}%)`;$('#profit').className=s.profit>=0?'good':'bad';$('#cash').textContent=money(s.cash);$('#holdingCount').textContent=(s.positions||[]).length+'개';$('#signal').textContent=s.last_signal;$('#daypnl').textContent=(s.day_profit_pct>=0?'+':'')+s.day_profit_pct+'%';$('#daypnl').className=s.day_profit_pct>=0?'good':'bad';$('#maxpos').textContent=s.config.max_positions;
const cs=s.candidates||[];$('#candidates').innerHTML=cs.length?cs.map((c,i)=>`<div class="item"><div><b>${i+1}. ${c.symbol}</b><div class="muted">${money(c.price)} · 추세 ${c.trend_pct}% · 모멘텀 ${c.momentum_pct}%</div></div><div class="score ${c.eligible?'good':''}">${c.score.toFixed(2)}</div></div>`).join(''):'<p class="muted">아직 분석 전입니다.</p>';
const ps=s.positions||[];$('#positions').innerHTML=ps.length?ps.map(p=>`<div class="item"><div><b>${p.symbol} · ${p.qty}주</b><div class="muted">평단 ${money(p.avg_price)} · 현재 ${money(p.price)}</div></div><div class="${p.pnl_pct>=0?'good':'bad'}">${p.pnl_pct>=0?'+':''}${p.pnl_pct.toFixed(2)}%</div></div>`).join(''):'<p class="muted">보유 종목이 없습니다.</p>';
Object.entries(s.config).forEach(([k,v])=>{let e=document.querySelector(`[name=${k}]`);if(e&&document.activeElement!==e)e.value=v});
$('#trades').innerHTML=s.trades.length?s.trades.map(t=>`<div class="item"><div><b class="${t.side==='BUY'?'buy':'sell'}">${t.side==='BUY'?'매수':'매도'} ${t.symbol} ${t.qty}주</b><div class="muted">${t.reason}</div></div><div>${money(t.price)}<div class="muted">${t.ts.slice(5,16).replace('T',' ')}</div></div></div>`).join(''):'<p class="muted">아직 거래 기록이 없습니다.</p>'}
async function refresh(){try{render(await api('/api/state'))}catch(e){toast(e.message)}}
$('#scan').onclick=async()=>{try{render(await api('/api/scan',{}));toast('분석 완료 · 주문은 하지 않았어요')}catch(e){toast(e.message)}};
$('#toggle').onclick=async()=>{try{render(await api(state.running?'/api/stop':'/api/start',{}));toast(state.running?'자동매매 시작':'자동매매 정지')}catch(e){toast(e.message)}};
$('#settings').onsubmit=async e=>{e.preventDefault();let d=Object.fromEntries(new FormData(e.target));for(let k of ['max_positions','position_pct','stop_loss_pct','take_profit_pct','min_score','poll_seconds'])d[k]=Number(d[k]);try{render(await api('/api/config',d));toast('설정 저장 완료')}catch(err){toast(err.message)}};
refresh();setInterval(refresh,10000);'''

EMBEDDED_WEB = {
    "index.html": base64.b64encode(INDEX_HTML.encode()).decode(),
    "style.css": base64.b64encode(STYLE_CSS.encode()).decode(),
    "app.js": base64.b64encode(APP_JS.encode()).decode(),
}


@dataclass
class Config:
    universe: str = DEFAULT_UNIVERSE
    max_positions: int = 3
    position_pct: float = 10.0
    stop_loss_pct: float = 3.0
    take_profit_pct: float = 6.0
    daily_loss_limit_pct: float = 2.0
    min_score: float = 0.15
    poll_seconds: int = 60
    bar_minutes: int = 5
    initial_cash: float = 10_000.0

    def symbols(self):
        out=[]
        for raw in self.universe.split(','):
            s=raw.strip().upper()
            if not s or ':' not in s: continue
            m,t=s.split(':',1)
            if m in ('NASD','NYSE','AMEX') and t and s not in out: out.append(s)
        return out[:20]


class Store:
    def __init__(self, path: Path):
        self.path=path; self.lock=threading.RLock()
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS prices (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, symbol TEXT NOT NULL, price REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, side TEXT NOT NULL, symbol TEXT NOT NULL, qty REAL NOT NULL, price REAL NOT NULL, reason TEXT NOT NULL);
            ''')
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10); db.row_factory=sqlite3.Row; return db
    def get(self,key,default=None):
        with self.lock,self.connect() as db:
            row=db.execute('SELECT value FROM kv WHERE key=?',(key,)).fetchone(); return json.loads(row[0]) if row else default
    def set(self,key,value):
        with self.lock,self.connect() as db:
            db.execute('INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value,ensure_ascii=False)))
    def add_price(self,symbol,price):
        with self.lock,self.connect() as db:
            db.execute('INSERT INTO prices(ts,symbol,price) VALUES(?,?,?)',(now(),symbol,price))
            db.execute('DELETE FROM prices WHERE id NOT IN (SELECT id FROM prices ORDER BY id DESC LIMIT 2000)')
    def add_trade(self,side,symbol,qty,price,reason):
        with self.lock,self.connect() as db: db.execute('INSERT INTO trades(ts,side,symbol,qty,price,reason) VALUES(?,?,?,?,?,?)',(now(),side,symbol,qty,price,reason))
    def trades(self,limit=50):
        with self.lock,self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM trades ORDER BY id DESC LIMIT ?',(limit,)).fetchall()]


def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')


class SimulatedMarket:
    def __init__(self,store): self.store=store; self.rng=random.Random(20260914); self.last={}
    def quote(self,symbol):
        last=self.last.get(symbol,100+self.rng.random()*200); p=round(max(2,last*(1+0.0004+self.rng.gauss(0,.004))),2); self.last[symbol]=p; return p
    def bars(self,symbol,n=40,minutes=5):
        p=self.quote(symbol); vals=[]
        for _ in range(n): p=max(2,p*(1+self.rng.gauss(.0002,.006))); vals.append(round(p,2))
        return vals


class KISMarket:
    BASE_VTS='https://openapivts.koreainvestment.com:29443'; BASE_REAL='https://openapi.koreainvestment.com:9443'
    EXCHANGES={'NASD':'NAS','NYSE':'NYS','AMEX':'AMS'}
    def __init__(self,live=False):
        self.app_key=os.getenv('KIS_APP_KEY',''); self.app_secret=os.getenv('KIS_APP_SECRET',''); self.token=''; self.token_expires=0.0; self.live=live
        if not self.app_key or not self.app_secret: raise RuntimeError('KIS_APP_KEY와 KIS_APP_SECRET이 필요합니다')
        self.BASE=self.BASE_REAL if live else self.BASE_VTS
    def request(self,method,path,data=None,headers=None):
        body=json.dumps(data).encode() if data is not None else None
        req=urllib.request.Request(self.BASE+path,data=body,method=method,headers={'Content-Type':'application/json',**(headers or {})})
        try:
            with urllib.request.urlopen(req,timeout=15) as res: return json.loads(res.read())
        except urllib.error.HTTPError as e:
            detail=e.read().decode(errors='replace')[:500]; raise RuntimeError(f'KIS API 오류 {e.code}: {detail}') from e
    def access_token(self):
        if self.token and time.time()<self.token_expires: return self.token
        r=self.request('POST','/oauth2/tokenP',{'grant_type':'client_credentials','appkey':self.app_key,'appsecret':self.app_secret})
        self.token=r['access_token']; self.token_expires=time.time()+int(r.get('expires_in',3600))-60; return self.token
    def auth_headers(self,tr_id): return {'authorization':'Bearer '+self.access_token(),'appkey':self.app_key,'appsecret':self.app_secret,'tr_id':tr_id,'custtype':'P'}
    def quote(self,symbol):
        market,ticker=symbol.split(':',1); excd=self.EXCHANGES[market]
        q=urllib.parse.urlencode({'AUTH':'','EXCD':excd,'SYMB':ticker})
        r=self.request('GET','/uapi/overseas-price/v1/quotations/price?'+q,headers=self.auth_headers('HHDFS00000300'))
        if r.get('rt_cd') not in (None,'0'): raise RuntimeError(r.get('msg1','KIS 시세 조회 실패'))
        p=float((r.get('output') or {}).get('last',0) or 0)
        if p<=0: raise RuntimeError(f'{symbol} 현재가 응답이 비어 있습니다')
        return p
    def bars(self,symbol,n=40,minutes=5):
        market,ticker=symbol.split(':',1); excd=self.EXCHANGES[market]
        q=urllib.parse.urlencode({'AUTH':'','EXCD':excd,'SYMB':ticker,'NMIN':str(minutes),'PINC':'1','NEXT':'','NREC':str(min(120,max(20,n))),'FILL':'','KEYB':''})
        r=self.request('GET','/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice?'+q,headers=self.auth_headers('HHDFS76950200'))
        if r.get('rt_cd') not in (None,'0'): raise RuntimeError(r.get('msg1',f'{symbol} 분봉 조회 실패'))
        rows=r.get('output2') or []
        closes=[]
        for row in rows:
            try:
                v=float(row.get('last',0) or 0)
                if v>0: closes.append(v)
            except (TypeError,ValueError): pass
        if len(closes)<20: raise RuntimeError(f'{symbol} 분봉 데이터 부족({len(closes)}개)')
        # KIS 응답은 최신→과거인 경우가 있어 시간 문자열 기준으로 정렬한다.
        if rows and any(k in rows[0] for k in ('xymd','xhms')):
            pairs=[]
            for row in rows:
                try: pairs.append((str(row.get('xymd',''))+str(row.get('xhms','')),float(row.get('last',0) or 0)))
                except: pass
            closes=[p for _,p in sorted((x for x in pairs if x[1]>0),key=lambda z:z[0])]
        return closes[-n:]
    def hashkey(self,payload):
        r=self.request('POST','/uapi/hashkey',payload,{'appkey':self.app_key,'appsecret':self.app_secret}); v=r.get('HASH')
        if not v: raise RuntimeError('KIS 주문 해시키 생성 실패')
        return v


class KISLiveBroker:
    def __init__(self,store,config,market):
        if os.getenv('LIVE_TRADING_ACK')!='I_UNDERSTAND_REAL_ORDERS': raise RuntimeError('실전 주문 확인값이 없어 시작을 차단했습니다')
        self.store=store; self.config=config; self.market=market
        self.account=os.getenv('KIS_ACCOUNT_NO',''); self.product=os.getenv('KIS_PRODUCT_CODE','01'); self.max_order_usd=float(os.getenv('MAX_ORDER_USD','100'))
        if len(self.account)!=8: raise RuntimeError('KIS_ACCOUNT_NO는 계좌 앞 8자리여야 합니다')
        if not (10<=self.max_order_usd<=5000): raise RuntimeError('MAX_ORDER_USD는 10~5000달러 범위만 허용합니다')
        self._positions_cache=None; self._positions_at=0.0
    def positions(self,force=False):
        if self._positions_cache is not None and not force and time.time()-self._positions_at<8: return self._positions_cache
        q=urllib.parse.urlencode({'CANO':self.account,'ACNT_PRDT_CD':self.product,'OVRS_EXCG_CD':'NASD','TR_CRCY_CD':'USD','CTX_AREA_FK200':'','CTX_AREA_NK200':''})
        r=self.market.request('GET','/uapi/overseas-stock/v1/trading/inquire-balance?'+q,headers=self.market.auth_headers('TTTS3012R'))
        if r.get('rt_cd')!='0': raise RuntimeError(r.get('msg1','실계좌 잔고 조회 실패'))
        out={}
        for row in r.get('output1',[]) or []:
            try: qty=float(row.get('ovrs_cblc_qty',0) or 0)
            except: qty=0
            if qty<=0: continue
            ticker=str(row.get('ovrs_pdno','')).upper(); market=str(row.get('ovrs_excg_cd','NASD')).upper()
            if market in ('NAS','NASD'): market='NASD'
            elif market in ('NYS','NYSE'): market='NYSE'
            elif market in ('AMS','AMEX'): market='AMEX'
            try: avg=float(row.get('pchs_avg_pric',0) or 0)
            except: avg=0
            out[f'{market}:{ticker}']={'qty':qty,'avg_price':avg}
        self._positions_cache=out; self._positions_at=time.time(); self._clear_filled_pending(out); return out
    def _pending(self): return self.store.get('live_pending_orders',{}) or {}
    def _clear_filled_pending(self,positions):
        pend=self._pending(); changed=False
        for sym,p in list(pend.items()):
            current=float(positions.get(sym,{}).get('qty',0)); before=float(p.get('before_qty',0))
            filled=(p.get('side')=='BUY' and current>before) or (p.get('side')=='SELL' and current<before)
            expired=time.time()-float(p.get('epoch',0) or 0)>900
            if filled or expired: pend.pop(sym,None); changed=True
        if changed: self.store.set('live_pending_orders',pend)
    def buying_power(self,symbol,price):
        market,ticker=symbol.split(':',1)
        q=urllib.parse.urlencode({'CANO':self.account,'ACNT_PRDT_CD':self.product,'OVRS_EXCG_CD':market,'OVRS_ORD_UNPR':f'{max(price,.01):.2f}','ITEM_CD':ticker})
        r=self.market.request('GET','/uapi/overseas-stock/v1/trading/inquire-psamount?'+q,headers=self.market.auth_headers('TTTS3007R'))
        if r.get('rt_cd')!='0': raise RuntimeError(r.get('msg1','매수가능금액 조회 실패'))
        out=r.get('output') or {}
        for key in ('ovrs_ord_psbl_amt','echm_af_ord_psbl_amt','ord_psbl_frcr_amt','frcr_ord_psbl_amt1'):
            try:
                v=float(out.get(key,0) or 0)
                if v>0:return v
            except: pass
        return 0.0
    def _order(self,side,symbol,qty,price,reason):
        pend=self._pending()
        if symbol in pend: return False
        market,ticker=symbol.split(':',1); limit=round(price*(1.002 if side=='BUY' else .998),2)
        payload={'CANO':self.account,'ACNT_PRDT_CD':self.product,'OVRS_EXCG_CD':market,'PDNO':ticker,'ORD_QTY':str(int(qty)),'OVRS_ORD_UNPR':f'{limit:.2f}','CTAC_TLNO':'','MGCO_APTM_ODNO':'','SLL_TYPE':'00' if side=='SELL' else '','ORD_SVR_DVSN_CD':'0','ORD_DVSN':'00'}
        tr_id='TTTT1002U' if side=='BUY' else 'TTTT1006U'; headers=self.market.auth_headers(tr_id); headers['hashkey']=self.market.hashkey(payload)
        r=self.market.request('POST','/uapi/overseas-stock/v1/trading/order',payload,headers)
        if r.get('rt_cd')!='0': raise RuntimeError(r.get('msg1','실전 주문 거절'))
        order_no=(r.get('output') or {}).get('ODNO',''); before=float(self.positions(True).get(symbol,{}).get('qty',0))
        self.store.add_trade(side,symbol,qty,limit,reason+(f' · 주문 {order_no}' if order_no else ''))
        pend[symbol]={'side':side,'qty':qty,'before_qty':before,'order_no':order_no,'epoch':time.time()}; self.store.set('live_pending_orders',pend); self._positions_at=0
        return True
    def buy(self,symbol,price,budget,reason):
        if symbol in self.positions(): return False
        available=self.buying_power(symbol,price); spend=min(float(budget),available,self.max_order_usd); qty=int(spend/(price*1.002))
        return self._order('BUY',symbol,qty,price,reason) if qty>=1 else False
    def sell(self,symbol,price,reason):
        pos=self.positions(True).get(symbol); qty=int(float(pos.get('qty',0))) if pos else 0
        return self._order('SELL',symbol,qty,price,reason) if qty>=1 else False


class PaperBroker:
    def __init__(self,store,config):
        self.store=store; self.config=config
        if self.store.get('paper_cash') is None: self.store.set('paper_cash',config.initial_cash)
        if self.store.get('paper_positions') is None: self.store.set('paper_positions',{})
    def positions(self,force=False): return self.store.get('paper_positions',{}) or {}
    def buying_power(self,symbol,price): return float(self.store.get('paper_cash',self.config.initial_cash))
    def buy(self,symbol,price,budget,reason):
        ps=self.positions()
        if symbol in ps:return False
        cash=self.buying_power(symbol,price); qty=int(min(cash,budget)/price)
        if qty<1:return False
        self.store.set('paper_cash',round(cash-qty*price,2)); ps[symbol]={'qty':qty,'avg_price':price}; self.store.set('paper_positions',ps); self.store.add_trade('BUY',symbol,qty,price,reason); return True
    def sell(self,symbol,price,reason):
        ps=self.positions(); p=ps.get(symbol)
        if not p:return False
        cash=self.buying_power(symbol,price)+float(p['qty'])*price; self.store.set('paper_cash',round(cash,2)); self.store.add_trade('SELL',symbol,p['qty'],price,reason); ps.pop(symbol,None); self.store.set('paper_positions',ps); return True


class Engine:
    def __init__(self,store):
        self.store=store
        saved=store.get('config',{}) or {}
        # migrate from the older single-symbol config without crashing.
        allowed=set(Config.__dataclass_fields__); self.config=Config(**{k:v for k,v in saved.items() if k in allowed})
        self.trading_mode=os.getenv('TRADING_MODE','paper').lower(); self.live=self.trading_mode=='live'
        if self.live and len(os.getenv('DASHBOARD_PASSWORD',''))<10: raise RuntimeError('실전 모드는 10자 이상의 DASHBOARD_PASSWORD가 필요합니다')
        self.market=KISMarket(live=True) if self.live else (KISMarket(live=False) if os.getenv('MARKET_MODE','simulated').lower()=='kis_quote' else SimulatedMarket(store))
        self.broker=KISLiveBroker(store,self.config,self.market) if self.live else PaperBroker(store,self.config)
        # deploy/update 후 뜻하지 않은 즉시 실전 주문을 막기 위해 항상 정지 상태로 시작.
        self.running=False; self.store.set('running',False)
        self.stop_event=threading.Event(); self.thread=None; self.last_signal='대기'; self.last_candidates=[]; self.last_prices={}
    def start(self):
        self.running=True; self.store.set('running',True)
        if not self.thread or not self.thread.is_alive(): self.stop_event.clear(); self.thread=threading.Thread(target=self.loop,daemon=True); self.thread.start()
    def stop(self): self.running=False; self.store.set('running',False)
    def loop(self):
        while not self.stop_event.is_set():
            if self.running:
                try:self.scan(execute=True)
                except Exception as e:self.last_signal=f'오류: {e}'; self.stop()
            self.stop_event.wait(max(30,self.config.poll_seconds))
    def _score(self,symbol):
        closes=self.market.bars(symbol,40,self.config.bar_minutes)
        if len(closes)<20:return None
        last=float(closes[-1]); short=sum(closes[-5:])/5; long=sum(closes[-20:])/20
        trend=(short/long-1)*100 if long else 0; mom=(last/closes[-7]-1)*100 if len(closes)>=7 and closes[-7] else 0
        rets=[(closes[i]/closes[i-1]-1)*100 for i in range(max(1,len(closes)-12),len(closes)) if closes[i-1]]
        vol=statistics.pstdev(rets) if len(rets)>1 else 0
        score=trend*0.55+mom*0.45-vol*0.20
        eligible=last>long and mom>0 and score>=self.config.min_score
        self.last_prices[symbol]=last; self.store.add_price(symbol,last)
        return {'symbol':symbol,'price':round(last,4),'score':round(score,4),'trend_pct':round(trend,3),'momentum_pct':round(mom,3),'volatility':round(vol,3),'eligible':eligible}
    def _snapshot_positions(self):
        raw=self.broker.positions(True); out=[]
        for sym,p in raw.items():
            try: price=self.last_prices.get(sym) or self.market.quote(sym)
            except: price=float(p.get('avg_price',0) or 0)
            avg=float(p.get('avg_price',0) or 0); qty=float(p.get('qty',0) or 0); pnl=(price/avg-1)*100 if avg>0 else 0
            out.append({'symbol':sym,'qty':qty,'avg_price':avg,'price':price,'pnl_pct':pnl})
        return out
    def scan(self,execute=False):
        symbols=self.config.symbols()
        if not symbols: raise ValueError('감시 종목이 없습니다')
        candidates=[]; errors=[]
        for sym in symbols:
            try:
                c=self._score(sym)
                if c:candidates.append(c)
            except Exception as e: errors.append(f'{sym}: {e}')
            time.sleep(0.12 if self.live else 0)
        candidates.sort(key=lambda x:x['score'],reverse=True); self.last_candidates=candidates[:8]
        positions=self._snapshot_positions(); held={p['symbol']:p for p in positions}
        if not execute:
            self.last_signal=f'분석 완료 · 후보 {sum(1 for c in candidates if c["eligible"])}개' + (f' · 오류 {len(errors)}개' if errors else '')
            return self.state()
        # 일 손실 제한: 첫 정상 평가액을 당일 기준으로 저장한다.
        equity,cash=self._equity_and_cash(positions,candidates)
        day_key=datetime.now(timezone.utc).date().isoformat(); saved_day=self.store.get('equity_day')
        if saved_day!=day_key or float(self.store.get('day_start_equity',0) or 0)<=0:
            self.store.set('equity_day',day_key); self.store.set('day_start_equity',equity)
        baseline=float(self.store.get('day_start_equity',equity) or equity); day_pct=(equity/baseline-1)*100 if baseline>0 else 0
        if day_pct<=-self.config.daily_loss_limit_pct:
            for p in positions:
                try:self.broker.sell(p['symbol'],p['price'],'하루 손실 제한')
                except:pass
            self.last_signal='하루 손실 한도 도달 · 자동정지'; self.stop(); return self.state()
        # 1) 보유 종목 손절/익절 또는 순위 이탈 정리
        top_symbols=[c['symbol'] for c in candidates if c['eligible']][:self.config.max_positions]
        sold=0
        for p in positions:
            sym=p['symbol']; pnl=p['pnl_pct']; score=next((c['score'] for c in candidates if c['symbol']==sym),-999)
            reason=None
            if pnl<=-self.config.stop_loss_pct: reason='손절'
            elif pnl>=self.config.take_profit_pct: reason='익절'
            elif sym in symbols and sym not in top_symbols and score<0: reason='순위 이탈 교체'
            if reason:
                try:
                    if self.broker.sell(sym,p['price'],reason): sold+=1
                except Exception as e: errors.append(f'{sym} 매도: {e}')
        if sold:
            self.last_signal=f'{sold}종목 매도 주문'; return self.state()
        # 2) 상위 후보 중 빈 슬롯만큼 분산 매수
        positions=self._snapshot_positions(); held={p['symbol'] for p in positions}; slots=max(0,self.config.max_positions-len(positions)); bought=0
        if slots>0:
            equity,cash=self._equity_and_cash(positions,candidates)
            per_budget=max(0,equity*self.config.position_pct/100)
            for c in candidates:
                if bought>=slots:break
                if not c['eligible'] or c['symbol'] in held:continue
                try:
                    if self.broker.buy(c['symbol'],c['price'],per_budget,f'자동선정 점수 {c["score"]:.2f}'):
                        bought+=1; held.add(c['symbol'])
                except Exception as e: errors.append(f'{c["symbol"]} 매수: {e}')
        self.last_signal=(f'{bought}종목 매수 주문' if bought else f'조건 대기 · 상위 {", ".join(top_symbols[:3]) or "없음"}') + (f' · 오류 {len(errors)}' if errors else '')
        return self.state()
    def _equity_and_cash(self,positions=None,candidates=None):
        positions=positions if positions is not None else self._snapshot_positions()
        ref=next((c for c in (candidates or self.last_candidates) if c.get('price')),None)
        if not ref:
            sym=self.config.symbols()[0]; price=self.last_prices.get(sym) or self.market.quote(sym)
        else:sym,price=ref['symbol'],ref['price']
        cash=self.broker.buying_power(sym,price)
        holdings=sum(float(p['qty'])*float(p['price']) for p in positions)
        return cash+holdings,cash
    def update(self,raw):
        merged=asdict(self.config)
        for k in merged:
            if k in raw: merged[k]=raw[k]
        c=Config(**merged)
        if not c.symbols(): raise ValueError('감시 종목은 NASD:AAPL 같은 형식으로 1개 이상 입력하세요')
        if not (1<=c.max_positions<=5): raise ValueError('최대 보유종목은 1~5개만 가능합니다')
        if not (1<=c.position_pct<=20): raise ValueError('종목당 투자비중은 1~20%만 가능합니다')
        if c.max_positions*c.position_pct>60: raise ValueError('총 목표 투자비중은 60% 이하로 설정하세요')
        if not (.5<=c.stop_loss_pct<=10 and 1<=c.take_profit_pct<=20): raise ValueError('손절/익절 범위를 확인하세요')
        if not (30<=c.poll_seconds<=3600): raise ValueError('판단 주기는 30~3600초만 가능합니다')
        self.config=c; self.broker.config=c; self.store.set('config',asdict(c)); return self.state()
    def state(self):
        positions=self._snapshot_positions()
        try: equity,cash=self._equity_and_cash(positions,self.last_candidates)
        except Exception: equity,cash=0.0,0.0
        day_base=float(self.store.get('day_start_equity',equity) or 0); day_pct=(equity/day_base-1)*100 if day_base>0 else 0
        baseline=day_base if self.live else self.config.initial_cash
        profit=equity-baseline if baseline>0 else 0; profit_pct=(profit/baseline*100) if baseline>0 else 0
        return {'running':self.running,'mode':'KIS 실계좌 · 다종목 자동선정' if self.live else '테스트 · 다종목 자동선정','config':asdict(self.config),'cash':round(cash,2),'positions':positions,'candidates':self.last_candidates,'equity':round(equity,2),'profit':round(profit,2),'profit_pct':round(profit_pct,2),'day_profit_pct':round(day_pct,2),'last_signal':self.last_signal,'trades':self.store.trades(40)}


STORE=Store(DB_PATH); ENGINE=Engine(STORE)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args): pass
    def authenticated(self):
        password=os.getenv('DASHBOARD_PASSWORD','')
        if not password:return True
        expected='Basic '+base64.b64encode(('owner:'+password).encode()).decode()
        if self.headers.get('Authorization')==expected:return True
        self.send_response(401); self.send_header('WWW-Authenticate','Basic realm="Sajangnim Trader"'); self.end_headers(); return False
    def send_json(self,value,code=200):
        body=json.dumps(value,ensure_ascii=False).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if not self.authenticated():return
        path=urlparse(self.path).path
        if path=='/api/state':return self.send_json(ENGINE.state())
        if path=='/api/health':return self.send_json({'ok':True,'time':now()})
        name='index.html' if path=='/' else path.lstrip('/'); encoded=EMBEDDED_WEB.get(name)
        if not encoded:return self.send_json({'error':'not found'},404)
        body=base64.b64decode(encoded); mime='text/html' if name.endswith('.html') else 'text/css' if name.endswith('.css') else 'application/javascript'
        self.send_response(200); self.send_header('Content-Type',mime+'; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        if not self.authenticated():return
        try:
            n=int(self.headers.get('Content-Length','0')); raw=json.loads(self.rfile.read(n) or b'{}'); path=urlparse(self.path).path
            if path=='/api/start':ENGINE.start(); state=ENGINE.state()
            elif path=='/api/stop':ENGINE.stop(); state=ENGINE.state()
            elif path in ('/api/scan','/api/tick'):state=ENGINE.scan(execute=False)
            elif path=='/api/config':state=ENGINE.update(raw)
            else:return self.send_json({'error':'not found'},404)
            self.send_json({'ok':True,'state':state})
        except Exception as e:self.send_json({'error':str(e)},400)

def main():
    print(f'사장님 자동매매 다종목: http://127.0.0.1:{PORT}')
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()

if __name__=='__main__':main()
