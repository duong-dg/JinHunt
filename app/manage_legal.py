"""Operator-only CLI: requires direct access to the configured database."""
import argparse
import json
import sys
from sqlalchemy import select
from .database import SessionLocal
from .models import LegalRequest, User, GuardianInvite
from .legal import start_guardian

def main():
    if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr,"reconfigure"): sys.stderr.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description="Xử lý yêu cầu pháp lý (chỉ chạy trên máy chủ được phân quyền).")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("list")
    show=sub.add_parser("show");show.add_argument("reference")
    close=sub.add_parser("close");close.add_argument("reference");close.add_argument("--processed",action="store_true",required=True,help="Chỉ dùng sau khi đã thực sự xử lý và phản hồi yêu cầu.")
    resend=sub.add_parser("resend-guardian");resend.add_argument("username")
    args=parser.parse_args()
    with SessionLocal() as db:
        if args.command=="list":
            for row in db.scalars(select(LegalRequest).where(LegalRequest.status=="received").order_by(LegalRequest.created_at).limit(100)):
                print(json.dumps({"reference":row.reference,"kind":row.kind,"created_at":row.created_at,"status":row.status},ensure_ascii=False))
        elif args.command=="resend-guardian":
            user=db.scalar(select(User).where(User.username==args.username.lower(),User.account_status=="pending_guardian"))
            if not user: parser.error("Không tìm thấy tài khoản đang chờ người đại diện.")
            invite=db.scalar(select(GuardianInvite).where(GuardianInvite.user_id==user.id).order_by(GuardianInvite.created_at.desc()))
            if not invite: parser.error("Không có email người đại diện đã đăng ký.")
            start_guardian(db,user,invite.guardian_email);db.commit();print("Đã gửi lại email; không in token/liên kết ra log.")
        else:
            row=db.get(LegalRequest,args.reference)
            if not row: parser.error("Không tìm thấy yêu cầu.")
            if args.command=="show":
                print(json.dumps({key:getattr(row,key) for key in ["reference","kind","name","email","content_url","details","created_at","status"]},ensure_ascii=False,indent=2))
            else:
                row.status="processed";db.commit();print("Đã đánh dấu. Lệnh này không tự xóa tài khoản, dữ liệu hoặc gỡ nội dung.")

if __name__=="__main__":main()
