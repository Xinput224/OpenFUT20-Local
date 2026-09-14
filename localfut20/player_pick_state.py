"""SQLite-backed lifecycle for FIFA 20 native Player Pick items.

Candidate cards keep stable instance IDs in temporary storage until selection.
"""
from __future__ import annotations
import json, time

SCHEMA="""
CREATE TABLE IF NOT EXISTS player_pick_tokens(token_id INTEGER PRIMARY KEY,pack_id INTEGER NOT NULL,pool_key TEXT NOT NULL,title TEXT NOT NULL,sequence INTEGER NOT NULL,token_json TEXT NOT NULL,pool_json TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'available',created_at INTEGER NOT NULL,redeemed_at INTEGER,resolved_at INTEGER);
CREATE TABLE IF NOT EXISTS player_pick_sessions(token_id INTEGER PRIMARY KEY,status TEXT NOT NULL DEFAULT 'pending',created_at INTEGER NOT NULL,resolved_at INTEGER,selected_candidate_id INTEGER,selected_resource_id INTEGER);
CREATE TABLE IF NOT EXISTS player_pick_candidates(candidate_id INTEGER PRIMARY KEY,token_id INTEGER NOT NULL,ordinal INTEGER NOT NULL,resource_id INTEGER NOT NULL,owned INTEGER NOT NULL DEFAULT 0,item_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS player_pick_candidates_token ON player_pick_candidates(token_id,ordinal);
CREATE TABLE IF NOT EXISTS player_pick_receipts(token_id INTEGER PRIMARY KEY,candidate_id INTEGER NOT NULL,resource_id INTEGER NOT NULL,item_json TEXT NOT NULL,selected_at INTEGER NOT NULL);
"""

def _dump(v): return json.dumps(v,separators=(",",":"),ensure_ascii=False)
def _load(v,default=None):
    try: return json.loads(v)
    except Exception: return default

def ensure(state):
    with state.lock:
        state.conn.executescript(SCHEMA); state.conn.commit()

def register_token(state,token,pack_id,pool_key,title,sequence,pool):
    ensure(state); tid=int(token["id"]); now=int(time.time())
    with state.lock:
        state.conn.execute("""INSERT OR REPLACE INTO player_pick_tokens
          (token_id,pack_id,pool_key,title,sequence,token_json,pool_json,status,created_at)
          VALUES(?,?,?,?,?,?,?,?,?)""",(tid,int(pack_id),str(pool_key),str(title),int(sequence),_dump(token),_dump([int(x) for x in pool]),"available",now))
        state.conn.commit()

def available_tokens(state):
    ensure(state)
    with state.lock:
        rows=state.conn.execute("""SELECT t.token_id,t.pack_id,t.pool_key,t.title,t.sequence,t.token_json,t.pool_json
          FROM player_pick_tokens t JOIN items i ON i.id=t.token_id WHERE t.status='available'
          ORDER BY t.created_at,t.sequence,t.token_id""").fetchall()
    return [{"token_id":int(r[0]),"pack_id":int(r[1]),"pool_key":r[2],"title":r[3],"sequence":int(r[4]),"token":_load(r[5],{}),"pool":_load(r[6],[])} for r in rows]

def token(state,token_id):
    token_id=int(token_id)
    return next((x for x in available_tokens(state) if x["token_id"]==token_id),None)

def _active_locked(conn):
    row=conn.execute("SELECT token_id FROM player_pick_sessions WHERE status='pending' ORDER BY created_at,token_id LIMIT 1").fetchone()
    if not row: return None
    tid=int(row[0]); rows=conn.execute("SELECT resource_id,owned,item_json FROM player_pick_candidates WHERE token_id=? ORDER BY ordinal",(tid,)).fetchall()
    return {"token_id":tid,"items":[_load(r[2],{}) for r in rows],"resource_ids":[int(r[0]) for r in rows],"ownership":[bool(r[1]) for r in rows]}

def active(state):
    ensure(state)
    with state.lock: return _active_locked(state.conn)

def begin(state,token_id,items,ownership):
    ensure(state); tid=int(token_id); now=int(time.time())
    with state.lock:
        existing=_active_locked(state.conn)
        if existing: return existing,False
        valid=state.conn.execute("SELECT 1 FROM player_pick_tokens t JOIN items i ON i.id=t.token_id WHERE t.token_id=? AND t.status='available'",(tid,)).fetchone()
        if not valid: return None,False
        try:
            state.conn.execute("BEGIN IMMEDIATE")
            state.conn.execute("DELETE FROM items WHERE id=?",(tid,))
            state.conn.execute("UPDATE player_pick_tokens SET status='redeemed',redeemed_at=? WHERE token_id=?",(now,tid))
            state.conn.execute("INSERT INTO player_pick_sessions(token_id,status,created_at) VALUES(?,?,?)",(tid,"pending",now))
            for n,item in enumerate(items):
                state.conn.execute("INSERT INTO player_pick_candidates(candidate_id,token_id,ordinal,resource_id,owned,item_json) VALUES(?,?,?,?,?,?)",(int(item["id"]),tid,n,int(item["resourceId"]),1 if ownership[n] else 0,_dump(item)))
            state.conn.commit()
        except Exception:
            state.conn.rollback(); raise
        return _active_locked(state.conn),True

def pending_flag(state): return active(state) is not None

def select(state,selected_value,duplicate=False):
    ensure(state); value=int(selected_value); now=int(time.time())
    with state.lock:
        current=_active_locked(state.conn)
        if not current: return None
        chosen=next((dict(x) for x in current["items"] if value in {int(x.get(k) or 0) for k in ("id","resourceId","assetId","definitionId","_definitionId")}),None)
        if chosen is None: return None
        tid=int(current["token_id"]); cid=int(chosen["id"]); rid=int(chosen["resourceId"])
        chosen.update({"pile":"unassigned","untradeable":True,"discardValue":0})
        if duplicate: chosen.update({"duplicate":True,"isDuplicate":True,"itemState":"duplicate"})
        try:
            state.conn.execute("BEGIN IMMEDIATE")
            state.conn.execute("INSERT INTO items(id,resource_id,pile,data) VALUES(?,?,?,?)",(cid,rid,"unassigned",_dump(chosen)))
            state.conn.execute("UPDATE player_pick_sessions SET status='resolved',resolved_at=?,selected_candidate_id=?,selected_resource_id=? WHERE token_id=?",(now,cid,rid,tid))
            state.conn.execute("UPDATE player_pick_tokens SET status='resolved',resolved_at=? WHERE token_id=?",(now,tid))
            state.conn.execute("INSERT OR REPLACE INTO player_pick_receipts(token_id,candidate_id,resource_id,item_json,selected_at) VALUES(?,?,?,?,?)",(tid,cid,rid,_dump(chosen),now))
            state.conn.execute("DELETE FROM player_pick_candidates WHERE token_id=?",(tid,))
            state.conn.commit()
        except Exception:
            state.conn.rollback(); raise
        return {"token_id":tid,"candidate_id":cid,"resource_id":rid,"item":chosen,"candidate_ids":[int(x["id"]) for x in current["items"]]}

def is_stale_selection(state,selected_value):
    ensure(state); value=int(selected_value)
    with state.lock: rows=state.conn.execute("SELECT candidate_id,resource_id FROM player_pick_receipts ORDER BY selected_at DESC LIMIT 16").fetchall()
    return any(value in (int(r[0]),int(r[1])) for r in rows)
