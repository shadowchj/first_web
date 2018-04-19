# -*- coding:utf-8 -*-
from webstructure import get
import asyncio
from Models import User

@get('/')
async def index(request):
	users = await User.findAll()
	return {
		'__template__':'test.html',
		'users':users	
	}


