import json
import math
import secrets
import time
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session
from PIL import Image
from .database import get_db
from .models import User, Case, Token, ImageReview, ContentReport, ModerationAudit

def build_router(current_user, get_case, upload_dir):
    router = APIRouter()
    def staff(user=Depends(current_user)):
        if user.role not in {"moderator","admin"} or user.guardian_managed:
            raise HTTPException(403,"Cần quyền kiểm duyệt viên.")
        return user

    def audit(db, actor, action, target, reason):
        db.add(ModerationAudit(actor_id=actor.id,action=action,target=str(target),reason=reason,created_at=time.time()))

    class ReportInput(BaseModel):
        reason: Literal["sexual","privacy","copyright","violence","other"]
        details: str = Field(default="",max_length=1000)

    @router.post('/api/cases/{case_id}/reports',status_code=201)
    def report(case_id:int,data:ReportInput,user=Depends(current_user),db:Session=Depends(get_db)):
        case=get_case(case_id,db)
        if db.scalar(select(func.count()).select_from(ContentReport).where(ContentReport.reporter_id==user.id,ContentReport.created_at>time.time()-3600)) >= 10:
            raise HTTPException(429,"Bạn đã gửi nhiều báo cáo. Hãy thử lại sau.")
        if db.scalar(select(ContentReport.id).where(ContentReport.case_id==case_id,ContentReport.reporter_id==user.id,ContentReport.status=="open")):
            return {"message":"Báo cáo của bạn đang được xử lý."}
        db.add(ContentReport(case_id=case_id,reporter_id=user.id,reason=data.reason,details=data.details,created_at=time.time()))
        if not db.get(ImageReview,case.image_url):
            db.add(ImageReview(image_url=case.image_url,user_id=case.creator_id,status="approved",scan=json.dumps({"state":"legacy","warnings":["Ảnh cũ chưa được quét tự động."]}),created_at=time.time()))
        db.commit()
        return {"message":"Đã gửi báo cáo riêng cho kiểm duyệt viên."}

    @router.get('/api/moderation/queue')
    def queue(offset:int=Query(0,ge=0),user=Depends(staff),db:Session=Depends(get_db)):
        images = list(db.scalars(select(ImageReview).where(ImageReview.status=="pending").order_by(ImageReview.created_at).offset(offset).limit(30)))
        cases = list(db.scalars(select(Case).where(Case.moderation_status=="pending").order_by(Case.id).offset(offset).limit(30)))
        reports = list(db.scalars(select(ContentReport).where(ContentReport.status=="open").order_by(ContentReport.id).offset(offset).limit(30)))
        for report in reports:
            image=db.get(ImageReview,db.get(Case,report.case_id).image_url)
            if image and image.image_url not in {item.image_url for item in images}: images.append(image)
        def case_data(c):
            return {"id":c.id,"creator_id":c.creator_id,"title":c.title,"description":c.description,"image_url":c.image_url,"status":c.moderation_status}
        return {"images":[{"image_url":i.image_url,"user_id":i.user_id,"status":i.status,"scan":json.loads(i.scan)} for i in images],
                "cases":[case_data(c) for c in cases],
                "reports":[{"id":r.id,"case_id":r.case_id,"reason":r.reason,"details":r.details,"case":case_data(db.get(Case,r.case_id))} for r in reports]}

    class Decision(BaseModel):
        action: Literal["approve","remove"]
        reason: str = Field(min_length=5,max_length=1000)

    @router.post('/api/moderation/cases/{case_id}')
    def decide_case(case_id:int,data:Decision,user=Depends(staff),db:Session=Depends(get_db)):
        case = db.scalar(select(Case).where(Case.id==case_id).with_for_update())
        if not case: raise HTTPException(404,"Không tìm thấy bài.")
        review = db.get(ImageReview,case.image_url)
        if data.action=="approve" and review and review.status!="approved":
            raise HTTPException(409,"Hãy duyệt ảnh trước khi duyệt bài.")
        case.moderation_status = "published" if data.action=="approve" else "removed"
        if data.action=="remove" and review:
            review.status="removed"
            for linked in db.scalars(select(Case).where(Case.image_url==case.image_url)):
                linked.moderation_status="removed"
        for item in db.scalars(select(ContentReport).where(ContentReport.case_id==case_id,ContentReport.status=="open")):
            item.status="resolved"
        audit(db,user,data.action,f"case:{case_id}",data.reason);db.commit()
        return {"status":case.moderation_status}

    class ImageDecision(Decision):
        image_url: str = Field(max_length=255)

    @router.post('/api/moderation/images/decision')
    def decide_image(data:ImageDecision,user=Depends(staff),db:Session=Depends(get_db)):
        image=db.scalar(select(ImageReview).where(ImageReview.image_url==data.image_url).with_for_update())
        if not image: raise HTTPException(404,"Không tìm thấy ảnh.")
        if image.status=="removed" and data.action=="approve":
            raise HTTPException(409,"Ảnh đã bị gỡ hoặc thay bằng bản che mới; không duyệt lại đường dẫn cũ.")
        image.status="approved" if data.action=="approve" else "removed"
        if data.action=="approve" and image.image_url.startswith('/uploads/avatar-'):
            db.get(User,image.user_id).avatar_url=image.image_url
        if data.action=="remove":
            for c in db.scalars(select(Case).where(Case.image_url==image.image_url)):
                c.moderation_status="removed"
            owner=db.get(User,image.user_id)
            if owner.avatar_url==image.image_url: owner.avatar_url=None
        audit(db,user,data.action,image.image_url,data.reason);db.commit()
        return {"status":image.status}

    class BlurInput(BaseModel):
        image_url: str = Field(max_length=255)
        # Normalized rectangles work for faces, number plates or other private details.
        boxes: list[tuple[float,float,float,float]] = Field(min_length=1,max_length=30)
        reason: str = Field(min_length=5,max_length=1000)

    @router.post('/api/moderation/images/redact')
    def redact(data:BlurInput,user=Depends(staff),db:Session=Depends(get_db)):
        from PIL import ImageFilter
        image=db.scalar(select(ImageReview).where(ImageReview.image_url==data.image_url).with_for_update())
        if not image: raise HTTPException(404,"Không tìm thấy ảnh.")
        if image.status=="removed": raise HTTPException(409,"Ảnh đã bị gỡ hoặc thay thế.")
        for x,y,w,h in data.boxes:
            if not all(math.isfinite(v) for v in (x,y,w,h)) or min(x,y)<0 or min(w,h)<=0 or x+w>1.000001 or y+h>1.000001:
                raise HTTPException(422,"Vùng che không hợp lệ.")
        path=upload_dir/image.image_url.split('/')[-1]
        with Image.open(path) as source: clean=source.convert('RGB')
        for x,y,w,h in data.boxes:
            box=(int(x*clean.width),int(y*clean.height),min(clean.width,int((x+w)*clean.width)),min(clean.height,int((y+h)*clean.height)))
            if box[2]<=box[0] or box[3]<=box[1]: raise HTTPException(422,"Vùng che quá nhỏ.")
            region=clean.crop(box);region=region.resize((3,3)).resize(region.size).filter(ImageFilter.GaussianBlur(16));clean.paste(region,box)
        # New URL prevents a previously cached image from surviving redaction.
        filename=f"{'avatar-' if 'avatar-' in path.name else ''}{image.user_id}-{secrets.token_hex(16)}.jpg"
        clean.save(upload_dir/filename,'JPEG',quality=88)
        new_url='/uploads/'+filename
        db.add(ImageReview(image_url=new_url,user_id=image.user_id,status='pending',scan=json.dumps({"state":"manual_redaction","warnings":[data.reason]}),created_at=time.time()))
        for c in db.scalars(select(Case).where(Case.image_url==image.image_url)):
            c.image_url=new_url;c.moderation_status='pending'
        owner=db.get(User,image.user_id)
        if owner.avatar_url==image.image_url: owner.avatar_url=None
        image.status='removed';audit(db,user,'redact',image.image_url,data.reason);db.commit()
        return {"image_url":new_url,"status":"pending"}

    class Suspension(BaseModel):
        suspended: bool = Field(strict=True)
        reason: str = Field(min_length=5,max_length=1000)

    @router.post('/api/moderation/users/{user_id}/suspension')
    def suspend(user_id:int,data:Suspension,user=Depends(staff),db:Session=Depends(get_db)):
        target=db.get(User,user_id)
        if not target: raise HTTPException(404,"Không tìm thấy tài khoản.")
        if target.id==user.id or target.role!='user':
            raise HTTPException(403,"Không khóa tài khoản của mình hoặc tài khoản quản trị qua công cụ này.")
        if not data.suspended and user.role!='admin': raise HTTPException(403,"Chỉ quản trị viên được mở khóa.")
        target.suspended=int(data.suspended)
        db.execute(delete(Token).where(Token.user_id==user_id))
        audit(db,user,'suspend' if data.suspended else 'unsuspend',f'user:{user_id}',data.reason);db.commit()
        return {"suspended":bool(target.suspended)}
    return router
