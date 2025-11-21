import os
import sys
import re
import json
import time
import asyncio # type: ignore
import logging
import psutil
import requests
import traceback
import subprocess
import paramiko
import threading
from datetime import datetime, timedelta, timezone
from pprint import pformat
from dotenv import load_dotenv
from urllib.parse import unquote, urljoin, parse_qs, urlparse
from typing import Any
from uuid import uuid4
from io import BytesIO

from telegram.ext import (
    filters,
    MessageHandler,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler
)
from telegram import (
    InputTextMessageContent,
    Update,
    Bot,
    MessageEntity,
    InputMediaPhoto,
    InputMediaVideo,
    LinkPreviewOptions,
    InlineQueryResultArticle,
    Message
)
from telegram.error import (
    NetworkError,
    BadRequest
)
from telegram.constants import (
    ParseMode,
    ChatAction,
)
from telegraph.aio import Telegraph # type: ignore
from PIL import Image
from pyzbar.pyzbar import decode # pyright: ignore[reportUnknownVariableType, reportMissingTypeStubs]

# Load environment variables from .env file
load_dotenv()

logging_file = os.path.join("log", f"{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.log")

# Configure logging to only show messages from your script
logging.basicConfig(
    handlers=[
        logging.FileHandler(
            filename=logging_file,
            encoding="utf-8",
            mode="w+",
        ),
        logging.StreamHandler()
    ],
    format="%(asctime)s.%(msecs)03d %(levelname)s %(module)s: %(message)s",
    datefmt="%F %A %T",
    level=logging.DEBUG
)

# Create your own logger for your bot messages
bot_logger = logging.getLogger("xhsfeedbot")
bot_logger.setLevel(logging.DEBUG)

# Global variables for network monitoring
last_successful_request = time.time()
network_timeout_threshold = 120  # 2 minutes without successful requests triggers restart
is_network_healthy = True

# Concurrency control
max_concurrent_requests = 5  # Maximum number of concurrent note processing
processing_semaphore = asyncio.Semaphore(max_concurrent_requests)

# Whitelist functionality
whitelist_enabled = os.getenv('WHITELIST_ENABLED', 'false').lower() == 'true'
bot_logger.debug(f"Whitelist enabled: {whitelist_enabled}")
whitelisted_users = []

def load_whitelist():
    """Load whitelisted user IDs from environment variable or file"""
    global whitelisted_users
    
    # Try to load from environment variable first (comma-separated)
    whitelist_env = os.getenv('WHITELISTED_USER_IDS', '')
    if whitelist_env:
        try:
            whitelisted_users = [int(uid.strip()) for uid in whitelist_env.split(',') if uid.strip()]
            bot_logger.info(f"Loaded {len(whitelisted_users)} whitelisted users from environment variable")
        except ValueError as e:
            bot_logger.error(f"Error parsing WHITELISTED_USER_IDS: {e}")
    
    # Try to load from whitelist.json file if it exists
    whitelist_file = 'whitelist.json'
    if os.path.exists(whitelist_file):
        try:
            with open(whitelist_file, 'r', encoding='utf-8') as f:
                whitelist_data: dict[str, list[int]] = json.load(f)
                if 'users' in whitelist_data:
                    users_list: list[int] = whitelist_data['users']
                    whitelisted_users.extend(users_list)
                # Remove duplicates
                whitelisted_users = list(set(whitelisted_users))
                bot_logger.info(f"Loaded whitelist from {whitelist_file}: {len(whitelisted_users)} users")
        except Exception as e:
            bot_logger.error(f"Error loading whitelist from {whitelist_file}: {e}")

def is_user_whitelisted(user_id: int | None) -> bool:
    """Check if a user is whitelisted"""
    if user_id is None:
        return False
    if not whitelist_enabled:
        return True
    return user_id in whitelisted_users

# Load whitelist at startup
load_whitelist()

with open('redtoemoji.json', 'r', encoding='utf-8') as f:
    redtoemoji = json.load(f)
    f.close()

URL_REGEX = r"""(?i)\b((?:https?:(?:/{1,3}|[a-z0-9%])|[a-z0-9.\-]+[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)/)(?:[^\s()<>{}\[\]]+|\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\))+(?:\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\)|[^\s`!()\[\]{};:\'\".,<>?«»“”‘’])|(?:(?<!@)[a-z0-9]+(?:[.\-][a-z0-9]+)*[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)\b/?(?!@)))"""

def replace_redemoji_with_emoji(text: str) -> str:
    for red_emoji, emoji in redtoemoji.items():
        text = text.replace(red_emoji, emoji)
    return text

def check_network_connectivity() -> bool:
    """Check if network connectivity is available by testing multiple endpoints"""
    test_urls = [
        "https://api.telegram.org",
        "https://www.google.com", 
        "https://1.1.1.1"
    ]
    
    for url in test_urls:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return True
        except:
            continue
    return False

def update_network_status(success: bool = True):
    """Update the global network status tracking"""
    global last_successful_request, is_network_healthy
    if success:
        last_successful_request = time.time()
        is_network_healthy = True
    else:
        current_time = time.time()
        if current_time - last_successful_request > network_timeout_threshold:
            is_network_healthy = False

def network_monitor():
    """Background network monitoring function"""
    global is_network_healthy
    while True:
        try:
            time.sleep(15)  # Check every 15 seconds
            current_time = time.time()
            if current_time - last_successful_request > network_timeout_threshold:
                bot_logger.warning(f"No successful network requests for {network_timeout_threshold} seconds")
                if not check_network_connectivity():
                    bot_logger.error("Network connectivity test failed - triggering restart")
                    is_network_healthy = False
                    restart_script()
                    break
        except Exception as e:
            bot_logger.error(f"Network monitor error: {e}")
            time.sleep(10)

class Note:
    def __init__(
            self,
            note_data: dict[str, Any],
            comment_list_data: dict[str, Any],
            live: bool = False,
            telegraph: bool = False,
            with_xsec_token: bool = False,
            original_xsec_token: str = '',
            with_full_data: bool = False,
            telegraph_account: Telegraph | None = None,
            anchorCommentId: str = ''
    ) -> None:
        self.telegraph_account = telegraph_account
        self.telegraph = telegraph
        self.live = live
        if not note_data['data']:
            raise Exception("Note data not found!")
        self.user: dict[str, str | int] = {
            'id': note_data['data'][0]['user']['id'],
            'name': note_data['data'][0]['user']['name'],
            'red_id': note_data['data'][0]['user']['red_id'],
            'image': get_clean_url(note_data['data'][0]['user']['image']),
        }
        # self.text_language_code = note_data['data'][0]['note_list'][0]['text_language_code']

        self.title: str = note_data['data'][0]['note_list'][0]['title'] if note_data['data'][0]['note_list'][0]['title'] else f"Untitled Note"
        self.type: str = note_data['data'][0]['note_list'][0]['type']

        self.raw_desc = replace_redemoji_with_emoji(note_data['data'][0]['note_list'][0]['desc'])
        bot_logger.debug(f"Note raw_desc\n\n {self.raw_desc}")
        self.desc = re.sub(
            r'(?P<tag>#\S+?)\[\S+\]#',
            r'\g<tag> ',
            self.raw_desc
        )
        self.time = note_data['data'][0]['note_list'][0]['time']
        self.ip_location = note_data['data'][0]['note_list'][0]['ip_location']\
            if 'ip_location' in note_data['data'][0]['note_list'][0] else 'Unknown'
        self.collected_count = note_data['data'][0]['note_list'][0]['collected_count']
        self.comments_count = note_data['data'][0]['note_list'][0]['comments_count']
        self.shared_count = note_data['data'][0]['note_list'][0]['shared_count']
        self.liked_count = note_data['data'][0]['note_list'][0]['liked_count']
        # self.last_update_time = note_data['data'][0]['note_list'][0]['last_update_time']
        self.comments_with_context: list[dict[str, Any]] = []
        if anchorCommentId:
            self.comments_with_context = extract_anchor_comment_id(comment_list_data['data'])
            bot_logger.debug(f"Comments with context extracted for anchorCommentId {anchorCommentId}:\n{pformat(self.comments_with_context)}")
        self.length: int = len(self.desc + self.title)

        self.tags: list[str] = [tag['name'] for tag in note_data['data'][0]['note_list'][0]['hash_tag']]
        self.tag_string: str = ' '.join([f"#{tag}" for tag in self.tags])

        self.thumbnail = note_data['data'][0]['note_list'][0]['share_info']['image']
        self.images_list: list[dict[str, str]] = []
        if 'images_list' in note_data['data'][0]['note_list'][0]:
            for each in note_data['data'][0]['note_list'][0]['images_list']:
                if 'live_photo' in each and self.live:
                    bot_logger.debug(f'live photo found in {each}')
                    live_urls: list[str] = []
                    for s in each['live_photo']['media']['stream']:
                        if each['live_photo']['media']['stream'][s]:
                            for ss in each['live_photo']['media']['stream'][s]:
                                live_urls.append(ss['backup_urls'][0] if ss['backup_urls'] else ss['master_url'])
                    if len(live_urls) > 0:
                        self.images_list.append(
                            {'live': 'True', 'url': live_urls[0], 'thumbnail': remove_image_url_params(each['url'])}
                        )
                original_img_url = each['original']
                if re.findall(r'sns-na-i\d.xhscdn.com', original_img_url):
                    original_img_url = re.sub(r'sns-na-i\d.xhscdn.com', 'sns-na-i6.xhscdn.com', original_img_url)
                self.images_list.append(
                    {
                        'live': '',
                        'url': remove_image_url_params(original_img_url),
                        'thumbnail': remove_image_url_params(each['url_multi_level']['low'])
                    }
                )
        bot_logger.debug(f"Images found: {self.images_list}")
        self.url = get_clean_url(note_data['data'][0]['note_list'][0]['share_info']['link'])
        self.with_xsec_token = with_xsec_token
        if with_xsec_token:
            if not original_xsec_token:
                parsed_url = urlparse(str(note_data['data'][0]['note_list'][0]['share_info']['link']))
                self.xsec_token = parse_qs(parsed_url.query)['xsec_token'][0]
            else:
                self.xsec_token = original_xsec_token
            self.url += f"?xsec_token={self.xsec_token}"
        self.noteId = re.findall(r"[a-z0-9]{24}", self.url)[0]
        self.video_url = ''
        if 'video' in note_data['data'][0]['note_list'][0]:
            self.video_url = note_data['data'][0]['note_list'][0]['video']['url']
            if not re.findall(r'sign=[0-9a-z]+', self.video_url):
                self.video_url = re.sub(r'[0-9a-z\-]+\.xhscdn\.(com|net)', 'sns-bak-v1.xhscdn.com', self.video_url)
        if telegraph:
            self.to_html()
        tgmsg_result = self.to_telegram_message(preview=bool(self.length >= 666))
        bot_logger.debug(f"tgmsg_result: {tgmsg_result}\nlen: {self.length}, preview? = {bool(self.length >= 666)}")
        media_group_result = self.to_media_group()
        bot_logger.debug(f"media_group_result: {media_group_result}")

    async def initialize(self) -> None:
        if self.telegraph:
            await self.to_telegraph()
        self.short_preview = ''

    def to_dict(self) -> dict[str, str | int | Any]:
        return {
            'user': self.user,
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
            html += f'<blockquote>{line_html}</blockquote>'
        html += f'<h4>👤 <a href="https://www.xiaohongshu.com/user/profile/{self.user["id"]}{f"?xsec_token={self.xsec_token}" if self.with_xsec_token else ""}"> @{self.user["name"]} ({self.user["red_id"]})</a></h4>'
        html += f'<img src="{self.user["image"]}"></img>'
        html += f'<p>{get_time_emoji(self.time)} {convert_timestamp_to_timestr(self.time)}</p>'
        html += f'<p>❤️ {self.liked_count} ⭐ {self.collected_count} 💬 {self.comments_count} 🔗 {self.shared_count}</p>'
        if hasattr(self, 'ip_location'):
            ipaddr_html = tg_msg_escape_html(self.ip_location)
        else:
            ipaddr_html = 'Unknown'
        html += f'<p>📍 {ipaddr_html}</p>'
        if self.comments_with_context:
            html += '<hr>'
            for i, comment in enumerate(self.comments_with_context):
                html += f'<h4>💬 <a href="https://www.xiaohongshu.com/discovery/item/{self.noteId}?anchorCommentId={comment["id"]}{f"&xsec_token={self.xsec_token}" if self.with_xsec_token else ""}">Comment</a></h4>'
                if 'target_comment' in comment:
                    html += f'<p>↪️ <a href="https://www.xiaohongshu.com/user/profile/{comment["target_comment"]["user"]["userid"]}{f"?xsec_token={self.xsec_token}" if self.with_xsec_token else ""}"> @{comment["target_comment"]["user"]["nickname"]} ({comment["target_comment"]["user"]["red_id"]})</a></p>'
                html += f'<blockquote>{tg_msg_escape_html(replace_redemoji_with_emoji(comment["content"]))}</blockquote>'
                for pic in comment['pictures']:
                    if 'mp4' in pic:
                        html += f'<video src="{pic}"></video>'
                    else:
                        html += f'<img src="{pic}"></img>'
                if comment.get('audio_url', ''):
                    html += f'<blockquote><a href="{comment["audio_url"]}">🎤 Voice</a></blockquote>'
                html += f'<p>❤️ {comment["like_count"]} 💬 {comment["sub_comment_count"]} 📍 {tg_msg_escape_html(comment["ip_location"])} {get_time_emoji(comment["time"])} {convert_timestamp_to_timestr(comment["time"])}</p>'
                html += f'<p>👤 <a href="https://www.xiaohongshu.com/user/profile/{comment["user"]["userid"]}{f"?xsec_token={self.xsec_token}" if self.with_xsec_token else ""}"> @{comment["user"]["nickname"]} ({comment["user"]["red_id"]})</a></p>'
                if i != len(self.comments_with_context) - 1:
                    html += f'<hr>'
        self.html = html
        bot_logger.debug(f"HTML generated, \n\n{self.html}\n\n")
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
        if not self.telegraph_account:
            self.telegraph_account = Telegraph()
            await self.telegraph_account.create_account( # type: ignore
                short_name='@xhsfeedbot',
            )
        response = await self.telegraph_account.create_page( # type: ignore
            title=f"{self.title} @{self.user['name']}",
            author_name=f'@{self.user["name"]} ({self.user["red_id"]})',
            author_url=f"https://www.xiaohongshu.com/user/profile/{self.user['id']}",
            html_content=self.html,
        )
        self.telegraph_url = response['url']
        bot_logger.debug(f"Generated Telegraph URL: {self.telegraph_url}")
        return self.telegraph_url

    async def to_telegram_message(self, preview: bool = False) -> str:
        message = ''
        message += f'*『[{tg_msg_escape_markdown_v2(self.title)}]({self.url})』*'
        if preview:
            message += f'\n{self.make_block_quotation(self.desc[:555] + '...')}\n'
            if hasattr(self, 'telegraph_url'):
                message += f'\n📝 [View more via Telegraph]({tg_msg_escape_markdown_v2(self.telegraph_url)})\n'
            else:
                message += f'\n📝 [View more via Telegraph]({tg_msg_escape_markdown_v2(await self.to_telegraph())})\n'
        else:
            message += f'\n{self.make_block_quotation(self.desc)}\n' if self.desc else '\n'
            if hasattr(self, 'telegraph_url'):
                message += f'\n📝 [Telegraph]({tg_msg_escape_markdown_v2(self.telegraph_url)})\n'
            elif self.telegraph:
                message += f'\n📝 [Telegraph]({tg_msg_escape_markdown_v2(await self.to_telegraph())})\n'
        message += f'\n[@{tg_msg_escape_markdown_v2(self.user["name"])} \\({tg_msg_escape_markdown_v2(self.user["red_id"])}\\)](https://www.xiaohongshu.com/user/profile/{self.user["id"]})\n'
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
            ip_html = 'Unknown'
        message += f'>📍 {ip_html}'
        self.message = message
        bot_logger.debug(f"Telegram message generated, \n\n{self.message}\n\n")
        return message

    async def to_media_group(self) -> list[list[InputMediaPhoto | InputMediaVideo]]:
        self.medien: list[InputMediaPhoto | InputMediaVideo] = []
        for _, imgs in enumerate(self.images_list):
            if not imgs['live']:
                self.medien.append(
                    InputMediaPhoto(imgs['url'])
                )
            # else:
            #     self.medien.append(
            #         InputMediaVideo(
            #             requests.get(imgs['url']).content
            #         )
            #     )
        if self.video_url:
            video_data = requests.get(self.video_url).content
            self.medien.append(
                InputMediaVideo(video_data)
            )
        self.medien_parts = [self.medien[i:i + 10] for i in range(0, len(self.medien), 10)]
        return self.medien_parts

    async def send_as_telegram_message(self, bot: Bot, chat_id: int, reply_to_message_id: int = 0, status: Message | None = None, status_md: str | None = None) -> tuple[Message | None, str | None]:
        sent_message = None
        if status and status_md is not None:
            status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Sending media group message`"
            await status.edit_text(
                status_md,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        if not hasattr(self, 'medien_parts'):
            if status and status_md is not None:
                status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Preparing media group`"
                await status.edit_text(
                    status_md,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            self.medien_parts: list[list[InputMediaPhoto | InputMediaVideo]] = await self.to_media_group()
        for i, part in enumerate(self.medien_parts):
            if status and status_md is not None:
                status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Sending media group part {i + 1} of {len(self.medien_parts)}`"
                await status.edit_text(
                    status_md,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                if self.video_url:
                    await bot.send_chat_action(
                        chat_id=chat_id,
                        action=ChatAction.UPLOAD_VIDEO,
                    )
                else:
                    await bot.send_chat_action(
                        chat_id=chat_id,
                        action=ChatAction.UPLOAD_PHOTO,
                    )
            if i != len(self.medien_parts) - 1:
                try:
                    sent_message = await bot.send_media_group(
                        chat_id=chat_id,
                        reply_to_message_id=reply_to_message_id,
                        media=part,
                        disable_notification=True
                    )
                except:
                    bot_logger.error(f"Failed to send media group:\n{traceback.format_exc()}")
                    if status and status_md is not None:
                        status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Retrying with downloaded media`"
                        await status.edit_text(
                            status_md,
                            parse_mode=ParseMode.MARKDOWN_V2,
                        )
                    media: list[InputMediaPhoto | InputMediaVideo] = []
                    for _, p in enumerate(part):
                        if type(p.media) == str and '.mp4' not in p.media:
                            media_content = requests.get(p.media).content
                            if status and status_md is not None:
                                status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Downloaded media {_ + 1} of {len(part)}`"
                                await status.edit_text(
                                    status_md,
                                    parse_mode=ParseMode.MARKDOWN_V2,
                                )
                            media.append(InputMediaPhoto(media_content))
                        elif self.video_url and type(p.media) != str:
                            media.append(p)
                    if status and status_md is not None:
                        status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Retrying upload of media group part {i + 1} of {len(self.medien_parts)}`"
                        await status.edit_text(
                            status_md,
                            parse_mode=ParseMode.MARKDOWN_V2,
                        )
                    sent_message = await bot.send_media_group(
                        chat_id=chat_id,
                        reply_to_message_id=reply_to_message_id,
                        media=media,
                    )
            else:
                try:
                    sent_message = await bot.send_media_group(
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
                        disable_notification=True
                    )
                except:
                    bot_logger.error(f"Failed to send media group:\n{pformat(part)}\n{traceback.format_exc()}")
                    if status and status_md is not None:
                        status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Retrying with downloaded media`"
                        await status.edit_text(
                            status_md,
                            parse_mode=ParseMode.MARKDOWN_V2,
                        )
                    media: list[InputMediaPhoto | InputMediaVideo] = []
                    for _, p in enumerate(part):
                        if type(p.media) == str and '.mp4' not in p.media:
                            media_content = requests.get(p.media).content
                            if status and status_md is not None:
                                status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Downloaded media {_ + 1} of {len(part)}`"
                                await status.edit_text(
                                    status_md,
                                    parse_mode=ParseMode.MARKDOWN_V2,
                                )
                            media.append(InputMediaPhoto(media_content))
                        elif self.video_url and type(p.media) != str:
                            media.append(p)
                    bot_logger.debug(f"Retrying with downloaded media:\n{pformat(media)}")
                    if status and status_md is not None:
                        status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Retrying upload of media group part {i + 1} of {len(self.medien_parts)}`"
                        await status.edit_text(
                            status_md,
                            parse_mode=ParseMode.MARKDOWN_V2,
                        )
                    sent_message = await bot.send_media_group(
                        chat_id=chat_id,
                        reply_to_message_id=reply_to_message_id,
                        media=media,
                        caption=self.message if hasattr(
                            self,
                            'message'
                        ) else await self.to_telegram_message(
                            preview=bool(self.length >= 666)
                        ),
                        parse_mode=ParseMode.MARKDOWN_V2,
                    )
        if not sent_message:
            bot_logger.error("No message was sent!")
            return status, status_md
        reply_id: int = sent_message[0].message_id
        comment_id_to_message_id: dict[str, Any] = {}
        if self.comments_with_context:
            if status and status_md is not None:
                status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Start sending comments`"
                await status.edit_text(
                    status_md,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            for _, comment in enumerate(self.comments_with_context):
                if status and status_md is not None:
                    status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Sending comment {_ + 1} of {len(self.comments_with_context)}`"
                    await status.edit_text(
                        status_md,
                        parse_mode=ParseMode.MARKDOWN_V2,
                    )
                comment_text = ''
                comment_text += f'💬 [Comment](https://www.xiaohongshu.com/discovery/item/{self.noteId}?anchorCommentId={comment["id"]}{f"&xsec_token={self.xsec_token}" if self.with_xsec_token else ""})'
                if 'target_comment' in comment:
                    comment_text += f'\n↪️ [@{tg_msg_escape_markdown_v2(comment["target_comment"]["user"]["nickname"])} \\({tg_msg_escape_markdown_v2(comment["target_comment"]["user"]["red_id"])}\\)](https://www.xiaohongshu.com/user/profile/{comment["target_comment"]["user"]["userid"]}{f"?xsec_token={self.xsec_token}" if self.with_xsec_token else ""})\n'
                else:
                    comment_text += '\n'
                comment_text += f'{self.make_block_quotation(replace_redemoji_with_emoji(comment["content"]))}\n'
                comment_text += f'❤️ {comment["like_count"]} 💬 {comment["sub_comment_count"]} 📍 {tg_msg_escape_markdown_v2(comment["ip_location"])} {get_time_emoji(comment["time"])} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(comment["time"]))}\n'
                comment_text += f'👤 [@{tg_msg_escape_markdown_v2(comment["user"]["nickname"])} \\({tg_msg_escape_markdown_v2(comment["user"]["red_id"])}\\)](https://www.xiaohongshu.com/user/profile/{comment["user"]["userid"]}{f"?xsec_token={self.xsec_token}" if self.with_xsec_token else ""})'
                bot_logger.debug(f"Sending comment:\n{comment_text}")
                if 'target_comment' in comment and _ > 0:
                    reply_id = comment_id_to_message_id[comment['target_comment']['id']].message_id
                if comment['pictures']:
                    await bot.send_chat_action(
                        chat_id=chat_id,
                        action=ChatAction.UPLOAD_PHOTO
                    )
                    # 1. Split pictures into chunks of 10
                    picture_chunks = [comment['pictures'][i:i + 10] for i in range(0, len(comment['pictures']), 10)]
                    for i, chunk in enumerate(picture_chunks):
                        media: list[InputMediaPhoto | InputMediaVideo] = []
                        for pic in chunk:
                            if 'mp4' not in pic:
                                if status and status_md is not None:
                                    status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Downloading picture {_ + 1} of {len(comment['pictures'])}`"
                                    await status.edit_text(
                                        status_md,
                                        parse_mode=ParseMode.MARKDOWN_V2,
                                    )
                                media_data = requests.get(pic).content
                                media.append(InputMediaPhoto(media_data))
                        if status and status_md is not None:
                            status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Uploading picture chunk {i + 1} of {len(picture_chunks)}`"
                            await status.edit_text(
                                status_md,
                                parse_mode=ParseMode.MARKDOWN_V2,
                            )
                        # 2. Check if this is the LAST chunk
                        if i == len(picture_chunks) - 1:
                            # Send the last chunk WITH the caption
                            sent_messages = await bot.send_media_group(
                                chat_id=chat_id,
                                reply_to_message_id=reply_id,
                                media=media,
                                caption=comment_text,
                                parse_mode=ParseMode.MARKDOWN_V2,
                                disable_notification=True
                            )
                            # 3. Store ONLY the first message object so .message_id works later
                            comment_id_to_message_id[comment['id']] = sent_messages[0]
                        else:
                            # Send intermediate chunks WITHOUT caption
                            await bot.send_media_group(
                                chat_id=chat_id,
                                reply_to_message_id=reply_id,
                                media=media,
                                disable_notification=True
                            )
                elif comment.get('audio_url', ''):
                    await bot.send_chat_action(
                        chat_id=chat_id,
                        action=ChatAction.RECORD_VOICE
                    )
                    # Download audio
                    if status and status_md is not None:
                        status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Downloading audio for comment {_ + 1} of {len(self.comments_with_context)}`"
                        await status.edit_text(
                            status_md,
                            parse_mode=ParseMode.MARKDOWN_V2,
                        )
                    r = requests.get(comment['audio_url'])
                    audio_bytes = r.content

                    # Convert to Ogg/Opus
                    if status and status_md is not None:
                        status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Converting to Ogg/Opus for comment {_ + 1} of {len(self.comments_with_context)}`"
                        await status.edit_text(
                            status_md,
                            parse_mode=ParseMode.MARKDOWN_V2,
                        )
                    ogg_bytes = convert_to_ogg_opus_pipe(audio_bytes)
                    if status and status_md is not None:
                        status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Sending voice for comment {_ + 1} of {len(self.comments_with_context)}`"
                        await status.edit_text(
                            status_md,
                            parse_mode=ParseMode.MARKDOWN_V2,
                        )
                    comment_id_to_message_id[comment['id']] = await bot.send_voice(
                        chat_id=chat_id,
                        voice=ogg_bytes,
                        reply_to_message_id=reply_id,
                        caption=comment_text,
                        parse_mode=ParseMode.MARKDOWN_V2,
                        disable_notification=True
                    )
                else:
                    await bot.send_chat_action(
                        chat_id=chat_id,
                        action=ChatAction.TYPING
                    )
                    if status and status_md is not None:
                        status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Sending text comment {_ + 1} of {len(self.comments_with_context)}`"
                        await status.edit_text(
                            status_md,
                            parse_mode=ParseMode.MARKDOWN_V2,
                        )
                    comment_id_to_message_id[comment['id']] = await bot.send_message(
                        chat_id=chat_id,
                        reply_to_message_id=reply_id,
                        text=comment_text,
                        parse_mode=ParseMode.MARKDOWN_V2,
                        disable_web_page_preview=True,
                        disable_notification=True
                    )
        return status, status_md

def get_redirected_url(url: str) -> str:
    return unquote(requests.get(url if 'http' in url else f'http://{url}').url.split("redirectPath=")[-1])

def get_clean_url(url: str) -> str:
    return urljoin(url, urlparse(url).path)

def get_time_emoji(timestamp: int) -> str:
    a = int(((timestamp + 8 * 3600) / 900 - 3) / 2 % 24)
    return f'{chr(128336 + a // 2 + a % 2 * 12)}'

def convert_timestamp_to_timestr(timestamp: int) -> str:
    utc_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    utc_plus_8 = utc_dt + timedelta(hours=8)
    return utc_plus_8.strftime('%Y-%m-%d %H:%M:%S')

def remove_image_url_params(url: str) -> str:
    for k, v in parse_qs(url).items():
        url = url.replace(f'&{k}={v[0]}', '')
    return url

def tg_msg_escape_html(t: str) -> str:
    return t.replace('<', '&lt;')\
        .replace('>','&gt;')\
        .replace('&', '&amp;')

def tg_msg_escape_markdown_v2(t: str | int) -> str:
    t = str(t)
    for i in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        t = t.replace(i, "\\" + i)
    return t

def open_note(noteId: str, connected_ssh_client: paramiko.SSHClient | None = None, anchorCommentId: str | None = None):
    if os.getenv('TARGET_DEVICE_TYPE') == '0':
        subprocess.run(["adb", "shell", "am", "start", "-d", f"xhsdiscover://item/{noteId}" + (f"?anchorCommentId={anchorCommentId}" if anchorCommentId else '')])
    elif os.getenv('TARGET_DEVICE_TYPE') == '1':
        if connected_ssh_client:
            _, _, _ = connected_ssh_client.exec_command(
                f"uiopen xhsdiscover://item/{noteId}" + (f"?anchorCommentId={anchorCommentId}" if anchorCommentId else '')
            )
        else:
            subprocess.run(["uiopen", f"xhsdiscover://item/{noteId}" + (f"?anchorCommentId={anchorCommentId}" if anchorCommentId else '')])

def home_page(connected_ssh_client: paramiko.SSHClient | None = None):
    if os.getenv('TARGET_DEVICE_TYPE') == '0':
        subprocess.run(["adb", "shell", "am", "start", "-d", "xhsdiscover://home"])
    elif os.getenv('TARGET_DEVICE_TYPE') == '1':
        if connected_ssh_client:
            _, _, _ = connected_ssh_client.exec_command(
                "uiopen xhsdiscover://home"
            )
        else:
            subprocess.run(["uiopen", "xhsdiscover://home"])

def get_url_info(message_text: str) -> dict[str, str | bool]:
    xsec_token = ''
    urls = re.findall(URL_REGEX, message_text)
    bot_logger.info(f'URLs:\n{urls}')
    anchorCommentId = ''
    if len(urls) == 0:
        bot_logger.debug("NO URL FOUND!")
        return {'success': False, 'msg': 'No URL found in the message.', 'noteId': '', 'xsec_token': '', 'anchorCommentId': ''}
    elif re.findall(r"[a-z0-9]{24}", message_text) and not re.findall(r"user/profile/[a-z0-9]{24}", message_text):
        noteId = re.findall(r"[a-z0-9]{24}", message_text)[0]
        note_url = [u for u in urls if re.findall(r"[a-z0-9]{24}", u) and not re.findall(r"user/profile/[a-z0-9]{24}", u)][0]
        parsed_url = urlparse(str(note_url))
        if 'xsec_token' in parse_qs(parsed_url.query):
            xsec_token = parse_qs(parsed_url.query)['xsec_token'][0]
        if 'anchorCommentId' in parse_qs(parsed_url.query):
            anchorCommentId = parse_qs(parsed_url.query)['anchorCommentId'][0]
    elif 'xhslink.com' in message_text or 'xiaohongshu.com' in message_text:
        xhslink = [u for u in urls if 'xhslink.com' in u][0]
        bot_logger.debug(f"URL found: {xhslink}")
        redirectPath = get_redirected_url(xhslink)
        bot_logger.debug(f"Redirected URL: {redirectPath}")
        if re.findall(r"https?://(?:www.)?xhslink.com/[a-z]/[A-Za-z0-9]+", xhslink):
            clean_url = get_clean_url(redirectPath)
            if 'xiaohongshu.com/404' in redirectPath or 'xiaohongshu.com/login' in redirectPath:
                noteId = re.findall(r"noteId=([a-z0-9]+)", redirectPath)[0]
                if 'redirectPath=' in redirectPath:
                    redirectPath = unquote(redirectPath.replace('https://www.xiaohongshu.com/login?redirectPath=', '').replace('https://www.xiaohongshu.com/404?redirectPath=', '').replace('https://www.xiaohongshu.com/login?redirectPath=', ''))
            else:
                noteId = re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/discovery\/item\/([a-z0-9]+)", clean_url)[0]
            parsed_url = urlparse(str(redirectPath))
            if 'xsec_token' in parse_qs(parsed_url.query):
                xsec_token = parse_qs(parsed_url.query)['xsec_token'][0]
            if 'anchorCommentId' in parse_qs(parsed_url.query):
                anchorCommentId = parse_qs(parsed_url.query)['anchorCommentId'][0]
        elif re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/discovery\/item\/[0-9a-z]+", xhslink):
            noteId = re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/discovery\/item\/([a-z0-9]+)", xhslink)[0]
            parsed_url = urlparse(str(xhslink))
            if 'xsec_token' in parse_qs(parsed_url.query):
                xsec_token = parse_qs(parsed_url.query)['xsec_token'][0]
            if 'anchorCommentId' in parse_qs(parsed_url.query):
                anchorCommentId = parse_qs(parsed_url.query)['anchorCommentId'][0]
        elif re.findall(r"https?://(?:www.)?xiaohongshu.com/explore/[a-z0-9]+", message_text):
            noteId = re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/explore\/([a-z0-9]+)", xhslink)[0]
            parsed_url = urlparse(str(xhslink))
            if 'xsec_token' in parse_qs(parsed_url.query):
                xsec_token = parse_qs(parsed_url.query)['xsec_token'][0]
            if 'anchorCommentId' in parse_qs(parsed_url.query):
                anchorCommentId = parse_qs(parsed_url.query)['anchorCommentId'][0]
        else:
            return {'success': False, 'msg': 'Invalid URL or the note is no longer available.', 'noteId': '', 'xsec_token': ''}
    else:
        return {'success': False, 'msg': 'Invalid URL.', 'noteId': '', 'xsec_token': ''}
    return {'success': True, 'msg': 'Success.', 'noteId': noteId, 'xsec_token': xsec_token, 'anchorCommentId': anchorCommentId}

def parse_comment(comment_data: dict[str, Any]):
    target_comment = comment_data.get('target_comment', {})
    user = comment_data.get('user', {})
    content = comment_data.get('content', '')
    content = re.sub(
        r'(?P<tag>#\S+?)\[\S+\]#',
        r'\g<tag> ',
        content
    )
    pictures = comment_data.get('pictures', [])
    picture_urls: list[str] = []
    for p in pictures:
        original_url = p.get('origin_url', '')
        if 'video_info' in p:
            video_info = p.get('video_info', '')
            if video_info:
                video_data = json.loads(video_info)
                for stream in video_data['stream']:
                    if video_data['stream'][stream]:
                        if 'backup_urls' in video_data['stream'][stream][0]:
                            video_url = video_data['stream'][stream][0]['backup_urls'][0]
                            picture_urls.append(video_url)
        picture_urls.append(re.sub(r'sns-note-i\d.xhscdn.com', 'sns-na-i6.xhscdn.com', original_url).split('?imageView')[0])
    audio_info = comment_data.get('audio_info', '')
    audio_url = ''
    if audio_info:
        audio_data = audio_info.get('play_info', {})
        if audio_data:
            audio_url = audio_data.get('url', '')
    id = comment_data.get('id', '')
    time = comment_data.get('time', 0)
    like_count = comment_data.get('like_count', 0)
    sub_comment_count = comment_data.get('sub_comment_count', 0)
    ip_location = comment_data.get('ip_location', 'Unknown')
    data: dict[str, Any] = {
        'user': user,
        'content': content,
        'pictures': picture_urls,
        'id': id,
        'time': time,
        'like_count': like_count,
        'sub_comment_count': sub_comment_count,
        'ip_location': ip_location,
        'audio_url': audio_url,
    }
    if target_comment:
        data['target_comment'] = target_comment
    return data

def extract_anchor_comment_id(json_data: dict[str, Any]) -> list[dict[str, Any]]:
    comments = json_data.get('comments', [])
    if not comments:
        bot_logger.error("No comments found in the data.")
        bot_logger.error(f"JSON data: {pformat(json_data)}")
        raise Exception("No comments found in the data.")
    comment = comments[0]
    sub_comments = comment.get('sub_comments', [])
    related_sub_comments: list[dict[str, Any]] = []
    if 'page_context' in json_data:
        page_context = json_data.get('page_context', '')
        if page_context:    
            page_context = json.loads(page_context)
            key_comments_id = page_context.get('top', [])
            for key in key_comments_id:
                for sub_comment in sub_comments:
                    if sub_comment.get('id', '') == key:
                        related_sub_comments.append(sub_comment)
    all_comments = [comment] + related_sub_comments

    data_parsed: list[dict[str, Any]] = []

    for c in all_comments:
        parsed_comment = parse_comment(c)
        data_parsed.append(parsed_comment)
    return data_parsed

def convert_to_ogg_opus_pipe(input_bytes: bytes) -> bytes:
    process = subprocess.Popen(
        [
            "ffmpeg", "-i", "pipe:0",
            "-c:a", "libopus",
            "-f", "ogg",
            "pipe:1"
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    out, _ = process.communicate(input_bytes)
    return out

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    chat = update.effective_chat
    
    if not is_user_whitelisted(user_id):
        bot_logger.warning(f"Unauthorized access attempt from user {user_id}")
        # if chat:
        #     try:
        #         await context.bot.send_message(
        #             chat_id=chat.id,
        #             text="Sorry, you are not authorized to use this bot."
        #         )
        #     except Exception as e:
        #         bot_logger.error(f"Failed to send unauthorized message: {e}")
        return
    
    if chat:
        try:
            await context.bot.send_message(chat_id=chat.id, text="I'm xhsfeedbot, please send me a xhs link!\n/help for more info.")
            update_network_status(success=True)
        except Exception as e:
            bot_logger.error(f"Failed to send start message: {e}")
            update_network_status(success=False)

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    bot_logger.debug(f"Help requested by user {user_id}")
    chat = update.effective_chat
    
    if not is_user_whitelisted(user_id):
        bot_logger.warning(f"Unauthorized access attempt from user {user_id}")
        # if chat:
        #     try:
        #         await context.bot.send_message(
        #             chat_id=chat.id,
        #             text="Sorry, you are not authorized to use this bot."
        #         )
        #     except Exception as e:
        #         bot_logger.error(f"Failed to send unauthorized message: {e}")
        return
    
    if chat:
        help_msg = """*Usage*
send `xhslink\\[\\.\\]com` or `xiaohongshu\\[\\.\\]com` note link to @xhsfeedbot
Link without `xsec_token` parameter is supported\\.
Telegraph link without media group as default output\\.

*Parameters*
`\\-x`  Note link with `xsec_token`\\.

*Inline mode*
Use `@xhsfeedbot <note link>` in any chat to get a short preview of the note in Telegraph page\\.

*Commands*
`/start` \\- Start chat with @xhsfeedbot\\.
`/help` \\- Show this help message\\.
`/note` \\- Forward note to Telegraph or Telegram message \\(with `-m` parameter\\)\\.

*Note*
Group privacy is on\\. You need to send command to bot manually or add bot as admin in group chat\\."""
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=help_msg,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True,
                disable_notification=True
            )
            update_network_status(success=True)
        except Exception as e:
            bot_logger.error(f"Failed to send help message: {e}")
            update_network_status(success=False)

async def process_note_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process a single note request with concurrency control"""
    user_id = update.effective_user.id if update.effective_user else "unknown"
    chat_id = update.effective_chat.id if update.effective_chat else "unknown"
    
    # Log when we're waiting for semaphore
    available_slots = processing_semaphore._value
    bot_logger.debug(f"Processing request from user {user_id} in chat {chat_id}. Available slots: {available_slots}")
    
    async with processing_semaphore:
        bot_logger.debug(f"Started concurrent processing for user {user_id}")
        try:
            await _note2feed_internal(update, context)
        except Exception as e:
            bot_logger.error(f"Error in concurrent processing for user {user_id}: {e}")
        finally:
            bot_logger.debug(f"Finished concurrent processing for user {user_id}")

async def note2feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main handler that creates concurrent tasks for note processing"""
    asyncio.create_task(process_note_request(update, context))

async def _note2feed_internal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Internal note processing function"""
    user_id = update.effective_user.id if update.effective_user else None
    
    chat = update.effective_chat
    if not chat:
        return
    # Check whitelist
    if not is_user_whitelisted(user_id):
        bot_logger.warning(f"Unauthorized access attempt from user {user_id}")
        msg = update.message
        # if msg and chat:
        #     try:
        #         await context.bot.send_message(
        #             chat_id=chat.id,
        #             text="Sorry, you are not authorized to use this bot.",
        #             reply_to_message_id=msg.message_id
        #         )
        #     except Exception as e:
        #         bot_logger.error(f"Failed to send unauthorized message: {e}")
        return

    msg = update.message
    if not msg:
        return
    message_text = str(update.message.text if update.message and update.message.text is not None else "")
    now_timestamp = int(datetime.timestamp(datetime.now()))
    await context.bot.send_chat_action(
        chat_id=chat.id,
        action=ChatAction.TYPING
    )
    status_md = f"{get_time_emoji(now_timestamp)} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(now_timestamp))} \\> `Received your message, processing...`"
    status = await msg.reply_text(
        status_md,
        parse_mode=ParseMode.MARKDOWN_V2,
        disable_notification=True
    )
    # If there is a photo, try to decode QR code
    if msg.photo:
        try:
            status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Decoding QR code from the photo`"
            await status.edit_text(
                status_md,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            # Get the lowest resolution photo
            photo_file = await msg.photo[-1].get_file()
            
            # Download to memory
            img_byte_arr: BytesIO = BytesIO()
            await photo_file.download_to_memory(img_byte_arr)
            img_byte_arr.seek(0)

            # Decode QR code
            image = Image.open(img_byte_arr)
            decoded_objects: list[Any] = decode(image) # pyright: ignore[reportUnknownVariableType]

            for obj in decoded_objects:
                if obj.type == 'QRCODE':
                    qr_data = obj.data.decode("utf-8")
                    bot_logger.info(f"QR Code detected: {qr_data}")
                    # Append decoded URL to message text so it gets processed
                    message_text += f" {qr_data} "
                    
                    status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `QR code decoded successfully: {tg_msg_escape_markdown_v2(qr_data)}`"
                    await status.edit_text(
                        status_md,
                        parse_mode=ParseMode.MARKDOWN_V2,
                    )
        except Exception as e:
            bot_logger.error(f"Failed to decode QR code: {e}")

    if msg.caption:
        message_text += f" {msg.caption} "

    with_xsec_token = bool(re.search(r"[^\S]+-x(?!\S)", message_text))
    url_info = get_url_info(message_text)
    if not url_info['success']:
        await context.bot.send_message(
            chat_id=chat.id,
            text=str(url_info['msg']),
            reply_to_message_id=msg.message_id,
            disable_notification=True
        )
        return
    status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Get URL info successfully`"
    await status.edit_text(
        status_md,
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    noteId = str(url_info['noteId'])
    status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Note ID: {tg_msg_escape_markdown_v2(noteId)}`"
    await status.edit_text(
        status_md,
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    xsec_token = str(url_info['xsec_token'])
    status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `xsec_token: {tg_msg_escape_markdown_v2(xsec_token) if xsec_token else "None"}`"
    await status.edit_text(
        status_md,
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    anchorCommentId = str(url_info['anchorCommentId'])
    status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `anchorCommentId: {tg_msg_escape_markdown_v2(anchorCommentId) if anchorCommentId else "None"}`"
    await status.edit_text(
        status_md,
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    bot_logger.info(f'Note ID: {noteId}, xsec_token: {xsec_token if xsec_token else "None"}, anchorCommentId: {anchorCommentId if anchorCommentId else "None"}')
    if os.getenv('TARGET_DEVICE_TYPE') == '1':
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_ip = os.getenv('SSH_IP')
        if not ssh_ip:
            raise ValueError("SSH_IP environment variable is required")
        ssh_port = os.getenv('SSH_PORT')
        if not ssh_port:
            raise ValueError("SSH_PORT environment variable is required")
        ssh.connect(
            ssh_ip,
            port=int(ssh_port),
            username=os.getenv('SSH_USERNAME'),
            password=os.getenv('SSH_PASSWORD')
        )
    else:
        ssh = None
    bot_logger.debug('try open note on device')
    status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Parsing Note`"
    await status.edit_text(
        status_md,
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    open_note(noteId, ssh, anchorCommentId=anchorCommentId)
    await asyncio.sleep(0.75)
    home_page(ssh)
    if ssh:
        ssh.close()

    note_data: dict[str, Any] = {}
    comment_list_data: dict[str, Any] = {'data': {}}

    try:
        note_data = requests.get(
            f"http://127.0.0.1:{os.getenv('SHARED_SERVER_PORT')}/get_note/{noteId}"
        ).json()
        with open(os.path.join("data", f"note_data-{noteId}.json"), "w", encoding='utf-8') as f:
            json.dump(note_data, f, indent=4, ensure_ascii=False)
            f.close()
        status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Fetch note data successfully`"
        await status.edit_text(
            status_md,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        times = 0
        if anchorCommentId:
            while True:
                times += 1
                try:
                    comment_list_data = requests.get(
                        f"http://127.0.0.1:{os.getenv('SHARED_SERVER_PORT')}/get_comment_list/{noteId}"
                    ).json()
                    with open(os.path.join("data", f"comment_list_data-{noteId}.json"), "w", encoding='utf-8') as f:
                        json.dump(comment_list_data, f, indent=4, ensure_ascii=False)
                        f.close()
                    bot_logger.debug('got comment list data')
                    status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Fetch comment list data successfully`"
                    await status.edit_text(
                        status_md,
                        parse_mode=ParseMode.MARKDOWN_V2,
                    )
                    break
                except:
                    if times <= 3:
                        await asyncio.sleep(0.1)
                    else:
                        raise Exception('error when getting comment list data')
    except:
        bot_logger.error(traceback.format_exc())
    finally:
        if not note_data or 'data' not in note_data:
            return
    if note_data['data']['data'][0]['note_list'][0]['model_type'] == 'error':
        bot_logger.warning(f'Note data not available\n{note_data['data']}')
        status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Note data not available`"
        await status.edit_text(
            status_md,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return
    status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Start parsing and sending note`"
    await status.edit_text(
        status_md,
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    try:
        try:
            await telegraph_account.get_account_info()  # type: ignore
        except:
            await telegraph_account.create_account( # type: ignore
                short_name='@xhsfeedbot',
            )
        note = Note(
            note_data['data'],
            comment_list_data=comment_list_data['data'],
            live=True,
            telegraph=True,
            with_xsec_token=with_xsec_token,
            original_xsec_token=xsec_token,
            telegraph_account=telegraph_account,
            anchorCommentId=anchorCommentId
        )
        await note.initialize()
        status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Parse note successfully`"
        await status.edit_text(
            status_md,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        try:
            # reply with rich text when sending media failed
            await context.bot.send_chat_action(
                chat_id=chat.id,
                action=ChatAction.TYPING
            )
            if not note.telegraph_url:
                await note.to_telegraph()
            telegraph_msg = await context.bot.send_message(
                chat_id = chat.id,
                text = f"📕 [{tg_msg_escape_markdown_v2(note.title)}]({note.url})\n{f"\n{tg_msg_escape_markdown_v2(note.tag_string)}" if note.tags else ""}\n\n👤 [@{tg_msg_escape_markdown_v2(note.user['name'])}](https://www.xiaohongshu.com/user/profile/{note.user['id']})\n\n📰 [View via Telegraph]({note.telegraph_url})",
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=False,
                reply_to_message_id=msg.message_id,
                disable_notification=True
            )
            status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Telegraph link sent successfully`"
            await status.edit_text(
                status_md,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            status, status_md = await note.send_as_telegram_message(context.bot, chat.id, msg.message_id, status, status_md)
            if telegraph_msg:
                await telegraph_msg.delete()
            if status and status_md is not None:
                status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Note sent successfully`"
                await status.edit_text(
                    status_md,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            update_network_status(success=True)  # Successfully sent message
        except:
            bot_logger.error(traceback.format_exc())
        if status:
            await status.delete()
    except Exception as e:
        try:
            if status and status_md is not None:
                status_md += f"\n{get_time_emoji(int(datetime.timestamp(datetime.now())))} {tg_msg_escape_markdown_v2(convert_timestamp_to_timestr(int(datetime.timestamp(datetime.now()))))} \\> `Failed to send note:`\n```python\n{tg_msg_escape_markdown_v2(str(e))}\n```"
                await status.edit_text(
                    status_md,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            update_network_status(success=True)
        except Exception as send_error:
            bot_logger.error(f"Failed to send error message: {send_error}")
            update_network_status(success=False)
        bot_logger.error(f"Error in note2feed: {e}\n{traceback.format_exc()}")

async def process_inline_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process a single inline query request with concurrency control"""
    user_id = update.effective_user.id if update.effective_user else "unknown"
    
    available_slots = processing_semaphore._value
    bot_logger.debug(f"Processing inline query from user {user_id}. Available slots: {available_slots}")
    
    async with processing_semaphore:
        bot_logger.debug(f"Started concurrent inline processing for user {user_id}")
        try:
            await _inline_note2feed_internal(update, context)
        except Exception as e:
            bot_logger.error(f"Error in concurrent inline processing for user {user_id}: {e}")
        finally:
            bot_logger.debug(f"Finished concurrent inline processing for user {user_id}")

async def inline_note2feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main inline handler that creates concurrent tasks"""
    # For inline queries, we need to respond quickly, so we await the result
    # but still use the semaphore for rate limiting
    await process_inline_request(update, context)

async def _inline_note2feed_internal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Internal inline query processing function"""
    user_id = update.effective_user.id if update.effective_user else None
    
    # Check whitelist
    if not is_user_whitelisted(user_id):
        bot_logger.warning(f"Unauthorized inline access attempt from user {user_id}")
        # inline_query = update.inline_query
        # if inline_query:
        #     try:
        #         await context.bot.answer_inline_query(
        #             inline_query_id=inline_query.id,
        #             results=[],
        #             cache_time=0
        #         )
        #     except Exception as e:
        #         bot_logger.error(f"Failed to respond to unauthorized inline query: {e}")
        return
    
    inline_query = update.inline_query
    bot_logger.debug(inline_query)
    if inline_query is None:
        return
    message_text = inline_query.query
    if not message_text:
        return
    with_xsec_token = bool(re.search(r"[^\S]+-x(?!\S)", message_text))
    url_info = get_url_info(message_text)
    if not url_info['success']:
        return
    noteId = str(url_info['noteId'])
    xsec_token = str(url_info['xsec_token'])
    bot_logger.info(f'Note ID: {noteId}, xsec_token: {xsec_token if xsec_token else "None"}')
    anchorCommentId = str(url_info['anchorCommentId'])
    bot_logger.info(f'Note ID: {noteId}, xsec_token: {xsec_token if xsec_token else "None"}, anchorCommentId: {anchorCommentId if anchorCommentId else "None"}')

    if os.getenv('TARGET_DEVICE_TYPE') == '1':
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_ip = os.getenv('SSH_IP')
        if not ssh_ip:
            raise ValueError("SSH_IP environment variable is required")
        ssh_port = os.getenv('SSH_PORT')
        if not ssh_port:
            raise ValueError("SSH_PORT environment variable is required")
        ssh.connect(
            ssh_ip,
            port=int(ssh_port),
            username=os.getenv('SSH_USERNAME'),
            password=os.getenv('SSH_PASSWORD')
        )
    else:
        ssh = None
    bot_logger.debug('try open note on device')
    open_note(noteId, ssh, anchorCommentId=anchorCommentId)
    await asyncio.sleep(0.6)
    home_page(ssh)
    if ssh:
        ssh.close()

    note_data: dict[str, Any] = {}
    comment_list_data: dict[str, Any] = {'data': {}}

    for _ in range(3):
        try:
            note_data = requests.get(
                f"http://127.0.0.1:{os.getenv('SHARED_SERVER_PORT')}/get_note/{noteId}"
            ).json()
            with open(os.path.join("data", f"note_data-{noteId}.json"), "w", encoding='utf-8') as f:
                json.dump(note_data, f, indent=4, ensure_ascii=False)
                f.close()
        except:
            if _ == 2:
                bot_logger.error(traceback.format_exc())
                return
            else:
                await asyncio.sleep(0.1)
                bot_logger.warning(f'Failed to retrieve note data for {noteId}, retrying...')
        else:
            break
    if not note_data or 'data' not in note_data:
        return
    try:
        try:
            await telegraph_account.get_account_info()  # type: ignore
        except:
            await telegraph_account.create_account( # type: ignore
                short_name='@xhsfeedbot',
            )
        note = Note(
            note_data['data'],
            comment_list_data=comment_list_data['data'],
            live=True,
            telegraph=True,
            with_xsec_token=with_xsec_token,
            original_xsec_token=xsec_token,
            telegraph_account=telegraph_account,
            anchorCommentId=anchorCommentId
        )
        await note.initialize()
        telegraph_url = note.telegraph_url if hasattr(note, 'telegraph_url') else await note.to_telegraph()
        inline_query_result = [
            InlineQueryResultArticle(
                id=str(uuid4()),
                title=note.title,
                input_message_content=InputTextMessageContent(
                    message_text=f"📕 [{tg_msg_escape_markdown_v2(note.title)}]({note.url})\n{f"\n{tg_msg_escape_markdown_v2(note.tag_string)}" if note.tags else ""}\n\n👤 [@{tg_msg_escape_markdown_v2(note.user['name'])}](https://www.xiaohongshu.com/user/profile/{note.user['id']})\n\n📰 [View via Telegraph]({telegraph_url})",
                    parse_mode=ParseMode.MARKDOWN_V2,
                    link_preview_options=LinkPreviewOptions(
                        is_disabled=False,
                        url=telegraph_url,
                        prefer_large_media=True
                    ),
                ),
                description=f"Telegraph URL with xiaohongshu.com URL ({'with' if with_xsec_token else 'no'} xsec_token)",
                thumbnail_url=note.thumbnail
            )
        ]
        await context.bot.answer_inline_query(
            inline_query_id=inline_query.id,
            results=inline_query_result
        )
        update_network_status(success=True)
    except Exception as e:
        bot_logger.error(f"Error in inline_note2feed: {e}\n{traceback.format_exc()}")
        update_network_status(success=False)
    return

async def error_handler(update: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    global logging_file
    admin_id = os.getenv('ADMIN_ID')
    error_str = str(context.error).lower()
    
    # Check for network-related errors that should trigger restart
    network_keywords = [
        'timeout', 'pool timeout', 'connection', 'network', 
        'timed out', 'connecttimeout', 'readtimeout', 'writetimeout'
    ]
    
    if isinstance(context.error, NetworkError) or any(keyword in error_str for keyword in network_keywords):
        bot_logger.error(f"Network-related error detected:\n{context.error}\n\n{traceback.format_exc()}")
        update_network_status(success=False)
        if not is_network_healthy or not check_network_connectivity():
            bot_logger.error("Network appears unhealthy - triggering restart")
            restart_script()
        return
    elif isinstance(context.error, BadRequest):
        bot_logger.error(f"BadRequest error:\n{context.error}\n\n{traceback.format_exc()}")
        return
    elif isinstance(context.error, KeyboardInterrupt):
        os._exit(0)
        return
    else:
        if admin_id:
            try:
                await context.bot.send_document(
                    chat_id=admin_id,
                    caption=f'```python\n{tg_msg_escape_markdown_v2(pformat(update))}\n```\n CAUSED \n```python\n{tg_msg_escape_markdown_v2(pformat(context.error))[-888:]}\n```',
                    parse_mode=ParseMode.MARKDOWN_V2,
                    document=logging_file,
                    disable_notification=True
                )
                update_network_status(success=True)  # Successfully sent message
            except Exception as send_error:
                bot_logger.error(f"Failed to send error report: {send_error}")
                update_network_status(success=False)
        bot_logger.error(f"Update {update} caused error:\n{context.error}\n\n{traceback.format_exc()}")

def run_telegram_bot():
    bot_token = os.getenv('BOT_TOKEN')
    if not bot_token:
        raise ValueError("BOT_TOKEN environment variable is required")
    
    # Start network monitoring in background thread
    monitor_thread = threading.Thread(target=network_monitor, daemon=True)
    monitor_thread.start()
    
    application = ApplicationBuilder()\
        .concurrent_updates(True)\
        .token(bot_token)\
        .read_timeout(30)\
        .write_timeout(30)\
        .media_write_timeout(120)\
        .connect_timeout(15)\
        .pool_timeout(10)\
        .concurrent_updates(True)\
        .build()
    try:
        start_handler = CommandHandler("start", start)
        application.add_handler(start_handler)
        help_handler = CommandHandler("help", help)
        application.add_handler(help_handler)

        application.add_error_handler(error_handler)

        note2feed_handler = MessageHandler(
            (~ filters.COMMAND) & (
                (filters.TEXT & (filters.Entity(MessageEntity.URL) | filters.Entity(MessageEntity.TEXT_LINK))) |
                filters.PHOTO
            ),
            note2feed
        )
        application.add_handler(note2feed_handler)

        note2feed_command_handler = CommandHandler(
            "note",
            note2feed,
            block=False
        )
        application.add_handler(InlineQueryHandler(inline_note2feed, block=False))
        application.add_handler(note2feed_command_handler)
        
        bot_logger.info(f'Bot started polling with concurrent processing enabled (max {max_concurrent_requests} concurrent requests)')
        application.run_polling()
    except KeyboardInterrupt:
        shutdown_result = application.shutdown()
        bot_logger.debug(f'KeyboardInterrupt received, shutdown:{shutdown_result}')
        raise Exception('KeyboardInterrupt received, script will quit now.')
    except NetworkError as e:
        bot_logger.error(f'NetworkError: {e}\n{traceback.format_exc()}')
        update_network_status(success=False)
        if not check_network_connectivity():
            bot_logger.error('Network connectivity test failed - restarting')
            restart_script()
        raise Exception('NetworkError received, script will quit now.')
    except Exception as e:
        error_str = str(e).lower()
        network_keywords = ['timeout', 'connection', 'network', 'timed out']
        
        if any(keyword in error_str for keyword in network_keywords):
            bot_logger.error(f'Network-related error in main loop: {e}\n{traceback.format_exc()}')
            update_network_status(success=False)
            if not check_network_connectivity():
                bot_logger.error('Network connectivity test failed - restarting')
                restart_script()
        else:
            bot_logger.error(f'Unexpected error:\n{traceback.format_exc()}\n\n SCRIPT WILL QUIT NOW')
        raise Exception(f'Error in main loop: {e}')

def restart_script():
    bot_logger.info("Restarting script...")
    try:
        process = psutil.Process(os.getpid())
        for handler in process.open_files() + process.net_connections():
            os.close(handler.fd)
    except Exception as e:
        bot_logger.error(f'Error when closing file descriptors: {e}\n{traceback.format_exc()}')
    python = sys.executable
    os.execl(python, python, *sys.argv)

if __name__ == "__main__":
    try:
        telegraph_account = Telegraph()
        run_telegram_bot()
    except Exception as e:
        restart_script()