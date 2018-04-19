# -*- coding:utf-8 -*-
import ormstructure
import asyncio
from Models import User


async def test(loop):
	await ormstructure.create_pool(loop,user='xxxx',password='xxxxxxx',db='awsome')
	for name in ['jack','bill','jenny','french']:
		u = User(name=name, email=name+'@example.com', passwd=name+'123456', image='about:'+name)
		await u.save()
	
if __name__ == '__main__':
	loop = asyncio.get_event_loop()
	loop.run_until_complete(test(loop))
	loop.close()

	
