# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/7 05:55
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
import asyncio

from dify import DifyWorkflowClient
import httpx
from httpx_sse import connect_sse


async def main():
    client = DifyWorkflowClient()
    with httpx.Client() as client:
        with connect_sse(client, "GET", "http://localhost:8000/sse") as event_source:
            for sse in event_source.iter_sse():
                print(sse.event, sse.data, sse.id, sse.retry)


if __name__ == '__main__':
    asyncio.run(main())
