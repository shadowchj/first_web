# -*- coding:utf-8 -*-

import logging, logging.basicConfig(level=logging.INFO)
import asyncio, os, json, time
from datetime import datetime
from aiohttp import web

#index界面，类型为html
def index(request):
	return web.Response(body=b'<h1>Awesome</h1>', content_type='text/html')

async def init(loop):
	app = web.Application(loop=loop)
	app.router.add_route('GET', '/', index)
	srv = await loop.create_sever(app.make_handler(), '127.0.0.1', 8888)
	logging.info('sever started at http://127.0.0.1:8888....')
	return srv

loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()