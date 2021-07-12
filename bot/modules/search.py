import os
import time
import html
import asyncio
import aiohttp
import json
import feedparser
import requests
import itertools

from telegram.ext import CommandHandler
from telegram import ParseMode

from urllib.parse import quote as urlencode, urlsplit


from bot import dispatcher
from bot.helper import custom_filters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters

search_lock = asyncio.Lock()
search_info = {False: dict(), True: dict()}

async def return_search(query, page=1, sukebei=False):
    page -= 1
    query = query.lower().strip()
    used_search_info = search_info[sukebei]
    async with search_lock:
        results, get_time = used_search_info.get(query, (None, 0))
        if (time.time() - get_time) > 3600:
            results = []
            async with aiohttp.ClientSession() as session:
                async with session.get(f'https://{"sukebei." if sukebei else ""}nyaa.si/?page=rss&q={urlencode(query)}') as resp:
                    d = feedparser.parse(await resp.text())
            text = ''
            a = 0
            parser = pyrogram_html.HTML(None)
            for i in sorted(d['entries'], key=lambda i: int(i['nyaa_seeders']), reverse=True):
                if i['nyaa_size'].startswith('0'):
                    continue
                if not int(i['nyaa_seeders']):
                    break
                link = i['link']
                splitted = urlsplit(link)
                if splitted.scheme == 'magnet' and splitted.query:
                    link = f'<code>{link}</code>'
                newtext = f'''<b>{a + 1}.</b> <code>{html.escape(i["title"])}</code>
<b>Link:</b> <code>{link}</code>
<b>Size:</b> <code>{i["nyaa_size"]}</code>
<b>Seeders:</b> <code>{i["nyaa_seeders"]}</code>
<b>Leechers:</b> <code>{i["nyaa_leechers"]}</code>
<b>Category:</b> <code>{i["nyaa_category"]}</code>\n\n'''
                futtext = text + newtext
                if (a and not a % 10) or len((await parser.parse(futtext))['message']) > 4096:
                    results.append(text)
                    futtext = newtext
                text = futtext
                a += 1
            results.append(text)
        ttl = time.time()
        used_search_info[query] = results, ttl
        try:
            return results[page], len(results), ttl
        except IndexError:
            return '', len(results), ttl

message_info = dict()
ignore = set()




# Using upstream API based on: https://github.com/Ryuk-me/Torrents-Api
# Implemented by https://github.com/jusidama18

class TorrentSearch:
    index = 0
    query = None
    message = None
    response = None
    response_range = None

    RESULT_LIMIT = 4
    RESULT_STR = None

    def __init__(self, command: str, source: str, result_str: str):
        self.command = command
        self.source = source.rstrip('/')
        self.RESULT_STR = result_str

        
    @staticmethod
    def format_magnet(string: str):
        if not string:
            return ""
        return string.split('&tr', 1)[0]

    def get_formatted_string(self, values):
        string = self.RESULT_STR.format(**values)
        extra = ""
        if "Files" in values:
            tmp_str = "➲[{Quality} - {Type} ({Size})]({Torrent}): `{magnet}`"
            extra += "\n".join(
                tmp_str.format(**f, magnet=self.format_magnet(f['Magnet']))
                for f in values['Files']
            )
        else:
            magnet = values.get('magnet', values.get('Magnet'))  # Avoid updating source dict
            if magnet:
                extra += f"➲Magnet: `{self.format_magnet(magnet)}`"
        if (extra):
            string += "\n" + extra
        return string

    async def update_message(self):
        prevBtn = InlineKeyboardButton(f"Prev", callback_data=f"{self.command}_previous")
        delBtn = InlineKeyboardButton(f"{emoji.CROSS_MARK}", callback_data=f"{self.command}_delete")
        nextBtn = InlineKeyboardButton(f"Next", callback_data=f"{self.command}_next")

        inline = []
        if (self.index != 0):
            inline.append(prevBtn)
        inline.append(delBtn)
        if (self.index != len(self.response_range) - 1):
            inline.append(nextBtn)

        res_lim = min(self.RESULT_LIMIT, len(self.response) - self.RESULT_LIMIT*self.index)
        result = f"**Page - {self.index+1}**\n\n"
        result += "\n\n=======================\n\n".join(
            self.get_formatted_string(self.response[self.response_range[self.index]+i])
            for i in range(res_lim)
        )

        await self.message.edit(
            result,
            reply_markup=InlineKeyboardMarkup([inline]),
            parse_mode="markdown",
        )

    async def find(self, client, message):
        if len(message.command) < 2:
            await message.reply_text(f"Usage: /{self.command} query")
            return

        query = urlencode(message.text.split(None, 1)[1])
        self.message = await message.reply_text("Searching")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.source}/{query}") as resp:
                    if (resp.status != 200):
                        raise Exception('unsuccessful request')
                    result = await resp.json()
                    if (result and isinstance(result[0], list)):
                        result = list(itertools.chain(*result))
                    self.response = result
                    self.response_range = range(0, len(self.response), self.RESULT_LIMIT)
        except:
            await self.message.edit("No Results Found.")
            return
        await self.update_message()

    async def delete(self, client, message):
        index = 0
        query = None
        message = None
        response = None
        response_range = None
        await self.message.delete()

    async def previous(self, client, message):
        self.index -= 1
        await self.update_message()

    async def next(self, client, message):
        self.index += 1
        await self.update_message()

RESULT_STR_1337 = (
    "➲Name: `{Name}`\n"
    "➲Size: {Size}\n"
    "➲Seeders: {Seeders} || ➲Leechers: {Leechers}"
)
RESULT_STR_PIRATEBAY = (
    "➲Name: `{Name}`\n"
    "➲Size: {Size}\n"
    "➲Seeders: {Seeders} || ➲Leechers: {Leechers}"
)
RESULT_STR_TGX = (
    "➲Name: `{Name}`\n" 
    "➲Size: {Size}\n"
    "➲Seeders: {Seeders} || ➲Leechers: {Leechers}"
)
RESULT_STR_YTS = (
    "➲Name: `{Name}`\n"
    "➲Released on: {ReleasedDate}\n"
    "➲Genre: {Genre}\n"
    "➲Rating: {Rating}\n"
    "➲Likes: {Likes}\n"
    "➲Duration: {Runtime}\n"
    "➲Language: {Language}"
)
RESULT_STR_EZTV = (
    "➲Name: `{Name}`\n"
    "➲Size: {Size}\n"
    "➲Seeders: {Seeders}"
)
RESULT_STR_TORLOCK = (
    "➲Name: `{Name}`\n"
    "➲Size: {Size}\n"
    "➲Seeders: {Seeders} || ➲Leechers: {Leechers}"
)
RESULT_STR_RARBG = (
    "➲Name: `{Name}`\n"
    "➲Size: {Size}\n"
    "➲Seeders: {Seeders} || ➲Leechers: {Leechers}"
)
RESULT_STR_ALL = (
    "➲Name: `{Name}`\n"
    "➲Size: {Size}\n"
    "➲Seeders: {Seeders} || ➲Leechers: {Leechers}"
)

torrents_dict = {
    '1337x': {'source': "https://slam-api.herokuapp.com/api/1337x/", 'result_str': RESULT_STR_1337},
    'piratebay': {'source': "https://slam-api.herokuapp.com/api/piratebay/", 'result_str': RESULT_STR_PIRATEBAY},
    'tgx': {'source': "https://slam-api.herokuapp.com/api/tgx/", 'result_str': RESULT_STR_TGX},
    'yts': {'source': "https://slam-api.herokuapp.com/api/yts/", 'result_str': RESULT_STR_YTS},
    'eztv': {'source': "https://slam-api.herokuapp.com/api/eztv/", 'result_str': RESULT_STR_EZTV},
    'torlock': {'source': "https://slam-api.herokuapp.com/api/torlock/", 'result_str': RESULT_STR_TORLOCK},
    'rarbg': {'source': "https://slam-api.herokuapp.com/api/rarbg/", 'result_str': RESULT_STR_RARBG},
    'ts': {'source': "https://slam-api.herokuapp.com/api/all/", 'result_str': RESULT_STR_ALL}
}

torrent_handlers = []
for command, value in torrents_dict.items():
    torrent_handlers.append(TorrentSearch(command, value['source'], value['result_str']))

def searchhelp(update, context):
    help_string = '''
• /nyaasi <i>[search query]</i>
• /sukebei <i>[search query]</i>
• /1337x <i>[search query]</i>
• /piratebay <i>[search query]</i>
• /tgx <i>[search query]</i>
• /yts <i>[search query]</i>
• /eztv <i>[search query]</i>
• /torlock <i>[search query]</i>
• /rarbg <i>[search query]</i>
• /ts <i>[search query]</i>
'''
    update.effective_message.reply_photo(help_string, parse_mode=ParseMode.HTML)
    
    
SEARCHHELP_HANDLER = CommandHandler(BotCommands.TsHelpCommand, searchhelp, filters=CustomFilters.owner_filter)
dispatcher.add_handler(SEARCHHELP_HANDLER)
