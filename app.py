from __future__ import annotations

import base64, json, os, sqlite3, threading, time, urllib.error, urllib.parse, urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parent
DB_PATH=Path(os.getenv("TRADER_DB",ROOT/"trader.db")); HOST="0.0.0.0"; PORT=int(os.getenv("PORT","8080"))
DEFAULT_WATCHLIST="NASD:GMEX,NASD:SOFI,NASD:INTC,NASD:CSCO,NASD:WBD"

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")

@dataclass
class Config:
    watchlist: str=DEFAULT_WATCHLIST
    short_window: int=3
    long_window: int=8
    max_positions: int=2
    max_order_usd: float=30.0
    stop_loss_pct: float=2.0
    take_profit_pct: float=4.0
    max_hold_minutes: int=60
    poll_seconds: int=20

class Store:
    def __init__(self,path):
        self.path=path; self.lock=threading.RLock()
        with self.db() as d:
            d.executescript("""
            CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS prices(id INTEGER PRIMARY KEY,ts TEXT,symbol TEXT,price REAL,volume REAL);
            CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY,ts TEXT,side TEXT,symbol TEXT,qty REAL,price REAL,reason TEXT);
            """)
            try: d.execute("ALTER TABLE prices ADD COLUMN volume REAL DEFAULT 0")
            except sqlite3.OperationalError: pass
    def db(self):
        d=sqlite3.connect(self.path,timeout=10); d.row_factory=sqlite3.Row; return d
    def get(self,k,default=None):
        with self.lock,self.db() as d:
            r=d.execute("SELECT value FROM kv WHERE key=?",(k,)).fetchone(); return json.loads(r[0]) if r else default
    def set(self,k,v):
        with self.lock,self.db() as d: d.execute("INSERT INTO kv VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,json.dumps(v,ensure_ascii=False)))
    def add_price(self,s,p,v=0):
        with self.lock,self.db() as d:
            d.execute("INSERT INTO prices(ts,symbol,price,volume) VALUES(?,?,?,?)",(now(),s,p,v))
            d.execute("DELETE FROM prices WHERE id NOT IN(SELECT id FROM prices ORDER BY id DESC LIMIT 3000)")
    def history(self,s,n=20):
        with self.lock,self.db() as d:
            r=d.execute("SELECT price,volume FROM prices WHERE symbol=? ORDER BY id DESC LIMIT ?",(s,n)).fetchall()
            return [dict(x) for x in reversed(r)]
    def add_trade(self,side,symbol,qty,price,reason):
        with self.lock,self.db() as d: d.execute("INSERT INTO trades(ts,side,symbol,qty,price,reason) VALUES(?,?,?,?,?,?)",(now(),side,symbol,qty,price,reason))
    def trades(self,n=30):
        with self.lock,self.db() as d: return [dict(x) for x in d.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?",(n,)).fetchall()]

class KIS:
    BASE="https://openapi.koreainvestment.com:9443"; EX={"NASD":"NAS","NYSE":"NYS","AMEX":"AMS"}
    def __init__(self):
        self.key=os.getenv("KIS_APP_KEY",""); self.secret=os.getenv("KIS_APP_SECRET",""); self.token=""; self.exp=0
        if not self.key or not self.secret: raise RuntimeError("KIS 키가 필요합니다")
    def req(self,method,path,data=None,headers=None):
        body=json.dumps(data).encode() if data is not None else None
        q=urllib.request.Request(self.BASE+path,data=body,method=method,headers={"Content-Type":"application/json",**(headers or {})})
        try:
            with urllib.request.urlopen(q,timeout=12) as r: return json.loads(r.read())
        except urllib.error.HTTPError as e: raise RuntimeError("KIS API 오류: "+e.read().decode(errors="replace")[:220])
    def auth(self,tr): return {"authorization":"Bearer "+self.access(),"appkey":self.key,"appsecret":self.secret,"tr_id":tr,"custtype":"P"}
    def access(self):
        if self.token and time.time()<self.exp:return self.token
        x=self.req("POST","/oauth2/tokenP",{"grant_type":"client_credentials","appkey":self.key,"appsecret":self.secret})
        self.token=x["access_token"]; self.exp=time.time()+int(x.get("expires_in",3600))-60; return self.token
    def quote(self,symbol):
        market,ticker=symbol.split(":",1); excd=self.EX.get(market)
        if not excd: raise ValueError("NASD:GMEX 형식으로 입력하세요")
        q=urllib.parse.urlencode({"AUTH":"","EXCD":excd,"SYMB":ticker})
        x=self.req("GET","/uapi/overseas-price/v1/quotations/price?"+q,headers=self.auth("HHDFS00000300"))
        if x.get("rt_cd") not in (None,"0"): raise RuntimeError(x.get("msg1","시세 조회 실패"))
        o=x.get("output",{}); price=float(o.get("last",0) or 0); volume=float(o.get("tvol",0) or 0)
        if price<=0: raise RuntimeError(symbol+" 현재가 없음")
        return price,volume
    def hashkey(self,p):
        x=self.req("POST","/uapi/hashkey",p,{"appkey":self.key,"appsecret":self.secret}); return x["HASH"]

class Broker:
    def __init__(self,store,config,kis):
        self.store=store; self.config=config; self.kis=kis; self.account=os.getenv("KIS_ACCOUNT_NO",""); self.product=os.getenv("KIS_PRODUCT_CODE","01")
        if len(self.account)!=8: raise RuntimeError("계좌 설정 오류")
    def positions(self):
        q=urllib.parse.urlencode({"CANO":self.account,"ACNT_PRDT_CD":self.product,"OVRS_EXCG_CD":"NASD","TR_CRCY_CD":"USD","CTX_AREA_FK200":"","CTX_AREA_NK200":""})
        x=self.kis.req("GET","/uapi/overseas-stock/v1/trading/inquire-balance?"+q,headers=self.kis.auth("TTTS3012R"))
        if x.get("rt_cd")!="0": raise RuntimeError(x.get("msg1","잔고 조회 실패"))
        out={}
        for r in x.get("output1",[]):
            qty=float(r.get("ovrs_cblc_qty",0) or 0)
            if qty>0:
                ticker=r.get("ovrs_pdno",""); market=r.get("ovrs_excg_cd","NASD")
                out[market+":"+ticker]={"qty":qty,"avg_price":float(r.get("pchs_avg_pric",0) or 0)}
        return out
    def buying_power(self,symbol,price):
        market,ticker=symbol.split(":",1)
        q=urllib.parse.urlencode({"CANO":self.account,"ACNT_PRDT_CD":self.product,"OVRS_EXCG_CD":market,"OVRS_ORD_UNPR":f"{price:.4f}","ITEM_CD":ticker})
        x=self.kis.req("GET","/uapi/overseas-stock/v1/trading/inquire-psamount?"+q,headers=self.kis.auth("TTTS3007R"))
        if x.get("rt_cd")!="0": raise RuntimeError(x.get("msg1","매수가능금액 조회 실패"))
        o=x.get("output",{}); amount=float(o.get("ord_psbl_frcr_amt",0) or 0); qty=int(float(o.get("max_ord_psbl_qty",0) or 0))
        return amount,qty
    def order(self,side,symbol,qty,price,reason):
        if os.getenv("ORDER_MODE","observe").lower()!="live": return False
        if os.getenv("LIVE_TRADING_ACK")!="I_UNDERSTAND_REAL_ORDERS": raise RuntimeError("실전 확인값 없음")
        market,ticker=symbol.split(":",1); limit=round(price*(1.002 if side=="BUY" else .998),2)
        p={"CANO":self.account,"ACNT_PRDT_CD":self.product,"OVRS_EXCG_CD":market,"PDNO":ticker,"ORD_QTY":str(int(qty)),"OVRS_ORD_UNPR":f"{limit:.2f}","CTAC_TLNO":"","MGCO_APTM_ODNO":"","SLL_TYPE":"00" if side=="SELL" else "","ORD_SVR_DVSN_CD":"0","ORD_DVSN":"00"}
        tr="TTTT1002U" if side=="BUY" else "TTTT1006U"; h=self.kis.auth(tr); h["hashkey"]=self.kis.hashkey(p)
        x=self.kis.req("POST","/uapi/overseas-stock/v1/trading/order",p,h)
        if x.get("rt_cd")!="0": raise RuntimeError(x.get("msg1","주문 거절"))
        self.store.add_trade(side,symbol,qty,limit,reason); return True

class Engine:
    def __init__(self,store):
        self.store=store; self.config=Config(**store.get("config",{})); self.kis=KIS(); self.broker=Broker(store,self.config,self.kis)
        self.running=False; self.thread=None; self.stop_event=threading.Event(); self.cursor=0; self.last="대기"; self.candidates=[]; self.errors=[]
    def symbols(self):
        seen=[]
        for s in self.config.watchlist.upper().replace(" ","").split(","):
            if s and s not in seen: seen.append(s)
        return seen[:30]
    def score(self,s):
        h=self.store.history(s,self.config.long_window); prices=[x["price"] for x in h]
        if len(prices)<self.config.long_window:return None
        short=sum(prices[-self.config.short_window:])/self.config.short_window; long=sum(prices)/len(prices)
        momentum=(prices[-1]/prices[0]-1)*100; trend=(short/long-1)*100
        return round(momentum+trend*2,3) if short>long and momentum>0 else None
    def tick(self):
        syms=self.symbols()
        if not syms: raise ValueError("감시 종목이 없습니다")
        s=syms[self.cursor%len(syms)]; self.cursor+=1
        try:
            p,v=self.kis.quote(s); self.store.add_price(s,p,v); self.errors=[]
        except Exception as e:
            self.errors=[f"{s}: {e}"]; self.last="시세 오류"; return
        positions=self.broker.positions()
        # Existing positions are always checked for exits before new entries.
        for ps,pos in list(positions.items()):
            try: pp,_=self.kis.quote(ps)
            except Exception: continue
            pnl=(pp/pos["avg_price"]-1)*100 if pos["avg_price"] else 0
            if pnl<=-self.config.stop_loss_pct:self.broker.order("SELL",ps,int(pos["qty"]),pp,"손절")
            elif pnl>=self.config.take_profit_pct:self.broker.order("SELL",ps,int(pos["qty"]),pp,"익절")
        ranked=[]
        for x in syms:
            sc=self.score(x); h=self.store.history(x,1)
            if sc is not None and h: ranked.append({"symbol":x,"score":sc,"price":h[-1]["price"]})
        self.candidates=sorted(ranked,key=lambda x:x["score"],reverse=True)[:5]
        mode=os.getenv("ORDER_MODE","observe").lower()
        if self.candidates and len(positions)<self.config.max_positions:
            c=self.candidates[0]
            if c["symbol"] not in positions:
                amount,maxqty=self.broker.buying_power(c["symbol"],c["price"]); qty=min(maxqty,int(self.config.max_order_usd/(c["price"]*1.002)))
                if qty>=1 and mode=="live": self.broker.order("BUY",c["symbol"],qty,c["price"],f"단타점수 {c['score']}"); self.last="실전 매수 주문"
                else:self.last=f"선정 {c['symbol']} · 관찰만"
        else:self.last=f"수집 {s} {len(self.store.history(s,self.config.long_window))}/{self.config.long_window}"
    def start(self):
        self.running=True
        if not self.thread or not self.thread.is_alive(): self.stop_event.clear(); self.thread=threading.Thread(target=self.loop,daemon=True); self.thread.start()
    def stop(self): self.running=False
    def loop(self):
        while not self.stop_event.is_set():
            if self.running:
                try:self.tick()
                except Exception as e:self.errors=[str(e)]; self.last="오류"; self.stop()
            self.stop_event.wait(self.config.poll_seconds)
    def update(self,raw):
        m=asdict(self.config); m.update({k:v for k,v in raw.items() if k in m}); c=Config(**m)
        if not (2<=c.short_window<c.long_window<=30): raise ValueError("단기선/장기선 설정 오류")
        if not (1<=c.max_positions<=3): raise ValueError("동시보유는 1~3개")
        if not (10<=c.max_order_usd<=100): raise ValueError("종목당 금액은 10~100달러")
        self.config=c; self.broker.config=c; self.store.set("config",asdict(c))
    def state(self):
        positions=self.broker.positions()
        return {"running":self.running,"order_mode":os.getenv("ORDER_MODE","observe").lower(),"config":asdict(self.config),"positions":positions,"candidates":self.candidates,"last":self.last,"errors":self.errors,"trades":self.store.trades()}

HTML='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>사장님 다종목 단타</title><style>
*{box-sizing:border-box}body{margin:0;background:#09101d;color:#eef3ff;font-family:system-ui}main{max-width:760px;margin:auto;padding:20px 15px 70px}header,.row{display:flex;justify-content:space-between;align-items:center;gap:10px}small{color:#91a0bb}.pill{padding:8px 12px;border-radius:99px;background:#26344e}.warn{background:#3a2614;color:#ffd08a;padding:14px;border-radius:14px;margin:15px 0}.card{background:#121d31;border:1px solid #293853;border-radius:18px;padding:17px;margin-top:13px}button{border:0;border-radius:12px;background:#4777ff;color:white;padding:13px 16px;font-weight:800}button.stop{background:#e85a68}input{width:100%;padding:12px;margin:6px 0 10px;border:1px solid #34435e;border-radius:10px;background:#0b1424;color:white}.grid{display:grid;grid-template-columns:1fr 1fr;gap:9px}.item{padding:12px 0;border-top:1px solid #26344b}.score{color:#55e6a5}label{font-size:13px;color:#a8b3c8}</style></head><body><main>
<header><div><small>KIS 미국주식 · 다종목 단타</small><h2>사장님 자동매매 V2</h2></div><span id="status" class="pill">정지</span></header>
<div id="mode" class="warn">관찰 모드 · 실제 주문 없음</div><button id="toggle">감시 시작</button><button id="once">1회 순환</button>
<section class="card"><h3>자동선정 후보</h3><div id="candidates">데이터 수집 전</div></section>
<section class="card"><h3>실계좌 보유종목</h3><div id="positions">없음</div></section>
<section class="card"><h3>설정</h3><form id="form"><label>감시종목 (쉼표 구분)</label><input name="watchlist"><div class="grid"><label>단기선<input name="short_window" type="number"></label><label>장기선<input name="long_window" type="number"></label><label>동시보유<input name="max_positions" type="number"></label><label>종목당 최대 USD<input name="max_order_usd" type="number"></label><label>손절 %<input name="stop_loss_pct" type="number" step=".5"></label><label>익절 %<input name="take_profit_pct" type="number" step=".5"></label></div><button>설정 저장</button></form></section>
<section class="card"><h3>상태</h3><div id="last">대기</div><div id="errors" style="color:#ff7b87"></div></section>
</main><script>
let st;const $=s=>document.querySelector(s);async function api(p,b){let r=await fetch(p,{method:b?'POST':'GET',headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):null}),d=await r.json();if(!r.ok)throw Error(d.error||'오류');return d.state||d}
function render(s){st=s;$('#status').textContent=s.running?'감시 중':'정지';$('#toggle').textContent=s.running?'감시 정지':'감시 시작';$('#toggle').className=s.running?'stop':'';$('#mode').textContent=s.order_mode==='live'?'실전 주문 모드':'관찰 모드 · 실제 주문 없음';$('#mode').style.background=s.order_mode==='live'?'#4b1820':'#3a2614';$('#last').textContent=s.last;$('#errors').textContent=(s.errors||[]).join('\n');$('#candidates').innerHTML=s.candidates.length?s.candidates.map((x,i)=>`<div class="item"><b>${i+1}. ${x.symbol}</b> · $${x.price.toFixed(2)} <span class="score">점수 ${x.score}</span></div>`).join(''):'조건 충족 종목 없음';let ps=Object.entries(s.positions);$('#positions').innerHTML=ps.length?ps.map(([k,v])=>`<div class="item"><b>${k}</b> ${v.qty}주 · 평단 $${v.avg_price.toFixed(2)}</div>`).join(''):'보유종목 없음';Object.entries(s.config).forEach(([k,v])=>{let e=document.querySelector(`[name="${k}"]`);if(e&&document.activeElement!==e)e.value=v})}
async function refresh(){try{render(await api('/api/state'))}catch(e){$('#errors').textContent=e.message}}$('#toggle').onclick=async()=>render(await api(st.running?'/api/stop':'/api/start',{}));$('#once').onclick=async()=>render(await api('/api/tick',{}));$('#form').onsubmit=async e=>{e.preventDefault();let d=Object.fromEntries(new FormData(e.target));['short_window','long_window','max_positions','max_order_usd','stop_loss_pct','take_profit_pct'].forEach(k=>d[k]=Number(d[k]));render(await api('/api/config',d))};refresh();setInterval(refresh,5000)
</script></body></html>'''

STORE=Store(DB_PATH); ENGINE=Engine(STORE)
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def auth(self):
        pw=os.getenv("DASHBOARD_PASSWORD",""); expected="Basic "+base64.b64encode(("owner:"+pw).encode()).decode()
        if pw and self.headers.get("Authorization")!=expected:self.send_response(401);self.send_header("WWW-Authenticate",'Basic realm="Trader"');self.end_headers();return False
        return True
    def sendj(self,x,code=200):
        b=json.dumps(x,ensure_ascii=False).encode();self.send_response(code);self.send_header("Content-Type","application/json;charset=utf-8");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        if not self.auth():return
        if urlparse(self.path).path=="/api/state":
            try:return self.sendj(ENGINE.state())
            except Exception as e:return self.sendj({"error":str(e)},500)
        b=HTML.encode();self.send_response(200);self.send_header("Content-Type","text/html;charset=utf-8");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def do_POST(self):
        if not self.auth():return
        try:
            n=int(self.headers.get("Content-Length",0)); raw=json.loads(self.rfile.read(n) or b"{}"); p=urlparse(self.path).path
            if p=="/api/start":ENGINE.start()
            elif p=="/api/stop":ENGINE.stop()
            elif p=="/api/tick":ENGINE.tick()
            elif p=="/api/config":ENGINE.update(raw)
            else:return self.sendj({"error":"not found"},404)
            self.sendj({"state":ENGINE.state()})
        except Exception as e:self.sendj({"error":str(e)},400)

if __name__=="__main__":
    print("사장님 다종목 단타 V2",PORT);ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
