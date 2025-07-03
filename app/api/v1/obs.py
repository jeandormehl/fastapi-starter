"""
Demo endpoints showcasing traces, metrics and log correlation.
"""

import asyncio
import random
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix='/demo', tags=['Observability Demo'])


@router.get('/simple')
async def simple() -> dict[str, str]:
    return {'message': 'simple trace demo'}


@router.get('/slow')
async def slow() -> dict[str, float]:
    delay = random.uniform(0.5, 2.0)
    await asyncio.sleep(delay)
    return {'slept_seconds': delay}


@router.get('/error')
async def error() -> Any:
    raise HTTPException(status_code=418, detail='I am a teapot')


@router.get('/chain')
async def chain() -> dict[str, str]:
    """
    Issues two downstream HTTPX requests to demonstrate distributed traces.
    """
    async with httpx.AsyncClient() as client:
        await client.get('https://httpbin.org/get')
        await client.get('https://httpbin.org/uuid')
    return {'message': 'chained external calls'}
