import sys
import argparse
import json
import os
import argparse
import praw
import spotipy
import spotipy.util as sp_util
from pprint import pprint

import util
from curate import PlaylistCurator

REDDIT_USER_AGENT='reddit_playlist_curator v1.0.0'

def load_config(config_file):
	with open(config_file, 'r') as fp:
		return json.load(fp)

def parse_args(argv):
	parser = argparse.ArgumentParser()
	parser.add_argument('--config-file', type=str, required=True,
		help='The config file that declares the different subreddits to pull music information from and their corresponding spotify playlist')
	parser.add_argument('--force', action='store_true',
		help='This flag instructs the application to create a spotify playlist if one does not already exist for this subreddit')

	return parser.parse_args(argv)

def main(args):
	# load all of our environment variables
	try:
		reddit_client_id = os.environ['REDDIT_CLIENT_ID']
		reddit_client_secret = os.environ['REDDIT_CLIENT_SECRET']
		spotify_username = os.environ['SPOTIFY_USERNAME']
		spotify_client_id = os.environ['SPOTIFY_CLIENT_ID']
		spotify_client_secret = os.environ['SPOTIFY_CLIENT_SECRET']
	except KeyError as ex:
		util.print_error('Reddit authentication environment variables have not been setup.', ex)
		sys.exit(1)

	# load our config file
	try:
		config = load_config(args.config_file)
	except Exception as ex:
		util.print_error('There was an error while reading the config file', ex)
		sys.exit(1)

	# create our reddit object
	try:
		reddit_client_id = os.environ['REDDIT_CLIENT_ID']
		reddit_client_secret = os.environ['REDDIT_CLIENT_SECRET']
		reddit = praw.Reddit(client_id=reddit_client_id,
			client_secret=reddit_client_secret,
			user_agent=REDDIT_USER_AGENT)
	except Exception as e:
		# TODO more specific exception handling
		util.print_error('There was an error initializing the reddit api wrapper', e)
		sys.exit(1)

	# initialize our reddit object
	try:
		# this scope allows us to create and modify public playlists
		scope='playlist-modify-public'
		token = sp_util.prompt_for_user_token(spotify_username, 
			scope,
			client_id=spotify_client_id,
			client_secret=spotify_client_secret,
			redirect_uri='https://www.google.com')

		if not token:
			raise util.TokenException('There was an error retrieving the spotify token')

		spotify = spotipy.Spotify(auth=token)
	except util.TokenException as ex:
		util.print_error('Spotify token retrieval failed', ex)
		sys.exit(1)
	except Exception as ex:
		util.print_error('There was an error initializing the spotify api wrapper', ex)
		sys.exit(1)

	# wrap it in a list because I'm lazy
	if not isinstance(config, list):
		config = [config]

	# curate!
	playlist_curator = PlaylistCurator(reddit, spotify, spotify_username)
	for c in config:
		playlist_curator.curate_playlist(**c)



if __name__ == '__main__':
	args = parse_args(sys.argv[1:])
	main(args)