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
    # KIS 조건검색이 일시 실패할 때만 쓰는 안전한 보조 후보군.
    "NASD:SOFI,NASD:INTC,NASD:CSCO,NASD:PYPL,NASD:PLTR,NASD:HOOD,"
    "NYSE:BAC,NYSE:F,NYSE:PFE,NYSE:T,NYSE:VZ,NYSE:GM,NYSE:NU,NYSE:SNAP"
)
CASH_REF_SYMBOL = "NASD:SOFI"
USD_KRW_RATE = float(os.getenv("USD_KRW_RATE", "1350"))

INDEX_HTML = r'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#101727"><title>사장님 자동매매</title><link rel="stylesheet" href="/style.css"></head><body><div class="shell"><main>
<header><div><small id="mode">-</small><h1>사장님 자동매매</h1></div><span id="status" class="pill">정지</span></header>
<section class="hero"><div><small>추정 총 평가금액</small><h2 id="equity">$0.00</h2><div class="sub-krw" id="equityKrw">₩0</div><span id="profit">$0.00 (0.00%)</span></div><button id="toggle">자동매매 시작</button></section>
<section class="grid"><article><small>매수가능금액</small><b id="cash">-</b><div class="sub-krw" id="cashKrw">₩0</div></article><article><small>보유 종목</small><b id="holdingCount">0개</b></article><article><small>최근 판단</small><b id="signal">대기</b></article><article><small>오늘 손익률</small><b id="daypnl">0.00%</b></article></section>
<section class="card"><div class="title"><h3>입출금 반영</h3><span>수익률 계산용</span></div><div class="capital-box"><div><small>총 투입원금</small><b id="principal">$0.00</b><div class="sub-krw" id="principalKrw">₩0</div></div><div class="capital-actions"><input id="cashflowAmount" type="number" step="0.01" min="0.01" placeholder="금액(달러)"><div class="action-row"><button type="button" id="depositBtn">입금 반영</button><button type="button" id="withdrawBtn" class="ghost">출금 반영</button></div></div></div></section>
<section class="market-panels"><section class="card"><div class="title"><h3>자동 선정 후보</h3><button id="scan" class="link">1회 분석</button></div><div id="candidates"></div></section><section class="card positions-card"><div class="title"><h3>현재 보유</h3><span>최대 <b id="maxpos">3</b>종목</span></div><div id="positions"></div></section></section>
<section class="card"><div class="title"><h3>자동매매 설정</h3><span>저장 즉시 적용</span></div><form id="settings">
<label>종목 선택<input value="실시간 자동 · 현재 자금으로 살 수 있는 종목만" disabled></label>
<div class="row"><label>최대 보유종목<input name="max_positions" type="number" min="1" max="5"></label><label>종목당 최대비중 %<input name="position_pct" type="number" step="1" min="10" max="70"></label></div>
<div class="row"><label>현금 보유비중 %<input name="cash_reserve_pct" type="number" step="1" min="10" max="30"></label><label>판단 주기(초)<input name="poll_seconds" type="number" min="30"></label></div>
<div class="row"><label>종목풀 갱신(초)<input name="universe_refresh_seconds" type="number" min="120" max="900"></label><label>최저 주가($)<input name="min_stock_price" type="number" step="0.5" min="1" max="20"></label></div><div class="row"><label>정밀분석 종목수<input name="max_dynamic_symbols" type="number" min="12" max="40"></label><label>실전 모드<input value="30종목 자동선정" disabled></label></div>
<div class="row"><label>손절 %<input name="stop_loss_pct" type="number" step="0.5"></label><label>최소 보유(분)<input name="min_hold_minutes" type="number" step="1" min="0" max="120"></label></div>
<div class="row"><label>수익보호 시작 %<input name="profit_protect_start_pct" type="number" step="0.1"></label><label>수익보호 고점이탈 %<input name="profit_protect_drop_pct" type="number" step="0.1"></label></div>
<div class="row"><label>트레일링 시작 %<input name="trailing_start_pct" type="number" step="0.5"></label><label>트레일링 고점이탈 %<input name="trailing_drop_pct" type="number" step="0.5"></label></div>
<div class="row"><label>추세교체 손실기준 %<input name="weak_exit_loss_pct" type="number" step="0.1"></label><label>추세악화 연속확인<input name="weak_exit_confirmations" type="number" step="1" min="1" max="5"></label></div>
<div class="row"><label>재매수 대기(분)<input name="rebuy_cooldown_minutes" type="number" step="1" min="0" max="240"></label><label>최소 점수<input name="min_score" type="number" step="0.05"></label></div>
<button class="secondary">설정 저장</button></form></section>
<section class="card"><div class="title"><h3>최근 거래</h3><span>실제 주문 기록</span></div><div id="trades"></div></section>
<p class="notice">⚠️ 자동 종목선정은 수익을 보장하지 않습니다. 점수 기반으로 후보를 비교하고, 최소보유·수익보호·트레일링·손절·재매수 쿨다운·일손실 제한을 적용합니다.</p>
</main><aside class="activity-panel"><div class="activity-head"><div><small>LIVE ENGINE</small><h3>실시간 작업창</h3></div><span id="activityState" class="pill">대기</span></div><div class="activity-meta" id="activityMeta">분석 준비 중</div><div id="activity" class="terminal"><div class="logline muted">엔진 로그가 여기에 표시됩니다.</div></div><p class="activity-note">API 키·계좌번호 같은 민감정보는 표시하지 않습니다.</p></aside></div><div id="toast"></div><script src="/app.js"></script></body></html>'''

STYLE_CSS = r''':root{font-family:system-ui,-apple-system,sans-serif;color:#edf2ff;background:#0a0f1c;color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:linear-gradient(160deg,#111a30,#080c16 55%);min-height:100vh}.shell{max-width:1180px;margin:auto;padding:24px 16px 60px;display:grid;grid-template-columns:minmax(0,760px) 360px;gap:18px;align-items:start}main{max-width:none;margin:0;padding:0}header,.title,.hero,.row{display:flex;align-items:center;justify-content:space-between;gap:12px}h1{font-size:23px;margin:4px 0}h2{font-size:36px;margin:8px 0}h3{margin:0;font-size:17px}small,.title span,label,.notice,.muted{color:#93a1bd}.pill{background:#33405b;padding:7px 12px;border-radius:999px;font-size:13px}.pill.on{background:#123f32;color:#52e3aa}.hero,.card{background:rgba(20,29,49,.94);border:1px solid #26334d;border-radius:20px;padding:20px;margin-top:16px;box-shadow:0 14px 40px #0004}.hero button,form button,.capital-actions button{border:0;border-radius:14px;background:#4777ff;color:#fff;font-weight:800;padding:15px 18px}.hero button.stop{background:#ef5b68}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}.grid article{background:#121b2e;border:1px solid #23304a;border-radius:16px;padding:15px;min-width:0}.grid b{display:block;margin-top:7px;overflow:hidden;text-overflow:ellipsis}.sub-krw{font-size:12px;color:#93a1bd;margin-top:4px}.hero .sub-krw{font-size:13px}.mini-krw{font-size:11px;color:#93a1bd;margin-left:4px}.capital-box{display:grid;grid-template-columns:minmax(180px,.9fr) minmax(0,1.1fr);gap:14px;align-items:end}.capital-box b{display:block;margin-top:7px;font-size:22px}.capital-actions input{margin-top:0}.action-row{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}.capital-actions .ghost{background:#23304a}.market-panels{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(260px,1fr);gap:16px;align-items:start}.market-panels .card{margin-top:16px}.positions-card{max-height:520px;overflow:auto}.title{margin-bottom:14px}.row label{width:50%}label{display:block;font-size:13px;margin:10px 0}input{display:block;width:100%;margin-top:7px;padding:13px;border-radius:12px;border:1px solid #34415a;background:#0d1424;color:#fff;font-size:15px}.secondary{width:100%;margin-top:10px}.link{background:transparent;border:0;color:#79a0ff;font-weight:700}.item{display:flex;justify-content:space-between;gap:12px;padding:12px 0;border-top:1px solid #29344a}.item:first-child{border-top:0}.buy{color:#ff6b76}.sell{color:#5b9dff}.score{font-weight:800}.good{color:#52e3aa}.bad{color:#ff6b76}.notice{text-align:center;line-height:1.6;font-size:13px}#toast{position:fixed;left:50%;bottom:28px;transform:translateX(-50%) translateY(90px);background:#edf2ff;color:#111827;padding:12px 18px;border-radius:12px;font-weight:700;transition:.25s;z-index:3;max-width:90%}#toast.show{transform:translateX(-50%) translateY(0)}.activity-panel{position:sticky;top:18px;background:#070b13;border:1px solid #26334d;border-radius:20px;padding:16px;height:calc(100vh - 36px);min-height:420px;box-shadow:0 14px 40px #0006;display:flex;flex-direction:column}.activity-head{display:flex;align-items:center;justify-content:space-between;gap:10px}.activity-head h3{margin-top:4px}.activity-meta{font-size:12px;color:#93a1bd;margin:12px 0;padding:9px 10px;border-radius:10px;background:#0d1424}.terminal{flex:1;overflow:auto;background:#03060b;border:1px solid #1c2739;border-radius:12px;padding:11px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:11.5px;line-height:1.55;white-space:pre-wrap}.logline{padding:3px 0;color:#d7e2f7}.logline .time{color:#6e7f9e}.logline.good{color:#52e3aa}.logline.warn{color:#ffd166}.logline.bad{color:#ff6b76}.activity-note{font-size:11px;color:#6f7d98;margin:9px 2px 0}.activity-panel .pill{font-size:11px;padding:6px 9px}@media(max-width:1050px){.shell{grid-template-columns:1fr;max-width:790px}.activity-panel{position:static;height:320px;min-height:320px}.market-panels{grid-template-columns:1fr}.capital-box{grid-template-columns:1fr}}@media(max-width:520px){.hero{align-items:flex-start}.hero button{padding:13px}.grid{grid-template-columns:1fr 1fr}.row{align-items:flex-start}.shell{padding:16px 12px 50px}.activity-panel{height:300px;min-height:300px}.market-panels{grid-template-columns:1fr}.positions-card{max-height:none}.action-row{grid-template-columns:1fr}}'''

APP_JS = r'''const $=s=>document.querySelector(s);let state=null;const money=n=>'$'+Number(n||0).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});const krw=(n,fx)=>'₩'+Math.round(Number(n||0)*Number(fx||1350)).toLocaleString('ko-KR');
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):null});const d=await r.json();if(!r.ok)throw Error(d.error||'요청 실패');return d.state||d}
function toast(t){$('#toast').textContent=t;$('#toast').classList.add('show');setTimeout(()=>$('#toast').classList.remove('show'),2200)}
function render(s){state=s;const fx=Number(s.fx_rate||1350);$('#mode').textContent=s.mode;$('#status').textContent=s.running?'자동 실행 중':'정지';$('#status').classList.toggle('on',s.running);$('#toggle').textContent=s.running?'자동매매 정지':'자동매매 시작';$('#toggle').classList.toggle('stop',s.running);$('#equity').textContent=money(s.equity);$('#equityKrw').textContent=krw(s.equity,fx);$('#profit').textContent=`${s.profit>=0?'+':''}${money(s.profit)} (${s.profit_pct}%)`;$('#profit').className=s.profit>=0?'good':'bad';$('#cash').textContent=money(s.cash);$('#cashKrw').textContent=krw(s.cash,fx);$('#principal').textContent=money(s.principal);$('#principalKrw').textContent=krw(s.principal,fx);$('#holdingCount').textContent=(s.positions||[]).length+'개';$('#signal').textContent=s.last_signal;$('#daypnl').textContent=(s.day_profit_pct>=0?'+':'')+s.day_profit_pct+'%';$('#daypnl').className=s.day_profit_pct>=0?'good':'bad';$('#maxpos').textContent=s.config.max_positions;
const cs=s.candidates||[];$('#candidates').innerHTML=cs.length?cs.map((c,i)=>`<div class="item"><div><b>${i+1}. ${c.symbol}</b><div class="muted">${money(c.price)} <span class="mini-krw">${krw(c.price,fx)}</span> · 추세 ${c.trend_pct}% · 모멘텀 ${c.momentum_pct}%${c.eligible?' · 매수조건 통과':' · 대기'}</div></div><div class="score ${c.eligible?'good':''}">${c.score.toFixed(2)}</div></div>`).join(''):'<p class="muted">현재 자금으로 살 수 있는 후보를 찾는 중입니다.</p>';
const ps=s.positions||[];$('#positions').innerHTML=ps.length?ps.map(p=>`<div class="item"><div><b>${p.symbol} · ${p.qty}주</b><div class="muted">평단 ${money(p.avg_price)} <span class="mini-krw">${krw(p.avg_price,fx)}</span> · 현재 ${money(p.price)} <span class="mini-krw">${krw(p.price,fx)}</span> · 보유 ${Math.floor(p.hold_minutes||0)}분${p.profit_protect_active?` · 수익보호 ON`:''}${p.trailing_active?` · 트레일링 ON · 고점 ${money(p.trailing_peak)} <span class="mini-krw">${krw(p.trailing_peak,fx)}</span> · 매도선 ${money(p.trailing_stop)} <span class="mini-krw">${krw(p.trailing_stop,fx)}</span>`:''}</div></div><div class="${p.pnl_pct>=0?'good':'bad'}">${p.pnl_pct>=0?'+':''}${p.pnl_pct.toFixed(2)}%</div></div>`).join(''):'<p class="muted">보유 종목이 없습니다.</p>';
Object.entries(s.config).forEach(([k,v])=>{let e=document.querySelector(`[name=${k}]`);if(e&&document.activeElement!==e)e.value=v});
$('#trades').innerHTML=s.trades.length?s.trades.map(t=>`<div class="item"><div><b class="${t.side==='BUY'?'buy':'sell'}">${t.side==='BUY'?'매수':'매도'} ${t.symbol} ${t.qty}주</b><div class="muted">${t.reason}</div></div><div>${money(t.price)}<div class="muted">${t.ts.slice(5,16).replace('T',' ')}</div></div></div>`).join(''):'<p class="muted">아직 거래 기록이 없습니다.</p>';const acts=s.activity||[];$('#activityState').textContent=s.running?'실전 자동':'대기';$('#activityState').classList.toggle('on',s.running);$('#activityMeta').textContent=`분석풀 ${s.dynamic_pool?.length||0}/${s.config.max_dynamic_symbols} · 갱신 ${s.config.universe_refresh_seconds}초 · 판단 ${s.config.poll_seconds}초`;$('#activity').innerHTML=acts.length?acts.map(a=>{let tm=new Date(a.ts).toLocaleTimeString('ko-KR',{hour12:false});return `<div class="logline ${a.level||''}"><span class="time">${tm}</span> ${a.message}</div>`}).join(''):'<div class="logline muted">엔진 로그가 여기에 표시됩니다.</div>';$('#activity').scrollTop=$('#activity').scrollHeight}
async function refresh(){try{render(await api('/api/state'))}catch(e){toast(e.message)}}
$('#scan').onclick=async()=>{try{render(await api('/api/scan',{}));toast('분석 완료 · 주문은 하지 않았어요')}catch(e){toast(e.message)}};
$('#toggle').onclick=async()=>{try{render(await api(state.running?'/api/stop':'/api/start',{}));toast(state.running?'자동매매 시작':'자동매매 정지')}catch(e){toast(e.message)}};
$('#settings').onsubmit=async e=>{e.preventDefault();let d=Object.fromEntries(new FormData(e.target));for(let k of ['max_positions','position_pct','cash_reserve_pct','stop_loss_pct','profit_protect_start_pct','profit_protect_drop_pct','trailing_start_pct','trailing_drop_pct','min_hold_minutes','weak_exit_loss_pct','weak_exit_confirmations','rebuy_cooldown_minutes','min_score','poll_seconds','universe_refresh_seconds','min_stock_price','max_dynamic_symbols'])d[k]=Number(d[k]);try{render(await api('/api/config',d));toast('설정 저장 완료')}catch(err){toast(err.message)}};
async function submitCashflow(kind){const amount=Number($('#cashflowAmount').value||0);if(!(amount>0))return toast('금액을 먼저 넣어줘');try{render(await api('/api/cashflow',{kind,amount}));$('#cashflowAmount').value='';toast(kind==='deposit'?'입금 반영 완료':'출금 반영 완료')}catch(err){toast(err.message)}}
$('#depositBtn').onclick=()=>submitCashflow('deposit');
$('#withdrawBtn').onclick=()=>submitCashflow('withdraw');
refresh();setInterval(refresh,3000);'''

EMBEDDED_WEB = {
    "index.html": base64.b64encode(INDEX_HTML.encode()).decode(),
    "style.css": base64.b64encode(STYLE_CSS.encode()).decode(),
    "app.js": base64.b64encode(APP_JS.encode()).decode(),
}


@dataclass
class Config:
    universe: str = DEFAULT_UNIVERSE
    max_positions: int = 3
    position_pct: float = 45.0
    cash_reserve_pct: float = 15.0
    stop_loss_pct: float = 3.0
    take_profit_pct: float = 6.0  # legacy: 이전 설정 호환용, 매도 판단에는 사용하지 않음
    trailing_start_pct: float = 4.0
    trailing_drop_pct: float = 1.5
    profit_protect_start_pct: float = 1.0
    profit_protect_drop_pct: float = 0.8
    min_hold_minutes: int = 15
    weak_exit_loss_pct: float = 1.0
    weak_exit_confirmations: int = 2
    rebuy_cooldown_minutes: int = 30
    daily_loss_limit_pct: float = 2.0
    min_score: float = 0.15
    poll_seconds: int = 30
    universe_refresh_seconds: int = 120
    min_stock_price: float = 3.0
    max_dynamic_symbols: int = 30
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
        # KIS 초당 호출 제한을 넘지 않도록 모든 REST 호출을 직렬화한다.
        self._api_lock=threading.RLock(); self._last_api_call=0.0; self._min_api_interval=float(os.getenv('KIS_MIN_API_INTERVAL','0.50'))
    def request(self,method,path,data=None,headers=None):
        body=json.dumps(data).encode() if data is not None else None
        last_error=None
        for attempt in range(4):
            with self._api_lock:
                wait=self._min_api_interval-(time.monotonic()-self._last_api_call)
                if wait>0: time.sleep(wait)
                req=urllib.request.Request(self.BASE+path,data=body,method=method,headers={'Content-Type':'application/json',**(headers or {})})
                try:
                    self._last_api_call=time.monotonic()
                    with urllib.request.urlopen(req,timeout=15) as res: return json.loads(res.read())
                except urllib.error.HTTPError as e:
                    self._last_api_call=time.monotonic()
                    detail=e.read().decode(errors='replace')[:800]
                    last_error=RuntimeError(f'KIS API 오류 {e.code}: {detail}')
                    # EGW00201 = 초당 거래건수 초과. 잠시 쉬고 재시도한다.
                    if 'EGW00201' in detail and attempt<3:
                        time.sleep(1.0+attempt*0.7)
                        continue
                    raise last_error from e
        raise last_error or RuntimeError('KIS API 호출 실패')
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
    def search_affordable(self,min_price,max_price,limit=90):
        """KIS 해외주식 조건검색을 단계적으로 완화해 넓은 1차 후보군을 만든다."""
        if max_price < min_price:
            return []
        market_names={'NAS':'NASD','NYS':'NYSE','AMS':'AMEX'}
        dedup={}
        # 1차는 유동성 높은 종목, 부족하면 단계적으로 완화한다.
        profiles=((100000,1000),(50000,500),(20000,200))
        for min_volume,min_amount in profiles:
            for excd in ('NAS','NYS','AMS'):
                params={
                    'AUTH':'','EXCD':excd,
                    'CO_YN_PRICECUR':'1','CO_ST_PRICECUR':f'{min_price:.2f}','CO_EN_PRICECUR':f'{max_price:.2f}',
                    'CO_YN_RATE':'','CO_ST_RATE':'','CO_EN_RATE':'',
                    'CO_YN_VALX':'','CO_ST_VALX':'','CO_EN_VALX':'',
                    'CO_YN_SHAR':'','CO_ST_SHAR':'','CO_EN_SHAR':'',
                    'CO_YN_VOLUME':'1','CO_ST_VOLUME':str(min_volume),'CO_EN_VOLUME':'',
                    'CO_YN_AMT':'1','CO_ST_AMT':str(min_amount),'CO_EN_AMT':'',
                    'CO_YN_EPS':'','CO_ST_EPS':'','CO_EN_EPS':'',
                    'CO_YN_PER':'','CO_ST_PER':'','CO_EN_PER':'','KEYB':''
                }
                q=urllib.parse.urlencode(params)
                try:
                    r=self.request('GET','/uapi/overseas-price/v1/quotations/inquire-search?'+q,headers=self.auth_headers('HHDFS76410000'))
                except Exception:
                    continue
                if r.get('rt_cd') not in (None,'0'):
                    continue
                data=[]
                for key in ('output2','output1','output'):
                    value=r.get(key)
                    if isinstance(value,list): data.extend(value)
                    elif isinstance(value,dict) and value.get('symb'): data.append(value)
                for row in data:
                    ticker=str(row.get('symb','') or '').strip().upper()
                    if not ticker or len(ticker)>8 or any(ch not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ.-' for ch in ticker):
                        continue
                    tradable=str(row.get('e_ordyn','') or '').strip().upper()
                    if tradable in ('0','N'):
                        continue
                    try:
                        price=float(row.get('last',0) or 0); vol=float(row.get('tvol',0) or 0); amt=float(row.get('avol',0) or 0); rate=float(row.get('rate',0) or 0)
                    except (TypeError,ValueError):
                        continue
                    if price < min_price or price > max_price or vol < min_volume:
                        continue
                    symbol=f"{market_names[excd]}:{ticker}"
                    item={'symbol':symbol,'price':price,'volume':vol,'amount':amt,'day_rate':rate}
                    old=dedup.get(symbol)
                    if old is None or (item['amount'],item['volume'])>(old['amount'],old['volume']):
                        dedup[symbol]=item
            if len(dedup)>=limit:
                break
        ranked=sorted(dedup.values(),key=lambda x:(x['amount'],x['volume'],abs(x['day_rate'])),reverse=True)
        return ranked[:max(30,int(limit))]

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
        self._buying_power_cache=None; self._buying_power_at=0.0
    def positions(self,force=False):
        if self._positions_cache is not None and not force and time.time()-self._positions_at<30: return self._positions_cache
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
    def buying_power(self,symbol,price,force=False):
        if self._buying_power_cache is not None and not force and time.time()-self._buying_power_at<30:
            return float(self._buying_power_cache)
        market,ticker=symbol.split(':',1)
        q=urllib.parse.urlencode({'CANO':self.account,'ACNT_PRDT_CD':self.product,'OVRS_EXCG_CD':market,'OVRS_ORD_UNPR':f'{max(price,.01):.2f}','ITEM_CD':ticker})
        r=self.market.request('GET','/uapi/overseas-stock/v1/trading/inquire-psamount?'+q,headers=self.market.auth_headers('TTTS3007R'))
        if r.get('rt_cd')!='0': raise RuntimeError(r.get('msg1','매수가능금액 조회 실패'))
        out=r.get('output') or {}
        value=0.0
        for key in ('ovrs_ord_psbl_amt','echm_af_ord_psbl_amt','ord_psbl_frcr_amt','frcr_ord_psbl_amt1'):
            try:
                v=float(out.get(key,0) or 0)
                if v>0:
                    value=v; break
            except: pass
        self._buying_power_cache=value; self._buying_power_at=time.time()
        return value
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
        pend[symbol]={'side':side,'qty':qty,'before_qty':before,'order_no':order_no,'epoch':time.time()}; self.store.set('live_pending_orders',pend); self._positions_at=0; self._buying_power_at=0
        return True
    def buy(self,symbol,price,budget,reason):
        if symbol in self.positions(): return False
        available=self.buying_power(symbol,price,force=True); spend=min(float(budget),available,self.max_order_usd); qty=int(spend/(price*1.002))
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
        # 이번 버전부터 시장 1차필터 후 30종목을 정밀 분석한다.
        if self.config.max_dynamic_symbols < 30: self.config.max_dynamic_symbols=30
        self.trading_mode=os.getenv('TRADING_MODE','paper').lower(); self.live=self.trading_mode=='live'
        if self.live and len(os.getenv('DASHBOARD_PASSWORD',''))<10: raise RuntimeError('실전 모드는 10자 이상의 DASHBOARD_PASSWORD가 필요합니다')
        self.market=KISMarket(live=True) if self.live else (KISMarket(live=False) if os.getenv('MARKET_MODE','simulated').lower()=='kis_quote' else SimulatedMarket(store))
        self.broker=KISLiveBroker(store,self.config,self.market) if self.live else PaperBroker(store,self.config)
        # deploy/update 후 뜻하지 않은 즉시 실전 주문을 막기 위해 항상 정지 상태로 시작.
        self.running=False; self.store.set('running',False)
        self.stop_event=threading.Event(); self.thread=None; self.last_signal='대기'; self.last_candidates=[]; self.last_prices={}; self.dynamic_symbols=[]; self.dynamic_meta={}; self.dynamic_updated_at=0.0; self.dynamic_price_cap=0.0; self.trailing_peaks=self.store.get('trailing_peaks',{}) or {}; self.profit_peaks=self.store.get('profit_peaks',{}) or {}; self.entry_times=self.store.get('position_entry_times',{}) or {}; self.last_sell_times=self.store.get('last_sell_times',{}) or {}; self.weak_counts=self.store.get('weak_exit_counts',{}) or {}; self.activity_lock=threading.RLock(); self.activity=[]; self._log('엔진 준비 완료 · 실전 주문은 시작 버튼 전까지 정지','good')
    def _log(self,message,level=''):
        with self.activity_lock:
            self.activity.append({'ts':now(),'message':str(message)[:220],'level':level})
            self.activity=self.activity[-120:]
    def start(self):
        self._log('▶ 실전 자동매매 시작 요청','warn')
        self.running=True; self.store.set('running',True)
        if not self.thread or not self.thread.is_alive(): self.stop_event.clear(); self.thread=threading.Thread(target=self.loop,daemon=True); self.thread.start()
    def stop(self):
        self.running=False; self.store.set('running',False); self._log('■ 자동매매 정지','warn')
    def loop(self):
        while not self.stop_event.is_set():
            if self.running:
                try:self.scan(execute=True)
                except Exception as e:self.last_signal=f'오류: {e}'; self._log(f'ERROR {e}','bad'); self.stop()
            self.stop_event.wait(max(30,self.config.poll_seconds))
    def _reference_cash(self,force=False):
        price=self.last_prices.get(CASH_REF_SYMBOL,10.0) or 10.0
        try:
            return float(self.broker.buying_power(CASH_REF_SYMBOL,price,force=force))
        except TypeError:
            return float(self.broker.buying_power(CASH_REF_SYMBOL,price))

    def _discover_symbols(self,cash,equity,held_symbols,force=False):
        age=time.time()-self.dynamic_updated_at
        refresh=max(120,int(self.config.universe_refresh_seconds))
        if self.dynamic_symbols and age < (30 if force else refresh):
            return list(dict.fromkeys(self.dynamic_symbols+list(held_symbols)))
        available=max(0.0,cash*(1-self.config.cash_reserve_pct/100))
        per_cap=max(0.0,equity*self.config.position_pct/100)
        price_cap=max(0.0,min(available,per_cap)/1.002)
        self.dynamic_price_cap=price_cap
        discovery_limit=max(60,int(self.config.max_dynamic_symbols)*3)
        self._log(f'[FILTER] 미국 3개 거래소 1차 탐색 · 목표 {discovery_limit}개 · 주가 ${self.config.min_stock_price:.2f}~${price_cap:.2f}','')
        discovered=[]; meta={}
        if isinstance(self.market,KISMarket) and price_cap>=self.config.min_stock_price:
            try:
                rows=self.market.search_affordable(self.config.min_stock_price,price_cap,discovery_limit)
                discovered=[r['symbol'] for r in rows]
                meta={r['symbol']:r for r in rows}
                self._log(f'[POOL] 1차 후보 {len(discovered)}개 · 상위 {min(len(discovered),self.config.max_dynamic_symbols)}개 정밀분석','good')
            except Exception as e:
                self.store.set('last_discovery_error',str(e)); self._log(f'[POOL] 조건검색 오류 · {e}','bad')
        if not discovered:
            self._log('[POOL] 조건검색 결과 없음 · 보조 후보군 사용','warn')
            discovered=self.config.symbols()
            meta={sym:{} for sym in discovered}
        # 거래대금/거래량 순위 상위 종목만 분봉 정밀분석해 API 폭주를 막는다.
        self.dynamic_symbols=list(dict.fromkeys(discovered))[:self.config.max_dynamic_symbols]
        self.dynamic_meta=meta; self.dynamic_updated_at=time.time()
        return list(dict.fromkeys(self.dynamic_symbols+list(held_symbols)))

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
    def _snapshot_positions(self,force=False):
        raw=self.broker.positions(force); out=[]
        for sym,p in raw.items():
            try: price=self.last_prices.get(sym) or self.market.quote(sym)
            except: price=float(p.get('avg_price',0) or 0)
            avg=float(p.get('avg_price',0) or 0); qty=float(p.get('qty',0) or 0); pnl=(price/avg-1)*100 if avg>0 else 0
            out.append({'symbol':sym,'qty':qty,'avg_price':avg,'price':price,'pnl_pct':pnl})
        return out
    def _sync_position_state(self,positions):
        held={p['symbol'] for p in positions}; now_epoch=time.time(); changed=False
        for bucket_name,bucket in (('trailing_peaks',self.trailing_peaks),('profit_peaks',self.profit_peaks),('position_entry_times',self.entry_times),('weak_exit_counts',self.weak_counts)):
            for sym in list(bucket):
                if sym not in held:
                    bucket.pop(sym,None); changed=True
            if bucket_name=='position_entry_times':
                for sym in held:
                    if sym not in bucket:
                        bucket[sym]=now_epoch; changed=True
            if changed: self.store.set(bucket_name,bucket)
        # 오래된 재매수 쿨다운 기록은 정리한다.
        cutoff=now_epoch-max(3600,self.config.rebuy_cooldown_minutes*60*4)
        if any(float(v or 0)<cutoff for v in self.last_sell_times.values()):
            self.last_sell_times={k:v for k,v in self.last_sell_times.items() if float(v or 0)>=cutoff}
            self.store.set('last_sell_times',self.last_sell_times)

    def scan(self,execute=False):
        errors=[]
        self._log('[SCAN] 실전 주문 포함 자동판단 시작' if execute else '[SCAN] 1회 분석 시작 · 주문 없음','warn' if execute else '')
        # 먼저 계좌를 읽고, 그 돈으로 실제 1주를 살 수 있는 가격 상한을 계산한 뒤 종목 풀을 자동 구성한다.
        positions=self._snapshot_positions(force=True); self._sync_position_state(positions); held_symbols={p['symbol'] for p in positions}; self._log(f'[ACCOUNT] 보유 {len(positions)}종목 확인')
        try:
            cash=self._reference_cash(force=True); self._log(f'[ACCOUNT] 매수가능금액 ${cash:.2f}','good')
        except Exception as e:
            raise RuntimeError(f'매수가능금액 조회 실패: {e}')
        holdings_value=sum(float(p['qty'])*float(p['price']) for p in positions)
        equity=cash+holdings_value
        symbols=self._discover_symbols(cash,equity,held_symbols,force=not execute)
        if not symbols:
            raise ValueError('현재 자금으로 분석할 종목을 찾지 못했습니다')
        candidates=[]
        total=len(symbols)
        for idx,sym in enumerate(symbols,1):
            self._log(f'[SCORE {idx:02d}/{total:02d}] {sym} 5분봉 분석 중')
            try:
                c=self._score(sym)
                if c:
                    m=self.dynamic_meta.get(sym,{})
                    c['volume']=float(m.get('volume',0) or 0); c['day_rate']=float(m.get('day_rate',0) or 0)
                    candidates.append(c); self._log(f'[SCORE] {sym} 점수 {c["score"]:.2f} · {"통과" if c["eligible"] else "대기"}', 'good' if c['eligible'] else '')
            except Exception as e:
                errors.append(f'{sym}: {e}'); self._log(f'[SCORE] {sym} 오류 · {e}','bad')
        candidates.sort(key=lambda x:x['score'],reverse=True)
        reserve_cash=max(0.0,cash*self.config.cash_reserve_pct/100)
        max_single_budget=min(max(0.0,equity*self.config.position_pct/100),max(0.0,cash-reserve_cash))
        for c in candidates:
            c['affordable']=bool(c['price']*1.002<=max_single_budget)
        # 화면에는 비싼 종목을 아예 숨기고 현재 계좌가 실제 살 수 있는 종목만 노출한다.
        affordable=[c for c in candidates if c['affordable']]
        self.last_candidates=sorted(affordable,key=lambda c:(1 if c['eligible'] else 0,c['score']),reverse=True)[:8]
        pool_count=len([s for s in self.dynamic_symbols if s not in held_symbols])
        if not execute:
            ready=sum(1 for c in affordable if c['eligible'])
            self.last_signal=f'실시간 종목풀 {pool_count}개 · 매수조건 통과 {ready}개' + (f' · 오류 {len(errors)}개' if errors else ''); self._log(f'[DONE] 분석 완료 · 풀 {pool_count}개 · 통과 {ready}개 · 주문 없음','good')
            self.store.set('last_scan_errors',errors[-5:] if errors else [])
            return self.state()

        day_key=datetime.now(timezone.utc).date().isoformat(); saved_day=self.store.get('equity_day')
        if saved_day!=day_key or float(self.store.get('day_start_equity',0) or 0)<=0:
            self.store.set('equity_day',day_key); self.store.set('day_start_equity',equity)
        baseline=float(self.store.get('day_start_equity',equity) or equity); day_pct=(equity/baseline-1)*100 if baseline>0 else 0
        if day_pct<=-self.config.daily_loss_limit_pct:
            for p in positions:
                try:self.broker.sell(p['symbol'],p['price'],'하루 손실 제한')
                except:pass
            self.last_signal='하루 손실 한도 도달 · 자동정지'; self.stop(); return self.state()

        top_symbols=[c['symbol'] for c in affordable if c['eligible']][:self.config.max_positions]
        sold=0; state_changed=False; now_epoch=time.time()
        for p in positions:
            sym=p['symbol']; pnl=float(p['pnl_pct']); price=float(p['price']); score=next((c['score'] for c in candidates if c['symbol']==sym),-999)
            reason=None
            entered=float(self.entry_times.get(sym,now_epoch) or now_epoch); hold_minutes=max(0.0,(now_epoch-entered)/60)
            # +1%부터 작은 수익을 지키는 완만한 보호선
            ppeak=float(self.profit_peaks.get(sym,0) or 0)
            if pnl>=self.config.profit_protect_start_pct or ppeak>0:
                if price>ppeak:
                    self.profit_peaks[sym]=price; ppeak=price; state_changed=True
            protect_stop=ppeak*(1-self.config.profit_protect_drop_pct/100) if ppeak>0 else 0
            # +4%부터는 더 넓은 트레일링으로 상승을 따라간다.
            tpeak=float(self.trailing_peaks.get(sym,0) or 0)
            if pnl>=self.config.trailing_start_pct or tpeak>0:
                if price>tpeak:
                    self.trailing_peaks[sym]=price; tpeak=price; state_changed=True
                    self._log(f'[TRAIL] {sym} 최고가 ${tpeak:.2f} · 이탈 {self.config.trailing_drop_pct:.1f}%','good')
            trail_stop=tpeak*(1-self.config.trailing_drop_pct/100) if tpeak>0 else 0
            if pnl<=-self.config.stop_loss_pct:
                reason='손절'
            elif tpeak>0 and price<=trail_stop:
                reason=f'트레일링 익절 · 고점 ${tpeak:.2f} 대비 {self.config.trailing_drop_pct:.1f}% 이탈'
            elif tpeak<=0 and ppeak>0 and price<=protect_stop:
                reason=f'수익 보호 · 고점 대비 {self.config.profit_protect_drop_pct:.1f}% 이탈'
            else:
                weak=(hold_minutes>=self.config.min_hold_minutes and pnl<=-self.config.weak_exit_loss_pct and top_symbols and sym not in top_symbols and score<0)
                if weak:
                    cnt=int(self.weak_counts.get(sym,0) or 0)+1; self.weak_counts[sym]=cnt; state_changed=True
                    self._log(f'[HOLD] {sym} 추세악화 {cnt}/{self.config.weak_exit_confirmations} · 손익 {pnl:+.2f}%','warn')
                    if cnt>=self.config.weak_exit_confirmations:
                        reason=f'추세 약화 확인 {cnt}회 · 손실 {pnl:.2f}%'
                elif int(self.weak_counts.get(sym,0) or 0)!=0:
                    self.weak_counts[sym]=0; state_changed=True
                if hold_minutes<self.config.min_hold_minutes and not reason:
                    self._log(f'[HOLD] {sym} 최소보유 {hold_minutes:.0f}/{self.config.min_hold_minutes}분 · 손익 {pnl:+.2f}%')
            if reason:
                try:
                    self._log(f'[SELL] {sym} {reason} 주문 시도','warn')
                    if self.broker.sell(sym,p['price'],reason):
                        sold+=1; self.trailing_peaks.pop(sym,None); self.profit_peaks.pop(sym,None); self.entry_times.pop(sym,None); self.weak_counts.pop(sym,None); self.last_sell_times[sym]=time.time(); state_changed=True; self._log(f'[SELL] {sym} 주문 접수','good')
                except Exception as e: errors.append(f'{sym} 매도: {e}'); self._log(f'[SELL] {sym} 실패 · {e}','bad')
        if state_changed:
            self.store.set('trailing_peaks',self.trailing_peaks); self.store.set('profit_peaks',self.profit_peaks); self.store.set('position_entry_times',self.entry_times); self.store.set('weak_exit_counts',self.weak_counts); self.store.set('last_sell_times',self.last_sell_times)
        if sold:
            self.last_signal=f'{sold}종목 매도 주문 · 다음 주기에 재선정'; return self.state()

        positions=self._snapshot_positions(); held={p['symbol'] for p in positions}; slots=max(0,self.config.max_positions-len(positions)); bought=0
        if slots>0:
            # 매수 직전 캐시된 매수가능금액을 사용해 API 호출 폭주를 막는다.
            cash=self._reference_cash(force=False); available_cash=max(0.0,cash-cash*self.config.cash_reserve_pct/100)
            per_cap=max(0.0,(cash+sum(float(p['qty'])*float(p['price']) for p in positions))*self.config.position_pct/100)
            for c in affordable:
                if bought>=slots or available_cash<=0: break
                if not c['eligible'] or c['symbol'] in held: continue
                last_sell=float(self.last_sell_times.get(c['symbol'],0) or 0)
                if last_sell and time.time()-last_sell < self.config.rebuy_cooldown_minutes*60:
                    self._log(f'[COOLDOWN] {c["symbol"]} 재매수 대기 중'); continue
                price=float(c['price']); one_share=price*1.002
                if one_share>available_cash or one_share>per_cap: continue
                remaining_slots=max(1,slots-bought); split_budget=available_cash/remaining_slots
                budget=min(available_cash,per_cap,max(split_budget,one_share))
                try:
                    self._log(f'[BUY] {c["symbol"]} 예산 ${budget:.2f} · 점수 {c["score"]:.2f} 주문 시도','warn')
                    if self.broker.buy(c['symbol'],price,budget,f'실시간 자동선정 점수 {c["score"]:.2f}'):
                        bought+=1; held.add(c['symbol']); available_cash=max(0.0,available_cash-budget); self.entry_times[c['symbol']]=time.time(); self.profit_peaks.pop(c['symbol'],None); self.trailing_peaks.pop(c['symbol'],None); self.weak_counts[c['symbol']]=0; self.store.set('position_entry_times',self.entry_times); self.store.set('profit_peaks',self.profit_peaks); self.store.set('trailing_peaks',self.trailing_peaks); self.store.set('weak_exit_counts',self.weak_counts); self._log(f'[BUY] {c["symbol"]} 주문 접수 · 최소보유 {self.config.min_hold_minutes}분','good')
                except Exception as e: errors.append(f'{c["symbol"]} 매수: {e}'); self._log(f'[BUY] {c["symbol"]} 실패 · {e}','bad')
        self.last_signal=(f'{bought}종목 매수 주문' if bought else f'조건 대기 · 후보 {", ".join(top_symbols[:3]) or "없음"}') + (f' · 오류 {len(errors)}' if errors else ''); self._log(f'[WAIT] {self.last_signal}','good' if bought else '')
        self.store.set('last_scan_errors',errors[-5:] if errors else [])
        return self.state()

    def _principal_key(self):
        return 'live_principal' if self.live else 'paper_principal'
    def _ensure_principal(self,equity):
        key=self._principal_key()
        default=self.config.initial_cash if not self.live else max(0.0,float(equity or 0))
        principal=float(self.store.get(key,default) or 0)
        if principal<=0 and default>0:
            principal=round(default,2); self.store.set(key,principal)
            if self.live:
                self.store.set('equity_day',datetime.now(timezone.utc).date().isoformat()); self.store.set('day_start_equity',principal)
                self._log(f'[CAPITAL] 새 수익 기준 설정 ${principal:.2f} · 이전 입금증가분은 수익에서 제외','good')
        return principal
    def adjust_cashflow(self,kind,amount):
        amount=float(amount or 0)
        if amount<=0: raise ValueError('금액은 0보다 커야 합니다')
        signed=amount if kind=='deposit' else -amount if kind=='withdraw' else None
        if signed is None: raise ValueError('kind는 deposit 또는 withdraw만 가능합니다')
        try: positions=self._snapshot_positions(force=True)
        except Exception: positions=[]
        try: equity,_=self._equity_and_cash(positions,self.last_candidates,force_cash=True)
        except Exception: equity=0.0
        principal=self._ensure_principal(equity)+signed
        if principal<0: raise ValueError('총 투입원금이 0보다 작아질 수 없습니다')
        self.store.set(self._principal_key(),round(principal,2))
        day_key=datetime.now(timezone.utc).date().isoformat()
        if self.store.get('equity_day')==day_key:
            day_base=float(self.store.get('day_start_equity',0) or 0)
            if day_base>0: self.store.set('day_start_equity',round(day_base+signed,2))
        self._log(f"[CAPITAL] {'입금' if signed>0 else '출금'} 반영 ${abs(signed):.2f} · 총 투입원금 ${principal:.2f}",'warn')
        return self.state()
    def _equity_and_cash(self,positions=None,candidates=None,force_cash=False):
        positions=positions if positions is not None else self._snapshot_positions()
        ref=next((c for c in (candidates or self.last_candidates) if c.get('price')),None)
        if not ref:
            sym=CASH_REF_SYMBOL; price=self.last_prices.get(sym) or 10.0
        else:sym,price=ref['symbol'],ref['price']
        try:
            cash=self.broker.buying_power(sym,price,force=force_cash)
        except TypeError:
            cash=self.broker.buying_power(sym,price)
        holdings=sum(float(p['qty'])*float(p['price']) for p in positions)
        return cash+holdings,cash
    def update(self,raw):
        merged=asdict(self.config)
        for k in merged:
            if k in raw: merged[k]=raw[k]
        c=Config(**merged)
        if not (1<=c.max_positions<=5): raise ValueError('최대 보유종목은 1~5개만 가능합니다')
        if not (10<=c.position_pct<=70): raise ValueError('종목당 최대비중은 10~70%만 가능합니다')
        if not (10<=c.cash_reserve_pct<=30): raise ValueError('현금 보유비중은 10~30%만 가능합니다')
        if not (.5<=c.stop_loss_pct<=10): raise ValueError('손절은 0.5~10%만 가능합니다')
        if not (.2<=c.profit_protect_start_pct<=10): raise ValueError('수익보호 시작은 0.2~10%만 가능합니다')
        if not (.2<=c.profit_protect_drop_pct<=5): raise ValueError('수익보호 고점이탈은 0.2~5%만 가능합니다')
        if not (1<=c.trailing_start_pct<=20): raise ValueError('트레일링 시작은 1~20%만 가능합니다')
        if not (.5<=c.trailing_drop_pct<=10): raise ValueError('트레일링 고점이탈은 0.5~10%만 가능합니다')
        if not (0<=c.min_hold_minutes<=120): raise ValueError('최소 보유는 0~120분만 가능합니다')
        if not (.2<=c.weak_exit_loss_pct<=10): raise ValueError('추세교체 손실기준은 0.2~10%만 가능합니다')
        if not (1<=c.weak_exit_confirmations<=5): raise ValueError('추세악화 연속확인은 1~5회만 가능합니다')
        if not (0<=c.rebuy_cooldown_minutes<=240): raise ValueError('재매수 대기는 0~240분만 가능합니다')
        if not (30<=c.poll_seconds<=3600): raise ValueError('판단 주기는 30~3600초만 가능합니다')
        if not (120<=c.universe_refresh_seconds<=900): raise ValueError('종목풀 갱신은 120~900초만 가능합니다')
        if not (1<=c.min_stock_price<=20): raise ValueError('최저 주가는 1~20달러만 가능합니다')
        if not (12<=c.max_dynamic_symbols<=40): raise ValueError('정밀분석 종목수는 12~40개만 가능합니다')
        self.config=c; self.broker.config=c; self.store.set('config',asdict(c)); return self.state()
    def state(self):
        try:
            positions=self._snapshot_positions(force=False)
        except Exception:
            positions=[]
        try: equity,cash=self._equity_and_cash(positions,self.last_candidates,force_cash=False)
        except Exception: equity,cash=0.0,0.0
        day_base=float(self.store.get('day_start_equity',equity) or 0); day_pct=(equity/day_base-1)*100 if day_base>0 else 0
        principal=self._ensure_principal(equity)
        profit=equity-principal if principal>0 else 0; profit_pct=(profit/principal*100) if principal>0 else 0
        now_epoch=time.time()
        for p in positions:
            sym=p['symbol']; peak=float(self.trailing_peaks.get(sym,0) or 0); ppeak=float(self.profit_peaks.get(sym,0) or 0); entered=float(self.entry_times.get(sym,now_epoch) or now_epoch)
            p['hold_minutes']=round(max(0.0,(now_epoch-entered)/60),1)
            p['profit_protect_active']=bool(ppeak>0)
            p['profit_peak']=round(ppeak,4) if ppeak>0 else 0
            p['profit_protect_stop']=round(ppeak*(1-self.config.profit_protect_drop_pct/100),4) if ppeak>0 else 0
            p['trailing_peak']=round(peak,4) if peak>0 else 0
            p['trailing_active']=bool(peak>0)
            p['trailing_stop']=round(peak*(1-self.config.trailing_drop_pct/100),4) if peak>0 else 0
        return {'running':self.running,'mode':'KIS 실계좌 · 실시간 종목자동선정' if self.live else '테스트 · 실시간 종목자동선정','config':asdict(self.config),'cash':round(cash,2),'positions':positions,'candidates':self.last_candidates,'equity':round(equity,2),'principal':round(principal,2),'profit':round(profit,2),'profit_pct':round(profit_pct,2),'day_profit_pct':round(day_pct,2),'fx_rate':USD_KRW_RATE,'last_signal':self.last_signal,'dynamic_pool':self.dynamic_symbols,'dynamic_price_cap':round(self.dynamic_price_cap,2),'pool_age_seconds':round(max(0,time.time()-self.dynamic_updated_at)) if self.dynamic_updated_at else None,'scan_errors':self.store.get('last_scan_errors',[]) or [],'activity':list(self.activity),'trades':self.store.trades(40)}


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
        body=json.dumps(value,ensure_ascii=False).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError): pass
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
            elif path=='/api/cashflow':state=ENGINE.adjust_cashflow(raw.get('kind'),raw.get('amount'))
            else:return self.send_json({'error':'not found'},404)
            self.send_json({'ok':True,'state':state})
        except Exception as e:self.send_json({'error':str(e)},400)

def main():
    print(f'사장님 자동매매 다종목: http://127.0.0.1:{PORT}')
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()

if __name__=='__main__':main()
