from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import Up, Video
from app.services.bilibili_service import fetch_up_info

router = APIRouter()


@router.post("/add/{uid}")
async def add_up(uid: str, db: AsyncSession = Depends(get_db)):
    try:
        int(uid)
    except ValueError:
        raise HTTPException(status_code=400, detail="UID必须是数字")

    result = await db.execute(select(Up).where(Up.uid == uid))
    if result.scalar_one_or_none():
        return {"success": False, "msg": "UP主已存在"}

    info = await fetch_up_info(uid)
    if not info.get("name"):
        raise HTTPException(status_code=404, detail="无法获取该UP主信息，请检查UID是否正确")

    up = Up(**info)
    db.add(up)
    await db.commit()
    await db.refresh(up)
    return {"success": True, "msg": "添加成功", "data": info}


@router.get("/list")
async def list_ups(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Up).order_by(Up.created_at.desc()))
    ups = result.scalars().all()
    return {"success": True, "data": [
        {
            "id": u.id,
            "uid": u.uid,
            "name": u.name,
            "face": u.face,
            "description": u.description,
            "created_at": u.created_at.isoformat() if u.created_at else None
        }
        for u in ups
    ]}


@router.delete("/{up_id}")
async def delete_up(up_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Up).where(Up.id == up_id))
    up = result.scalar_one_or_none()
    if not up:
        raise HTTPException(status_code=404, detail="UP主不存在")

    await db.delete(up)
    await db.commit()
    return {"success": True, "msg": "删除成功"}
