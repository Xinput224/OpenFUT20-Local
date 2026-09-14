from __future__ import annotations
import importlib, json, sqlite3, sys, threading
from pathlib import Path

SERVER=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SERVER)); promo=importlib.import_module("promo_packs")

class State:
    def __init__(self):
        self.lock=threading.RLock(); self.conn=sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE items(id INTEGER PRIMARY KEY,resource_id INTEGER NOT NULL,pile TEXT NOT NULL,data TEXT NOT NULL)")
        self._next=900000000000
    def next_item_id(self): self._next+=1; return self._next
    def build_player_item(self,rid,iid,pile="club",loan_games=0):
        return {"id":int(iid),"resourceId":int(rid),"assetId":int(rid)%1000000,"definitionId":int(rid),"_definitionId":int(rid),"pile":pile,"itemType":"player","itemState":"free","untradeable":True,"discardValue":0}
    def make_consumable_item(self,rid,pile="unassigned",amount=1):
        iid=self.next_item_id(); item={"id":iid,"resourceId":int(rid),"pile":pile,"amount":amount,"itemType":"misc"}
        self.conn.execute("INSERT INTO items VALUES(?,?,?,?)",(iid,int(rid),pile,json.dumps(item))); self.conn.commit(); return item
    def update_item_fields(self,iid,fields):
        item=self.get_item(iid); item.update(fields); pile=item.get("pile","unassigned")
        self.conn.execute("UPDATE items SET resource_id=?,pile=?,data=? WHERE id=?",(int(item["resourceId"]),pile,json.dumps(item),int(iid))); self.conn.commit()
    def get_item(self,iid):
        row=self.conn.execute("SELECT data FROM items WHERE id=?",(int(iid),)).fetchone(); return json.loads(row[0]) if row else None
    def delete_item(self,iid): self.conn.execute("DELETE FROM items WHERE id=?",(int(iid),)); self.conn.commit()
    def owned_player_resource_ids(self):
        return [int(r[0]) for r in self.conn.execute("SELECT resource_id FROM items WHERE json_extract(data,'$.itemType')='player'")]
    def credits(self): return 70000000

class Log:
    def warning(self,*args,**kwargs): pass

def payload(response): return json.loads(response[2].decode("utf-8"))

def build_db():
    db={}
    # Five players, each with Baby/Mid/Prime Icon versions.
    for asset in range(1,6):
        for version,rating in enumerate((85,88,91),1):
            rid=asset*100000+version
            db[str(rid)]={"resourceId":rid,"assetId":asset,"rating":rating,"rarityName":"Icon","name":f"Icon {asset}-{version}","special":True}
    # Special 86+ pool, including a real 99 possibility.
    for i,rating in enumerate((86,87,88,90,92,94,96,97,98,99),1):
        rid=2000000+i
        db[str(rid)]={"resourceId":rid,"assetId":rid,"rating":rating,"rarityName":"Flashback","name":f"Special {rating}","special":True}
    # TOTY-only pool.
    for i,rating in enumerate((94,96,97,98,99),1):
        rid=3000000+i
        db[str(rid)]={"resourceId":rid,"assetId":rid,"rating":rating,"rarityName":"Team of the Year","name":f"TOTY {rating}","special":True}
    # TOTS-only pool.
    for i,rating in enumerate((86,88,90,92,95,97,99),1):
        rid=4000000+i
        rarity="TOTS Moments" if i==1 else "Team of the Season So Far"
        db[str(rid)]={"resourceId":rid,"assetId":rid,"rating":rating,"rarityName":rarity,"name":f"TOTS {rating}","special":True}
    return db

def main():
    state=State(); db=build_db()
    def pack_wire(raw):
        out=dict(raw); out.pop("pile",None); out["contracts"]=int(out.get("contract") or 7); out["injuryType"]="none"; return out
    selected_wire_calls=[]
    def player_wire(raw): selected_wire_calls.append(int(raw.get("id") or 0)); return dict(raw)
    g={"PLAYER_DB":db,"CONSUMABLE_DB":{},"log":Log(),"_native_pack_item":pack_wire,"_native_player_item":player_wire}

    # Icon packs: three tokens, and every token is a native 1-of-3 pick.
    opened=promo.create_custom_pack(state,26,g); tokens=[int(x["id"]) for x in opened["items"]]
    assert len(tokens)==3
    for token_id in tokens:
        token=state.get_item(token_id)
        assert int(token["resourceId"])==5004241
        assert token["name"]=="PlayerPickItemName113"
        assert int(token["amount"])==4012
        assert all(k not in token for k in ("availablePicks","pickSize","selectionSize"))

    # Simulate an unresolved V28 1-of-5 token and confirm in-place migration.
    legacy=tokens[0]; token=state.get_item(legacy); token.update({
        "resourceId":5004094,"definitionId":5004094,"_definitionId":5004094,
        "name":"PlayerPickItemName27","detaildescription":"PlayerPickItemDetailDesc27","amount":4219,
    })
    raw=json.dumps(token,separators=(",",":"));
    state.conn.execute("UPDATE items SET resource_id=?,data=? WHERE id=?",(5004094,raw,legacy))
    state.conn.execute("UPDATE player_pick_tokens SET token_json=? WHERE token_id=?",(raw,legacy)); state.conn.commit()
    changed=promo._migrate_legacy_pick_tokens(state,g); assert changed==[legacy]
    assert state.get_item(legacy)["resourceId"]==5004241

    selected=[]
    for turn,token_id in enumerate(tokens):
        first=payload(promo.handle_native_request(state,"POST",f"/ut/game/fifa20/item/nontargeted?itemId={token_id}",{},b"",g))
        ids=[int(x["id"]) for x in first["items"]]
        assert len(ids)==3 and len(set(ids))==3 and first["pickSize"]==3 and first["selectionSize"]==3
        assert all("pile" not in x for x in first["items"])
        chosen=first["items"][turn%3]; rid=int(chosen["resourceId"]); cid=int(chosen["id"])
        ack=promo.handle_native_request(state,"POST",f"/ut/game/fifa20/playerpicks/item/{rid}/select",{},b"",g)
        selected_response=payload(ack)
        assert int(selected_response["id"])==cid and int(selected_response["resourceId"])==rid
        assert selected_response["pile"]=="unassigned"
        stored=state.get_item(cid); assert stored and stored["pile"]=="unassigned"
        before=state.conn.execute("SELECT count(*) FROM items").fetchone()[0]
        stale=payload(promo.handle_native_request(state,"POST",f"/ut/game/fifa20/playerpicks/item/{rid}/select",{},b"",g))
        assert int(stale["id"])==cid and state.conn.execute("SELECT count(*) FROM items").fetchone()[0]==before
        selected.append((cid,rid))
    assert len(selected)==3 and not promo.pick_state.pending_flag(state)

    # New pools are constrained exactly as advertised.
    pools=promo._pools(g)
    assert pools["special86"] and all(db[str(r)]["special"] and db[str(r)]["rating"]>=86 for r in pools["special86"])
    assert pools["toty"] and all(db[str(r)]["rarityName"]=="Team of the Year" for r in pools["toty"])
    assert pools["tots"] and all(db[str(r)]["rarityName"] in {"Team of the Season So Far","TOTS Moments"} for r in pools["tots"])
    for pid,key in ((29,"special86"),(30,"toty"),(31,"tots")):
        s2=State(); op=promo.create_custom_pack(s2,pid,g); assert len(op["items"])==1
        token_id=int(op["items"][0]["id"])
        pick=payload(promo.handle_native_request(s2,"POST",f"/ut/game/fifa20/item/nontargeted?itemId={token_id}",{},b"",g))
        assert len(pick["items"])==3
        assert all(int(x["resourceId"]) in pools[key] for x in pick["items"])
        # Resolve it so globals/durable state are clean before the next pack.
        rid=int(pick["items"][0]["resourceId"])
        promo.handle_native_request(s2,"POST",f"/ut/game/fifa20/playerpicks/item/{rid}/select",{},b"",g)
        promo._PICK_TOKENS={}; promo._ACTIVE_PICK=None

    assert selected_wire_calls
    print("PASS: V29 1-of-3 semantics, 3x Icon picks, and constrained Special/TOTY/TOTS pools")
    print("icon selections:",selected)

if __name__=="__main__": main()
