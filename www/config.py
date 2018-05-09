# -*- coding:utf-8 -*-
import config_default

#配置数据库信息configs
def merge(defaults, override):
	r = {}
	for k,v in defaults.items():
		if k in override:
			if isinstance(v,dict):
				r[k] = merge(v, override[k])
			else:
				r[k] = override[k]
		else:
			r[k] = v
	return r

configs = config_default.configs

try:
	import config_override
	configs = merge(configs,config_override.configs)
except ImportError:
	pass
