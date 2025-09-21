import os
import re
import json
import time
import asyncio # type: ignore
import logging
import requests
import traceback
import subprocess
import paramiko
from datetime import datetime, timedelta, timezone
from pprint import pformat
from uuid import uuid4
from dotenv import load_dotenv
from urllib.parse import unquote, urljoin, parse_qs, urlparse
from typing import Any

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
from telegraph.aio import Telegraph # type: ignore

# Load environment variables from .env file
load_dotenv()

logging_file = os.path.join("log", f"{datetime.now().strftime('%Y%m%d%H%M%S')}.log")
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

class Note:
    def __init__(
            self,
            note_data: dict[str, list[dict[str, Any]]],
            comment_list_data: dict[str, list[dict[str, Any]]],
            live: bool = False,
            telegraph: bool = False,
            inline: bool = False,
    ) -> None:
        self.telegraph = telegraph
        logging.warning(f"Note telegraph? {self.telegraph}")
        self.inline = inline
        logging.warning(f"Note inline? {self.inline}")
        self.live = live
        logging.warning(f"Note live? {self.live}")
        if not note_data['data']:
            raise Exception("Note data not found!")
        self.user: dict[str, str | int] = {
            'id': note_data['data'][0]['user']['id'],
            'name': note_data['data'][0]['user']['name'],
            'red_id': note_data['data'][0]['user']['red_id'],
            # 'image': note_data['data'][0]['user']['image'],
            # 'nickname': note_data['data'][0]['user']['nickname'],
            # 'userid': note_data['data'][0]['user']['userid'],
        }
        # self.text_language_code = note_data['data'][0]['note_list'][0]['text_language_code']

        self.title: str = note_data['data'][0]['note_list'][0]['title'] if note_data['data'][0]['note_list'][0]['title'] else f"Untitled Note by @{self.user['name']} ({self.user['red_id']})"
        self.type: str = note_data['data'][0]['note_list'][0]['type']

        self.raw_desc = replace_redemoji_with_emoji(note_data['data'][0]['note_list'][0]['desc'])
        logging.warning(f"Note raw_desc\n\n {self.raw_desc}")
        self.desc = re.sub(
            r'(?P<tag>#\S+?)\[[⺀-⺙⺛-⻳⼀-⿕々〇〡-〩〸-〺〻㐀-䶵一-鿃豈-鶴侮-頻並-龎]+\]#',
            r' \g<tag> ',
            self.raw_desc
        )
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
            self.length = len(self.desc + self.title + self.first_comment)
        else:
            self.length = len(self.desc + self.title)

        self.images_list = []
        if 'images_list' in note_data['data'][0]['note_list'][0] and 'video' not in note_data['data'][0]['note_list'][0]:
            for each in note_data['data'][0]['note_list'][0]['images_list']:
                self.images_list.append(
                    {
                        'live': False,
                        'url': remove_image_url_params(each['original']),
                        'thumbnail': remove_image_url_params(each['url_multi_level']['low'])
                    }
                )
                if 'live_photo' in each and self.live:
                    logging.warning(f'live photo found in {each}')
                    live_urls = []
                    for s in each['live_photo']['media']['stream']:
                        if each['live_photo']['media']['stream'][s]:
                            for ss in each['live_photo']['media']['stream'][s]:
                                live_urls.append(ss['backup_urls'][0] if ss['backup_urls'] else ss['master_url'])
                    if len(live_urls) > 0:
                        self.images_list.append(
                            {'live': True, 'url': live_urls[0], 'thumbnail': remove_image_url_params(each['url'])}
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
        for lines in self.desc.split('\n'):
            line_html = tg_msg_escape_html(lines)
            html += f'<p>{line_html}</p>'
        html += f'<h4>👤 <a href="https://www.xiaohongshu.com/user/profile/{self.user["id"]}"> @{self.user["name"]} ({self.user["red_id"]})</a></h4>'
        html += f'<p>{get_time_emoji(self.time)} {convert_timestamp_to_timestr(self.time)}</p>'
        html += f'<p>❤️ {self.liked_count} ⭐ {self.collected_count} 💬 {self.comments_count} 🔗 {self.shared_count}</p>'
        if hasattr(self, 'ip_location'):
            ipaddr_html = tg_msg_escape_html(self.ip_location)
        else:
            ipaddr_html = 'Unknown IP Address'
        html += f'<p>📍 {ipaddr_html}</p>'
        html += '<br><i>via</i> <a href="https://t.me/xhsfeedbot">@xhsfeedbot</a>'
        self.html = html
        logging.warning(f"HTML generated, \n\n{self.html}\n\n")
        return self.html
    
    def make_block_quotation(self, text: str) -> str:
        lines = [f'>{tg_msg_escape_markdown_v2(line)}' for line in text.split('\n') if len(line) > 0 and bool(re.findall(r'\S+', line))]
        if len(lines) > 3:
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

    async def to_telegram_message(self, preview: bool = False) -> str:
        message = ''
        message += f'*『[{tg_msg_escape_markdown_v2(self.title)}]({self.url})』*\n\n'
        if preview:
            message += f'{self.make_block_quotation(self.desc[:555] + '...')}\n\n\n'
            if hasattr(self, 'telegraph_url'):
                message += f'📝 [View more via Telegraph]({tg_msg_escape_markdown_v2(self.telegraph_url)})\n\n'
            else:
                message += f'📝 [View more via Telegraph]({tg_msg_escape_markdown_v2(await self.to_telegraph())})\n\n'
        else:
            message += f'{self.make_block_quotation(self.desc)}\n\n\n'
            if hasattr(self, 'telegraph_url'):
                message += f'📝 [Telegraph]({tg_msg_escape_markdown_v2(self.telegraph_url)})\n\n'
            elif self.telegraph:
                message += f'📝 [Telegraph]({tg_msg_escape_markdown_v2(await self.to_telegraph())})\n\n'
        message += f'[@{tg_msg_escape_markdown_v2(self.user["name"])} \\({tg_msg_escape_markdown_v2(self.user["red_id"])}\\)](https://www.xiaohongshu.com/user/profile/{self.user["id"]})\n'
        if type(self.liked_count) == str:
            like_html = tg_msg_escape_markdown_v2(self.liked_count)
        else:
            like_html = str(self.liked_count)
        if type(self.collected_count) == str:
            collected_html = tg_msg_escape_markdown_v2(self.collected_count)
        else:
            collected_html = self.collected_count
        if type(self.comments_count) == str:
            comments_html = tg_msg_escape_markdown_v2(self.comments_count)
        else:
            comments_html = self.comments_count
        if type(self.shared_count) == str:
            shared_html = tg_msg_escape_markdown_v2(self.shared_count)
        else:
            shared_html = self.shared_count
        message += f'>❤️ {like_html} ⭐ {collected_html} 💬 {comments_html} 🔗 {shared_html}'
        message += f'\n>{get_time_emoji(self.time)} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(self.time))}\n'
        if hasattr(self, 'ip_location'):
            ip_html = tg_msg_escape_markdown_v2(self.ip_location)
        else:
            ip_html = 'Unknown IP Address'
        message += f'>📍 {ip_html}\n\n'
        comment_tag = ''
        if hasattr(self, 'first_comment_tag_v2'):
            if self.first_comment_tag_v2:
                comment_tag = f'[{self.first_comment_tag_v2}]'
        message += self.make_block_quotation(
            f'🗨️ @{self.comment_user} {comment_tag}\n'
            f'{self.first_comment}'
        ) if self.first_comment else ''
        message += '\n_via_ @xhsfeedbot'
        self.message = message
        logging.warning(f"Telegram message generated, \n\n{self.message}\n\n")
        return message

    async def to_short_preview(self):
        message = ''
        message += f'*『[{tg_msg_escape_markdown_v2(self.title)}]({self.url})』*\n\n'
        message += f'{self.make_block_quotation(self.desc[:166] + '...')}\n\n'
        if hasattr(self, 'telegraph_url'):
            message += f'📝 [View more via Telegraph]({tg_msg_escape_markdown_v2(self.telegraph_url)})\n\n'
        else:
            message += f'📝 [View more via Telegraph]({tg_msg_escape_markdown_v2(await self.to_telegraph())})\n\n'
        message += f'[@{tg_msg_escape_markdown_v2(self.user["name"])} \\({tg_msg_escape_markdown_v2(self.user["red_id"])}\\)](https://www.xiaohongshu.com/user/profile/{self.user["id"]})\n\n'
        if type(self.liked_count) == str:
            like_html = tg_msg_escape_markdown_v2(self.liked_count)
        else:
            like_html = self.liked_count
        if type(self.collected_count) == str:
            collected_html = tg_msg_escape_markdown_v2(self.collected_count)
        else:
            collected_html = self.collected_count
        if type(self.comments_count) == str:
            comments_html = tg_msg_escape_markdown_v2(self.comments_count)
        else:
            comments_html = self.comments_count
        if type(self.shared_count) == str:
            shared_html = tg_msg_escape_markdown_v2(self.shared_count)
        else:
            shared_html = self.shared_count
        message += f'>❤️ {like_html} ⭐ {collected_html} 💬 {comments_html} 🔗 {shared_html}'
        message += f'\n>{get_time_emoji(self.time)} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(self.time))}\n'
        if hasattr(self, 'ip_location'):
            ip_html = tg_msg_escape_markdown_v2(self.ip_location)
        else:
            ip_html = 'Unknown IP Address'
        message += f'>📍 {ip_html}'
        message += '\n_via_ @xhsfeedbot'
        self.short_preview = message
        logging.warning(f"Short preview generated, {self.short_preview}")
        return message

    async def to_media_group(self, inline: bool) -> list:
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
                        media=[InputMediaPhoto(requests.get(p.media).content) if type(p.media) == str and 'imageView' in p.media else InputMediaVideo(requests.get(p.media).content) if type(p.media) == str else p for p in part],
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
                        media=[InputMediaPhoto(requests.get(p.media).content) if type(p.media) == str and 'imageView' in p.media else InputMediaVideo(requests.get(p.media).content) if type(p.media) == str else p for p in part],
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

def open_note(noteId: str, connected_ssh_client=None):
    if os.getenv('TARGET_DEVICE_TYPE') == '0':
        subprocess.run(["adb", "shell", "am", "start", "-d", f"xhsdiscover://item/{noteId}"])
    elif os.getenv('TARGET_DEVICE_TYPE') == '1':
        if os.getenv('LOCAL_DEVICE_TYPE') == '0':
            ssh_stdin, ssh_stdout, ssh_stderr = connected_ssh_client.exec_command(
                f"uiopen xhsdiscover://item/{noteId}"
            )
        else:
            subprocess.run(["uiopen", f"xhsdiscover://item/{noteId}"])

def home_page(connected_ssh_client=None):
    if os.getenv('TARGET_DEVICE_TYPE') == '0':
        subprocess.run(["adb", "shell", "am", "start", "-d", "xhsdiscover://home"])
    elif os.getenv('TARGET_DEVICE_TYPE') == '1':
        if os.getenv('LOCAL_DEVICE_TYPE') == '0':
            ssh_stdin, ssh_stdout, ssh_stderr = connected_ssh_client.exec_command(
                "uiopen xhsdiscover://home"
            )
        else:
            subprocess.run(["uiopen", "xhsdiscover://home"])

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
        xhslink = [u for u in urls if 'xhslink.com' in u][0]
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
    if os.getenv('TARGET_DEVICE_TYPE') == '1' and os.getenv('LOCAL_DEVICE_TYPE') != '1':
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            os.getenv('SSH_IP'),
            port=int(os.getenv('SSH_PORT')),
            username=os.getenv('SSH_USERNAME'),
            password=os.getenv('SSH_PASSWORD')
        )
    else:
        ssh = None
    open_note(noteId, ssh)
    time.sleep(3)

    try:
        note_data = requests.get(
            f"http://127.0.0.1:5001/get_note/{noteId}"
        ).json()
        with open(os.path.join("data", f"note_data-{noteId}.json"), "w", encoding='utf-8') as f:
            json.dump(note_data, f, indent=4, ensure_ascii=False)
            f.close()

        try:
            comment_list_data = requests.get(
                f"http://127.0.0.1:5001/get_comment_list/{noteId}"
            ).json()
            with open(os.path.join("data", f"comment_list_data-{noteId}.json"), "w", encoding='utf-8') as f:
                json.dump(comment_list_data, f, indent=4, ensure_ascii=False)
                f.close()
        except:
            comment_list_data = None
    except:
        ssh.close()
        logging.error(traceback.format_exc())
        return

    telegraph = bool(re.search(r"[^\S]+-t(?!\S)", update.message.text))
    live = bool(re.search(r"[^\S]+-l(?!\S)", update.message.text))
    try:
        note = Note(
            note_data['data'],
            comment_list_data=comment_list_data['data'],
            live=live,
            telegraph=telegraph,
            inline=False
        )
        await note.initialize()
        home_page(ssh)
        await note.send_as_telegram_message(context.bot, update.effective_chat.id, update.message.message_id)
        ssh.close()
    except:
        home_page(ssh)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="An error occurred while processing your request."
        )
        ssh.close()
        logging.error(traceback.format_exc())

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
        # .proxy(os.getenv('BOT_PROXY_URL'))\
        # .get_updates_proxy(os.getenv('BOT_PROXY_URL'))\

    start_handler = CommandHandler("start", start)
    application.add_handler(start_handler)

    application.add_error_handler(error_handler)

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


if __name__ == "__main__":
    run_telegram_bot()
