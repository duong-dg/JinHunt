"""Run on the server; role assignment is never available to public registration."""
import argparse
import getpass
import time
import pyotp
from datetime import date
from sqlalchemy import select, delete
from .database import engine, SessionLocal
from .migrations import upgrade
from .models import User, Token, ModerationAudit
from .auth_security import secret_cipher

def main():
    parser=argparse.ArgumentParser(description="Assign an existing adult account a staff role")
    parser.add_argument('username')
    parser.add_argument('role',choices=['user','moderator','admin'])
    parser.add_argument('--setup-2fa',action='store_true',help='Enroll an authenticator from this trusted terminal')
    parser.add_argument('--reset-2fa',action='store_true',help='Replace a lost authenticator; revoke all sessions')
    args=parser.parse_args()
    upgrade(engine)
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.username==args.username.lower()))
        if not user: parser.error('Account not found')
        born=user.player_birth_date
        adult=born and (date.today().year-born.year-((date.today().month,date.today().day)<(born.month,born.day)))>=18
        if args.role!='user' and (not adult or user.guardian_managed or user.suspended or user.account_status!='active'):
            parser.error('Staff must be an active adult account without guardian management')
        user.role=args.role
        if args.setup_2fa or args.reset_2fa:
            if args.role=='user': parser.error('Only staff accounts can enroll staff 2FA')
            if user.staff_totp_secret and not args.reset_2fa: parser.error('2FA exists; use --reset-2fa only to replace it')
            cipher=secret_cipher()
            secret=pyotp.random_base32()
            totp=pyotp.TOTP(secret)
            print('PRIVATE: enter this setup key in your authenticator. Do not share it or use a public QR website.')
            print('Account: JinHunt Staff / '+user.username)
            print('Setup key: '+secret)
            code=getpass.getpass('Enter the 6-digit code from your authenticator: ').strip()
            now=int(time.time()//30)
            matched=next((step for step in (now-1,now,now+1) if totp.generate_otp(step)==code),None)
            if matched is None: parser.error('Invalid code; no changes saved')
            user.staff_totp_secret=cipher.encrypt(secret.encode()).decode()
            user.staff_totp_counter=matched
            db.add(ModerationAudit(actor_id=user.id,action='reset_2fa_cli' if args.reset_2fa else 'setup_2fa_cli',target=f'user:{user.id}',reason='Authenticator verified in trusted server terminal',created_at=time.time()))
        db.add(ModerationAudit(actor_id=user.id,action='set_role_cli',target=f'user:{user.id}',reason=f'Trusted server CLI assigned {args.role}',created_at=time.time()))
        db.execute(delete(Token).where(Token.user_id==user.id));db.commit()
        print(f'{user.username}: {args.role}. Sign in at /staff/login; wait for the next OTP if just enrolled.')
        if args.role!='user' and not user.staff_totp_secret:
            print('Staff login stays blocked until you run this command with --setup-2fa.')

if __name__=='__main__': main()
