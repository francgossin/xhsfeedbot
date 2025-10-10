import os
import sys
import re
import json
import time
import asyncio # type: ignore
import random
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
)
from telegram.error import (
    NetworkError,
    BadRequest
)
from telegram.constants import ParseMode
from telegraph.aio import Telegraph # type: ignore

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
        self.first_comment = ''
        if int(self.comments_count) and comment_list_data:
            nonblank_comments_index = [c for c in range(len(comment_list_data['data']['comments'])) if comment_list_data['data']['comments'][c]['content']]
            if nonblank_comments_index:
                comment_index = nonblank_comments_index[0]
            else:
                comment_index = random.choice(nonblank_comments_index)
            self.first_comment = replace_redemoji_with_emoji(
                comment_list_data['data']['comments'][comment_index]['content']
            )
            self.first_comment = re.sub(
                r'#(?P<tag_text>\S+?)\[\S+\]#',
                r'\g<tag_text>',
                self.first_comment
            )
            self.comment_user = comment_list_data['data']['comments'][comment_index]['user']['nickname'] if comment_list_data['data']['comments'] else ''
            self.first_comment_tag_v2 = comment_list_data['data']['comments'][comment_index]['show_tags_v2'][0]['text'] if comment_list_data['data']['comments'][comment_index]['show_tags_v2'] else ''
        self.length: int = len(self.desc + self.title + self.first_comment)

        self.tags: list[str] = [tag['name'] for tag in note_data['data'][0]['note_list'][0]['hash_tag']]
        self.tag_string: str = ' '.join([f"#{tag}" for tag in self.tags])

        self.share_content: str = note_data['data'][0]['note_list'][0]['share_info']['content']
        self.share_content = re.sub(r'(#\S+)', '', self.share_content)
        self.share_content += "..." if self.share_content.strip().strip('#') and not self.share_content.endswith("...") else ""

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
                self.video_url = re.sub(r'[0-9a-z\-]+.xhscdn.com', 'sns-bak-v1.xhscdn.com', self.video_url)
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
            html += f'<p>{line_html}</p>'
        html += f'<h4>👤 <a href="https://www.xiaohongshu.com/user/profile/{self.user["id"]}"> @{self.user["name"]} ({self.user["red_id"]})</a></h4>'
        html += f'<img src="{self.user["image"]}"></img>'
        html += f'<p>{get_time_emoji(self.time)} {convert_timestamp_to_timestr(self.time)}</p>'
        html += f'<p>❤️ {self.liked_count} ⭐ {self.collected_count} 💬 {self.comments_count} 🔗 {self.shared_count}</p>'
        if hasattr(self, 'ip_location'):
            ipaddr_html = tg_msg_escape_html(self.ip_location)
        else:
            ipaddr_html = 'Unknown IP Address'
        html += f'<p>📍 {ipaddr_html}</p>'
        # html += '<br><i>via</i> <a href="https://t.me/xhsfeedbot">@xhsfeedbot</a>'
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
            author_name=f'@xhsfeedbot',
            author_url=f"https://t.me/xhsfeedbot",
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
            ip_html = 'Unknown IP Address'
        message += f'>📍 {ip_html}\n'
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
        bot_logger.debug(f"Telegram message generated, \n\n{self.message}\n\n")
        return message

    async def to_short_preview(self):
        message = ''
        message += f'*『[{tg_msg_escape_markdown_v2(self.title)}]({self.url})』*\n'
        message += f'{self.make_block_quotation(self.desc[:166] + '...')}\n'
        if hasattr(self, 'telegraph_url'):
            message += f'📝 [View more via Telegraph]({tg_msg_escape_markdown_v2(self.telegraph_url)})\n'
        else:
            message += f'📝 [View more via Telegraph]({tg_msg_escape_markdown_v2(await self.to_telegraph())})\n'
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
        bot_logger.debug(f"Short preview generated, {self.short_preview}")
        return message

    async def to_media_group(self) -> list[list[InputMediaPhoto | InputMediaVideo]]:
        self.medien: list[InputMediaPhoto | InputMediaVideo] = []
        for _, imgs in enumerate(self.images_list):
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

    async def send_as_telegram_message(self, bot: Bot, chat_id: int, reply_to_message_id: int = 0) -> None:
        if not hasattr(self, 'medien_parts'):
            self.medien_parts: list[list[InputMediaPhoto | InputMediaVideo]] = await self.to_media_group()
        for i, part in enumerate(self.medien_parts):
            if i != len(self.medien_parts) - 1:
                try:
                    await bot.send_media_group(
                        chat_id=chat_id,
                        reply_to_message_id=reply_to_message_id,
                        media=part,
                    )
                except:
                    bot_logger.error(f"Failed to send media group:\n{traceback.format_exc()}")
                    media: list[InputMediaPhoto | InputMediaVideo] = []
                    for p in part:
                        if type(p.media) == str and '.mp4' not in p.media:
                            media.append(InputMediaPhoto(requests.get(p.media).content))
                        elif type(p.media) == str:
                            media.append(InputMediaVideo(requests.get(p.media).content))
                        else:
                            media.append(p)
                    await bot.send_media_group(
                        chat_id=chat_id,
                        reply_to_message_id=reply_to_message_id,
                        media=media,
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
                    bot_logger.error(f"Failed to send media group:\n{traceback.format_exc()}")
                    media: list[InputMediaPhoto | InputMediaVideo] = []
                    for p in part:
                        if type(p.media) == str and '.mp4' not in p.media:
                            media.append(InputMediaPhoto(requests.get(p.media).content))
                        elif type(p.media) == str:
                            media.append(InputMediaVideo(requests.get(p.media).content))
                        else:
                            media.append(p)
                    await bot.send_media_group(
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

def open_note(noteId: str, connected_ssh_client: paramiko.SSHClient | None = None):
    if os.getenv('TARGET_DEVICE_TYPE') == '0':
        subprocess.run(["adb", "shell", "am", "start", "-d", f"xhsdiscover://item/{noteId}"])
    elif os.getenv('TARGET_DEVICE_TYPE') == '1':
        if connected_ssh_client:
            _, _, _ = connected_ssh_client.exec_command(
                f"uiopen xhsdiscover://item/{noteId}"
            )
        else:
            subprocess.run(["uiopen", f"xhsdiscover://item/{noteId}"])

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
    if len(urls) == 0:
        bot_logger.debug("NO URL FOUND!")
        return {'success': False, 'msg': 'No URL found in the message.', 'noteId': '', 'xsec_token': ''}
    elif re.findall(r"[a-z0-9]{24}", message_text) and not re.findall(r"user/profile/[a-z0-9]{24}", message_text):
        noteId = re.findall(r"[a-z0-9]{24}", message_text)[0]
        note_url = [u for u in urls if re.findall(r"[a-z0-9]{24}", u) and not re.findall(r"user/profile/[a-z0-9]{24}", u)][0]
        parsed_url = urlparse(str(note_url))
        if 'xsec_token' in parse_qs(parsed_url.query):
            xsec_token = parse_qs(parsed_url.query)['xsec_token'][0]
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
                    redirectPath = unquote(redirectPath.replace('https://www.xiaohongshu.com/login?redirectPath=', '').replace('https://www.xiaohongshu.com/404?redirectPath=', ''))
            else:
                noteId = re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/discovery\/item\/([a-z0-9]+)", clean_url)[0]
            parsed_url = urlparse(str(redirectPath))
            if 'xsec_token' in parse_qs(parsed_url.query):
                xsec_token = parse_qs(parsed_url.query)['xsec_token'][0]
        elif re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/discovery\/item\/[0-9a-z]+", xhslink):
            noteId = re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/discovery\/item\/([a-z0-9]+)", xhslink)[0]
            parsed_url = urlparse(str(xhslink))
            if 'xsec_token' in parse_qs(parsed_url.query):
                xsec_token = parse_qs(parsed_url.query)['xsec_token'][0]
        elif re.findall(r"https?://(?:www.)?xiaohongshu.com/explore/[a-z0-9]+", message_text):
            noteId = re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/explore\/([a-z0-9]+)", xhslink)[0]
            parsed_url = urlparse(str(xhslink))
            if 'xsec_token' in parse_qs(parsed_url.query):
                xsec_token = parse_qs(parsed_url.query)['xsec_token'][0]
        else:
            return {'success': False, 'msg': 'Invalid URL or the note is no longer available.', 'noteId': '', 'xsec_token': ''}
    else:
        return {'success': False, 'msg': 'Invalid URL or the note is no longer available.', 'noteId': '', 'xsec_token': ''}
    return {'success': True, 'msg': 'Success.', 'noteId': noteId, 'xsec_token': xsec_token}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat:
        try:
            await context.bot.send_message(chat_id=chat.id, text="I'm xhsfeedbot, please send me a xhs link!\n/help for more info.")
            update_network_status(success=True)
        except Exception as e:
            bot_logger.error(f"Failed to send start message: {e}")
            update_network_status(success=False)

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat:
        help_msg = """*Usage*
send `xhslink\\[\\.\\]com` or `xiaohongshu\\[\\.\\]com` note link to @xhsfeedbot
Link without `xsec_token` parameter is supported\\.
Telegraph link without media group as default output\\.

*Parameters*
`\\-l`  Output Telegram message media group and Telegraph media with live photo video\\.
`\\-x`  Note link with `xsec_token`\\.
`\\-m`  Output note media and content as direct Telegram messages \\(may consume more time\\)\\.

*Inline mode*
Use `@xhsfeedbot <note link>` in any chat to get a short preview of the note\\.
`\\-m` parameter is not supported in inline mode\\.

*Commands*
`/start` \\- Start chat with @xhsfeedbot\\.
`/help` \\- Show this help message\\.
`/note` \\- Forward note to Telegraph or Telegram message \\(with `-m` parameter\\)\\.

*Note*
Group privacy is on\\. You need to send command to bot manually or add bot as admin in group chat\\.

Due to referer policy of images and videos of `xiaohongshu\\[\\.\\]com`, media in Telegraph may not work sometimes in browser\\.

If you really need to view Telegraph outside Telegram Instant View, addons like [this on Firefox](https://addons.mozilla.org/firefox/addon/togglereferrer/) may help\\."""
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=help_msg,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True
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
    msg = update.message
    if not msg:
        return
    chat = update.effective_chat
    if not chat:
        return
    message_text = update.message.text if update.message and update.message.text is not None else ""
    live = bool(re.search(r"[^\S]+-l(?!\S)", message_text))
    with_xsec_token = bool(re.search(r"[^\S]+-x(?!\S)", message_text))
    with_full_data = bool(re.search(r"[^\S]+-m(?!\S)", message_text))
    url_info = get_url_info(message_text)
    if not url_info['success']:
        await context.bot.send_message(
            chat_id=chat.id,
            text=str(url_info['msg']),
            reply_to_message_id=msg.message_id
        )
        return
    noteId = str(url_info['noteId'])
    xsec_token = str(url_info['xsec_token'])
    bot_logger.info(f'Note ID: {noteId}, xsec_token: {xsec_token if xsec_token else "None"}')
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
    open_note(noteId, ssh)
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
        times = 0
        if with_full_data:
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
        await context.bot.send_message(
            chat_id=chat.id,
            text=f"{note_data['data']['data'][0]['note_list'][0]['text']}\nThe note may be deleted or the account is private.\nIf you think this is an error, please contact the bot owner.\n\nNote URL: https://www.xiaohongshu.com/discovery/item/{noteId}\nAuthor URL: https://www.xiaohongshu.com/user/profile/{note_data['data']['data'][0]['note_list'][0]['user_id']}",
            reply_to_message_id=msg.message_id
        )
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
            live=live,
            telegraph=True,
            with_xsec_token=with_xsec_token,
            original_xsec_token=xsec_token,
            telegraph_account=telegraph_account
        )
        await note.initialize()
        if with_full_data:
            await note.send_as_telegram_message(context.bot, chat.id, msg.message_id)
        else:
            telegraph_url = note.telegraph_url if hasattr(note, 'telegraph_url') else await note.to_telegraph()
            await context.bot.send_message(
                chat_id=chat.id,
                text=f"📕 [{tg_msg_escape_markdown_v2(note.title)}]({note.url})\n{f"\n{tg_msg_escape_markdown_v2(note.share_content)}" if note.share_content.strip() else ""}{f"\n{tg_msg_escape_markdown_v2(note.tag_string)}" if note.tags else ""}\n\n👤 [@{tg_msg_escape_markdown_v2(note.user['name'])}](https://www.xiaohongshu.com/user/profile/{note.user['id']})\n\n📰 [View via Telegraph]({telegraph_url})",
                parse_mode=ParseMode.MARKDOWN_V2,
                link_preview_options=LinkPreviewOptions(
                    is_disabled=False,
                    url=telegraph_url,
                    prefer_large_media=True
                ),
                reply_to_message_id=msg.message_id
            )
            update_network_status(success=True)  # Successfully sent message
    except Exception as e:
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text="An error occurred while processing your request.",
                reply_to_message_id=msg.message_id
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
    inline_query = update.inline_query
    bot_logger.debug(inline_query)
    if inline_query is None:
        return
    message_text = inline_query.query
    if not message_text:
        return
    live = bool(re.search(r"[^\S]+-l(?!\S)", message_text))
    with_xsec_token = bool(re.search(r"[^\S]+-x(?!\S)", message_text))
    url_info = get_url_info(message_text)
    if not url_info['success']:
        return
    noteId = str(url_info['noteId'])
    xsec_token = str(url_info['xsec_token'])
    bot_logger.info(f'Note ID: {noteId}, xsec_token: {xsec_token if xsec_token else "None"}')
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
    open_note(noteId, ssh)
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
            live=live,
            telegraph=True,
            with_xsec_token=with_xsec_token,
            original_xsec_token=xsec_token,
            telegraph_account=telegraph_account
        )
        await note.initialize()
        telegraph_url = note.telegraph_url if hasattr(note, 'telegraph_url') else await note.to_telegraph()
        inline_query_result = [
            InlineQueryResultArticle(
                id=str(uuid4()),
                title=note.title,
                input_message_content=InputTextMessageContent(
                    message_text=f"📕 [{tg_msg_escape_markdown_v2(note.title)}]({note.url})\n{f"\n{tg_msg_escape_markdown_v2(note.share_content)}" if note.share_content.strip() else ""}{f"\n{tg_msg_escape_markdown_v2(note.tag_string)}" if note.tags else ""}\n\n👤 [@{tg_msg_escape_markdown_v2(note.user['name'])}](https://www.xiaohongshu.com/user/profile/{note.user['id']})\n\n📰 [View via Telegraph]({telegraph_url})",
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
        if with_xsec_token:
            inline_query_result.append(
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title=note.title,
                    input_message_content=InputTextMessageContent(
                        message_text=f"📕 [{tg_msg_escape_markdown_v2(note.title)}]({note.url})\n{f"\n{tg_msg_escape_markdown_v2(note.share_content)}" if note.share_content.strip() else ""}{f"\n{tg_msg_escape_markdown_v2(note.tag_string)}" if note.tags else ""}\n\n👤 [@{tg_msg_escape_markdown_v2(note.user['name'])}](https://www.xiaohongshu.com/user/profile/{note.user['id']})\n\n📰 [View via Telegraph]({telegraph_url})",
                        parse_mode=ParseMode.MARKDOWN_V2,
                        link_preview_options=LinkPreviewOptions(
                            is_disabled=False,
                            url=telegraph_url,
                            prefer_large_media=True
                        ),
                    ),
                    description="Telegraph URL with xiaohongshu.com URL (no xsec_token)",
                    thumbnail_url=note.thumbnail
                )
            )
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
            filters.TEXT & (~ filters.COMMAND) & (
                filters.Entity(MessageEntity.URL) |
                filters.Entity(MessageEntity.TEXT_LINK)
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