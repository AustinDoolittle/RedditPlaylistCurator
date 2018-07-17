def print_error(msg, exception=None):
	if exception:
		formatted_string = '%s: %s'%(msg, str(exception))
	else:
		formatted_string = msg

	print '[ERROR] %s'%formatted_string

def print_warning(msg):
	print '[WARNING] %s'%msg

def print_info(msg):
	print '[INFO] %s'%msg

class TokenException(Exception):
	pass