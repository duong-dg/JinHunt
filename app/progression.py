"""Progression thresholds and avatar tiers, derived from total XP."""
from datetime import datetime, timezone, timedelta

TIERS=((50,"diamond","Kim cương"),(30,"platinum","Bạch kim"),(20,"gold","Vàng"),(10,"silver","Bạc"),(5,"bronze","Đồng"),(1,"none","Khởi hành"))

def progression(xp):
    xp=max(0,int(xp or 0))
    level,floor,needed=1,0,200
    while xp>=floor+needed:
        floor+=needed
        level+=1
        # Grow by 15%, rounding up to an integer XP without float drift.
        needed=(needed*115+99)//100
    tier=next(t for t in TIERS if level>=t[0])
    return {"level":level,"xp_in_level":xp-floor,"xp_for_next_level":needed,"xp_to_next_level":needed-(xp-floor),"avatar_frame":tier[1],"rank_name":tier[2]}

def local_day():
    return datetime.now(timezone(timedelta(hours=7))).date()
