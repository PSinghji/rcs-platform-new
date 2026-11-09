from fastapi import HTTPException, Header
from jose import jwt, JWTError
from app.config import settings
from app.database import users_col

def get_current_user(authorization: str = Header(...)):
    try:
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        user = users_col.find_one({"_id": payload["uid"]})
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Token error")

