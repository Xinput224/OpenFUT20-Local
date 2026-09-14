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

def main():
    state=State(); db={}
    # Five players, each with Baby/Mid/Prime Icon versions.
    for asset in range(1,6):
        for version,rating in enumerate((85,88,91),1):
            rid=asset*100000+version
            db[str(rid)]={"resourceId":rid,"assetId":asset,"rating":rating,"rarityName":"Icon","name":f"Icon {asset}-{version}"}
    def pack_wire(raw):
        out=dict(raw)
        out.pop("pile",None)
        out["contracts"]=int(out.get("contract") or 7)
        out["injuryType"]="none"
        return out
    def wrong_serializer(_raw):
        raise AssertionError("Player Pick candidates must prefer _native_pack_item")
    g={"PLAYER_DB":db,"CONSUMABLE_DB":{},"log":Log(),
       "_native_pack_item":pack_wire,"_native_player_item":wrong_serializer}
    opened=promo.create_custom_pack(state,26,g); tokens=[int(x["id"]) for x in opened["items"]]
    assert len(tokens)==1
    # FIFA 20 native 1-of-5 definition: 5004094 / Name27 / amount 4219.
    for token_id in tokens:
        token=state.get_item(token_id)
        assert int(token["resourceId"])==5004094
        assert token["name"]=="PlayerPickItemName27"
        assert int(token["amount"])==4219
        assert all(k not in token for k in ("availablePicks","pickSize","selectionSize"))

    # Simulate two unresolved V24 tokens. V25 must migrate them in place so a
    # user's existing save keeps the same token instance IDs and purchase.
    for token_id in tokens:
        token=state.get_item(token_id); token.update({
            "resourceId":5004241,"definitionId":5004241,"_definitionId":5004241,
            "name":"PlayerPickItemName113","detaildescription":"PlayerPickItemDetailDesc113",
            "amount":4012,"availablePicks":1,"pickSize":5,"selectionSize":5,
        })
        raw=json.dumps(token,separators=(",",":"))
        state.conn.execute("UPDATE items SET resource_id=?,data=? WHERE id=?",(5004241,raw,token_id))
        state.conn.execute("UPDATE player_pick_tokens SET token_json=? WHERE token_id=?",(raw,token_id))
    state.conn.commit()
    changed=promo._migrate_legacy_pick_tokens(state,g)
    assert changed==tokens
    for token_id in tokens:
        token=state.get_item(token_id)
        assert int(token["resourceId"])==5004094 and token["name"]=="PlayerPickItemName27" and int(token["amount"])==4219
        assert all(k not in token for k in ("availablePicks","pickSize","selectionSize"))

    selected=[]
    for turn,token_id in enumerate(tokens):
        response=promo.handle_native_request(state,"POST",f"/ut/game/fifa20/item/nontargeted?itemId={token_id}",{},b"",g)
        first=payload(response); ids=[int(x["id"]) for x in first["items"]]
        assert len(ids)==5 and len(set(ids))==5
        # Temporary Player Pick candidates must not claim a normal repository pile.
        # FIFA's successful confirm path performs that transition itself.
        assert all("pile" not in x for x in first["items"])
        assert all("definitionId" not in x and "_definitionId" not in x for x in first["items"])
        assert all(x.get("contracts")==7 and x.get("injuryType")=="none" for x in first["items"])
        # Simulate a process restart by discarding all compatibility globals.
        promo._PICK_TOKENS={}; promo._ACTIVE_PICK=None
        pending=payload(promo.handle_native_request(state,"GET","/ut/game/fifa20/playerpicks/pending",{},b"",g))
        assert [int(x["id"]) for x in pending["items"]]==ids
        chosen=pending["items"][turn%5]; rid=int(chosen["resourceId"]); cid=int(chosen["id"])
        ack=promo.handle_native_request(state,"POST",f"/ut/game/fifa20/playerpicks/item/{rid}/select",{},b"",g)
        assert ack[0]==200 and ack[2]==b""
        assert "Content-Type" not in ack[1]
        assert "Content-Length" not in ack[1]
        stored=state.get_item(cid)
        assert stored and int(stored["id"])==cid and int(stored["resourceId"])==rid and stored["pile"]=="unassigned"
        assert state.conn.execute("SELECT count(*) FROM player_pick_candidates").fetchone()[0]==0
        selected.append((cid,rid))
        before=state.conn.execute("SELECT count(*) FROM items").fetchone()[0]
        stale=promo.handle_native_request(state,"POST",f"/ut/game/fifa20/playerpicks/item/{rid}/select",{},b"",g)
        assert stale[0]==200 and stale[2]==b""
        assert "Content-Type" not in stale[1]
        assert "Content-Length" not in stale[1]
        assert state.conn.execute("SELECT count(*) FROM items").fetchone()[0]==before
        remaining=len(promo.pick_state.available_tokens(state)); assert remaining==0
    assert not promo.pick_state.pending_flag(state)
    assert len(selected)==1
    mass=promo.augment_response(state,"GET","/ut/game/fifa20/usermassinfo",(200,{},b'{"userInfo":{}}'),g)
    assert payload(mass)["isPlayerPicksTemporaryStorageNotEmpty"] is False
    settings=promo.augment_response(state,"GET","/ut/game/fifa20/settings",(200,{},b'{"settings":{}}'),g)
    assert payload(settings)["enablePlayerPicks"]==1
    print("PASS: 1 token -> 1 persistent pick -> 1 exact-ID Unassigned player")
    print("selected:",selected)

if __name__=="__main__": main()
