
from .common import ChatDownloader

from ..utils import microseconds_to_timestamp

from ..errors import *  # only import used TODO

from urllib import parse

import json
import time
import re

from ..utils import (
    try_get,
    time_to_seconds,
    seconds_to_time,
    int_or_none,
    get_colours,
    try_get_first_key,
    remove_prefixes,
    remove_suffixes,
    camel_case_split,
    debug_print,
    ensure_seconds
)


class YouTubeChatDownloader(ChatDownloader):
    def __init__(self, updated_init_params={}):
        super().__init__(updated_init_params)

    def __str__(self):
        return 'YouTube.com'

    # Regex provided by youtube-dl
    _VALID_URL = r"""(?x)^
                     (
                         (?:https?://|//)                                    # http(s):// or protocol-independent URL
                         (?:(?:(?:(?:\w+\.)?[yY][oO][uU][tT][uU][bB][eE](?:-nocookie|kids)?\.com/|
                            youtube\.googleapis\.com/)                        # the various hostnames, with wildcard subdomains
                         (?:.*?\#/)?                                          # handle anchor (#/) redirect urls
                         (?:                                                  # the various things that can precede the ID:
                             (?:(?:v|embed|e)/(?!videoseries))                # v/ or embed/ or e/
                             |(?:                                             # or the v= param in all its forms
                                 (?:(?:watch|movie)(?:_popup)?(?:\.php)?/?)?  # preceding watch(_popup|.php) or nothing (like /?v=xxxx)
                                 (?:\?|\#!?)                                  # the params delimiter ? or # or #!
                                 (?:.*?[&;])??                                # any other preceding param (like /?s=tuff&v=xxxx or ?s=tuff&amp;v=V36LpHqtcDY)
                                 v=
                             )
                         ))
                         |(?:
                            youtu\.be                                        # just youtu.be/xxxx
                         )/)
                     )?                                                       # all until now is optional -> you can pass the naked ID
                     (?P<id>[0-9A-Za-z_-]{11})                                      # here is it! the YouTube video ID
                     (?!.*?\blist=
                        (?:
                            %(playlist_id)s|                                  # combined list/video URLs are handled by the playlist IE
                            WL                                                # WL are handled by the watch later IE
                        )
                     )
                     (?(1).+)?                                                # if we found the ID, everything can follow
                     $"""

    _TESTS = [
        # OTHER:
        # Japanese characters and lots of superchats
        # https://www.youtube.com/watch?v=UlemRwXYWHg

        # strange end times:
        # https://www.youtube.com/watch?v=DzEbfQI4TPQ
        # https://www.youtube.com/watch?v=7PPnCOhkxqo

        # purchased a product linked to the YouTube channel merchandising
        # https://youtu.be/y5ih7nqEoc4


        # TESTING FOR CORRECT FUNCIONALITY
        {
            'name': 'Get chat messages from live chat replay',
            'params': {
                'url': 'https://www.youtube.com/watch?v=wXspodtIxYU',
                'start_time': 10,
                'end_time': 30,
            },

            'expected_result': {
                'message_types': ['text_message', 'placeholder_item', 'membership_item', 'ticker_sponsor_item'],
                'action_types': ['add_chat_item', 'add_live_chat_ticker_item'],
                'messages_condition': lambda messages: len(messages) > 0,
            }
        },
        {
            'name': 'Get superchat messages from live chat replay',
            'params': {
                'url': 'https://www.youtube.com/watch?v=97w16cYskVI',
                'end_time': 50,
                'message_types': ['superchat']
            },

            'expected_result': {
                'message_types': ['paid_message', 'ticker_paid_message_item', 'text_message', 'paid_sticker', 'ticker_paid_sticker_item'],
                'action_types': ['add_chat_item', 'add_live_chat_ticker_item'],
                'messages_condition': lambda messages: len(messages) > 0,
            }
        },
        {
            'name': 'Get all messages from live chat replay',
            'params': {
                'url': 'https://www.youtube.com/watch?v=97w16cYskVI',
                'end_time': 50,
                'message_types': ['all']
            },

            'expected_result': {
                'message_types': ['paid_message', 'ticker_paid_message_item', 'text_message', 'paid_sticker', 'ticker_paid_sticker_item'],
                'action_types': ['add_chat_item', 'add_live_chat_ticker_item'],
                'messages_condition': lambda messages: len(messages) > 0,
            }
        },
        {
            'name': 'Get messages from top chat replay',
            'params': {
                'url': 'https://www.youtube.com/watch?v=zVCs9Cug_qM',
                'start_time': 0,
                'end_time': 20,
                'chat_type': 'top'
            },

            'expected_result': {
                'message_types': ['text_message'],
                'action_types': ['add_chat_item'],
                'messages_condition': lambda messages: len(messages) > 0,
            }
        },
        {
            'name': 'Chat replay with donations',
            'params': {
                'url': 'https://www.youtube.com/watch?v=Ih2WTyY62J4',
                'start_time': 0,
                'end_time': 50,
            },

            'expected_result': {
                'message_types': ['viewer_engagement_message', 'membership_item', 'ticker_sponsor_item', 'text_message', 'placeholder_item', 'donation_announcement'],
                'action_types': ['add_chat_item', 'add_live_chat_ticker_item'],
                'messages_condition': lambda messages: len(messages) > 0,
            }
        },
        {
            'name': 'Get a certain number of messages from a livestream.',
            'params': {
                'url': 'https://www.youtube.com/watch?v=5qap5aO4i9A',
                'max_messages': 10
            },

            'expected_result': {
                'messages_condition': lambda messages: len(messages) == 10,
            }
        },

        # TESTING FOR ERRORS
        {
            'name': 'Video does not exist',
            'params': {
                'url': 'https://www.youtube.com/watch?v=xxxxxxxxxxx',
            },
            'expected_result': {
                'error': VideoUnavailable,
            }
        },
        {
            'name': 'Members-only content',
            'params': {
                'url': 'https://www.youtube.com/watch?v=vprErlL1w2E',
            },
            'expected_result': {
                'error': NoChatReplay,
            }
        },
        {
            'name': 'Chat is disabled for this live stream',
            'params': {
                'url': 'https://www.youtube.com/watch?v=XWq5kBlakcQ',
            },
            'expected_result': {
                'error': NoChatReplay,
            }
        },
        {
            'name': 'Live chat replay has been turned off for this video',
            'params': {
                'url': 'https://www.youtube.com/watch?v=7lGZvbasx6A',
            },
            'expected_result': {
                'error': NoChatReplay,
            }
        },
        {
            'name': 'Video is private',
            'params': {
                'url': 'https://www.youtube.com/watch?v=ijFMXqa-N0c',
            },
            'expected_result': {
                'error': VideoUnavailable,
            }
        }
    ]

    # 'messages_condition': lambda messages: messages == [],

    _YT_INITIAL_DATA_RE = r'(?:window\s*\[\s*["\']ytInitialData["\']\s*\]|ytInitialData)\s*=\s*({.+?})\s*;'

    _YT_HOME = 'https://www.youtube.com'
    # __YT_REGEX = r'(?:/|%3D|v=|vi=)([0-9A-z-_]{11})(?:[%#?&]|$)'
    _YOUTUBE_API_BASE_TEMPLATE = '{}/{}/{}?continuation={}&pbj=1&hidden=false'
    _YOUTUBE_API_PARAMETERS_TEMPLATE = '&playerOffsetMs={}'

    # CLI argument allows users to specify a list of messages groups/types they want
    _MESSAGE_GROUPS = {
        # 'group_name':[
        #     'message_types'
        # ]
        'messages': [
            'text_message'  # normal message
        ],
        'superchat': [
            # superchat messages which appear in chat
            'membership_item',
            'paid_message',
            'paid_sticker',
        ],
        'tickers': [
            # superchat messages which appear ticker (at the top)
            'ticker_paid_sticker_item',
            'ticker_paid_message_item',
            'ticker_sponsor_item',
        ],
        'banners': [
            'banner',
            'banner_header'
        ],

        'donations': [
            'donation_announcement'
        ],
        'engagement': [
            # message saying live chat replay is on
            'viewer_engagement_message',
        ],
        'purchases': [
            'purchased_product_message'  # product purchased
        ],

        'mode_changes': [
            'mode_change_message'  # e.g. slow mode enabled
        ],

        'deleted': [
            'deleted_message'  # old: 'deleted_state_message'
        ],

        'placeholder': [
            'placeholder_item'  # placeholder
        ]
    }

    @ staticmethod
    def parse_youtube_link(text):
        if(text.startswith('/redirect')):  # is a redirect link
            info = dict(parse.parse_qsl(parse.urlsplit(text).query))
            return info.get('q') or ''  # ['q'] if 'q' in info else ''
        elif(text.startswith('//')):
            return 'https:' + text
        elif(text.startswith('/')):  # is a youtube link e.g. '/watch','/results'
            return YouTubeChatDownloader.YT_HOME + text
        else:  # is a normal link
            return text

    @ staticmethod
    def parse_navigation_endpoint(navigation_endpoint, default_text=''):

        url = try_get(navigation_endpoint, lambda x: YouTubeChatDownloader.parse_youtube_link(
            x['commandMetadata']['webCommandMetadata']['url'])) or default_text

        return url

    @ staticmethod
    def parse_runs(run_info, parse_links=False):
        """ Reads and parses YouTube formatted messages (i.e. runs). """
        message_text = ''

        runs = run_info.get('runs')
        if(runs):
            for run in runs:
                if 'text' in run:
                    if parse_links and 'navigationEndpoint' in run:  # is a link and must parse

                        # if something fails, use default text
                        message_text += YouTubeChatDownloader.parse_navigation_endpoint(
                            run['navigationEndpoint'], run['text'])

                    else:  # is a normal message
                        message_text += run['text']
                elif 'emoji' in run:
                    message_text += run['emoji']['shortcuts'][0]
                else:
                    raise ValueError('Unknown run: {}'.format(run))

        return message_text

    # @staticmethod
    # def strip_live_chat_renderer(index):

    #     return index

    @ staticmethod
    def _parse_item(item, info={}):
        # info is starting point

        item_index = try_get_first_key(item)
        item_info = item.get(item_index)

        # if item_index not in YouTubeChatDownloader._KNOWN_MESSAGE_TYPES:
        #     print('Unknown message:',item_index)
        #     print(item)
        #     input()
        # TODO maybe move check for types here?
        # item indexes

        if(not item_info):
            return info  # invalid # TODO log this

        # print(item_info.keys())
        # all messages should have the following
        for key in item_info:
            ChatDownloader.remap(info, YouTubeChatDownloader._REMAPPING,
                                 YouTubeChatDownloader._REMAP_FUNCTIONS, key, item_info[key])

            # original_info = item_info[key]
            # remap = YouTubeChatDownloader._REMAPPING.get(key)
            # if(remap):
            #     index, mapping_function = remap
            #     info[index] = YouTubeChatDownloader._REMAP_FUNCTIONS[mapping_function](
            #         original_info)

        # check for colour information
        for colour_key in YouTubeChatDownloader._COLOUR_KEYS:
            if(colour_key in item_info):  # if item has colour information
                info[camel_case_split(colour_key.replace('Color', 'Colour'))] = get_colours(
                    item_info.get(colour_key)).get('hex')
        # OLD: dict of colours
        # for colour_key in YouTubeChatDownloader._COLOUR_KEYS:
        #     if(colour_key in item_info):  # if item has colour information
        #         if('colours' not in info):  # create colour dict if not set
        #             info['colours'] = {}

        #         info['colours'][camel_case_split(
        #             remove_suffixes(colour_key, 'Color'))] = get_colours(item_info.get(colour_key)).get('hex')

        item_endpoint = item_info.get('showItemEndpoint')
        if(item_endpoint):  # has additional information
            renderer = try_get(
                item_endpoint, (lambda x: x['showLiveChatItemEndpoint']['renderer']))

            if(renderer):
                info.update(YouTubeChatDownloader._parse_item(renderer))
                # return info

            # update without overwriting ? TODO decide which to use
            # update_dict_without_overwrite

        # amount is money with currency
        amount = info.get('amount')
        if amount:
            pass # TODO split amount into:
            # currency type
            # amount (float)

        time_in_seconds = info.get('time_in_seconds')
        time_text = info.get('time_text')

        if(time_in_seconds is not None):

            if(time_text is not None):
                # all information was provided
                # check if time_in_seconds is <= 0
                if(time_in_seconds <= 0):
                    info['time_in_seconds'] = time_to_seconds(time_text)
            else:
                # recreate time text from time in seconds
                info['time_text'] = seconds_to_time(int(time_in_seconds))

        elif(time_text is not None):  # doesn't have time in seconds, but has time text
            info['time_in_seconds'] = time_to_seconds(time_text)
        else:
            pass
            # has no current video time information
            # (usually live video or a sub-item)

        return info

    _IMAGE_SIZE_REGEX = r'=s(\d+)'
    # TODO move regex to inline where possible?

    @ staticmethod
    def parse_badges(badge_items):
        badges = []

        for badge in badge_items:
            to_add = {}
            parsed_badge = YouTubeChatDownloader._parse_item(badge)

            title = parsed_badge.pop('tooltip', None)
            if title:
                to_add['title'] = title

            icon = parsed_badge.pop('icon', None)
            if icon:
                to_add['icon_name'] = icon.lower()

            badge_icons = parsed_badge.pop('badge_icons', None)
            if badge_icons:
                to_add['icons'] = []

                url = None
                for icon in badge_icons:
                    url = icon.get('url')
                    if url:
                        matches = re.search(
                            YouTubeChatDownloader._IMAGE_SIZE_REGEX, url)
                        if matches:
                            size = int(matches.group(1))
                            to_add['icons'].append(
                                ChatDownloader.create_image(url, size, size))
                if url:
                    to_add['icons'].append(ChatDownloader.create_image(
                        url[0:url.index('=')], id='source'))

            badges.append(to_add)

            # if 'member'
            # remove the tooltip afterwards
            # print(badges)
        return badges

    @ staticmethod
    def parse_thumbnails(item):

        # sometimes thumbnails come as a list
        if(isinstance(item, list)):
            item = item[0]  # rebase

        return item.get('thumbnails')

    @ staticmethod
    def parse_action_button(item):
        return {
            'url': try_get(item, lambda x: YouTubeChatDownloader.parse_navigation_endpoint(x['buttonRenderer']['navigationEndpoint'])) or '',
            'text': try_get(item, lambda x: x['buttonRenderer']['text']['simpleText']) or ''
        }

    _REMAP_FUNCTIONS = {
        'simple_text': lambda x: x.get('simpleText'),
        'convert_to_int': lambda x: int_or_none(x),
        'get_thumbnails': lambda x: YouTubeChatDownloader.parse_thumbnails(x),
        'parse_runs': lambda x: YouTubeChatDownloader.parse_runs(x, True),
        'parse_badges': lambda x: YouTubeChatDownloader.parse_badges(x),

        'parse_icon': lambda x: x.get('iconType'),

        'parse_action_button': lambda x: YouTubeChatDownloader.parse_action_button(x),
    }

    _REMAPPING = {
        # 'youtubeID' : ('mapped_id', 'remapping_function')
        'id': 'message_id',
        'authorExternalChannelId': 'author_id',
        'authorName': ('author_name', 'simple_text'),
        # TODO author_display_name
        'purchaseAmountText': ('amount', 'simple_text'),
        'message': ('message', 'parse_runs'),
        'timestampText': ('time_text', 'simple_text'),
        'timestampUsec': ('timestamp', 'convert_to_int'),
        'authorPhoto': ('author_images', 'get_thumbnails'),
        'tooltip': 'tooltip',

        'icon': ('icon', 'parse_icon'),
        'authorBadges': ('author_badges', 'parse_badges'),

        # stickers
        'sticker': ('sticker_images', 'get_thumbnails'),

        # ticker_paid_message_item
        'fullDurationSec': ('ticker_duration', 'convert_to_int'),
        'amount': ('amount', 'simple_text'),


        # ticker_sponsor_item
        'detailText': ('message', 'parse_runs'),

        'customThumbnail': ('badge_icons', 'get_thumbnails'),

        # membership_item
        'headerSubtext': ('message', 'parse_runs'),
        'sponsorPhoto': ('sponsor_icons', 'get_thumbnails'),

        # ticker_paid_sticker_item
        'tickerThumbnails': ('ticker_icons', 'get_thumbnails'),

        # deleted messages
        'deletedStateMessage': ('message', 'parse_runs'),
        'targetItemId': 'target_message_id',

        'externalChannelId': 'author_id',

        # action buttons
        'actionButton': ('action', 'parse_action_button'),

        # addBannerToLiveChatCommand
        'text': ('message', 'parse_runs'),
        'viewerIsCreator': 'viewer_is_creator',
        'targetId': 'target_message_id',

        # donation_announcement
        'subtext': ('sub_message', 'parse_runs'),

        # tooltip
        'detailsText': ('message', 'parse_runs'),
    }

    _COLOUR_KEYS = [
        # paid_message
        'authorNameTextColor', 'timestampColor', 'bodyBackgroundColor',
        'headerTextColor', 'headerBackgroundColor', 'bodyTextColor',

        # paid_sticker
        'backgroundColor', 'moneyChipTextColor', 'moneyChipBackgroundColor',

        # ticker_paid_message_item
        'startBackgroundColor', 'amountTextColor', 'endBackgroundColor',

        # ticker_sponsor_item
        'detailTextColor'
    ]

    _STICKER_KEYS = [
        # to actually ignore
        'stickerDisplayWidth', 'stickerDisplayHeight',  # ignore

        # parsed elsewhere
        'sticker',
    ]

    _KEYS_TO_IGNORE = [
        # to actually ignore
        'contextMenuAccessibility', 'contextMenuEndpoint', 'trackingParams', 'accessibility',

        'contextMenuButton',

        # parsed elsewhere
        'showItemEndpoint',
        'durationSec',

        # banner parsed elsewhere
        'header', 'contents', 'actionId',

        # tooltipRenderer
        'dismissStrategy', 'suggestedPosition', 'promoConfig'
    ]

    _KNOWN_KEYS = set(list(_REMAPPING.keys()) +
                      _COLOUR_KEYS + _STICKER_KEYS + _KEYS_TO_IGNORE)

    # KNOWN ACTIONS AND MESSAGE TYPES
    _KNOWN_ADD_TICKER_TYPES = {
        'addLiveChatTickerItemAction': [
            'liveChatTickerSponsorItemRenderer',
            'liveChatTickerPaidStickerItemRenderer',
            'liveChatTickerPaidMessageItemRenderer'
        ]
    }

    _KNOWN_ADD_ACTION_TYPES = {
        'addChatItemAction': [
            # message saying Live Chat replay is on
            'liveChatViewerEngagementMessageRenderer',
            'liveChatMembershipItemRenderer',
            'liveChatTextMessageRenderer',
            'liveChatPaidMessageRenderer',
            'liveChatPlaceholderItemRenderer',  # placeholder
            'liveChatDonationAnnouncementRenderer',

            'liveChatPaidStickerRenderer',
            'liveChatModeChangeMessageRenderer', # e.g. slow mode enabled

            # TODO find examples of:
            'liveChatPurchasedProductMessageRenderer', # product purchased


        ]
    }

    _KNOWN_REPLACE_ACTION_TYPES = {
        'replaceChatItemAction': [
            'liveChatPlaceholderItemRenderer',
            'liveChatTextMessageRenderer'
        ]
    }

    # actions that have an 'item'
    _KNOWN_ITEM_ACTION_TYPES = {
        **_KNOWN_ADD_TICKER_TYPES, **_KNOWN_ADD_ACTION_TYPES}

    # [message deleted] or [message retracted]
    _KNOWN_REMOVE_ACTION_TYPES = {
        'markChatItemsByAuthorAsDeletedAction': [  # TODO ban?
            'deletedStateMessage'
        ],
        'markChatItemAsDeletedAction': [
            'deletedStateMessage'
        ]
    }

    _KNOWN_ADD_BANNER_TYPES = {
        'addBannerToLiveChatCommand': [
            'liveChatBannerRenderer',
            'liveChatBannerHeaderRenderer'
            'liveChatTextMessageRenderer'
        ]
    }

    _KNOWN_TOOLTIP_ACTION_TYPES = {
        'showLiveChatTooltipCommand': [
            'tooltipRenderer'
        ]
    }

    # Not checked for
    _KNOWN_OTHER_ACTION_TYPES = {
        'authorBadges':[
            'liveChatAuthorBadgeRenderer'
        ],
        'showLiveChatItemEndpoint':[
            'liveChatPaidStickerRenderer',
            'liveChatPaidMessageRenderer',
            'liveChatMembershipItemRenderer'
        ]
    }
    _KNOWN_IGNORE_ACTION_TYPES = {}

    _KNOWN_ACTION_TYPES = {
        **_KNOWN_ADD_TICKER_TYPES,
        **_KNOWN_ITEM_ACTION_TYPES,
        **_KNOWN_REMOVE_ACTION_TYPES,
        **_KNOWN_REPLACE_ACTION_TYPES,
        **_KNOWN_ADD_BANNER_TYPES,
        **_KNOWN_TOOLTIP_ACTION_TYPES,
        **_KNOWN_OTHER_ACTION_TYPES,
        **_KNOWN_IGNORE_ACTION_TYPES
    }
    _KNOWN_MESSAGE_TYPES = []
    for action in _KNOWN_ACTION_TYPES:
        _KNOWN_MESSAGE_TYPES += _KNOWN_ACTION_TYPES[action]

    # print('_KNOWN_ACTION_TYPES', _KNOWN_ACTION_TYPES)
    # print('_KNOWN_MESSAGE_TYPES', _KNOWN_MESSAGE_TYPES)
    # continuations
    _KNOWN_SEEK_CONTINUATIONS = [
        'playerSeekContinuationData'
    ]

    _KNOWN_CHAT_CONTINUATIONS = [
        'invalidationContinuationData', 'timedContinuationData',
        'liveChatReplayContinuationData', 'reloadContinuationData'
    ]

    _KNOWN_CONTINUATIONS = _KNOWN_SEEK_CONTINUATIONS + _KNOWN_CHAT_CONTINUATIONS

    def _get_initial_info(self, video_id):
        """ Get initial YouTube video information. """
        original_url = '{}/watch?v={}'.format(self._YT_HOME, video_id)
        html = self._session_get(original_url)

        info = re.search(self._YT_INITIAL_DATA_RE, html.text)

        if(not info):
            raise ParsingError(
                'Unable to parse video data. Please try again.')

        ytInitialData = json.loads(info.group(1))
        # print(ytInitialData)
        contents = ytInitialData.get('contents')
        if(not contents):
            raise VideoUnavailable('Video is unavailable (may be private).')

        columns = contents.get('twoColumnWatchNextResults')

        if('conversationBar' not in columns or 'liveChatRenderer' not in columns['conversationBar']):
            error_message = 'Video does not have a chat replay.'
            try:
                error_message = self.parse_runs(
                    columns['conversationBar']['conversationBarRenderer']['availabilityMessage']['messageRenderer']['text'])
            except KeyError:
                pass
            finally:
                raise NoChatReplay(error_message)

        livechat_header = columns['conversationBar']['liveChatRenderer']['header']
        viewselector_submenuitems = livechat_header['liveChatHeaderRenderer'][
            'viewSelector']['sortFilterSubMenuRenderer']['subMenuItems']

        continuation_by_title_map = {
            x['title']: x['continuation']['reloadContinuationData']['continuation']
            for x in viewselector_submenuitems
        }
        # print(columns['results']['results']['contents'][0]['videoPrimaryInfoRenderer']['title'])
        return {
            'title': try_get(columns, lambda x: self.parse_runs(x['results']['results']['contents'][0]['videoPrimaryInfoRenderer']['title'])),
            'continuation_info': continuation_by_title_map
        }

    def _get_replay_info(self, continuation, offset_microseconds=None):
        """Get YouTube replay info, given a continuation or a certain offset."""
        url = self._YOUTUBE_API_BASE_TEMPLATE.format(self._YT_HOME,
                                                     'live_chat_replay', 'get_live_chat_replay', continuation)
        if(offset_microseconds is not None):
            url += self._YOUTUBE_API_PARAMETERS_TEMPLATE.format(
                offset_microseconds)
        # print(url)  # TODO make printing url as debug option?
        return self._get_continuation_info(url)

    def _get_live_info(self, continuation):
        """Get YouTube live info, given a continuation."""
        url = self._YOUTUBE_API_BASE_TEMPLATE.format(self._YT_HOME,
                                                     'live_chat', 'get_live_chat', continuation)
        return(self._get_continuation_info(url))

    def _get_continuation_info(self, url):
        """Get continuation info for a YouTube video."""
        json = self._session_get_json(url)
        if('continuationContents' in json['response']):
            return json['response']['continuationContents']['liveChatContinuation']
        else:
            raise NoContinuation

    def get_chat_by_video_id(self, video_id, params):
        """ Get chat messages for a YouTube video. """
        # getting a template of all types of raw message types

        initial_info = self._get_initial_info(video_id)

        initial_continuation_info = initial_info.get('continuation_info')
        initial_title_info = initial_info.get('title')

        start_time = ensure_seconds(
            self.get_param_value(params, 'start_time'))
        end_time = ensure_seconds(
            self.get_param_value(params, 'end_time'))

        # Top chat replay - Some messages, such as potential spam, may not be visible
        # Live chat replay - All messages are visible

        chat_type = self.get_param_value(params, 'chat_type')

        chat_type_field = chat_type.title()
        chat_replay_field = '{} chat replay'.format(chat_type_field)
        chat_live_field = '{} chat'.format(chat_type_field)

        if(chat_replay_field in initial_continuation_info):
            is_live = False
            continuation_title = chat_replay_field
        elif(chat_live_field in initial_continuation_info):
            is_live = True
            continuation_title = chat_live_field
        else:
            raise NoChatReplay('Video does not have a chat replay.')

        continuation = initial_continuation_info[continuation_title]
        offset_milliseconds = start_time * \
            1000 if isinstance(start_time, int) else None

        if(params.get('logging') != 'none'):
            print('Getting chat for', initial_title_info, flush=True)

        max_attempts = self.get_param_value(params, 'max_attempts')
        max_messages = self.get_param_value(params, 'max_messages')
        message_list = self.get_param_value(params, 'messages')
        callback = self.get_param_value(params, 'callback')

        messages_groups_to_add = self.get_param_value(params, 'message_groups')
        messages_types_to_add = self.get_param_value(params, 'message_types')
        # print(types_of_messages_to_add)

        first_time = True
        while True:
            info = None
            # the following can raise NoContinuation error or JSONParseError
            attempt_number = 1
            while(not info):
                try:
                    if(is_live):
                        info = self._get_live_info(continuation)
                    else:
                        # must run to get first few messages, otherwise might miss some
                        if(first_time):
                            info = self._get_replay_info(continuation)
                        else:
                            info = self._get_replay_info(
                                continuation, offset_milliseconds)
                except JSONParseError as e:
                    if(params.get('logging') in ('debug', 'errors_only')):
                        debug_print('Retry #{}'.format(attempt_number))
                        debug_print('Error:', e)
                        input()

                    if(attempt_number >= max_attempts):
                        # TODO maybe raise?
                        raise RetriesExceeded(
                            'Maximum number of retries has been reached ({}).'.format(max_attempts))
                        # return message_list
                    attempt_number += 1

                except NoContinuation:
                    # Live stream ended
                    return message_list

            actions = info.get('actions')

            if(actions):
                for action in actions:
                    data = {}

                    # if it is a replay chat item action, must re-base it
                    replay_chat_item_action = action.get(
                        'replayChatItemAction')
                    if(replay_chat_item_action):
                        offset_time = replay_chat_item_action.get(
                            'videoOffsetTimeMsec')
                        if(offset_time):
                            data['time_in_seconds'] = int(offset_time)/1000

                        action = replay_chat_item_action['actions'][0]

                    action.pop('clickTrackingParams', None)
                    original_action_type = try_get_first_key(action)

                    if(original_action_type not in self._KNOWN_ACTION_TYPES):
                        if(params.get('logging') in ('debug', 'errors_only')):
                            debug_print('Unknown action:',
                                        original_action_type)
                            debug_print(action)
                            debug_print(data)
                            input()

                        data['action_type'] = 'unknown'  # TODO temp
                    else:
                        data['action_type'] = camel_case_split(
                            remove_suffixes(original_action_type, ('Action', 'Command')))

                    original_message_type = None
                    original_item = {}

                    # We now parse the info and get the message
                    # type based on the type of action
                    if(original_action_type in self._KNOWN_ITEM_ACTION_TYPES):
                        original_item = try_get(
                            action, lambda x: x[original_action_type]['item'])
                        original_message_type = try_get_first_key(
                            original_item)
                        data = self._parse_item(original_item, data)

                    elif(original_action_type in self._KNOWN_REMOVE_ACTION_TYPES):
                        original_item = action
                        original_message_type = 'deletedStateMessage'
                        data = self._parse_item(original_item, data)

                    elif original_action_type in self._KNOWN_REPLACE_ACTION_TYPES:
                        original_item = try_get(
                            action, lambda x: x[original_action_type]['replacementItem'])
                        original_message_type = try_get_first_key(
                            original_item)
                        data = self._parse_item(original_item, data)

                    elif original_action_type in self._KNOWN_TOOLTIP_ACTION_TYPES:
                        original_item = try_get(
                            action, lambda x: x[original_action_type]['tooltip'])
                        original_message_type = try_get_first_key(
                            original_item)
                        data = self._parse_item(original_item, data)

                    elif(original_action_type in self._KNOWN_ADD_BANNER_TYPES):
                        original_item = try_get(
                            action, lambda x: x[original_action_type]['bannerRenderer'])

                        original_message_type = try_get_first_key(
                            original_item)

                        if(original_item):
                            header = original_item[original_message_type].get(
                                'header')
                            parsed_header = self._parse_item(header)
                            header_message = parsed_header.get('message')

                            contents = original_item[original_message_type].get(
                                'contents')
                            parsed_contents = self._parse_item(contents)

                            data.update(parsed_header)
                            data.update(parsed_contents)
                            data['header_message'] = header_message
                        else:
                            # TODO debug
                            pass

                    elif(original_action_type in self._KNOWN_IGNORE_ACTION_TYPES):
                        continue
                        # ignore these
                    else:
                        if(params.get('logging') in ('debug', 'errors_only')):
                            debug_print('Unknown action:',
                                        original_action_type)
                            debug_print(action)
                            debug_print(data)
                            input()

                    if(params.get('logging') in ('debug', 'errors_only')):  # TODO
                        test_for_missing_keys = original_item.get(
                            original_message_type, {}).keys()
                        missing_keys = test_for_missing_keys-self._KNOWN_KEYS

                        if not data:  # TODO debug
                            debug_print(
                                'Parse of action returned empty results:', original_action_type)
                            debug_print(action)
                            input()

                        if(missing_keys):  # TODO debugging for missing keys
                            debug_print('Missing keys found:', missing_keys)
                            debug_print('Message type:', original_message_type)
                            debug_print('Action type:', original_action_type)
                            debug_print('Action:', action)
                            debug_print('Parsed data:', data)
                            # when missing keys found, if ignore:
                            # append to _KEYS_TO_IGNORE
                            input()

                    if(original_message_type):
                        if original_message_type == 'deletedStateMessage':
                            data['message_type'] = 'deleted_message'
                        else:

                            new_index = remove_prefixes(
                                original_message_type, 'liveChat')
                            new_index = remove_suffixes(new_index, 'Renderer')
                            data['message_type'] = camel_case_split(new_index)

                        if(params.get('logging') in ('debug', 'errors_only')):

                            if original_message_type not in self._KNOWN_ACTION_TYPES[original_action_type]:
                                debug_print('Unknown message type ',
                                            '"'+original_message_type+'"', 'for action',
                                            '"'+original_action_type+'"')
                                debug_print('New message type:',
                                            data['message_type'])
                                debug_print('Action:', action)
                                debug_print('Parsed data:', data)
                                input()

                    else:  # no type # can ignore message
                        if(params.get('logging') in ('debug', 'errors_only')):
                            # TODO error? unknown message type
                            debug_print('No message type')
                            debug_print('Action type:', original_action_type)
                            debug_print('Action:', action)
                            debug_print('Parsed data:', data)
                            input()

                        continue

        # messages_types_to_add = self.get_param_value(params, 'message_types')
        # messages_groups_to_add = self.get_param_value(params, 'message_groups')
                    # TODO make this param a list for more variety

                    # user wants everything, keep going TODO True temp
                    if('all' in messages_groups_to_add):
                        pass

                    else:
                        # check whether to skip this message or not, based on its type

                        valid_message_types = []
                        for message_group in messages_groups_to_add or []:
                            valid_message_types += self._MESSAGE_GROUPS.get(
                                message_group, [])

                        for message_type in messages_types_to_add or []:
                            valid_message_types.append(message_type)

                        if(data.get('message_type') not in valid_message_types):
                            continue
                        # for key in self._TYPES_OF_MESSAGES:
                        #     #print(key)
                        #     # user does not want a message type + message is that type
                        #     #corresponding_message_types = [original_message_type for in self._TYPES_OF_MESSAGES[key]]

                        #     print(1,key, types_of_messages_to_add)
                        #     print(2,original_message_type, self._TYPES_OF_MESSAGES[key])
                        #     if(key not in types_of_messages_to_add and original_message_type in self._TYPES_OF_MESSAGES[key]):
                        #         print(key, 'not in', types_of_messages_to_add)

                        #     # else:
                        #     #     print(key, 'in', types_of_messages_to_add)

                    # if from a replay, check whether to skip this message or not, based on its time
                    if(not is_live):
                        # assume message is at beginning if it does not have a time component
                        time_in_seconds = data.get('time_in_seconds', 0)

                        before_start = start_time is not None and time_in_seconds < start_time
                        after_end = end_time is not None and time_in_seconds > end_time

                        if(first_time and before_start):
                            continue  # first time and invalid start time
                        elif(before_start or after_end):
                            return message_list  # while actually searching, if time is invalid

                    # valid timing, add

                    message_list.append(data)
                    if(max_messages is not None and len(message_list) >= max_messages):
                        return message_list  # if max_messages specified, return once limit has been reached

                    self.perform_callback(callback, data)

            elif(not is_live):
                # no more actions to process in a chat replay
                break
            else:
                pass
                # otherwise, is live, so keep trying

            if(params.get('logging') == 'debug'):
                debug_print('Total number of messages:', len(message_list))

            # assume there are no more chat continuations
            no_continuation = True

            # parse the continuation information
            for cont in info.get('continuations') or []:

                continuation_key = try_get_first_key(cont)
                continuation_info = cont[continuation_key]

                if(continuation_key in self._KNOWN_CHAT_CONTINUATIONS):

                    # set new chat continuation
                    # overwrite if there is continuation data
                    continuation = continuation_info.get('continuation')

                    # there is a chat continuation
                    no_continuation = False

                elif(continuation_key in self._KNOWN_SEEK_CONTINUATIONS):
                    pass
                    # ignore these continuations
                else:
                    if(params.get('logging') in ('debug', 'errors_only')):
                        debug_print('Unknown continuation:', continuation_key)
                        debug_print(cont)
                        input()

                # sometimes continuation contains timeout info
                timeout = continuation_info.get('timeoutMs')
                if timeout:
                    # must wait before calling again
                    # prevents 429 errors (too many requests)
                    time.sleep(timeout/1000)

            if(no_continuation):  # no continuation, end
                break

            if(first_time):
                first_time = False

        return message_list
    # override base method

    def get_chat_messages(self, params):
        super().get_chat_messages(params)

        url = self.get_param_value(params, 'url')
        # messages = YouTubeChatDownloader.get_param_value(params, 'messages')

        match = re.search(self._VALID_URL, url)

        if(match):

            if(match.group('id')):  # normal youtube video
                return self.get_chat_by_video_id(match.group('id'), params)

            else:  # TODO add profile, etc.
                pass
