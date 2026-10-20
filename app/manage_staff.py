"""Run on the server; role assignment is never available to public registration."""
import argparse
import time
from datetime import date
from sqlalchemy import select, delete
from .database import engine, SessionLocal
from .migrations import upgrade
from .models import User, Token, ModerationAudit

def main():
    parser=argparse.ArgumentParser(description="Assign an existing adult account a staff role")
    parser.add_argument('username')
    parser.add_argument('role',choices=['user','moderator','admin'])
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
        db.add(ModerationAudit(actor_id=user.id,action='set_role_cli',target=f'user:{user.id}',reason=f'Trusted server CLI assigned {args.role}',created_at=time.time()))
        db.execute(delete(Token).where(Token.user_id==user.id));db.commit()
        print(f'{user.username}: {args.role}. Sign in again.')

if __name__=='__main__': main()
