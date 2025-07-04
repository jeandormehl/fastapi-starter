"""
Demo endpoints showcasing traces, metrics and log correlation.
"""

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from app.core.logging import get_logger

router = APIRouter(prefix='/demo', tags=['Observability Demo'])


_logger = get_logger(__name__)


@router.get('/simple')
async def simple() -> dict[str, str]:
    _logger.info(__name__)
    return {'message': 'simple trace demo'}


@router.get('/slow')
async def slow() -> dict[str, float]:
    _logger.info(__name__)
    # delay = random.uniform(0.5, 2.0)
    await asyncio.sleep(20)
    return {'slept_seconds': 20}


@router.get('/error')
async def error() -> Any:
    _logger.info(__name__)
    raise HTTPException(status_code=418, detail='I am a teapot')


@router.get('/chain')
async def chain() -> dict[str, str]:
    """
    Issues two downstream HTTPX requests to demonstrate distributed traces.
    """
    async with httpx.AsyncClient() as client:
        await client.get('https://httpbin.org/get')
        await client.get('https://httpbin.org/uuid')
        _logger.info(__name__)
    return {'message': 'chained external calls'}
