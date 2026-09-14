from __future__ import annotations
import json, random, time, re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from localfut20 import player_pick_state as pick_state

# Custom store packs. These are intentionally store/runtime-only and do not touch launcher/auth.
CUSTOM_CONFIG = {
    24: {"enabled": True, "name": "Baby Icon 3x3 Player Pick", "bio": "3 Player Picks. Each pick shows 3 Baby Icons. Choose 1 player from each pick.", "price": 1000000, "size": 3, "gold_weight": 100, "silver_weight": 0, "bronze_weight": 0, "rare_slots": 3, "special_chance": 1.0, "store_group": "special", "pack_asset_id": 4, "special_weights": {}, "_special_weights": {}},
    25: {"enabled": True, "name": "Mid Icon 3x3 Player Pick", "bio": "3 Player Picks. Each pick shows 3 Mid Icons. Choose 1 player from each pick.", "price": 1000000, "size": 3, "gold_weight": 100, "silver_weight": 0, "bronze_weight": 0, "rare_slots": 3, "special_chance": 1.0, "store_group": "special", "pack_asset_id": 5, "special_weights": {}, "_special_weights": {}},
    26: {"enabled": True, "name": "Prime Icon 3x3 Player Pick", "bio": "3 Player Picks. Each pick shows 3 Prime Icons. Choose 1 player from each pick.", "price": 1000000, "size": 3, "gold_weight": 100, "silver_weight": 0, "bronze_weight": 0, "rare_slots": 3, "special_chance": 1.0, "store_group": "special", "pack_asset_id": 6, "special_weights": {}, "_special_weights": {}},
    27: {"enabled": True, "name": "Icon Moments 3x3 Player Pick", "bio": "3 Player Picks. Each pick shows 3 Icon Moments. Choose 1 player from each pick.", "price": 1000000, "size": 3, "gold_weight": 100, "silver_weight": 0, "bronze_weight": 0, "rare_slots": 3, "special_chance": 1.0, "store_group": "special", "pack_asset_id": 4, "special_weights": {}, "_special_weights": {}},
    29: {"enabled": True, "name": "86+ Special 1 of 3 Player Pick", "bio": "1 Player Pick. Shows 3 special players rated 86-99. Choose 1. High-end cards are possible, not guaranteed.", "price": 500000, "size": 1, "gold_weight": 100, "silver_weight": 0, "bronze_weight": 0, "rare_slots": 1, "special_chance": 1.0, "store_group": "special", "pack_asset_id": 4, "special_weights": {}, "_special_weights": {}},
    30: {"enabled": True, "name": "TOTY 1 of 3 Player Pick", "bio": "1 Player Pick. Shows 3 Team of the Year players. Choose 1.", "price": 750000, "size": 1, "gold_weight": 100, "silver_weight": 0, "bronze_weight": 0, "rare_slots": 1, "special_chance": 1.0, "store_group": "special", "pack_asset_id": 4, "special_weights": {}, "_special_weights": {}},
    31: {"enabled": True, "name": "TOTS 1 of 3 Player Pick", "bio": "1 Player Pick. Shows 3 Team of the Season players. Choose 1.", "price": 500000, "size": 1, "gold_weight": 100, "silver_weight": 0, "bronze_weight": 0, "rare_slots": 1, "special_chance": 1.0, "store_group": "special", "pack_asset_id": 4, "special_weights": {}, "_special_weights": {}},
    32: {"enabled": True, "name": "Gold Players Pack", "bio": "12 Gold players only. Contains at least 1 Rare Gold player and no Silver, Bronze, or special cards.", "price": 12500, "size": 12, "gold_weight": 100, "silver_weight": 0, "bronze_weight": 0, "rare_slots": 1, "special_chance": 0.0, "store_group": "gold", "pack_asset_id": 3, "special_weights": {}, "_special_weights": {}},
}
CUSTOM_IDS=set(CUSTOM_CONFIG)
PICK_IDS={24,25,26,27,29,30,31}

# FIFA 20 native 1-of-3 player-pick item from the FUT 20 static catalog.
# V28 proved the successful selection contract; V29 switches the carousel back
# to the matching 1-of-3 static definition for all current custom Player Picks.
LEGACY_PICK_RESOURCE_IDS = {5004094}
REAL_PICK_RESOURCE_ID = 5004241
REAL_PICK_CARD_ASSET_ID = 44
REAL_PICK_STATIC = {
    "cardassetid": REAL_PICK_CARD_ASSET_ID,
    "cardsubtypeid": 237,
    "rating": 99,
    "rareflag": 1,
    "amount": 4012,
    "bronze": 0,
    "silver": 0,
    "gold": 0,
    "discardValue": 0,
    "sourceMember": "miscPlayerPick",
}

# Native pick state is process-local, exactly like a live FUT session.
_PICK_TOKENS = {}
_ACTIVE_PICK = None
_NEXT_TOKEN_ID = 980000000000
_NEXT_CANDIDATE_ID = 981000000000
_AWAITING_NEW_ITEMS = False
_PENDING_REJECT_CLEANUP = set()
_LAST_CONFIRMED = None
_PENDING_CONFIRM = None
_FALLBACK_BLOCK_UNTIL = 0.0
_PICK_HEAD_ALIASES = {}
_PICK_HEAD_RE = re.compile(r"/fut/playerheads/g4/single/p(\d+)\.dds$", re.IGNORECASE)


def get_custom_cfg(pack_id):
    cfg=CUSTOM_CONFIG.get(int(pack_id))
    return dict(cfg) if cfg else None


def _store_entry(pid,cfg):
    pid=int(pid); size=int(cfg["size"]); price=int(cfg["price"]); name=str(cfg["name"]); bio=str(cfg["bio"])
    # Match the stock Local FUT store schema one-for-one. Keep all IDs aligned,
    # and expose the copy in every title/description field FIFA has been seen to read.
    visual_asset_id = int(cfg.get("pack_asset_id") or 4)
    store_group = str(cfg.get("store_group") or "special")
    rare_qty = max(0,min(size,int(cfg.get("rare_slots") or 0)))
    return {
      "id":pid,"assetId":visual_asset_id,"packId":pid,"packAssetId":visual_asset_id,
      "quantity":1,"unopenedQuantity":0,"unopened":False,"isReward":False,"isMyPack":False,"tradable":True,"tradeable":True,
      "name":name,"packName":name,"displayName":name,"title":name,"description":name,
      "packDescription":bio,"longDescription":bio,"shortDescription":bio,"bio":bio,
      "label":name,"displayLabel":name,"storePackName":name,
      "localizedName":name,"localizedDescription":bio,"titleText":name,"descriptionText":bio,"packDesc":bio,
      "finalPrice":price,"originalPrice":price,"coins":price,"points":0,
      "currencies":[{"name":"coins","funds":price,"finalFunds":price},{"name":"points","funds":0,"finalFunds":0}],
      "categoryList":{"categoryId":4,"orderInCategory":pid},"displayGroup":{"value":store_group,"priority":4},
      "purchaseGroup":store_group,"group":store_group,"state":"active","packType":"GOLD","sortPriority":pid,
      "packContentInfo":{"itemQuantity":size,"goldQuantity":size,"silverQuantity":0,"bronzeQuantity":0,"rareQuantity":rare_qty},
      "visible":True,"isPurchaseable":True,"isCoinPurchasable":True,"isFifaPointPurchasable":False,"isPromo":True,"isAvailableInStore":True,
    }


def store_entries():
    return [_store_entry(pid,CUSTOM_CONFIG[pid]) for pid in sorted(CUSTOM_CONFIG)]


def _rid(m): return int(m.get("resourceId") or 0)
def _name(m): return str(m.get("name") or m.get("commonName") or m.get("lastName") or m.get("resourceId") or "Player")
def _meta(g,rid):
    f=g.get("player_meta")
    if callable(f): return f(int(rid))
    db=g["PLAYER_DB"]; return db.get(str(int(rid)),{}) or db.get(int(rid),{}) or {}


def _head_file_candidates(resource_id):
    root=Path(__file__).resolve().parent
    rid=int(resource_id)
    return (
        root / "localfut20" / "playerheads" / f"p{rid}.dds",
        root / "runtime" / "content-cache" / "content-cache" / "catalog-playerheads-v12" / f"p{rid}.dds",
    )


def _valid_head_file(path):
    try:
        if not path.is_file() or path.stat().st_size < 128:
            return False
        with path.open("rb") as fh:
            return fh.read(4) == b"DDS "
    except Exception:
        return False


def _register_pick_head_aliases(g, resource_ids):
    """Register only verified same-player portrait aliases for Player Picks.

    V29 used a generic bundled Icon portrait when no matching file existed.
    That prevented the normal FUT content resolver from handling non-Icon
    special cards and produced the repeated/wrong face seen on TOTY/TOTS/TOTW
    picks. V30 deliberately leaves unresolved heads unaliased so the server's
    catalog portrait path can build the correct DDS for that exact resource.
    """
    db=g.get("PLAYER_DB") or {}
    by_asset=defaultdict(list)
    for meta in db.values():
        try:
            rid=int(meta.get("resourceId") or 0)
            aid=int(meta.get("assetId") or rid)
        except Exception:
            continue
        if rid and aid:
            by_asset[aid].append(meta)

    log=g.get("log")
    for rid0 in resource_ids:
        rid=int(rid0)
        meta=_meta(g,rid)
        aid=int(meta.get("assetId") or rid)
        source=None

        # Exact resource portrait always wins.
        for p in _head_file_candidates(rid):
            if _valid_head_file(p):
                source=p
                break

        # Icons may safely reuse another version of the *same player*.
        rarity=str(meta.get("rarityName") or "")
        if source is None and rarity in {"Icon","Icon Moments"}:
            rows=sorted(
                by_asset.get(aid,[]),
                key=lambda m:(0 if str(m.get("rarityName") or "")=="Icon Moments" else 1,
                              -int(m.get("rating") or 0), int(m.get("resourceId") or 0))
            )
            for candidate in rows:
                crid=int(candidate.get("resourceId") or 0)
                for p in _head_file_candidates(crid):
                    if _valid_head_file(p):
                        source=p
                        break
                if source:
                    break

        if source is not None:
            _PICK_HEAD_ALIASES[rid]=str(source)
            # Asset-id alias is safe only when the source is the same player's image.
            _PICK_HEAD_ALIASES[aid]=str(source)
            if log:
                log.warning("PLAYER-PICK HEAD MAP resource=%s asset=%s source=%s",rid,aid,source.name)
        else:
            # Remove stale aliases so the stock dynamic portrait resolver gets the request.
            _PICK_HEAD_ALIASES.pop(rid,None)
            _PICK_HEAD_ALIASES.pop(aid,None)
            if log:
                log.warning("PLAYER-PICK HEAD FALLTHROUGH resource=%s asset=%s rarity=%s",rid,aid,rarity)

def _serve_pick_head(raw_path, g):
    match=_PICK_HEAD_RE.search(urlsplit(str(raw_path)).path)
    if not match:
        return None
    requested=int(match.group(1))
    source=_PICK_HEAD_ALIASES.get(requested)
    if not source:
        return None
    path=Path(source)
    if not _valid_head_file(path):
        return None
    try:
        body=path.read_bytes()
    except Exception:
        return None
    log=g.get("log")
    if log:
        log.warning("PLAYER-PICK HEAD SERVE request=%s source=%s bytes=%s",requested,path.name,len(body))
    return 200, {
        "Content-Type":"application/octet-stream",
        "Cache-Control":"no-store, no-cache, must-revalidate, max-age=0",
        "Pragma":"no-cache",
        "Connection":"close",
        "Content-Length":str(len(body)),
    }, body


def _all99(g):
    rows=[m for m in g["PLAYER_DB"].values() if _rid(m) and int(m.get("rating") or 0)==99]
    rows.sort(key=lambda m:(_name(m).casefold(),str(m.get("rarityName") or ""),_rid(m)))
    return [_rid(m) for m in rows]


def _pools(g):
    by=defaultdict(list); moments=[]; special86=[]; toty=[]; tots=[]
    for m in g["PLAYER_DB"].values():
        rid=_rid(m)
        if not rid: continue
        rarity=str(m.get("rarityName") or "")
        rating=int(m.get("rating") or 0)
        if rarity=="Icon": by[int(m.get("assetId") or rid)].append(m)
        elif rarity=="Icon Moments": moments.append(rid)
        if bool(m.get("special")) and rating>=86:
            special86.append(rid)
        if rarity=="Team of the Year":
            toty.append(rid)
        if rarity in {"Team of the Season So Far","TOTS Moments"}:
            tots.append(rid)
    baby=[]; mid=[]; prime=[]; overflow=[]
    for rows in by.values():
        rows=sorted(rows,key=lambda m:(int(m.get("rating") or 0),_rid(m)))
        if rows: baby.append(_rid(rows[0]))
        if len(rows)>=2: mid.append(_rid(rows[1]))
        if len(rows)>=3: prime.append(_rid(rows[2]))
        if len(rows)>3: overflow.extend(_rid(m) for m in rows[3:])
    moments.extend(overflow)
    return {
        "baby":sorted(set(baby)),"mid":sorted(set(mid)),"prime":sorted(set(prime)),
        "moments":sorted(set(moments)),"special86":sorted(set(special86)),
        "toty":sorted(set(toty)),"tots":sorted(set(tots)),
    }


def _weighted_sample_resources(pool, g, count, rating_bias=1.0):
    """Unique random sample with a gentle rating bias for the 86+ special pick."""
    rng=random.SystemRandom(); remaining=list(dict.fromkeys(int(x) for x in pool)); out=[]
    count=min(int(count),len(remaining))
    while remaining and len(out)<count:
        weights=[]
        for rid in remaining:
            rating=int(_meta(g,rid).get("rating") or 0)
            weights.append(float(rating_bias) ** max(0,rating-86))
        total=sum(weights)
        needle=rng.random()*total
        acc=0.0; chosen_index=len(remaining)-1
        for i,w in enumerate(weights):
            acc+=w
            if needle<=acc:
                chosen_index=i; break
        out.append(remaining.pop(chosen_index))
    return out


def _response(state,g,pid,resources):
    owned=set(int(x) for x in state.owned_player_resource_ids()); seen=set(); items=[]; dups=[]
    for rid in resources:
        rid=int(rid); dup=rid in owned or rid in seen; item=state.make_player_item(rid,"unassigned")
        if dup:
            state.mark_item_duplicate(int(item["id"]),True); item=state.get_item(int(item["id"])) or item; dups.append(item)
        items.append(item); seen.add(rid)
    return {"packId":int(pid),"purchasedPackId":int(pid),"packType":"CUSTOM_PACK","itemList":items,"itemData":items,"items":items,"newcards":max(0,len(items)-len(dups)),"numberItems":len(items),"duplicateItemIdList":dups,"credits":state.credits()}


def _next_token_id():
    global _NEXT_TOKEN_ID
    _NEXT_TOKEN_ID += 1
    return _NEXT_TOKEN_ID


def _next_candidate_id():
    global _NEXT_CANDIDATE_ID
    _NEXT_CANDIDATE_ID += 1
    return _NEXT_CANDIDATE_ID


def _ensure_real_pick_static(g):
    """Expose the genuine FUT 20 player-pick definition to the local State builder."""
    db=g.get("CONSUMABLE_DB")
    if isinstance(db,dict) and int(REAL_PICK_RESOURCE_ID) not in db:
        db[int(REAL_PICK_RESOURCE_ID)]=dict(REAL_PICK_STATIC)


def _token_item(backing, pack_id, title, sequence):
    """Return a subtype-237 token whose static identity is FIFA 20's 1-of-3 pick."""
    item=dict(backing or {})
    token_id=int(item.get("id") or 0)
    item.update({
        "id":token_id,
        "resourceId":REAL_PICK_RESOURCE_ID,
        "assetId":0,
        "definitionId":REAL_PICK_RESOURCE_ID,
        "_definitionId":REAL_PICK_RESOURCE_ID,
        "cardassetid":REAL_PICK_CARD_ASSET_ID,
        "rating":99,
        "itemState":"free",
        "rareflag":1,"rareFlag":1,
        "itemType":"misc","type":"playerPick",
        "cardsubtypeid":237,"cardSubtypeId":237,"subtype":237,"itemSubType":237,
        "owners":1,"untradeable":True,"pile":"unassigned","discardValue":0,
        "formation":"f433","teamid":0,"leagueId":0,"loans":0,
        "statsList":[],"lifetimeStats":[],"attributeList":[],
        "resourceGameYear":2020,"weightrare":0,"amount":4012,
        "name":"PlayerPickItemName113",
        "detaildescription":"PlayerPickItemDetailDesc113",
        "description":"1 of 3 FUT Champions Players",
        # These aliases are retained because the local repository uses them to
        # classify an owned item; the underlying static resource is now exact.
        "displayName":title,"shortName":title,"title":title,
        "sequence":int(sequence),"customPackId":int(pack_id),"isPlayerPick":True,
    })
    # Keep synthetic cardinality fields off the owned token. The native 1-of-3
    # static definition already carries its own cardinality semantics.
    for key in ("availablePicks","pickSize","selectionSize"):
        item.pop(key,None)
    return item


def _migrate_legacy_pick_tokens(state, g=None):
    """Upgrade unresolved older custom pick tokens; never touch resolved players."""
    pick_state.ensure(state)
    changed=[]
    with state.lock:
        rows=state.conn.execute("""SELECT t.token_id,t.pack_id,t.title,t.sequence,t.token_json,i.data
          FROM player_pick_tokens t JOIN items i ON i.id=t.token_id
          WHERE t.status='available' ORDER BY t.token_id""").fetchall()
        for token_id,pack_id,title,sequence,token_json,item_data in rows:
            try: token=json.loads(token_json or "{}")
            except Exception: token={}
            try: stored=json.loads(item_data or "{}")
            except Exception: stored={}
            rid=int(token.get("resourceId") or stored.get("resourceId") or 0)
            if rid==REAL_PICK_RESOURCE_ID:
                continue
            # Limit migration to our legacy custom Player Pick instances.
            subtype=int(token.get("cardsubtypeid") or stored.get("cardsubtypeid") or 0)
            name=str(token.get("name") or stored.get("name") or "")
            if rid not in LEGACY_PICK_RESOURCE_IDS and subtype!=237 and not name.startswith("PlayerPickItemName"):
                continue
            base=stored or token
            migrated=_token_item(base,int(pack_id),str(title),int(sequence))
            payload=json.dumps(migrated,separators=(",",":"),ensure_ascii=False)
            state.conn.execute("UPDATE items SET resource_id=?,pile=?,data=? WHERE id=?",
                               (REAL_PICK_RESOURCE_ID,"unassigned",payload,int(token_id)))
            state.conn.execute("UPDATE player_pick_tokens SET token_json=? WHERE token_id=?",
                               (payload,int(token_id)))
            changed.append(int(token_id))
        if changed:
            state.conn.commit()
    if changed and g and g.get("log"):
        g["log"].warning(
            "PLAYER-PICK STATIC MIGRATION tokens=%s old=%s new=%s name=%s amount=%s",
            changed,sorted(LEGACY_PICK_RESOURCE_IDS),REAL_PICK_RESOURCE_ID,
            "PlayerPickItemName113",4012,
        )
    return changed


def _persist_pick_token(state, pack_id, title, sequence, g):
    _ensure_real_pick_static(g)
    backing=state.make_consumable_item(REAL_PICK_RESOURCE_ID,"unassigned",1)
    token=_token_item(backing,pack_id,title,sequence)
    token_id=int(token["id"])
    fields={k:v for k,v in token.items() if k not in {"id","timestamp"}}
    state.update_item_fields(token_id,fields)
    stored=state.get_item(token_id) or token
    return _token_item(stored,pack_id,title,sequence)


def _create_pick_tokens(state, pack_id, g):
    pid=int(pack_id)
    specs={
        24:("baby","Baby Icon 3x3 Player Pick",3),
        25:("mid","Mid Icon 3x3 Player Pick",3),
        26:("prime","Prime Icon 3x3 Player Pick",3),
        27:("moments","Icon Moments 3x3 Player Pick",3),
        29:("special86","86+ Special 1 of 3 Player Pick",1),
        30:("toty","TOTY 1 of 3 Player Pick",1),
        31:("tots","TOTS 1 of 3 Player Pick",1),
    }
    key,title,token_count=specs[pid]
    pool=list(_pools(g)[key])
    if len(pool)<3: raise RuntimeError(f"{title}: player pool has only {len(pool)} cards")
    out=[]
    for seq in range(1,int(token_count)+1):
        token=_persist_pick_token(state,pid,title,seq,g)
        token_id=int(token["id"])
        pick_state.register_token(state,token,pid,key,title,seq,pool)
        log=g.get("log")
        if log: log.warning("PICK_TOKEN_CREATED token=%s pack=%s sequence=%s pile=unassigned",token_id,pid,seq)
        out.append(token)
    return out


def _gold_players_pack_resources(g, count=12, rare_slots=1):
    """Return base Gold player resources only; specials are intentionally excluded."""
    normal=[]; rare=[]
    for m in (g.get("PLAYER_DB") or {}).values():
        try:
            rid=_rid(m); rating=int(m.get("rating") or 0)
        except Exception:
            continue
        if not rid or bool(m.get("special")) or rating < 75:
            continue
        tier=str(m.get("tier") or "").lower()
        rarity=str(m.get("rarityName") or "")
        if tier != "gold" and "Gold" not in rarity:
            continue
        (rare if int(m.get("rareflag") or 0) else normal).append(rid)
    rng=random.SystemRandom()
    rare_slots=max(1,min(int(rare_slots),int(count)))
    if len(rare) < rare_slots or len(normal)+len(rare) < count:
        raise RuntimeError("Gold Players Pack: not enough eligible Gold players")
    chosen=rng.sample(rare,rare_slots)
    pool=[rid for rid in normal+rare if rid not in chosen]
    chosen.extend(rng.sample(pool,int(count)-len(chosen)))
    rng.shuffle(chosen)
    return chosen


def create_custom_pack(state,pid,g):
    pid=int(pid)
    if pid in PICK_IDS:
        tokens=_create_pick_tokens(state,pid,g)
        log=g.get("log")
        if log: log.warning("NATIVE PLAYER PICK pack=%s tokens=%s",pid,[x["id"] for x in tokens])
        return {"packId":pid,"purchasedPackId":pid,"packType":"PLAYER_PICK","itemList":tokens,"itemData":tokens,"items":tokens,"newcards":len(tokens),"numberItems":len(tokens),"duplicateItemIdList":[],"credits":state.credits()}
    if pid==32:
        resources=_gold_players_pack_resources(g,12,1)
        log=g.get("log")
        if log: log.warning("CUSTOM GOLD PLAYERS PACK pack=%s resources=%s",pid,resources)
        return _response(state,g,pid,resources)
    raise RuntimeError(f"Unknown custom pack id {pid}")


def _candidate_payload(state, g, token_id):
    """Redeem one token into persistent temporary candidate storage."""
    token_id=int(token_id)
    active=pick_state.active(state)
    if active:
        return _pick_payload(state,active,g,"PICK_PENDING_RETURNED")
    spec=pick_state.token(state,token_id)
    if not spec: return None
    candidates=(_weighted_sample_resources(spec["pool"],g,3,1.10) if spec.get("pool_key")=="special86" else random.SystemRandom().sample(list(spec["pool"]),3))
    _register_pick_head_aliases(g,candidates)
    owned=set(int(x) for x in state.owned_player_resource_ids())
    # Player-pick candidates are temporary reward items, not Unassigned-repository
    # items yet.  Serialize them with the same wire shape used by normal pack
    # rewards.  The previous _native_player_item serializer leaked repository-only
    # state (pile=unassigned, definitionId aliases, numeric injuryType) into the
    # Player Pick carousel.  FIFA renders that shape, but its *successful confirm*
    # path then tries to transition the temporary item into New Items and can crash
    # because the item already claims to live in Unassigned.
    #
    # _native_pack_item preserves the stock pack wire contract (including contracts
    # and the string injuryType) and deliberately has no pile.  We still keep a
    # stable instance id so the exact displayed card can later be persisted.
    native_item=g.get("_native_pack_item") or g.get("_native_player_item")
    items=[]; ownership=[]
    for rid in candidates:
        cid=state.next_item_id()
        raw=state.build_player_item(int(rid),int(cid),"unassigned",0)
        raw.update({"id":int(cid),"resourceId":int(rid),"untradeable":True,"discardValue":0})
        item=native_item(raw) if callable(native_item) else dict(raw)
        item.update({"id":int(cid),"resourceId":int(rid),"untradeable":True,"discardValue":0})
        # These fields describe repository/static aliases, not temporary pick
        # candidates.  Keep the wire model identical to an unopened pack reward.
        for transient_key in ("pile","definitionId","_definitionId"):
            item.pop(transient_key,None)
        items.append(item); ownership.append(int(rid) in owned)
    active,created=pick_state.begin(state,token_id,items,ownership)
    if not active: return None
    log=g.get("log")
    if log:
        log.warning("PICK_TOKEN_REDEEMED token=%s consumed=1 created=%s",token_id,created)
        log.warning("PICK_TEMP_STORAGE_CREATED token=%s candidateIds=%s resources=%s",token_id,[x.get("id") for x in active["items"]],active["resource_ids"])
    _sync_pick_state(state)
    return _pick_payload(state,active,g,"PICK_PENDING_RETURNED")


def _pick_payload(state,active,g,event=None):
    items=list(active["items"]); ownership=list(active.get("ownership") or [False]*len(items))
    if event and g.get("log"):
        g["log"].warning("%s token=%s candidateIds=%s",event,active["token_id"],[x.get("id") for x in items])
    return {"success":True,"playerPickItemId":active["token_id"],"pickId":active["token_id"],
        "data":{"playerPicks":items,"availablePicks":1,"ownership":ownership},
        "response":{"items":items,"availablePicks":1,"ownership":ownership},
        "playerPicks":items,"itemData":items,"itemList":items,"items":items,
        "numberItems":len(items),"availablePicks":1,"pickSize":3,"selectionSize":3,
        "ownership":ownership,"duplicateItemIdList":[],"credits":state.credits()}


def _confirm_active(state, selected_value, g):
    """Move the exact selected candidate instance into Unassigned."""
    global _LAST_CONFIRMED
    active=pick_state.active(state)
    if not active: return None
    selected_value=int(selected_value)
    chosen=next((x for x in active["items"] if selected_value in
        {int(x.get(k) or 0) for k in ("id","resourceId","assetId","definitionId","_definitionId")}),None)
    if not chosen: return None
    token_id=int(active["token_id"]); rid=int(chosen["resourceId"])
    duplicate=rid in set(int(x) for x in state.owned_player_resource_ids())
    log=g.get("log")
    if log: log.warning("PICK_SELECTION_REQUEST token=%s value=%s",token_id,selected_value)
    result=pick_state.select(state,selected_value,duplicate)
    if not result: return None
    final=state.get_item(result["candidate_id"]) or result["item"]
    _LAST_CONFIRMED=dict(result)
    _sync_pick_state(state)
    if log:
        log.warning("PICK_SELECTED_INSTANCE token=%s candidate=%s resource=%s",token_id,result["candidate_id"],rid)
        log.warning("PICK_TEMP_STORAGE_CLEARED token=%s candidates=%s",token_id,result["candidate_ids"])
        log.warning("PICK_SELECTED_MOVED_UNASSIGNED token=%s item=%s resource=%s pile=unassigned",token_id,result["candidate_id"],rid)
    return dict(final)


def _commit_pending_confirmation(state, g):
    # V21 commits during /select because the three candidates are virtual and
    # therefore there is no live DB candidate object to mutate unsafely.
    return False

def _decode_body(body):
    if not body: return None
    try:
        if isinstance(body,(bytes,bytearray)): body=body.decode("utf-8","replace")
        return json.loads(body)
    except Exception:
        return None


def _ints(value, out=None):
    if out is None: out=set()
    if isinstance(value,bool) or value is None: return out
    if isinstance(value,int): out.add(int(value)); return out
    if isinstance(value,float) and value.is_integer(): out.add(int(value)); return out
    if isinstance(value,str):
        try:
            s=value.strip()
            if s.isdigit(): out.add(int(s))
        except Exception: pass
        return out
    if isinstance(value,dict):
        for k,v in value.items(): _ints(k,out); _ints(v,out)
    elif isinstance(value,(list,tuple,set)):
        for v in value: _ints(v,out)
    return out


def _json_tuple(payload,status=200):
    return int(status), {"Cache-Control":"no-store"}, json.dumps(payload,separators=(",",":"),ensure_ascii=False).encode("utf-8")


def _sync_pick_state(state, g=None):
    """Refresh compatibility views from durable state for existing routes."""
    global _PICK_TOKENS, _ACTIVE_PICK
    _migrate_legacy_pick_tokens(state,g)
    tokens=pick_state.available_tokens(state)
    _PICK_TOKENS={x["token_id"]:{**x,"backing_item_id":x["token_id"]} for x in tokens}
    _ACTIVE_PICK=pick_state.active(state)


def handle_native_request(state, method, raw_path, headers, body, g):
    """Intercept only native player-pick traffic. Everything else falls through unchanged."""
    global _ACTIVE_PICK, _AWAITING_NEW_ITEMS, _FALLBACK_BLOCK_UNTIL, _PENDING_REJECT_CLEANUP, _PENDING_CONFIRM
    _sync_pick_state(state,g)
    split=urlsplit(str(raw_path))
    path=split.path
    raw_low=str(raw_path).lower()
    low=path.lower()
    method=str(method).upper()
    body_obj=_decode_body(body)
    vals=_ints(body_obj)

    # Commit the accepted choice only when FIFA has left the Player Pick view
    # and starts its normal New Items refresh.  This happens BEFORE the stock
    # purchased/items handler serializes the database, so the selected card is
    # returned exactly like a normal pack card.
    normalized_low=low.replace("/ut/ut/","/ut/")
    if method=="GET" and normalized_low=="/ut/game/fifa20/purchased/items" and _PENDING_CONFIRM:
        _commit_pending_confirmation(state,g)

    # The v12 crash report showed FIFA dying immediately after a 404 for the
    # selected Icon's player-head DDS. Serve a bundled same-player Icon portrait
    # before the stock content fallback can return 404.
    if method=="GET":
        head_response=_serve_pick_head(raw_path,g)
        if head_response is not None:
            return head_response

    # FIFA can put the player-pick instance id in the query string rather than
    # the JSON body. v6 did not inspect query values, which could leave the
    # native pick screen open with no active candidate set.
    query=parse_qs(split.query, keep_blank_values=True)
    _ints(query, vals)
    for part in path.replace("/"," ").replace("-"," ").split():
        if part.isdigit(): vals.add(int(part))

    log=g.get("log")
    if log and (_PICK_TOKENS or _ACTIVE_PICK):
        log.warning(
            "PLAYER-PICK TRACE method=%s raw=%s values=%s active=%s pending=%s",
            method, raw_path, sorted(vals),
            (_ACTIVE_PICK or {}).get("token_id"), sorted(_PICK_TOKENS),
        )

    token_id=next((v for v in vals if v in _PICK_TOKENS),None)
    pick_route = any(key in raw_low for key in (
        "playerpick","player-pick","player_pick","playerpicks",
        "pickitemselection","pick-item-selection","pendingpick","pending-pick"
    ))
    select_route = bool(re.search(r"/playerpicks/item/\d+/select/?$", low))

    # Confirmation must only intercept the dedicated player-pick service. v8
    # accepted ANY POST/PUT/DELETE containing a candidate number, which could
    # swallow an unrelated item/telemetry request and return the wrong schema.
    if _ACTIVE_PICK and pick_route and method in {"POST","PUT","DELETE"}:
        for item in _ACTIVE_PICK["items"]:
            candidates={int(item.get("id") or 0),int(item.get("resourceId") or 0),int(item.get("assetId") or 0),int(item.get("definitionId") or 0)}
            hit=next((v for v in vals if v in candidates),None)
            if hit is not None:
                if log: log.warning("PLAYER-PICK CONFIRM ROUTE hit=%s via=%s %s body=%r",hit,method,raw_path,body_obj)
                confirmed = _confirm_active(state,hit,g)
                if confirmed is not None:
                    # FUT 19's native PC Player Pick flow does NOT finish selection
                    # with an empty acknowledgement.  It persists the exact selected
                    # candidate into New Items first, then returns that selected player
                    # as the top-level JSON response.  FIFA wraps/consumes the item as
                    # part of the successful view transition.  Our previous FIFA 20
                    # builds returned HTTP 200 with a zero-byte body; the game then
                    # exited before it ever requested /purchased/items.
                    #
                    # Keep the three carousel candidates on the proven pack-wire shape,
                    # but return the selected *owned/unassigned* item using the normal
                    # native player serializer after the transactional state move.
                    # This mirrors FutDeba FUT19's /playerpicks/item/{resourceId}/select
                    # contract while retaining FIFA 20's own static Pick Item identity.
                    native_selected = g.get("_native_player_item")
                    selected_wire = (native_selected(dict(confirmed))
                                     if callable(native_selected) else dict(confirmed))
                    if log:
                        log.warning(
                            "PLAYER-PICK CONFIRM RESPONSE status=200 selectedItem=%s resource=%s pile=%s bytes=json semantics=FUT19",
                            selected_wire.get("id"), selected_wire.get("resourceId"),
                            selected_wire.get("pile"),
                        )
                    return _json_tuple(selected_wire)

    # A late /select from a pick that has already been confirmed must NEVER
    # activate another token. FIFA 20 can replay one of the old candidate
    # resource IDs while rebuilding New Items. Treat that replay as an
    # idempotent success and leave the two untouched pick tokens alone.
    if select_route and method in {"POST","PUT","DELETE"} and _ACTIVE_PICK is None:
        # Make a repeated native confirmation idempotent. If FIFA replays the
        # exact selection while rebuilding New Items, return the same selected
        # player object again instead of an empty body. This preserves the FUT19
        # selection contract and cannot create a second inventory row.
        last_item = dict((_LAST_CONFIRMED or {}).get("item") or {})
        last_values = {
            int((_LAST_CONFIRMED or {}).get("candidate_id") or 0),
            int((_LAST_CONFIRMED or {}).get("resource_id") or 0),
            int(last_item.get("id") or 0),
            int(last_item.get("resourceId") or 0),
        }
        if last_item and any(v and v in vals for v in last_values):
            native_selected = g.get("_native_player_item")
            selected_wire = (native_selected(last_item)
                             if callable(native_selected) else last_item)
            if log:
                log.warning("PLAYER-PICK STALE SELECT replayed selected item via=%s %s values=%s",
                            method,raw_path,sorted(vals))
            return _json_tuple(selected_wire)
        if log:
            log.warning("PLAYER-PICK STALE SELECT ignored unmatched via=%s %s values=%s last=%s",
                        method,raw_path,sorted(vals),_LAST_CONFIRMED)
        return 200, {"Cache-Control":"no-store"}, b""

    # Redeem/open a player-pick token. Permit GET as well because different FUT
    # clients expose the instance id in a query-string read before opening.
    if token_id is not None and method in {"GET","POST","PUT"}:
        # An explicit token id means the user intentionally redeemed another
        # Player Pick from New Items. It is safe to arm a fresh native pick.
        _AWAITING_NEW_ITEMS=False
        _FALLBACK_BLOCK_UNTIL=0.0
        if _PENDING_REJECT_CLEANUP:
            cleanup_ids=sorted(_PENDING_REJECT_CLEANUP)
            for iid in cleanup_ids:
                try: state.delete_item(int(iid))
                except Exception: pass
            _PENDING_REJECT_CLEANUP.clear()
            if log: log.warning("PLAYER-PICK CLEANUP before next explicit token rejected=%s",cleanup_ids)
        payload=_candidate_payload(state,g,token_id)
        if log: log.warning("PLAYER-PICK ACTIVATE token=%s via=%s %s",token_id,method,raw_path)
        return _json_tuple(payload)

    if pick_route:
        # v14 crash telemetry proved that automatic fallback activation is
        # unsafe: FIFA can replay an old /select request after the first pick
        # has already completed. Only an explicit token redemption may arm a
        # new pick. If a pick is active, return its existing three candidates;
        # otherwise report no pending selection.
        if _ACTIVE_PICK:
            a=_ACTIVE_PICK
            ownership=list(a.get("ownership") or [False]*len(a["items"]))
            payload={
                "items":a["items"],"availablePicks":1,"ownership":ownership,
                "itemData":a["items"],"itemList":a["items"],"playerPicks":a["items"],
                "numberItems":len(a["items"]),"playerPickItemId":a["token_id"],"pickId":a["token_id"],
                "success":True,"credits":state.credits(),
                "data":{"playerPicks":a["items"],"availablePicks":1,"ownership":ownership},
                "response":{"items":a["items"],"availablePicks":1,"ownership":ownership},
            }
            return _json_tuple(payload)
        if log:
            log.warning("PLAYER-PICK NO ACTIVE PICK; explicit token redemption required via=%s",raw_path)
        return _json_tuple({
            "items":[],"availablePicks":0,"ownership":[],
            "itemData":[],"itemList":[],"playerPicks":[],"numberItems":0,
            "success":True,
            "response":{"items":[],"availablePicks":0},
            "data":{"playerPicks":[],"availablePicks":0},
        })
    return None

def _xml_escape(value):
    return (str(value).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            .replace('"',"&quot;").replace("'","&apos;"))


def augment_response(state, method, raw_path, response, g):
    """Add custom pack localization and keep unredeemed pick tokens visible."""
    global _AWAITING_NEW_ITEMS, _PENDING_REJECT_CLEANUP, _FALLBACK_BLOCK_UNTIL, _PENDING_CONFIRM
    try:
        _sync_pick_state(state)
        path=urlsplit(str(raw_path)).path.lower().replace("/ut/ut/","/ut/")
        status,headers,raw=response

        # FIFA 20 ignores custom title/description fields in the store JSON and
        # resolves visible store copy through this XLIFF localization catalog.
        # IDs 23-27 must therefore exist here just like the stock packs do.
        if str(method).upper()=="GET" and "storepackdescriptions." in path and path.endswith(".xml"):
            text=raw.decode("utf-8","replace")
            if "</body>" in text:
                units=[]
                for pid in sorted(CUSTOM_CONFIG):
                    cfg=CUSTOM_CONFIG[pid]
                    name=_xml_escape(cfg["name"]); desc=_xml_escape(cfg["bio"])
                    if f'FUT_STORE_PACK_{pid}_NAME' in text:
                        continue
                    units.extend([
                        f'      <trans-unit id="FUT_STORE_PACK_{pid}_NAME" resname="FUT_STORE_PACK_{pid}_NAME"><source>{name}</source></trans-unit>',
                        f'      <trans-unit id="FUT_STORE_PACK_{pid}_DESC" resname="FUT_STORE_PACK_{pid}_DESC"><source>{desc}</source></trans-unit>',
                        f'      <trans-unit id="FUT_STORE_PACK_{pid}_NAME_MOBILE" resname="FUT_STORE_PACK_{pid}_NAME_MOBILE"><source>{name}</source></trans-unit>',
                    ])
                if units:
                    text=text.replace("    </body>","\n".join(units)+"\n    </body>")
                    raw=text.encode("utf-8")
                    headers=dict(headers)
                    headers["Content-Length"]=str(len(raw))
                    log=g.get("log")
                    if log: log.warning("CUSTOM PACK LOC injected ids=%s",sorted(CUSTOM_CONFIG))
            return status,headers,raw

        if str(method).upper()=="GET" and ("usermassinfo" in path or "/user/massinfo" in path or path.endswith("/settings")):
            obj=json.loads(raw.decode("utf-8")); pending=pick_state.pending_flag(state)
            if "settings" in path:
                obj["enablePlayerPicks"]=1
                if isinstance(obj.get("settings"),dict): obj["settings"]["enablePlayerPicks"]=1
            else:
                obj["isPlayerPicksTemporaryStorageNotEmpty"]=pending
                if isinstance(obj.get("userInfo"),dict): obj["userInfo"]["isPlayerPicksTemporaryStorageNotEmpty"]=pending
            encoded=json.dumps(obj,separators=(",",":"),ensure_ascii=False).encode("utf-8")
            headers=dict(headers); headers["Content-Length"]=str(len(encoded))
            return status,headers,encoded

        if str(method).upper()!="GET" or path!="/ut/game/fifa20/purchased/items":
            return response

        # Reaching purchased/items means FIFA has safely left the native pick
        # view and is rebuilding New Items. Only now remove the four rejected
        # temporary candidates and re-enable fallback activation for a later
        # player-pick token.
        # Seeing New Items proves navigation progressed, but keep the short
        # post-confirm time barrier in place because FIFA can still issue a late
        # pending-pick poll during the transition. Rejected candidate rows are
        # cleaned only after that barrier or when the user explicitly redeems
        # another token.
        if _PENDING_REJECT_CLEANUP and time.monotonic() >= _FALLBACK_BLOCK_UNTIL:
            cleanup_ids=sorted(_PENDING_REJECT_CLEANUP)
            for iid in cleanup_ids:
                try: state.delete_item(int(iid))
                except Exception: pass
            _PENDING_REJECT_CLEANUP.clear()
            log=g.get("log")
            if log: log.warning("PLAYER-PICK CLEANUP after safe New Items rejected=%s",cleanup_ids)
        if _AWAITING_NEW_ITEMS:
            _AWAITING_NEW_ITEMS=False
            log=g.get("log")
            if log: log.warning("PLAYER-PICK NEW ITEMS reached; post-confirm timer remains until=%s",_FALLBACK_BLOCK_UNTIL)

        if not _PICK_TOKENS:
            return response
        obj=json.loads(raw.decode("utf-8"))
        rows=list(obj.get("itemData") or [])
        # V21 candidates live only in temporary player-pick state, so there are no
        # native success transition sees a valid inventory object. They must not
        # appear in New Items before a choice is confirmed, so hide the three active
        # temporary candidate instance IDs to filter from purchased/items serialization.
        hidden_candidate_ids=set()
        if _ACTIVE_PICK:
            hidden_candidate_ids.update(int(x.get("id") or 0) for x in _ACTIVE_PICK.get("items") or [] if int(x.get("id") or 0))
        if hidden_candidate_ids:
            rows=[row for row in rows if not (isinstance(row,dict) and int(row.get("id") or 0) in hidden_candidate_ids)]
        replaced=[]
        seen=set()
        for row in rows:
            iid=int(row.get("id") or 0) if isinstance(row,dict) else 0
            spec=_PICK_TOKENS.get(iid)
            if spec:
                replaced.append(dict(spec["token"]))
                seen.add(iid)
            else:
                replaced.append(row)
        pending=[dict(spec["token"]) for tid,spec in sorted(_PICK_TOKENS.items()) if int(tid) not in seen]
        rows=pending+replaced
        obj["itemData"]=rows
        obj["itemList"]=rows
        obj["items"]=rows
        obj["numberItems"]=len(rows)
        obj["itemCount"]=len(rows)
        encoded=json.dumps(obj,separators=(",",":"),ensure_ascii=False).encode("utf-8")
        headers=dict(headers)
        headers["Content-Length"]=str(len(encoded))
        return status,headers,encoded
    except Exception as exc:
        log=g.get("log")
        if log: log.warning("Native pick/localization augmentation failed: %s",exc)
        return response

