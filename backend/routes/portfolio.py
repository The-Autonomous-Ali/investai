"""
Portfolio routes — track user's actual holdings.
The AI agents read this to personalize recommendations:
- Don't recommend sectors user is already overweight in
- Calculate real P&L for performance tracking
- Tax optimization based on actual holding periods
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from database.connection import get_db
from models.models import User, PortfolioItem
from utils.auth import get_current_user

router = APIRouter()


class AddHoldingRequest(BaseModel):
    symbol: str
    name: str
    instrument_type: str = "stock"  # stock, etf, mutual_fund, gold, bond
    quantity: float
    avg_buy_price: float
    buy_date: Optional[str] = None  # ISO date string
    sector: Optional[str] = None


class UpdateHoldingRequest(BaseModel):
    quantity: Optional[float] = None
    avg_buy_price: Optional[float] = None
    current_price: Optional[float] = None
    is_active: Optional[bool] = None


@router.get("/")
async def list_holdings(
    active_only: bool = True,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all portfolio holdings for the current user."""
    query = select(PortfolioItem).where(PortfolioItem.user_id == user.id)
    if active_only:
        query = query.where(PortfolioItem.is_active == True)
    query = query.order_by(PortfolioItem.created_at.desc())

    result = await db.execute(query)
    items = result.scalars().all()

    total_invested = sum((i.avg_buy_price or 0) * (i.quantity or 0) for i in items)
    total_current = sum((i.current_price or i.avg_buy_price or 0) * (i.quantity or 0) for i in items)

    return {
        "holdings": [_serialize_holding(i) for i in items],
        "summary": {
            "total_holdings": len(items),
            "total_invested": round(total_invested, 2),
            "total_current_value": round(total_current, 2),
            "total_pnl": round(total_current - total_invested, 2),
            "total_pnl_pct": round(((total_current - total_invested) / total_invested * 100), 2) if total_invested > 0 else 0,
        },
    }


@router.post("/")
async def add_holding(
    body: AddHoldingRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a new holding to the portfolio."""
    # Check subscription — free tier can track up to 5 holdings
    tier = user.subscription_tier.value if user.subscription_tier else "free"
    if tier == "free":
        count_result = await db.execute(
            select(PortfolioItem)
            .where(PortfolioItem.user_id == user.id, PortfolioItem.is_active == True)
        )
        if len(count_result.scalars().all()) >= 5:
            raise HTTPException(status_code=403, detail="Free tier limited to 5 holdings. Upgrade to add more.")

    buy_date = None
    if body.buy_date:
        buy_date = datetime.fromisoformat(body.buy_date)

    item = PortfolioItem(
        user_id=user.id,
        symbol=body.symbol.upper(),
        name=body.name,
        instrument_type=body.instrument_type,
        quantity=body.quantity,
        avg_buy_price=body.avg_buy_price,
        buy_date=buy_date,
        current_price=body.avg_buy_price,  # initial current = buy price
        sector=body.sector,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    return {"status": "added", "holding": _serialize_holding(item)}


@router.patch("/{holding_id}")
async def update_holding(
    holding_id: str,
    body: UpdateHoldingRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a holding (e.g., new quantity after averaging, current price update)."""
    result = await db.execute(
        select(PortfolioItem).where(
            PortfolioItem.id == holding_id,
            PortfolioItem.user_id == user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Holding not found")

    updates = body.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(item, field, value)

    await db.commit()
    await db.refresh(item)
    return {"status": "updated", "holding": _serialize_holding(item)}


@router.delete("/{holding_id}")
async def remove_holding(
    holding_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a holding (marks as inactive, doesn't delete — keeps history)."""
    result = await db.execute(
        select(PortfolioItem).where(
            PortfolioItem.id == holding_id,
            PortfolioItem.user_id == user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Holding not found")

    item.is_active = False
    await db.commit()
    return {"status": "removed", "symbol": item.symbol}


def _serialize_holding(item: PortfolioItem) -> dict:
    invested = (item.avg_buy_price or 0) * (item.quantity or 0)
    current = (item.current_price or item.avg_buy_price or 0) * (item.quantity or 0)
    pnl = current - invested

    return {
        "id": item.id,
        "symbol": item.symbol,
        "name": item.name,
        "instrument_type": item.instrument_type,
        "quantity": item.quantity,
        "avg_buy_price": item.avg_buy_price,
        "current_price": item.current_price,
        "buy_date": item.buy_date.isoformat() if item.buy_date else None,
        "sector": item.sector,
        "is_active": item.is_active,
        "invested_value": round(invested, 2),
        "current_value": round(current, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round((pnl / invested * 100), 2) if invested > 0 else 0,
    }
