import sys
import json
import os
import argparse
import praw
import spotipy
import spotipy.util as sp_util

import util
from curate import PlaylistCurator

def load_api_auth_info():
	return {
		'reddit_client_id': os.environ['REDDIT_CLIENT_ID'],
		'reddit_client_secret': os.environ['REDDIT_CLIENT_SECRET'],
		'reddit_user_agent': os.environ['REDDIT_USER_AGENT'],
		'spotify_username': os.environ['SPOTIFY_USERNAME'],
		'spotify_client_id': os.environ['SPOTIFY_CLIENT_ID'],
		'spotify_client_secret': os.environ['SPOTIFY_CLIENT_SECRET']
	}

def add_handler(args):
	# load our auth information	
	try:
		api_auth = load_api_auth_info()
	except KeyError as e:
		util.print_error('API authorization environment variables have not been setup correctly', e)
		return 1

	# either load or create, based on config file's existence
	if os.path.isfile(args.config_file):
		try:
			curator = PlaylistCurator.load(args.config_file, **api_auth)
		except IOError as e:
			util.print_error('There was an error while loading config file %s'%args.config_file, e)
			return 1
	else:
		curator = PlaylistCurator(**api_auth)

	# add the new configuration
	curator.add(playlist_id=args.playlist_id, playlist_name=args.playlist_name, top_n = args.top_n,
		expire_days=args.expire_days, subreddits=args.subreddits)


	# save the changes we just made
	try:
		curator.save(args.config_file)
	except IOError as e:
		util.print_error('There was an error while saving the updated curator configuration to %s'%args.config_file, e)
		return 1

	return 0

def list_handler(args):
	# load our auth information	
	try:
		api_auth = load_api_auth_info()
	except KeyError as e:
		util.print_error('API authorization environment variables have not been setup correctly', e)
		return 1

	try:
		curator = PlaylistCurator.load(args.config_file, **api_auth)
	except IOError as e:
		util.print_error('There was an error while loading config file %s'%args.config_file, e)
		return 1

	# TODO pull information from spotify and reddit for all of the listed subreddits
	print(str(curator))

	return 0

def update_handler(args):
	# load our auth information	
	try:
		api_auth = load_api_auth_info()
	except KeyError as e:
		util.print_error('API authorization environment variables have not been setup correctly', e)
		return 1

	# load our config file
	try:
		curator = PlaylistCurator.load(args.config_file, **api_auth)
	except IOError as e:
		util.print_error('There was an error while loading config file %s'%args.config_file, e)
		return 1

	curator.update(args.playlist_id, top_n=args.top_n, subreddits=args.subreddits, expire_days=args.expire_days)

	# save the changes we just made
	try:
		curator.save(args.config_file)
	except IOError as e:
		util.print_error('There was an error while saving the updated curator configuration to %s'%args.config_file, e)
		return 1

	return 0


def curate_handler(args):
	# load our auth information	
	try:
		api_auth = load_api_auth_info()
	except KeyError as e:
		util.print_error('API authorization environment variables have not been setup correctly', e)
		return 1

	# load our config file
	try:
		curator = PlaylistCurator.load(args.config_file, **api_auth)
	except IOError as e:
		util.print_error('There was an error while loading config file %s'%args.config_file, e)
		return 1

	# create our spotify object
	curator.curate()

	return 0

def parse_args(argv):
	parser = argparse.ArgumentParser()
	subparsers = parser.add_subparsers()

	# subparser that facilitates adding new configurations
	add_subparser = subparsers.add_parser('add', help='Adds a new playlist')
	add_subparser.add_argument('--config-file', type=str, required=True,
		help='The config file to augment. If this file does not exist, a new config file is created at that location')
	add_subparser.add_argument('--top-n', type=int, default=25,
		help='The number of posts per query to add to the playlist.')
	add_subparser.add_argument('--expire-days', type=int, default=7,
		help='The number of days to retain added songs.')
	add_subparser.add_argument('--subreddits', type=str, required=True, nargs='+',
		help='The subreddits to pull posts from.')

	# mutex that makes creation vs retrieve preexisting easier
	playlist_mutex = add_subparser.add_mutually_exclusive_group(required=True)
	playlist_mutex.add_argument('--playlist-id', type=str,
		help='The Spotify playlist id to use for this configuration. If another playlist in this configuration has \
		the same playlist id, an error will be raised. If this spotify id does not exist or the \
		authenticated user does not have access to this playlist, an exception will be raised. Note that entering \
		a preexisting playlist will cause all songs to be removed that are older than --expire-days.')
	playlist_mutex.add_argument('--playlist-name', type=str,
		help='The name of the playlist. If this is specified instead of --playlist-id, a new playlist will be created with this name.')
	add_subparser.set_defaults(func=add_handler)


	list_subparser = subparsers.add_parser('list', help='Lists the current configurations.')
	list_subparser.add_argument('--config-file', type=str, required=True,
		help='The config file to list the contents of.')
	list_subparser.set_defaults(func=list_handler)

	update_subparser = subparsers.add_parser('update', help='Facilitates updating preexisting configurations. \
		Any value provided will overwrite the current settings for this playlist_id')
	update_subparser.add_argument('--config-file', type=str, required=True,
		help='The config file to make changes to')
	update_subparser.add_argument('--playlist-id', type=str, required=True,
		help='The playlist id to change. This is used as the key to lookup the item.')
	update_subparser.add_argument('--top-n', type=int,
		help='The number of posts per query to add to the playlist. Providing this value will overwrite the current value.')
	update_subparser.add_argument('--expire-days', type=int,
		help='The number of days to retain added songs. Providing this value will overwrite the current value.')
	update_subparser.add_argument('--subreddits', type=str, nargs='+',
		help='The subreddit to pull posts from. Providing this value will overwrite the current value.')
	update_subparser.set_defaults(func=update_handler)

	curate_subparser = subparsers.add_parser('curate', help='Runs a curation cycle, removing expired tracks and adding \
		new tracks from posts.')
	curate_subparser.add_argument('--config-file', type=str, required=True,
		help='The config file to pull playlist information from.')
	curate_subparser.set_defaults(func=curate_handler)

	return parser.parse_args(argv)

def main(argv):
	args = parse_args(argv)
	return args.func(args)

if __name__ == '__main__':
	sys.exit(main(sys.argv[1:]))