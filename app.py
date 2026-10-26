from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import sqlite3, csv, io, json, os

BASE = Path(__file__).resolve().parent
DB = Path(os.environ.get('MULE_DB_PATH', BASE / 'mule_platform.db'))
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'local-demo-only-change-before-deployment')

def conn():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c

def log(c, action, details): c.execute('INSERT INTO audit_log(action,details) VALUES(?,?)', (action, details))

def score_all(c):
    rows = c.execute('SELECT * FROM transactions ORDER BY timestamp').fetchall()
    incoming, outgoing, neighbors = defaultdict(list), defaultdict(list), defaultdict(set)
    for r in rows:
        incoming[r['receiver']].append(r); outgoing[r['sender']].append(r)
        neighbors[r['sender']].add(r['receiver']); neighbors[r['receiver']].add(r['sender'])
    for r in rows:
        score, reasons = 0, []
        if r['amount'] >= 40000: score += 20; reasons.append('High-value transfer (≥ ₹40,000)')
        if len(outgoing[r['sender']]) >= 3: score += 15; reasons.append('Sender has multiple outgoing transfers')
        if len(incoming[r['receiver']]) >= 2: score += 15; reasons.append('Receiver has multiple incoming transfers')
        if outgoing[r['receiver']] and len(incoming[r['receiver']]) >= 1: score += 25; reasons.append('Receiver also sends funds onward (pass-through pattern)')
        if len(neighbors[r['sender']]) >= 4: score += 10; reasons.append('Sender is connected to many accounts')
        score = min(score, 100); level = 'High' if score >= 60 else 'Medium' if score >= 30 else 'Low'
        c.execute('UPDATE transactions SET risk_score=?,risk_level=?,risk_reasons=? WHERE id=?', (score, level, json.dumps(reasons), r['id']))

def init_db():
    with conn() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY, txn_ref TEXT UNIQUE NOT NULL, timestamp TEXT NOT NULL, sender TEXT NOT NULL, receiver TEXT NOT NULL, amount REAL NOT NULL CHECK(amount>=0), channel TEXT NOT NULL DEFAULT 'UPI', narration TEXT DEFAULT '', risk_score INTEGER NOT NULL DEFAULT 0, risk_level TEXT NOT NULL DEFAULT 'Low', risk_reasons TEXT NOT NULL DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS cases(id INTEGER PRIMARY KEY, account_id TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Open', priority TEXT NOT NULL DEFAULT 'Medium', notes TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, action TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);''')
        if c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0] == 0:
            now = datetime.now().replace(microsecond=0)
            samples = [('TXN-1001',-1,'ACC-100','ACC-200',45000,'UPI','Rent payment'),('TXN-1002',-1,'ACC-200','ACC-301',43800,'IMPS','Transfer'),('TXN-1003',-2,'ACC-450','ACC-200',1200,'UPI','Refund'),('TXN-1004',-3,'ACC-501','ACC-502',750,'UPI','Groceries'),('TXN-1005',-3,'ACC-502','ACC-503',700,'UPI','Shared expense'),('TXN-1006',-4,'ACC-700','ACC-701',120000,'NEFT','Invoice'),('TXN-1007',-4,'ACC-701','ACC-702',118500,'IMPS','Transfer'),('TXN-1008',-4,'ACC-702','ACC-900',117000,'UPI','Transfer'),('TXN-1009',-5,'ACC-300','ACC-301',500,'UPI','Lunch'),('TXN-1010',0,'ACC-100','ACC-888',44000,'UPI','Urgent transfer'),('TXN-1011',0,'ACC-888','ACC-889',43000,'IMPS','Transfer'),('TXN-1012',0,'ACC-889','ACC-890',42000,'UPI','Transfer')]
            for ref, days, s, r, amount, channel, note in samples:
                c.execute('INSERT INTO transactions(txn_ref,timestamp,sender,receiver,amount,channel,narration) VALUES(?,?,?,?,?,?,?)', (ref,(now+timedelta(days=days)).isoformat(sep=' '),s,r,amount,channel,note))
            log(c,'SYSTEM_INIT','Synthetic demo dataset created.')
        score_all(c)

def summary(c):
    return {'transactions': c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0], 'high': c.execute("SELECT COUNT(*) FROM transactions WHERE risk_level='High'").fetchone()[0], 'medium': c.execute("SELECT COUNT(*) FROM transactions WHERE risk_level='Medium'").fetchone()[0], 'open_cases': c.execute("SELECT COUNT(*) FROM cases WHERE status!='Closed'").fetchone()[0]}

@app.template_filter('fromjson')
def fromjson(v):
    try: return json.loads(v or '[]')
    except (ValueError, TypeError): return []

@app.route('/')
def dashboard():
    with conn() as c:
        tx = c.execute('SELECT * FROM transactions ORDER BY timestamp DESC LIMIT 10').fetchall()
        ids = {r['sender'] for r in c.execute('SELECT sender FROM transactions')} | {r['receiver'] for r in c.execute('SELECT receiver FROM transactions')}
        accounts=[]
        for a in ids:
            rows=c.execute('SELECT MAX(risk_score) score, COUNT(*) n FROM transactions WHERE sender=? OR receiver=?',(a,a)).fetchone()
            accounts.append({'id':a,'score':rows['score'] or 0,'n':rows['n']})
        accounts.sort(key=lambda x:x['score'],reverse=True)
        return render_template('dashboard.html', stats=summary(c), tx=tx, accounts=accounts[:8])

@app.route('/transactions')
def transactions():
    q=request.args.get('q','').strip(); level=request.args.get('level','All')
    with conn() as c:
        sql='SELECT * FROM transactions WHERE 1=1'; args=[]
        if q: sql+=' AND (txn_ref LIKE ? OR sender LIKE ? OR receiver LIKE ?)'; args += [f'%{q}%']*3
        if level in ('Low','Medium','High'): sql+=' AND risk_level=?'; args.append(level)
        rows=c.execute(sql+' ORDER BY timestamp DESC',args).fetchall()
        return render_template('transactions.html', rows=rows, q=q, level=level)

@app.route('/accounts')
def accounts():
    with conn() as c:
        ids={r['sender'] for r in c.execute('SELECT sender FROM transactions')} | {r['receiver'] for r in c.execute('SELECT receiver FROM transactions')}; out=[]
        for a in ids:
            sent=c.execute('SELECT COUNT(*) n,COALESCE(SUM(amount),0) total FROM transactions WHERE sender=?',(a,)).fetchone()
            rec=c.execute('SELECT COUNT(*) n,COALESCE(SUM(amount),0) total FROM transactions WHERE receiver=?',(a,)).fetchone()
            score=c.execute('SELECT MAX(risk_score) s FROM transactions WHERE sender=? OR receiver=?',(a,a)).fetchone()['s'] or 0
            out.append(dict(id=a,sn=sent['n'],sv=sent['total'],rn=rec['n'],rv=rec['total'],score=score))
        return render_template('accounts.html', accounts=sorted(out,key=lambda x:x['score'],reverse=True))

@app.route('/account/<account_id>')
def account(account_id):
    with conn() as c:
        rows=c.execute('SELECT * FROM transactions WHERE sender=? OR receiver=? ORDER BY timestamp DESC',(account_id,account_id)).fetchall()
        if not rows: flash('Account not found.','warning'); return redirect(url_for('accounts'))
        return render_template('account.html', account_id=account_id, rows=rows, score=max(r['risk_score'] for r in rows))

@app.route('/network')
def network():
    with conn() as c:
        rows=c.execute('SELECT sender,receiver,amount,risk_score FROM transactions').fetchall(); ids=set(); edges=[]
        for r in rows: ids.update((r['sender'],r['receiver'])); edges.append(dict(source=r['sender'],target=r['receiver'],amount=r['amount'],risk=r['risk_score']))
        return render_template('network.html', nodes=sorted(ids), edges=edges)

@app.route('/cases', methods=['GET','POST'])
def cases():
    with conn() as c:
        if request.method=='POST':
            a=request.form.get('account_id','').strip(); title=request.form.get('title','').strip(); priority=request.form.get('priority','Medium'); notes=request.form.get('notes','').strip()
            if not a or not title: flash('Account ID and title are required.','danger')
            else: c.execute('INSERT INTO cases(account_id,title,priority,notes) VALUES(?,?,?,?)',(a,title,priority,notes)); log(c,'CASE_CREATED',f'Case opened for {a}: {title}'); flash('Investigation case created.','success')
            return redirect(url_for('cases'))
        return render_template('cases.html', cases=c.execute('SELECT * FROM cases ORDER BY updated_at DESC').fetchall())

@app.route('/cases/<int:case_id>/update', methods=['POST'])
def update_case(case_id):
    status=request.form.get('status','Open')
    if status not in ('Open','In Review','Escalated','Closed'): flash('Invalid status.','danger'); return redirect(url_for('cases'))
    with conn() as c:
        case=c.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone()
        if not case: flash('Case not found.','warning')
        else: c.execute('UPDATE cases SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(status,case_id)); log(c,'CASE_STATUS_CHANGED',f'Case #{case_id}: {case["status"]} -> {status}'); flash('Case status updated.','success')
    return redirect(url_for('cases'))

@app.route('/upload',methods=['POST'])
def upload():
    f=request.files.get('file')
    if not f or not f.filename.lower().endswith('.csv'): flash('Choose a CSV file.','danger'); return redirect(url_for('transactions'))
    try:
        reader=csv.DictReader(io.StringIO(f.stream.read().decode('utf-8-sig'))); required={'txn_ref','timestamp','sender','receiver','amount','channel'}
        if not reader.fieldnames or not required.issubset(reader.fieldnames): raise ValueError('Required CSV columns: txn_ref,timestamp,sender,receiver,amount,channel (optional narration)')
        added=0
        with conn() as c:
            for row in reader:
                ref=(row.get('txn_ref') or '').strip(); s=(row.get('sender') or '').strip(); r=(row.get('receiver') or '').strip(); stamp=(row.get('timestamp') or '').strip()
                if not ref or not s or not r: continue
                amount=float(row['amount']); datetime.fromisoformat(stamp.replace('Z','+00:00'))
                if amount<0: raise ValueError('Amount cannot be negative.')
                cur=c.execute('INSERT OR IGNORE INTO transactions(txn_ref,timestamp,sender,receiver,amount,channel,narration) VALUES(?,?,?,?,?,?,?)',(ref,stamp,s,r,amount,(row.get('channel') or 'UPI').strip(),(row.get('narration') or '').strip())); added+=cur.rowcount
            score_all(c); log(c,'CSV_IMPORTED',f'Imported {added} transaction(s).')
        flash(f'Imported {added} new transaction(s); scores recalculated.','success')
    except Exception as e: flash(f'Import failed: {e}','danger')
    return redirect(url_for('transactions'))

@app.route('/export.csv')
def export_csv():
    with conn() as c: rows=c.execute('SELECT txn_ref,timestamp,sender,receiver,amount,channel,narration,risk_score,risk_level,risk_reasons FROM transactions ORDER BY timestamp DESC').fetchall()
    out=io.StringIO(); w=csv.writer(out); w.writerow(['txn_ref','timestamp','sender','receiver','amount','channel','narration','risk_score','risk_level','risk_reasons']); w.writerows([list(r) for r in rows])
    res=make_response(out.getvalue()); res.headers['Content-Type']='text/csv; charset=utf-8'; res.headers['Content-Disposition']='attachment; filename=mule_risk_report.csv'; return res

@app.route('/audit')
def audit():
    with conn() as c: return render_template('audit.html', rows=c.execute('SELECT * FROM audit_log ORDER BY id DESC LIMIT 100').fetchall())
@app.route('/health')
def health(): return jsonify(status='ok', mode='synthetic demo', database='sqlite')
@app.route('/recalculate',methods=['POST'])
def recalculate():
    with conn() as c: score_all(c); log(c,'RISK_RECALCULATED','Scores recalculated using documented demo rules.')
    flash('Risk scores recalculated.','success'); return redirect(request.referrer or url_for('dashboard'))

if __name__=='__main__':
    init_db()
    # Localhost-only: no public/network exposure by default.
    app.run(host='127.0.0.1',port=5000,debug=False)
