# -*- coding:utf-8 -*-

import time, uuid

from ormstructure import Model, StringField, BooleanField, FloatField, TextField

def next_id():
	return '%015d%s000' % (int(time.time() * 1000), uuid.uuid4().hex)

class User(Model):
	__table__ = 'users'

	id = StringField(primary_key=True, default=next_id, c_type='varchar(50)')
	email = StringField(c_type='varchar(50)')
	passwd = StringField(c_type='varchar(50)')
	name = StringField(c_type='varchar(50)')
	admin = BooleanField()
	image = StringField(c_type='varchar(500)')
	created_at = FloatField(default=time.time)


class Blog(Model):
	__table__ = 'blogs'

	id = StringField(primary_key=True, default=next_id, c_type='varchar(50)')
	user_id = StringField(c_type='varchar(50)')
	user_name = StringField(c_type='varchar(50)')
	user_image = StringField(c_type='varchar(500)')
	name = StringField(c_type='varchar(50)')
	summary = StringField(c_type='varchar(200)')
	content = TextField()
	created_at = FloatField(default=time.time)

class Comment(Model):
	__table__ = 'comments'

	id = StringField(primary_key=True, default=next_id, c_type='varchar(50)')
	blog_id = StringField(c_type='varchar(50)')
	user_id = StringField(c_type='varchar(50)')
	user_name = StringField(c_type='varchar(50)')
	user_image = StringField(c_type='varchar(500)')
	content = TextField()
	created_at = FloatField(default=time.time)

