import os
import re
import json
import time
import asyncio
import logging
import requests
import traceback
import subprocess
import multiprocessing
from datetime import datetime, timedelta, timezone
from pprint import pformat
from uuid import uuid4
from dotenv import load_dotenv
from urllib.parse import unquote, urljoin, parse_qs, urlparse

from telegram.ext import (
    filters,
    MessageHandler,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler
)
from telegram import (
    Update,
    Bot,
    MessageEntity,
    InputMediaPhoto,
    InputMediaVideo,
    InlineQueryResultPhoto,
    InlineQueryResultVideo
)
from telegram.constants import ParseMode
from telegraph.aio import Telegraph

from mitmproxy.tools.main import mitmdump
from mitmproxy import http

# Load environment variables from .env file
load_dotenv()


logging_file = f".\\log\\{datetime.now().strftime('%Y%m%d%H%M%S')}.log"
logging.basicConfig(
    handlers=[
        logging.FileHandler(
            filename=logging_file,
            encoding="utf-8",
            mode="w+",
        ),
        logging.StreamHandler()
    ],
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%F %A %T",
    level=logging.WARNING
)
logging.getLogger("httpx").setLevel(logging.WARNING)

with open('redtoemoji.json', 'r', encoding='utf-8') as f:
    redtoemoji = json.load(f)
    f.close()

def replace_redemoji_with_emoji(text: str) -> str:
    for red_emoji, emoji in redtoemoji.items():
        text = text.replace(red_emoji, emoji)
    return text

def set_request(note_id:str, url: str, headers: dict, type: str) -> dict:
    if note_id is None:
        return {}
    requests.post(
        f"http://127.0.0.1:5001/set_{type}",
        json={"note_id": note_id, "url": url, "headers": headers}
    )
    return {'url': url, 'headers': headers}


class ImageFeedFilter:
    def __init__(self, callback):
        self.callback = callback
        self.url_pattern = re.compile(r"https://edith.xiaohongshu.com/api/sns/v\d+/note/imagefeed")
        self.type = 'note'

    def get_note_id(self, url: str) -> str:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        note_id = query_params.get('note_id', [None])[0]
        return note_id

    def request(self, flow: http.HTTPFlow) -> None:
        if self.url_pattern.search(flow.request.pretty_url):
            self.callback(
                self.get_note_id(flow.request.pretty_url),
                flow.request.pretty_url,
                {k: v for k, v in flow.request.headers.items()},
                self.type
            )
    
    def response(self, flow: http.HTTPFlow) -> None:
        if self.url_pattern.search(flow.request.pretty_url):
            flow.response.status_code = 404
            flow.response.content = b"{\"fuckxhs\":true}"

class CommentListFilter(ImageFeedFilter):
    def __init__(self, callback):
        super().__init__(callback)
        self.url_pattern = re.compile(r'https?://edith.xiaohongshu.com/api/sns/v\d+/note/comment/list')
        self.type = 'comment_list'

    def request(self, flow: http.HTTPFlow) -> None:
        if self.url_pattern.search(flow.request.pretty_url):
            self.callback(
                self.get_note_id(flow.request.pretty_url),
                flow.request.pretty_url,
                {k: v for k, v in flow.request.headers.items()},
                self.type
            )

    def response(self, flow: http.HTTPFlow) -> None:
        pass


class BlockURLs:
    def __init__(self, block_pattern_list):
        self.block_pattern_list = block_pattern_list
    
    def response(self, flow: http.HTTPFlow) -> None:
        if [True for pattern in self.block_pattern_list if re.findall(pattern, flow.request.pretty_url)]:
            flow.response.status_code = 345
            flow.response.content = b"{'fuckxhs': true}"


class Note:
    def __init__(
            self,
            note_data: dict,
            comment_list_data: dict,
            live: bool = False,
            telegraph: bool = False,
            inline: bool = False
    ) -> None:
        self.telegraph = telegraph
        logging.warning(f"Note telegraph? {self.telegraph}")
        self.inline = inline
        logging.warning(f"Note inline? {self.inline}")
        if not note_data['data']:
            raise Exception("Note data not found!")
        self.user = {
            'id': note_data['data'][0]['user']['id'],
            'name': note_data['data'][0]['user']['name'],
            'red_id': note_data['data'][0]['user']['red_id'],
            # 'image': note_data['data'][0]['user']['image'],
            # 'nickname': note_data['data'][0]['user']['nickname'],
            # 'userid': note_data['data'][0]['user']['userid'],
        }
        # self.text_language_code = note_data['data'][0]['note_list'][0]['text_language_code']

        self.title = note_data['data'][0]['note_list'][0]['title'] if note_data['data'][0]['note_list'][0]['title'] else f"Untitled Note by @{self.user['name']} ({self.user['red_id']})"
        self.type = note_data['data'][0]['note_list'][0]['type']

        self.raw_desc = replace_redemoji_with_emoji(note_data['data'][0]['note_list'][0]['desc'])
        logging.warning(f"Note raw_desc\n\n {self.raw_desc}")
        self.desc = re.sub(
            r'(?P<tag>#\S+?)\[[⺀-⺙⺛-⻳⼀-⿕々〇〡-〩〸-〺〻㐀-䶵一-鿃豈-鶴侮-頻並-龎]+\]#',
            r' \g<tag> ',
            self.raw_desc
        )
        self.length = len(self.desc + self.title)
        self.time = note_data['data'][0]['note_list'][0]['time']
        self.ip_location = note_data['data'][0]['note_list'][0]['ip_location']\
            if 'ip_location' in note_data['data'][0]['note_list'][0] else 'Unknown IP Address'
        self.collected_count = note_data['data'][0]['note_list'][0]['collected_count']
        self.comments_count = note_data['data'][0]['note_list'][0]['comments_count']
        self.shared_count = note_data['data'][0]['note_list'][0]['shared_count']
        self.liked_count = note_data['data'][0]['note_list'][0]['liked_count']
        # self.last_update_time = note_data['data'][0]['note_list'][0]['last_update_time']

        self.first_comment = replace_redemoji_with_emoji(
            comment_list_data['data']['comments'][0]['content'] if comment_list_data['data']['comments'] else ''
        )
        if self.first_comment:
            self.first_comment = re.sub(
                r'#(?P<tag_text>\S+?)\[搜索高亮\]#',
                r'\g<tag_text>',
                self.first_comment
            )
            self.comment_user = comment_list_data['data']['comments'][0]['user']['nickname'] if comment_list_data['data']['comments'] else ''
            self.first_comment_tag_v2 = comment_list_data['data']['comments'][0]['show_tags_v2'][0]['text'] if comment_list_data['data']['comments'][0]['show_tags_v2'] else ''
            # self.comment_user_red_id = comment_list_data['data']['comments'][0]['user']['red_id'] if comment_list_data['data']['comments'] else '114514'
            # self.first_comment_type = comment_list_data['data']['comments'][0]['comment_type'] if comment_list_data['data']['comments'] else -1

        self.images_list = []
        if 'images_list' in note_data['data'][0]['note_list'][0] and 'video' not in note_data['data'][0]['note_list'][0]:
            self.images_list = []
            for each in note_data['data'][0]['note_list'][0]['images_list']:
                self.images_list.append(
                    {
                        'live': False,
                        'url': remove_image_url_params(each['original']),
                        'thumbnail': remove_image_url_params(each['url_multi_level']['low'])
                    }
                )
                if 'live_photo' in each and live:
                    for s in each['live_photo']['media']['stream']:
                        live_urls = []
                        if each['live_photo']['media']['stream'][s]:
                            for ss in each['live_photo']['media']['stream'][s]:
                                live_urls.append(remove_image_url_params(ss['master_url']))
                        if len(live_urls) > 0:
                            self.images_list.append(
                                {'live': True, 'url': remove_image_url_params(live_urls[0]), 'thumbnail': remove_image_url_params(each['original'])}
                            )
        logging.warning(f"Images found: {self.images_list}")
        self.video_url = ''
        if 'video' in note_data['data'][0]['note_list'][0]:
            self.video_url = note_data['data'][0]['note_list'][0]['video']['url']
            self.video_thumbnail = note_data['data'][0]['note_list'][0]['images_list'][0]['url_multi_level']['low']
        self.url = get_clean_url(note_data['data'][0]['note_list'][0]['share_info']['link'])
        self.noteId = re.findall(r"[a-z0-9]{24}", self.url)[0]

        self.to_html()
        self.to_telegram_message(preview=bool(self.length >= 666))
        logging.warning(f"len: {self.length}, preview? = {bool(self.length >= 666)}")
        self.to_media_group(inline=self.inline)
    
    async def initialize(self) -> None:
        if self.telegraph:
            await self.to_telegraph()
        self.short_preview = ''
        if self.inline:
            await self.to_short_preview()

    def to_dict(self) -> dict:
        return {
            'user': self.user,
            'text_language_code': self.text_language_code,
            'title': self.title,
            'type': self.type,
            'desc': self.desc,
            'length': self.length,
            'time': self.time,
            'ip_location': self.ip_location,
            'collected_count': self.collected_count,
            'comments_count': self.comments_count,
            'shared_count': self.shared_count,
            'liked_count': self.liked_count,
            'images_list': getattr(self, 'images_list', []),
            'video_url': getattr(self, 'video_url', ''),
            'url': self.url,
            # 'last_update_time': self.last_update_time,
        }
    
    def to_html(self) -> str:
        html = ''
        html += f'<h3>『<a href="{self.url}">{self.title}</a>』</h3>'
        for img in self.images_list:
            if not img['live']:
                html += f'<img src="{img["url"]}"></img>'
            else:
                html += f'<video src="{img["url"]}"></video>'
        if self.video_url:
            html += f'<video src="{self.video_url}"></video>'
        html += f'<p>{self.desc.replace('\n', '<br>')}</p>'
        html += f'<h4>👤 <a href="https://www.xiaohongshu.com/user/profile/{self.user["id"]}"> @{self.user["name"]} ({self.user["red_id"]})</a></h4>'
        html += f'<p>{get_time_emoji(self.time)} {convert_timestamp_to_timestr(self.time)}</p>'
        html += f'<p>❤️ {self.liked_count} ⭐ {self.collected_count} 💬 {self.comments_count} 🔗 {self.shared_count}</p>'
        html += f'<p>📍 {tg_msg_escape_markdown_v2(self.ip_location) if hasattr(self, 'ip_location') else 'Unknown IP Address'}</p>'
        html += '<br><i>via</i> <a href="https://t.me/xhsfeedbot">@xhsfeedbot</a>'
        self.html = html
        return self.html
    
    def make_block_quotation(self, text: str) -> str:
        lines = [f'> {tg_msg_escape_markdown_v2(line)}' for line in text.split('\n')]
        lines[0] = f'**{lines[0]}'
        lines[-1] = f'{lines[-1]}||'
        return '\n'.join(lines)

    async def to_telegraph(self) -> str:
        if not hasattr(self, 'html'):
            self.to_html()
        telegraph = Telegraph()
        await telegraph.create_account(
            short_name='@xhsfeed',
        )
        response = await telegraph.create_page(
            title=self.title if self.title else f"Note by @{self.user['name']} ({self.user['red_id']})",
            author_name=f'@xhsfeed',
            author_url=f"https://t.me/xhsfeed",
            html_content=self.html,
        )
        self.telegraph_url = response['url']
        logging.warning(f"Generated Telegraph URL: {self.telegraph_url}")
        return self.telegraph_url

    async def to_telegram_message(self, preview=False) -> str:
        message = ''
        message += f'*『[{tg_msg_escape_markdown_v2(self.title)}]({self.url})』*\n\n'
        if preview:
            message += f'{self.make_block_quotation(self.desc[:555]+' ...')}\n\n'
            if hasattr(self, 'telegraph_url'):
                message += f'📝 [View more via Telegraph]({tg_msg_escape_markdown_v2(self.telegraph_url)})\n\n'
            else:
                message += f'📝 [View more via Telegraph]({tg_msg_escape_markdown_v2(await self.to_telegraph())})\n\n'
        else:
            message += f'{self.make_block_quotation(self.desc)}\n\n'
            if hasattr(self, 'telegraph_url'):
                message += f'📝 [Telegraph]({tg_msg_escape_markdown_v2(self.telegraph_url)})\n\n'
            elif self.telegraph:
                message += f'📝 [Telegraph]({tg_msg_escape_markdown_v2(await self.to_telegraph())})\n\n'
        message += f'[@{tg_msg_escape_markdown_v2(self.user["name"])} \\({tg_msg_escape_markdown_v2(self.user["red_id"])}\\)](https://www.xiaohongshu.com/user/profile/{self.user["id"]})\n\n'
        message += f'**>❤️ {
            tg_msg_escape_markdown_v2(self.liked_count) if type(self.liked_count) == str else self.liked_count
        } ⭐ {
            tg_msg_escape_markdown_v2(self.collected_count) if type(self.collected_count) == str else self.collected_count
        } 💬 {
            tg_msg_escape_markdown_v2(self.comments_count) if type(self.comments_count) == str else self.comments_count
        } 🔗 {
            tg_msg_escape_markdown_v2(self.shared_count) if type(self.shared_count) == str else self.shared_count
        }'
        message += f'\n>{get_time_emoji(self.time)} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(self.time))}\n'
        message += f'>📍 {tg_msg_escape_markdown_v2(self.ip_location) if hasattr(self, 'ip_location') else 'Unknown IP Address'}||\n\n'
        message += self.make_block_quotation(
            f'🗨️ @{self.comment_user} {f'[{self.first_comment_tag_v2}]' if self.first_comment_tag_v2 else ''}\n'
            f'{self.first_comment}'
        ) if self.first_comment else ''
        message += '\n_via_ @xhsfeedbot'
        self.message = message
        logging.warning(f"Telegram message generated, \n\n{self.message}\n\n")
        return message

    async def to_short_preview(self):
        message = ''
        message += f'*『[{tg_msg_escape_markdown_v2(self.title)}]({self.url})』*\n\n'
        message += f'{self.make_block_quotation(self.desc[:166] + ' ...')}\n\n'
        if hasattr(self, 'telegraph_url'):
            message += f'📝 [View more via Telegraph]({tg_msg_escape_markdown_v2(self.telegraph_url)})\n\n'
        else:
            message += f'📝 [View more via Telegraph]({tg_msg_escape_markdown_v2(await self.to_telegraph())})\n\n'
        message += f'[@{tg_msg_escape_markdown_v2(self.user["name"])} \\({tg_msg_escape_markdown_v2(self.user["red_id"])}\\)](https://www.xiaohongshu.com/user/profile/{self.user["id"]})\n\n'
        message += f'**>❤️ {
            tg_msg_escape_markdown_v2(self.liked_count) if type(self.liked_count) == str else self.liked_count
        } 💬 {
            tg_msg_escape_markdown_v2(self.comments_count) if type(self.comments_count) == str else self.comments_count
        } 🔗 {
            tg_msg_escape_markdown_v2(self.shared_count) if type(self.shared_count) == str else self.shared_count
        } 💬 {
            tg_msg_escape_markdown_v2(self.comments_count) if type(self.comments_count) == str else self.comments_count
        }'
        message += f'\n>{get_time_emoji(self.time)} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(self.time))}\n'
        message += f'>📍 {tg_msg_escape_markdown_v2(self.ip_location) if hasattr(self, 'ip_location') else 'Unknown IP Address'}||'
        message += '\n_via_ @xhsfeedbot'
        self.short_preview = message
        logging.warning(f"Short preview generated, {self.short_preview}")
        return message

    async def to_media_group(self, inline: bool):
        if inline:
            if not self.short_preview:
                self.short_preview = await self.to_short_preview()
            self.inline_medien = []
            for n, imgs in enumerate(self.images_list):
                if not imgs['live']:
                    self.inline_medien.append(
                            InlineQueryResultPhoto(
                                id=str(uuid4()),
                                photo_url=imgs['url'],
                                thumbnail_url=imgs['url'],
                                title=f"Photo {n + 1}",
                                description=f"{self.title}",
                                caption=self.short_preview,
                                parse_mode=ParseMode.MARKDOWN_V2
                        )
                    )
                else:
                    self.inline_medien.append(
                        InlineQueryResultVideo(
                            id=str(uuid4()),
                            video_url=imgs['url'],
                            mime_type="video/mp4",
                            thumbnail_url=imgs['thumbnail'],
                            title=f"Live Photo {n + 1}",
                            description=f"{self.title}",
                            caption=self.short_preview,
                            parse_mode=ParseMode.MARKDOWN_V2
                        )
                    )
            if self.video_url:
                self.inline_medien.append(
                    InlineQueryResultVideo(
                        id=str(uuid4()),
                        video_url=self.video_url,
                        mime_type="video/mp4",
                        title=f"Video",
                        description=f"{self.title}",
                        thumbnail_url=self.video_thumbnail,
                        caption=self.short_preview,
                        parse_mode=ParseMode.MARKDOWN_V2,
                    )
                )
            return self.inline_medien
        else:
            self.medien = []
            for n, imgs in enumerate(self.images_list):
                if not imgs['live']:
                    self.medien.append(
                            InputMediaPhoto(imgs['url'])
                    )
                else:
                    self.medien.append(
                        InputMediaVideo(
                            requests.get(imgs['url']).content
                        )
                    )
            if self.video_url:
                self.medien.append(
                    InputMediaVideo(requests.get(self.video_url).content)
                )
            self.medien_parts = [self.medien[i:i + 10] for i in range(0, len(self.medien), 10)]
            return self.medien_parts

    async def send_as_telegram_message(self, bot: Bot, chat_id: int, reply_to_message_id: int = None):
        if not hasattr(self, 'medien_parts'):
            self.medien_parts = await self.to_media_group(inline=False)
        for i, part in enumerate(self.medien_parts):
            if i != len(self.medien_parts) - 1:
                try:
                    await bot.send_media_group(
                        chat_id=chat_id,
                        reply_to_message_id=reply_to_message_id,
                        media=part,
                    )
                except:
                    await bot.send_media_group(
                        chat_id=chat_id,
                        reply_to_message_id=reply_to_message_id,
                        media=[requests.get(p).content for p in part],
                    )
            else:
                try:
                    await bot.send_media_group(
                        chat_id=chat_id,
                        reply_to_message_id=reply_to_message_id,
                        media=part,
                        caption=self.message if hasattr(
                            self,
                            'message'
                        ) else await self.to_telegram_message(
                            preview=bool(self.length >= 666)
                        ),
                        parse_mode=ParseMode.MARKDOWN_V2,
                    )
                except:
                    await bot.send_media_group(
                        chat_id=chat_id,
                        reply_to_message_id=reply_to_message_id,
                        media=[requests.get(p).content for p in part],
                        caption=self.message if hasattr(
                            self,
                            'message'
                        ) else await self.to_telegram_message(
                            preview=bool(self.length >= 666)
                        ),
                        parse_mode=ParseMode.MARKDOWN_V2,
                    )


    async def send_as_telegram_inline(self, bot: Bot, inline_query_id: str):
        await bot.answer_inline_query(
            inline_query_id=inline_query_id,
            results=self.inline_medien if hasattr(self, 'inline_medien') else await self.to_media_group(inline=True),
            cache_time=0
        )

def get_redirected_url(url: str) -> str:
    return unquote(requests.get(url if 'http' in url else f'http://{url}').url.split("redirectPath=")[-1])

def get_clean_url(url: str) -> str:
    return urljoin(url, urlparse(url).path)

def get_time_emoji(timestamp: int) -> str:
    a = int(((timestamp + 8 * 3600) / 900 - 3) / 2 % 24)
    return f'{chr(128336 + a // 2 + a % 2 * 12)}'

def convert_timestamp_to_timestr(timestamp):
    utc_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    utc_plus_8 = utc_dt + timedelta(hours=8)
    return utc_plus_8.strftime('%Y-%m-%d %H:%M:%S UTC+0800')

def remove_image_url_params(url: str) -> str:
    for k, v in parse_qs(url).items():
        url = url.replace(f'&{k}={v[0]}', '')
    return url

def tg_msg_escape_html(t: str) -> str:
    return t.replace('<', '&lt;')\
        .replace('>','&gt;')\
        .replace('&', '&amp;')

def tg_msg_escape_markdown_v2(t: str) -> str:
    assert isinstance(t, str)
    for i in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        t = t.replace(i, "\\" + i)
    return t

def open_note(noteId: str):
    subprocess.run(["adb", "shell", "am", "start", "-d", f"xhsdiscover://item/{noteId}"])

def home_page():
    subprocess.run(["adb", "shell", "am", "start", "-d", "xhsdiscover://home"])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a xhsfeedbot, please send me a xhs link!")

async def note2feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    urls = re.findall(r"((?:[a-zA-Z0-9]+?:\/\/)?[a-zA-Z0-9_-]+\.[a-zA-Z0-9_/-]+)", update.message.text)
    if len(urls) == 0:
        logging.warning("NO URL FOUND!")
        return
    elif re.findall(r"[a-z0-9]{24}", update.message.text) and not re.findall(r"user/profile/[a-z0-9]{24}", update.message.text):
        noteId = re.findall(r"[a-z0-9]{24}", update.message.text)[0]
    else:
        xhslink = urls[0]
        logging.warning(f"URL found: {xhslink}")
        redirectPath = get_redirected_url(xhslink)
        if re.findall(r"https?://(?:www.)?xhslink.com/[a-z]/[A-Za-z0-9]+", xhslink):
            clean_url = get_clean_url(redirectPath)
            if 'xiaohongshu.com/404' not in redirectPath:
                noteId = re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/discovery\/item\/([a-z0-9]+)", clean_url)[0]
            else:
                noteId = re.findall(r"noteId=([a-z0-9]+)", redirectPath)[0]
        elif re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/discovery\/item\/[0-9a-z]+", xhslink):
            noteId = re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/discovery\/item\/([a-z0-9]+)", xhslink)[0]
        elif re.findall(r"https?://(?:www.)?xiaohongshu.com/explore/[a-z0-9]+", update.message.text):
            noteId = re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/explore\/([a-z0-9]+)", xhslink)[0]
        else:
            return
    open_note(noteId)
    time.sleep(0.5)

    try:
        note_request_data = requests.get(
            f"http://127.0.0.1:5001/get_note/{noteId}"
        ).json()
        comment_list_request_data = requests.get(
            f"http://127.0.0.1:5001/get_comment_list/{noteId}"
        ).json()

        note_data = requests.get(url=note_request_data['url'], headers=note_request_data['headers']).json()
        with open(f".\\data\\note_data-{noteId}.json", "w", encoding='utf-8') as f:
            json.dump(note_data, f, indent=4, ensure_ascii=False)
            f.close()

        comment_list_data = requests.get(
            url=comment_list_request_data['url'],
            headers=comment_list_request_data['headers']
        ).json()
        with open(f".\\data\\comment_list_data-{noteId}.json", "w", encoding='utf-8') as f:
            json.dump(comment_list_data, f, indent=4, ensure_ascii=False)
            f.close()
    except:
        return

    telegraph = bool(re.search(r" -t*(?![^ ])", update.message.text))
    live = bool(re.search(r" -l*(?![^ ])", update.message.text))
    try:
        note = Note(
            note_data,
            comment_list_data=comment_list_data,
            live=live,
            telegraph=telegraph,
            inline=False
        )
        await note.initialize()
        home_page()
        await note.send_as_telegram_message(context.bot, update.effective_chat.id, update.message.message_id)
    except:
        home_page()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="An error occurred while processing your request."
        )
        raise Exception(traceback.format_exc())

async def inline_note2feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    if not query:
        return
    urls = re.findall(r"((?:[a-zA-Z0-9]+?:\/\/)?[a-zA-Z0-9_-]+\.[a-zA-Z0-9_/-]+)", query)
    if len(urls) == 0 and not re.findall(r"[a-z0-9]{24}", query):
        return
    elif re.findall(r"[a-z0-9]{24}", query) and not re.findall(r"user/profile/[a-z0-9]{24}", query):
        noteId = re.findall(r"[a-z0-9]{24}", query)[0]
    else:
        xhslink = urls[0]
        redirectPath = get_redirected_url(xhslink)
        if re.findall(r"https?://(?:www.)?xhslink.com/[a-z]/[A-Za-z0-9]+", xhslink):
            clean_url = get_clean_url(redirectPath)
            if 'xiaohongshu.com/404' not in redirectPath:
                noteId = re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/discovery\/item\/([a-z0-9]+)", clean_url)[0]
            else:
                noteId = re.findall(r"noteId=([a-z0-9]+)", redirectPath)[0]
        elif re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/discovery\/item\/[0-9a-z]+", xhslink):
            noteId = re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/discovery\/item\/([a-z0-9]+)", xhslink)[0]
        elif re.findall(r"https?://(?:www.)?xiaohongshu.com/explore/[a-z0-9]+", query):
            noteId = re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/explore\/([a-z0-9]+)", xhslink)[0]
        else:
            raise Exception("No valid URL or Note ID found!")
    open_note(noteId)
    time.sleep(0.5)
    note_request_data = requests.get(
        f"http://127.0.0.1:5001/get_note/{noteId}"
    ).json()
    note_data = requests.get(url=note_request_data['url'], headers=note_request_data['headers']).json()

    comment_list_request_data = requests.get(
        f"http://127.0.0.1:5001/get_comment_list/{noteId}"
    ).json()
    comment_list_data = requests.get(
        url=comment_list_request_data['url'],
        headers=comment_list_request_data['headers']
    ).json()
    with open(f".\\data\\comment_list_data-{noteId}.json", "w", encoding='utf-8') as f:
        json.dump(comment_list_data, f, indent=4, ensure_ascii=False)
        f.close()
    telegraph = bool(re.search(r" -t*(?![^ ])", query))
    live = bool(re.search(r" -l*(?![^ ])", query))
    note = Note(
        note_data,
        comment_list_data=comment_list_data,
        live=live,
        telegraph=telegraph,
        inline=True,
    )
    await note.initialize()
    home_page()
    await note.send_as_telegram_inline(context.bot, update.inline_query.id)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global logging_file
    try:
        await context.bot.send_document(
            chat_id=os.getenv('ADMIN_ID'),
            caption=f'```python\n{tg_msg_escape_markdown_v2(pformat(update))}\n```\n CAUSED \n```python\n{tg_msg_escape_markdown_v2(pformat(context.error))}```',
            parse_mode=ParseMode.MARKDOWN_V2,
            document=logging_file,
            disable_notification=True
        )
        logging.error(f"Update {update} caused error:\n{context.error}\n\n send message ok\n\n{traceback.format_exc()}")
    except Exception as e:
        logging.error(f"Update {update} caused error:\n{context.error}\n\n try shutdown\nsend message also error:\n\n{traceback.format_exc()}")

def run_telegram_bot():
    bot_token = os.getenv('BOT_TOKEN')
    if not bot_token:
        raise ValueError("BOT_TOKEN environment variable is required")
    
    application = ApplicationBuilder()\
        .token(bot_token)\
        .read_timeout(60)\
        .write_timeout(60)\
        .media_write_timeout(300)\
        .build()

    start_handler = CommandHandler("start", start)
    application.add_handler(start_handler)

    application.add_error_handler(error_handler)

    inline_note2feed_handler = InlineQueryHandler(inline_note2feed)
    application.add_handler(inline_note2feed_handler)

    note2feed_handler = MessageHandler(
        filters.TEXT & (
            filters.Entity(MessageEntity.URL) |
            filters.Entity(MessageEntity.TEXT_LINK)
        ),
        note2feed
    )
    application.add_handler(note2feed_handler)

    while 1:
        try:
            application.run_polling()
        except:
            application.shutdown()
            logging.error(f'Error! {traceback.format_exc()}')

def run_mitm():
    mitmdump(args=["-s", "xhsfeedbot.py"])

def get_block_pattern_list() -> list:
    return [
        r'https?://fe-static.xhscdn.com/data/formula-static/hammer/patch/\S*',
        r'https?://cdn.xiaohongshu.com/webview/\S*',
        r'https?://infra-webview-s1.xhscdn.com/webview/\S*',
        r'https?://apm-fe.xiaohongshu.com/api/data/\S*',
        r'https?://apm-native.xiaohongshu.com/api/collect/?\S*',
        r'https?://lng.xiaohongshu.com/api/collect/?\S*',
        r'https?://edith.xiaohongshu.com/api/sns/celestial/connect/config\S*',
        r'https?://edith.xiaohongshu.com/api/im/users/filterUser/stranger',
        r'https?://t\d.xiaohongshu.com/api/collect/?\S*',
        r'https?://edith.xiaohongshu.com/api/sns/v\d/note/metrics_report',
        r'https?://edith.xiaohongshu.com/api/sns/v\d/system_service/flag_exp\S*',
        r'https?://edith.xiaohongshu.com/api/sns/v\d/system_service/config\S*',
        r'https?://sns-avatar-qc.xhscdn.com/avatar\S*',
        r'https?://edith.xiaohongshu.com/api/sns/v\d/user/signoff/flow',
        r'https?://rec.xiaohongshu.com/api/sns/v\d/followings/reddot',
        r'https?://gslb.xiaohongshu.com/api/gslb/v\d/domainNew\S*',
        r'https?://edith-seb.xiaohongshu.com/api/sns/v\d/system_service/config\S*',
        r'https?://sns-na-i\d.xhscdn.com/?\S*',
        r'https?://sns-avatar-qc.xhscdn.com/user_banner\S*',
        r'https?://www.xiaohongshu.com/api/sns/v\d/hey\S*',
        r'https?://edith.xiaohongshu.com/api/sns/v\d/note/detailfeed/preload\S*',
        r'https?://sns-na-i\d.xhscdn.com/?\S*',
        r'https?://edith.xiaohongshu.com/api/media/v\d/upload/permit\S*',
        r'https?://sns-na-i\d.xhscdn.com/notes_pre_post\S*',
        r'https?://infra-app-log-\d*.cos.ap-shanghai.myqcloud.com/xhslog\S*',
        r'https?://edith.xiaohongshu.com/api/sns/v\d/note/video_played',
        r'https?://edith.xiaohongshu.com/api/sns/v\d/note/widgets',
        r'https?://ros-upload.xiaohongshu.com/bad_frame\S*',
        r'https?://infra-app-log-\d*.cos.accelerate.myqcloud.com/xhslog\S*',
        r'https?://mall.xiaohongshu.com/api/store/guide/components/shop_entrance\S*',
        r'https?://edith.xiaohongshu.com/api/sns/v\d/system_service/launch',
        r'https?://spider-tracker.xiaohongshu.com/api/spider\S*',
        r'https?://open.kuaishouzt.com/rest/log/open/sdk/collect\S*',
        r'https?://ci.xiaohongshu.com/icons/user\S*',
        r'https?://picasso-static-bak.xhscdn.com/fe-platform\S*',
        r'https?://edith.xiaohongshu.com/api/sns/v1/system/service/ui/config\S*',
        r'https?://apm-fe.xiaohongshu.com/api/data\S*',
        r'https?://ci.xiaohongshu.com/1040g00831lni0o1j520g4bnb0m4mho3oa1dtrao\S*',
        r'https?://edith.xiaohongshu.com/api/sns/user_cache/follow/rotate\S*',
        r'https?://edith.xiaohongshu.com/api/sns/v1/im/get_recent_chats\S*',
        r'https?://as.xiaohongshu.com/api/v1/profile/android\S*',
        r'https?://edith.xiaohongshu.com/api/sns/v\d/message/detect\S*',
        r'https?://fe-platform-i\d.xhscdn.com/platform\S*',
        r'https?://fe-video-qc.xhscdn.com/fe-platform\S*'
        # r'https?://edith.xiaohongshu.com/api/sns/v\d/note/collection/list\S*',
        # r'https?://edith.xiaohongshu.com/api/sns/v\d/user/collect_filter',
        # r'https?://edith.xiaohongshu.com/api/sns/v\d/note/user/posted\S*',
    ]

addons = [
    ImageFeedFilter(set_request),
    CommentListFilter(set_request),
    BlockURLs(get_block_pattern_list())
]

if __name__ == "__main__":
    multiprocessing.freeze_support()

    mitm_proc = multiprocessing.Process(
        target=run_mitm,
    )
    mitm_proc.start()

    run_telegram_bot()