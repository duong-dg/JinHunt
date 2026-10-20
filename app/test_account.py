"""Server-only test account management: python -m app.test_account --help."""
import argparse
from getpass import getpass
import re
from sqlalchemy import select
from .database import SessionLocal, engine
from .migrations import upgrade
from .models import User
from .main import password_hash
from .progression import progression, xp_for_level, MAX_TEST_LEVEL


def change_test_account(db, action, username, level, before_level=False, password=None):
    if not re.fullmatch(r"jhtest_[a-z0-9_]{1,23}",username):
        raise ValueError("Tên tài khoản test cần bắt đầu bằng jhtest_, chỉ dùng chữ thường, số và dấu gạch dưới (tối đa 30 ký tự).")
    target=xp_for_level(level)
    if before_level:
        if level==1:
            raise ValueError("Không có mốc trước cấp 1.")
        target-=1
    person=db.scalar(select(User).where(User.username==username))
    if action=="create":
        if person:
            raise ValueError("Tên đã tồn tại; không ghi đè tài khoản hoặc mật khẩu. Dùng lệnh set-level cho tài khoản test đã tạo.")
        if not password or not 8<=len(password)<=128:
            raise ValueError("Mật khẩu phải từ 8 đến 128 ký tự.")
        person=User(username=username,password_hash=password_hash(password),display_name="[TEST] "+username,is_test=1,total_xp=target)
        db.add(person)
    elif action=="set-level":
        if not person or not person.is_test:
            raise ValueError("Chỉ đổi XP của tài khoản test được tạo bằng công cụ này.")
        person.total_xp=target
    else:
        raise ValueError("Lệnh không hợp lệ.")
    db.commit()
    db.refresh(person)
    return {"username":person.username,"xp":person.total_xp,**progression(person.total_xp)}


def main():
    parser=argparse.ArgumentParser(description="Tạo tài khoản test hoặc gán cấp, chỉ chạy trên server.")
    parser.add_argument("action",choices=("create","set-level"))
    parser.add_argument("--username",required=True)
    parser.add_argument("--level",required=True,type=int,choices=range(1,MAX_TEST_LEVEL+1),metavar=f"1..{MAX_TEST_LEVEL}")
    parser.add_argument("--before-level",action="store_true",help="Đặt XP ngay trước mốc lên cấp để thử thông báo.")
    args=parser.parse_args()
    try:
        password=None
        if args.action=="create":
            password=getpass("Mật khẩu tài khoản test: ")
            if password!=getpass("Nhập lại mật khẩu: "):
                raise ValueError("Hai mật khẩu không khớp.")
        upgrade(engine)
        with SessionLocal() as db:
            result=change_test_account(db,args.action,args.username,args.level,args.before_level,password)
        print(f"Đã cập nhật {result['username']}: {result['xp']} XP, Level {result['level']}, hạng {result['rank_name']}.")
        if args.action=="create":
            print("Đăng nhập trên web bằng tài khoản vừa tạo. Đọc và xác nhận điều khoản/ngày sinh trong app trước khi tham gia. Công cụ không tự ghi nhận đồng ý hoặc xác minh email.")
        print("Tài khoản test không xuất hiện trong bảng xếp hạng. Tải lại trang nếu đang đăng nhập.")
    except (ValueError,EOFError) as error:
        parser.exit(1,f"{error}\n")


if __name__=="__main__":
    main()
