"""Public profiles, follows, private bookmarks and user blocking."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, delete, or_, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, Case, Follow, UserBlock, Bookmark, Notification


def blocked_ids(db,viewer):
    if not viewer:return set()
    rows=db.execute(select(UserBlock.user_id,UserBlock.target_id).where(or_(UserBlock.user_id==viewer.id,UserBlock.target_id==viewer.id)))
    return {target if owner==viewer.id else owner for owner,target in rows}


def is_blocked(db,viewer,target_id):
    return bool(viewer and target_id in blocked_ids(db,viewer))


def visible_cases(db,viewer):
    query=select(Case).join(User,Case.creator_id==User.id).where(User.account_status=='active',User.suspended==0,Case.moderation_status=='published')
    excluded=blocked_ids(db,viewer)
    return query.where(Case.creator_id.not_in(excluded)) if excluded else query


def build_router(current_user,participant,optional_user,public_user,public_case,get_case):
    router=APIRouter()
    def target_user(db,user_id,viewer=None):
        target=db.get(User,user_id)
        if not target or target.account_status!='active' or target.suspended or is_blocked(db,viewer,user_id):raise HTTPException(404,'Không tìm thấy hồ sơ.')
        return target
    def insert_once(db,model,**values):
        try:
            with db.begin_nested():db.add(model(**values));db.flush()
        except IntegrityError:pass

    @router.get('/api/users/{user_id}')
    def profile(user_id:int,db:Session=Depends(get_db),viewer=Depends(optional_user)):
        target=target_user(db,user_id,viewer)
        excluded=blocked_ids(db,viewer)
        followers=select(func.count()).select_from(Follow).join(User,Follow.user_id==User.id).where(Follow.target_id==user_id,User.account_status=='active',User.suspended==0,Follow.user_id.not_in(excluded))
        following=select(func.count()).select_from(Follow).join(User,Follow.target_id==User.id).where(Follow.user_id==user_id,User.account_status=='active',User.suspended==0,Follow.target_id.not_in(excluded))
        return {**public_user(target),'followers':db.scalar(followers),'following':db.scalar(following),'post_count':db.scalar(select(func.count()).select_from(Case).where(Case.creator_id==user_id,Case.moderation_status=='published')),'followed_by_me':bool(viewer and db.scalar(select(Follow.id).where(Follow.user_id==viewer.id,Follow.target_id==user_id)))}

    @router.get('/api/users/{user_id}/cases')
    def posts(user_id:int,offset:int=Query(0,ge=0),limit:int=Query(12,ge=1,le=100),db:Session=Depends(get_db),viewer=Depends(optional_user)):
        target_user(db,user_id,viewer)
        return [public_case(c,db,viewer) for c in db.scalars(visible_cases(db,viewer).where(Case.creator_id==user_id).order_by(Case.id.desc()).offset(offset).limit(limit))]

    @router.put('/api/users/{user_id}/follow')
    def follow(user_id:int,user=Depends(participant),db:Session=Depends(get_db)):
        target_user(db,user_id,user)
        if user_id==user.id:raise HTTPException(400,'Không thể theo dõi chính mình.')
        insert_once(db,Follow,user_id=user.id,target_id=user_id)
        # One persistent event per pair prevents refollow/HTTP retries spamming.
        key=f"follow:{user_id}:{user.id}"
        if not db.scalar(select(Notification.id).where(Notification.event_key==key)):
            insert_once(db,Notification,event_key=key,recipient_id=user_id,actor_id=user.id,case_id=None,kind='follow')
        db.commit()
        return {'followed_by_me':True}

    @router.delete('/api/users/{user_id}/follow')
    def unfollow(user_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
        db.execute(delete(Follow).where(Follow.user_id==user.id,Follow.target_id==user_id));db.commit()
        return {'followed_by_me':False}

    @router.get('/api/users/{user_id}/followers')
    def followers(user_id:int,offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100),db:Session=Depends(get_db),viewer=Depends(optional_user)):
        target_user(db,user_id,viewer)
        query=select(User).join(Follow,Follow.user_id==User.id).where(Follow.target_id==user_id,User.account_status=='active',User.suspended==0,User.id.not_in(blocked_ids(db,viewer))).order_by(Follow.id.desc()).offset(offset).limit(limit)
        return [public_user(u) for u in db.scalars(query)]

    @router.get('/api/users/{user_id}/following')
    def following_users(user_id:int,offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100),db:Session=Depends(get_db),viewer=Depends(optional_user)):
        target_user(db,user_id,viewer)
        query=select(User).join(Follow,Follow.target_id==User.id).where(Follow.user_id==user_id,User.account_status=='active',User.suspended==0,User.id.not_in(blocked_ids(db,viewer))).order_by(Follow.id.desc()).offset(offset).limit(limit)
        return [public_user(u) for u in db.scalars(query)]

    @router.get('/api/me/bookmarks')
    def bookmarks(offset:int=Query(0,ge=0),limit:int=Query(12,ge=1,le=100),user=Depends(current_user),db:Session=Depends(get_db)):
        query=visible_cases(db,user).join(Bookmark,Bookmark.case_id==Case.id).where(Bookmark.user_id==user.id).order_by(Bookmark.id.desc()).offset(offset).limit(limit)
        return [public_case(c,db,user) for c in db.scalars(query)]

    @router.put('/api/cases/{case_id}/bookmark')
    def bookmark(case_id:int,user=Depends(participant),db:Session=Depends(get_db)):
        get_case(case_id,db,user);insert_once(db,Bookmark,user_id=user.id,case_id=case_id);db.commit()
        return {'bookmarked_by_me':True}

    @router.delete('/api/cases/{case_id}/bookmark')
    def unbookmark(case_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
        db.execute(delete(Bookmark).where(Bookmark.user_id==user.id,Bookmark.case_id==case_id));db.commit()
        return {'bookmarked_by_me':False}

    @router.put('/api/users/{user_id}/block')
    def block(user_id:int,user=Depends(participant),db:Session=Depends(get_db)):
        target=db.get(User,user_id)
        if not target or user_id==user.id:raise HTTPException(400,'Tài khoản không hợp lệ.')
        insert_once(db,UserBlock,user_id=user.id,target_id=user_id)
        db.execute(delete(Follow).where(or_(and_(Follow.user_id==user.id,Follow.target_id==user_id),and_(Follow.user_id==user_id,Follow.target_id==user.id))))
        db.commit();return {'blocked':True}

    @router.delete('/api/users/{user_id}/block')
    def unblock(user_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
        db.execute(delete(UserBlock).where(UserBlock.user_id==user.id,UserBlock.target_id==user_id));db.commit()
        return {'blocked':False}

    @router.get('/api/me/blocks')
    def blocks(offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100),user=Depends(current_user),db:Session=Depends(get_db)):
        query=select(User).join(UserBlock,UserBlock.target_id==User.id).where(UserBlock.user_id==user.id).order_by(UserBlock.id.desc()).offset(offset).limit(limit)
        return [public_user(u) for u in db.scalars(query)]
    return router
