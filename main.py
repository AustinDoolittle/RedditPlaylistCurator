import sys
import os
import argparse
import re
import spotipy
import spotipy.util as sp_util
import praw
from datetime import datetime
import dateutil.parser
import pytz
import json

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
		print_error('API authorization environment variables have not been setup correctly', e)
		return 1

	# either load or create, based on config file's existence
	if os.path.isfile(args.config_file):
		try:
			curator = PlaylistCurator.load(args.config_file, **api_auth)
		except IOError as e:
			print_error('There was an error while loading config file %s'%args.config_file, e)
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
		print_error('There was an error while saving the updated curator configuration to %s'%args.config_file, e)
		return 1

	return 0

def list_handler(args):
	# load our auth information	
	try:
		api_auth = load_api_auth_info()
	except KeyError as e:
		print_error('API authorization environment variables have not been setup correctly', e)
		return 1

	try:
		curator = PlaylistCurator.load(args.config_file, **api_auth)
	except IOError as e:
		print_error('There was an error while loading config file %s'%args.config_file, e)
		return 1

	# TODO pull information from spotify and reddit for all of the listed subreddits
	print(str(curator))

	return 0

def update_handler(args):
	# load our auth information	
	try:
		api_auth = load_api_auth_info()
	except KeyError as e:
		print_error('API authorization environment variables have not been setup correctly', e)
		return 1

	# load our config file
	try:
		curator = PlaylistCurator.load(args.config_file, **api_auth)
	except IOError as e:
		print_error('There was an error while loading config file %s'%args.config_file, e)
		return 1

	curator.update(args.playlist_id, top_n=args.top_n, subreddits=args.subreddits, expire_days=args.expire_days)

	# save the changes we just made
	try:
		curator.save(args.config_file)
	except IOError as e:
		print_error('There was an error while saving the updated curator configuration to %s'%args.config_file, e)
		return 1

	return 0

def curate_handler(args):
	# load our auth information	
	try:
		api_auth = load_api_auth_info()
	except KeyError as e:
		print_error('API authorization environment variables have not been setup correctly', e)
		return 1

	# load our config file
	try:
		curator = PlaylistCurator.load(args.config_file, **api_auth)
	except IOError as e:
		print_error('There was an error while loading config file %s'%args.config_file, e)
		return 1

	# create our spotify object
	curator.curate()

	return 0

def sanitize_song_name(post_title):
	return re.sub(r'(\[.*\]|\(\w+\d+\w+\)+|-)', '', post_title)

def is_song_link(post_link):
	return 'youtube' in post_link or 'youtu.be' in post_link or \
			'spotify' in post_link or 'bandcamp' in post_link

def parse_spotify_datetime(datetime_str):
	return dateutil.parser.parse(datetime_str)

def initialize_reddit_api(reddit_client_id, reddit_client_secret, reddit_user_agent):
	reddit = praw.Reddit(client_id=reddit_client_id,
		client_secret=reddit_client_secret,
		user_agent=reddit_user_agent)
	return reddit

def initialize_spotify_api(spotify_client_id, spotify_client_secret, spotify_username):
	# this scope allows us to create and modify public playlists
	scope='playlist-modify-public'
	token = sp_util.prompt_for_user_token(spotify_username, 
		scope,
		client_id=spotify_client_id,
		client_secret=spotify_client_secret,
		redirect_uri='https://www.google.com')

	# check that we were successful
	if not token:
		raise TokenException('There was an error retrieving the spotify token')

	spotify = spotipy.Spotify(auth=token)
	return spotify

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

class PlaylistCurator(object):
	def __init__(self, reddit_client_id, reddit_client_secret, reddit_user_agent,
				spotify_client_id, spotify_client_secret, spotify_username):
		self.reddit = initialize_reddit_api(reddit_client_id, reddit_client_secret, reddit_user_agent)
		self.spotify = initialize_spotify_api(spotify_client_id, spotify_client_secret, spotify_username)
		self.spotify_username = spotify_username
		self._config_dict = {}

	@staticmethod
	def load(config_file, *args, **kwargs):
		with open(config_file, 'r') as fp:
			config_dict = json.load(fp)
		retval = PlaylistCurator(*args, **kwargs)
		retval._config_dict = config_dict
		return retval

	def save(self, out_file):
		with open(out_file, 'w') as fp:
			json.dump(self._config_dict, fp, indent=4, sort_keys=True)

	def __str__(self):
		ret_str = ''
		for playlist_id, playlist_settings in self._config_dict.items():
			ret_str += 'Playlist ID: %s\n'%playlist_id
			ret_str += '\tTop N: %i posts\n'%playlist_settings['top_n']
			ret_str += '\tExpire Days: %i days\n'%playlist_settings['expire_days']
			ret_str += '\tSubreddit(s): %s\n\n'%(', '.join(playlist_settings['subreddits']))
		return ret_str

	def update(self, playlist_id, top_n=None, expire_days=None, subreddits=None):
		if not self.contains_playlist(playlist_id):
			raise ValueError('This configuration does not contain playlist id %s'%playlist_id)

		update_dict = {}
		if not top_n is None:
			update_dict['top_n'] = top_n

		if not expire_days is None:
			update_dict['expire_days'] = expire_days

		if not subreddits is None:
			update_dict['subreddits'] = subreddits

		self._config_dict[playlist_id].update(update_dict)

	def add(self, playlist_id=None, playlist_name=None, top_n=25, expire_days=7, subreddits=None):
		# validate our input
		if playlist_id is None != playlist_name is None:
			raise ArgumentError('You must specify one and only one of the following arguments: "playlist_name", "playlist_id"')

		if not subreddits:
			raise ArgumentError('Missing argument "subreddits"')

		# check whether we should use a preexisting playlist or create a new one
		if playlist_id:
			# ensure that we don't already have this playlist
			if self.contains_playlist(playlist_id):
				raise ValueError('This configuration already contains a playlist with the id %s'%playlist_id)

			# TODO validate the playlist exists and we have permissions to edit it
			# if not self._valid_playlist(playlist_id):
			# 	raise ValueError('Playlist with id %s either does not exist or Spotify username %s does not have write access'%(playlist_id, self.spotify_username))
		else:
			# create the playlist
			new_playlist = self.spotify.user_playlist_create(self.spotify_username, 
				playlist_name,
				public=True)
			playlist_id = new_playlist['id']

		self._config_dict[playlist_id] = {
			'top_n': top_n,
			'expire_days': expire_days,
			'subreddits': subreddits
		}


	def _is_valid_playlist_id(self, playlist_id):
		raise NotImplemented()

	def contains_playlist(self, playlist_id):
		return playlist_id in self._config_dict

	def _trim_expired_from_playlist(self, playlist_id, expire_days):
		# get the playlist tracks
		playlist = self.spotify.user_playlist(self.spotify_username, playlist_id, fields='tracks,next')
		playlist_tracks = playlist['tracks']

		# have one unified start time for consistency
		start_time = datetime.now(pytz.utc)
		remove_tracks = []

		# iterate until pagination stops
		while True:
			# iterate over the tracks in the current response
			for track in playlist_tracks['items']:
				# figure out when it was added
				added_at = parse_spotify_datetime(track['added_at'])
				days_since_added = (start_time - added_at).days

				# if we are over expiration days, add this track to be removed
				if days_since_added > expire_days:
					remove_tracks.append(track['id'])

			# check for termination condition
			if playlist_tracks['next'] is None:
				break

			# retrieve the next page
			playlist_tracks = self.spotify.next(playlist_tracks['next'])
		
		# if we have tracks to remove, do it
		if remove_tracks:
			self.spotify.user_playlist_remoe_all_occurrences_of_tracks(self.spotify_username, playlist_id, remove_tracks)

	def _add_top_posts(self, subreddits, playlist_id, top_n):
		# add top posts from today
		songs_to_add = []
		for subreddit in subreddits:
			for post in self.reddit.subreddit(subreddit).top('day', limit=None):
				if not is_song_link(post.url):
					# this isn't a youtube link, it's fair to assume this isn't a song
					continue

				# sanitize our title and search spotify for a match
				sanitized_title = sanitize_song_name(post.title)
				search_result = self.spotify.search(q=sanitized_title, type='track')

				# check the case that no valid items were returnd
				if len(search_result['tracks']['items']) == 0:
					continue

				# get the first result and add it to our playlist
				songs_to_add.append(search_result['tracks']['items'][0]['id'])
				if len(songs_to_add) == top_n:
					break

			if songs_to_add:
				self.spotify.user_playlist_add_tracks(self.spotify_username, playlist_id, songs_to_add)


	def curate(self):
		#clear out songs that are currently in the playlist that have been there longer than *expire_days*
		for playlist_id, config_dict in self._config_dict.items():
			if config_dict['expire_days'] >= 0:
				self._trim_expired_from_playlist(playlist_id, config_dict['expire_days'])

			# add new songs
			self._add_top_posts(config_dict['subreddits'], playlist_id, config_dict['top_n'])




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