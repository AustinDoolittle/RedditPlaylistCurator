import sys
import json
import os
import argparse
import praw
import spotipy
import spotipy.util as sp_util

import util
from curate import PlaylistCurator

REDDIT_USER_AGENT='reddit_playlist_curator v1.0.0'

def load_config(config_file):
	with open(config_file, 'r') as fp:
		return json.load(fp)

def save_config(config_dict, config_file):
	with open(config_file, 'w') as fp:
		json.dump(config_dict, fp)

def initialize_reddit_api():
	reddit_client_id = os.environ['REDDIT_CLIENT_ID']
	reddit_client_secret = os.environ['REDDIT_CLIENT_SECRET']
	reddit = praw.Reddit(client_id=reddit_client_id,
		client_secret=reddit_client_secret,
		user_agent=REDDIT_USER_AGENT)
	return reddit

def initialize_spotify_api():
	spotify_username = os.environ['SPOTIFY_USERNAME']
	spotify_client_id = os.environ['SPOTIFY_CLIENT_ID']
	spotify_client_secret = os.environ['SPOTIFY_CLIENT_SECRET']

	# this scope allows us to create and modify public playlists
	scope='playlist-modify-public'
	token = sp_util.prompt_for_user_token(spotify_username, 
		scope,
		client_id=spotify_client_id,
		client_secret=spotify_client_secret,
		redirect_uri='https://www.google.com')

	# check that we were successful
	if not token:
		raise util.TokenException('There was an error retrieving the spotify token')

	spotify = spotipy.Spotify(auth=token)
	return spotify, spotify_username

def add_handler(args):
	raise NotImplemented

def list_handler(args):
	try:
		config_dict = load_config(args.config_file)
	except IOError as e:
		util.print_error('There was an error while loading config file %s'%args.config_file, e)
		return 1

	# TODO pull information from spotify and reddit for all of the listed subreddits
	for playlist_id, playlist_settings in config_dict.items():
		print 'Playlist ID: %s'%playlist_id
		print '\tTop N: %i posts'%playlist_settings['top_n']
		print '\tExpire Days: %i days'%playlist_settings['expire_days']
		print '\tSubreddit(s): %s'%(', '.join(playlist_settings['subreddits']))
		print

	return 0

def update_handler(args):
	# load our config file
	try:
		config = load_config(args.config_file)
	except Exception as ex:
		util.print_error('There was an error while reading the config file', ex)
		return 1

	# pop our dictionary
	c = config.pop(args.playlist_id, None)

	# check that we actually are using this playlist id
	if c is None:
		util.print_error('Config file %s does not contain configuration details for playlist id %s'%(args.config_file, args.playlist_id))
		return 1

	# create our update dictionary based on what parameters were provided
	if not args.top_n is None:
		c['top_n'] = args.top_n

	if args.subreddits:
		c['subreddits'] = args.subreddits

	if args.expire_days:
		c['expire_days'] = args.expire_days


	playlist_id = args.new_playlist_id or args.playlist_id

	config[playlist_id] = c

	try:
		save_config(config, args.config_file)
	except IOError as e:
		util.print_error('There was an error while saving the updated config file to %s'%args.config_file, e)
		return 1

	return 0


def curate_handler(args):
	# load our config file
	try:
		config = load_config(args.config_file)
	except Exception as ex:
		util.print_error('There was an error while reading the config file', ex)
		return 1

	# create our reddit object
	try:
		reddit = initialize_reddit_api()
	except Exception as e:
		# TODO more specific exception handling
		util.print_error('There was an error initializing the reddit api wrapper', e)
		return 1

	# create our spotify object
	try:
		spotify, spotify_username = initialize_spotify_api()
	except util.TokenException as ex:
		util.print_error('Spotify token retrieval failed', ex)
		return 1
	except Exception as ex:
		util.print_error('There was an error initializing the spotify api wrapper', ex)
		return 1

	# curate!
	playlist_curator = PlaylistCurator(reddit, spotify, spotify_username)
	for playlist_id, kwargs in config.items():
		playlist_curator.curate_playlist(playlist_id=playlist_id, **kwargs)

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
	update_subparser.add_argument('--new-playlist-id', type=str,
		help='The playlist id is overwritten to this value. If this playlist id already exists \
		in this configuration, an exception is raised.')
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