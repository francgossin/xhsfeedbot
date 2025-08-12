import asyncio, logging, re, requests, json, time, pytz, threading, random, traceback
from telegram.ext import filters, MessageHandler, ApplicationBuilder, CommandHandler, ContextTypes, InlineQueryHandler
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent, MessageEntity, InputMediaPhoto, InputMediaVideo, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultPhoto, InlineQueryResultVideo
from telegram.constants import ParseMode
from urllib.parse import unquote, urljoin, urlparse, parse_qs, quote_plus
from uuid import uuid4
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from httpcore._exceptions import ReadTimeout
from json.decoder import JSONDecodeError
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
from selenium.common.exceptions import ElementNotInteractableException

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

class WebPage:
    def __init__(self):
        self.scroll_distance = 0
        try:
            with open('./cookie.json', 'r+', encoding="utf-8") as c:
                self.cookies = json.load(c)
                logging.info(f"cookie load FROM FILE:\n{self.cookies}")
                c.close()
            with open('./headers.json', 'r+', encoding="utf-8") as h:
                self.headers = json.load(h)
                logging.info(f"header load FROM FILE:\n{self.headers}")
                h.close()
        except:
            logging.error(f"no previous cache!\n{traceback.format_exc()}")
        options = webdriver.ChromeOptions()
        options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        options.add_argument("user-data-dir=selenium")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument('--remote-debugging-pipe')
        options.add_argument("--log-level=3")
        logging.info("try start selenium now")
        self.driver = webdriver.Chrome(options)
        self.actions = ActionChains(self.driver)
        # self.driver.add_cookie(self.cookies)
        self.open_url()
        self.init_page()
        self.lock = threading.Lock()
    
    def init_page(self):
        try:
            if self.driver.find_elements(By.XPATH, '//*[@class="icon-btn-wrapper close-button"]') or self.driver.find_elements(By.XPATH, '//*[@class="login-reason"]'):
                self.close_login_window()
        except Exception as e:
            logging.error(f'ERROR\n{traceback.format_exc()}')

    def open_url(self):
        self.driver.get("https://www.xiaohongshu.com/explore")

    def get_cookie_from_webdriver(self):
        cookies = self.driver.get_cookies()
        return {i["name"]: i["value"] for i in cookies if "xiaohongshu.com" in i["domain"]}

    def get_headers_from_webdriver(self):
        return {
            "accept" : "*/*",
            "accept-language" : "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "access-control-request-headers" : "x-b3-traceid,x-s,x-s-common,x-t,x-xray-traceid",
            "access-control-request-method" : "GET",
            "origin" : "https://www.xiaohongshu.com",
            "priority" : "u=1, i",
            "referer" : "https://www.xiaohongshu.com/",
            "sec-fetch-dest" : "empty",
            "sec-fetch-mode" : "cors",
            "sec-fetch-site" : "same-site",
        }

        # log = self.driver.get_log('performance')
        # for each in log:
        #     if 'explore' in each['message']:
        #         m = json.loads(each['message'])
        #         d = m['message']['params']
        #         if 'request' in d:
        #             if 'https://www.xiaohongshu.com/explore' in d['request']['url']:
        #                 if d['request']['headers'] is not None:
        #                     return d['request']['headers']
        # else:
        #     return self.headers
    
    def close_login_window(self):
        try:
            self.driver.find_element(By.XPATH, '//*[@class="icon-btn-wrapper close-button"]').click()
        except:
            login_reason = self.driver.find_elements(By.XPATH, '//*[@class="login-reason"]')
            if len(login_reason) > 0:
                self.actions.move_to_element_with_offset(login_reason[0], 0,0)
                self.actions.move_by_offset(0, -200).click().perform()
    
    def random_choose_note_to_view(self):
        random.choice(self.driver.find_elements(By.XPATH, "//a[contains(@href, '/explore/')]/..")).click()
        time.sleep(random.randint(3,15))
        if random.random() < 0.335:
            self.driver.find_element(By.XPATH, "//div[@class='close close-mask-dark']").click()
        else:
            self.driver.get(
                f"{random.choice(self.driver.find_elements(By.XPATH, "//*[contains(@href, '/explore/')][contains(@href, 'xsec_token')]")).get_attribute('href')}"
            )
            self.scroll_distance = 0
    
    def scroll_down_for_more_note(self):
        if random.random() < 0.7:
            self.scroll_distance += random.randint(500, 800)
        else:
            self.scroll_distance -= random.randint(500, 800)
        logging.info(f"window.scrollTo(0, {self.scroll_distance})")
        self.driver.execute_script(f"window.scrollTo(0, {self.scroll_distance})")
    
    def go_home(self):
        self.open_url()

    def keep_cookie_alive(self):
        while True:
            self.acts = [self.open_url, self.random_choose_note_to_view, self.scroll_down_for_more_note, self.go_home]
            try:
                # with self.lock:
                #     cs = self.get_cookie_from_webdriver()
                #     if cs is not None:
                #         self.cookies = cs
                #     hs = self.get_headers_from_webdriver()
                #     if hs is not None:
                #         self.headers = hs
                # with open('./cookie.json', 'wb+') as c:
                #     c.write(
                #         json.dumps(
                #             self.cookies,
                #             sort_keys=True,
                #             indent=4,
                #             separators=(',', ': '),
                #             ensure_ascii=False
                #     ).encode('utf8'))
                #     c.close()
                # with open('./headers.json', 'wb+') as h:
                #     h.write(
                #         json.dumps(
                #             self.headers,
                #             sort_keys=True,
                #             indent=4,
                #             separators=(',', ': '),
                #             ensure_ascii=False
                #     ).encode('utf8'))
                #     h.close()
                for i in range(random.randint(2,10)):
                    a = random.choice(self.acts)
                    logging.info(f"{i} th ACTION! -> {a}")
                    try:
                        a()
                    except:
                        continue
                    t = random.randint(5, 30)
                    logging.info(f"{i} th ACTION! -> {t}s sleep")
                    time.sleep(t)
                    if random.random() <= 0.05:
                        l = random.randint(300, 500)
                        logging.info(f"{i} th ACTION! -> {l}s sleep")
                        time.sleep(l)
            except ElementNotInteractableException:
                logging.error('ElementNotInteractableException')
            except Exception as e:
                logging.error(f"Error refreshing cookie!\n{traceback.format_exc()}")
                time.sleep(random.randint(10, 20))

class Note:
    def __init__(self, noteId: str, xsec_token: str, webpage: WebPage, typ: str, xhslink: str):
        self.noteId = noteId
        self.typ = typ # explore, discovery/item
        self.xhslink = xhslink
        self.url = f"https://www.xiaohongshu.com/{self.typ}/{self.noteId}?xsec_token={xsec_token}"
        self.data = self.get_note_data(xsec_token)
        with open(f'./note_data/{self.noteId}.json', 'wb+')as f:
            f.write(
                json.dumps(
                    self.data,
                    sort_keys=True,
                    indent=4,
                    separators=(',', ': '),
                    ensure_ascii=False
                ).encode('utf-8')
            )
            f.close()
        self.type = self.data["type"] # normal, video
        self.user = self.data["user"]
        if self.data["title"] != "":
            self.title = self.data["title"]
        else:
            self.title = " "
        self.desc = self.data["desc"]
        self.collectedCount = self.data["interactInfo"]["collectedCount"]
        self.commentCount = self.data["interactInfo"]["commentCount"]
        self.likedCount = self.data["interactInfo"]["likedCount"]
        self.shareCount = self.data["interactInfo"]["shareCount"]
        if "ipLocation" in self.data:
            self.ipLocation = self.data["ipLocation"]
        else:
            self.ipLocation = "ip address unknown"
        self.time = self.data["time"]
        self.lastUpdateTime = self.data["lastUpdateTime"]
        self.tagList = self.data["tagList"]
        self.xsecToken = self.data["xsecToken"]
        if self.type == "normal":
            self.imageList = self.data["imageList"]
            self.get_image_list_data()
        elif self.type == "video":
            self.video = self.data["video"]
            self.get_video_data()
        self.webpage = webpage

    def get_note_data(self, xsec_token: str) -> dict:
        with webpage.lock:
            self.cookies = webpage.get_cookie_from_webdriver()
            self.headers = webpage.get_headers_from_webdriver()
        logging.info(f'\n\nurl=\'{self.url}\'\n\ncookies={self.cookies}\n\n')
        req = requests.get(
            self.url,
            cookies=self.cookies,
            # headers=self.headers,
        )
        logging.info(f"try url: {self.url}")
        response = req.text
        self.soup = BeautifulSoup(response,"html.parser")
        try:
            self.preload = self.soup.find_all("link", rel="preload")[0]["href"]
        except:
            self.preload = "https://picasso-static.xiaohongshu.com/fe-platform/0014d22afee72e538cadbe0be76e06bd1ebe55ec.png"
        try:
            data = json.loads(self.soup.find_all("script")[-1].contents[0].replace("window.__INITIAL_STATE__=", '').replace("undefined", "\"undefined\"").replace("\"\"undefined\"\"", "\"undefined\""))["note"]["noteDetailMap"][self.noteId]["note"]
            if "type" in data:
                return data
            else:
                raise Exception
        except:
            with open(f'./note_data/error/{self.noteId}-JSONDecodeError.json', 'w+', encoding="utf-8") as f:
                f.write(self.soup.find_all("script")[-1].contents[0].replace("window.__INITIAL_STATE__=", '').replace("undefined", "\"undefined\"").replace("\"\"undefined\"\"", "\"undefined\""))

            req = requests.get(
                self.xhslink,
                cookies=self.cookies,
                # headers=self.headers,
            )
            logging.warning(f'try xhslink\n{self.xhslink}')
            response = req.text
            try:
                data = json.loads(self.soup.find_all("script")[-1].contents[0].replace("window.__INITIAL_STATE__=", '').replace("undefined", "\"undefined\"").replace("\"\"undefined\"\"", "\"undefined\""))["note"]["noteDetailMap"][self.noteId]["note"]
                if "type" in data:
                    return data
                else:
                    raise Exception
            except:
                if 'discovery/item' in self.url:
                    u = self.url.replace('discovery/item', 'explore')
                elif 'explore' in self.url:
                    u = self.url.replace('explore', 'discovery/item')
                else:
                    u = self.url
                    logging.info(f"???{u}???")
                logging.info(f"{u}")
                req = requests.get(
                    u,
                    cookies=self.cookies,
                )
                response = req.text
                try:
                    data = json.loads(self.soup.find_all("script")[-1].contents[0].replace("window.__INITIAL_STATE__=", '').replace("undefined", "\"undefined\"").replace("\"\"undefined\"\"", "\"undefined\""))["note"]["noteDetailMap"][self.noteId]["note"]
                    if "type" in data:
                        return data
                    else:
                        raise Exception
                except:
                    return

    def get_image_list_data(self):
        self.imageListData = []
        for img in self.imageList:
            WB_DFT = [i["url"] for i in img["infoList"] if i["imageScene"] == "WB_DFT"][0]
            data = {'Data': WB_DFT}
            if img["livePhoto"]:
                for encode in img["stream"]:
                    if len(img["stream"][encode]) > 0:
                        data["livePhotoData"] = img["stream"][encode][0]["masterUrl"]
                        break
            self.imageListData.append(data)
        return self.imageListData

    def get_video_data(self):
        self.videoData = [v["masterUrl"] for v in self.data["video"]["media"]["stream"]["h264"]]
        return self.videoData

    def note_to_telegram_msg(self):
        self.telegram_msg = {}
        preview_len = 233
        self.telegram_msg["preview_text"] = f"""<a href="https://www.xiaohongshu.com/user/profile/{self.user["userId"]}">@{self.user["nickname"]}</a> :: <a href="https://www.xiaohongshu.com/{self.typ}/{self.noteId}">[[ {self.title} ]]</a>
<blockquote>{self.desc[:preview_len]}...</blockquote>
<blockquote>👍 {self.likedCount} | ⭐️ {self.collectedCount} | 💬 {self.commentCount}
📍 {self.ipLocation}
{get_time_emoji(self.time)} {convert_timestamp_to_timestr(self.time/1000, 'Asia/Shanghai')}
✏️ {convert_timestamp_to_timestr(self.lastUpdateTime/1000, 'Asia/Shanghai')}</blockquote>"""

        if self.type == "normal":
            self.telegram_msg["media"] = []
            self.telegram_msg["inline_media"] = []
            for n, img in enumerate(self.imageListData):
                self.telegram_msg["media"].append(InputMediaPhoto(img["Data"]))
                self.telegram_msg["inline_media"].append(InlineQueryResultPhoto(
                        id=str(uuid4()),
                        photo_url=img["Data"],
                        thumbnail_url=img["Data"],
                        title=f"{n + 1} th photo",
                        description=f"{self.title}",
                        caption=self.telegram_msg["preview_text"],
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup(
                            [ [ InlineKeyboardButton("View More", url=f"tg://resolve?domain=xhsfeedbot&text=https://xiaohongshu.com/{self.typ}/{self.noteId}?xsec_token={self.xsecToken}"), ] ]
                        )
                    ),
                )
                if "livePhotoData" in img:
                    self.telegram_msg["media"].append(InputMediaVideo(
                        requests.get(img["livePhotoData"]).content),
                    )
                    self.telegram_msg["inline_media"].append(InlineQueryResultVideo(
                        id=str(uuid4()),
                        video_url=img["livePhotoData"],
                        mime_type="video/mp4",
                        thumbnail_url=img["Data"],
                        title=f"live video of {n + 1} th photo",
                        description=f"{self.title}",
                        caption=self.telegram_msg["preview_text"],
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup(
                            [ [ InlineKeyboardButton("View More", url=f"tg://resolve?domain=xhsfeedbot&text=https://xiaohongshu.com/{self.typ}/{self.noteId}?xsec_token={self.xsecToken}"), ] ]
                        )
                    ))
        if self.type == "video":
            self.telegram_msg["media"] = [InputMediaVideo(requests.get(v).content) for v in self.videoData]
            self.telegram_msg["inline_media"] = [InlineQueryResultVideo(
                id=str(uuid4()),
                video_url=v,
                mime_type="video/mp4",
                title=f"Video",
                description=f"{self.title}",
                thumbnail_url=self.preload,
                caption=self.telegram_msg["preview_text"],
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(
                    [ [ InlineKeyboardButton("View More", url=f"tg://resolve?domain=xhsfeedbot&text=https://xiaohongshu.com/{self.typ}/{self.noteId}?xsec_token={self.xsecToken}"), ] ]
                )
            ) for v in self.videoData]
        logging.info(self.url)
        self.telegram_msg["msg"] = [f"""<a href="https://www.xiaohongshu.com/user/profile/{self.user["userId"]}">@{self.user["nickname"]}</a> :: <a href="https://www.xiaohongshu.com/{self.typ}/{self.noteId}">[[ {self.title} ]]</a>
<blockquote>{self.desc}</blockquote>
<blockquote>👍 {self.likedCount} | ⭐️ {self.collectedCount} | 💬 {self.commentCount}
📍 {self.ipLocation}
{get_time_emoji(self.time)} {convert_timestamp_to_timestr(self.time/1000, 'Asia/Shanghai')}
✏️ {convert_timestamp_to_timestr(self.lastUpdateTime/1000, 'Asia/Shanghai')}</blockquote>"""]

        logging.warning(f"MSG LENGTH: {len(self.telegram_msg["msg"][0])}!!!\n")
        split_lenth = 750
        if len(self.desc) > split_lenth:
            logging.warning("msg_TOO_LONG!!!")
            msgs = [f"<blockquote>{self.desc[i:i + split_lenth]}</blockquote>" for i in range(0, len(self.desc), split_lenth)]
            self.telegram_msg["msg"] = []
            for each in range(len(msgs)):
                if each == 0:
                    logging.info(f"MSGLIST creating, {each} th HEAD adding")
                    self.telegram_msg["msg"].append(f"""<a href="https://www.xiaohongshu.com/user/profile/{self.user["userId"]}">@{self.user["nickname"]}</a> :: <a href="https://www.xiaohongshu.com/{self.typ}/{self.noteId}">[[ {self.title} ]]</a>
{msgs[each]}""")
                elif each == len(msgs) - 1:
                    logging.info(f"MSGLIST creating, {each} th TAIL adding")
                    self.telegram_msg["msg"].append(f"""{msgs[each]}
<blockquote>👍 {self.likedCount} | ⭐️ {self.collectedCount} | 💬 {self.commentCount}
📍 {self.ipLocation}
{get_time_emoji(self.time)} {convert_timestamp_to_timestr(self.time/1000, 'Asia/Shanghai')}
✏️ {convert_timestamp_to_timestr(self.lastUpdateTime/1000, 'Asia/Shanghai')}</blockquote>""")
                else:
                    logging.info(f"MSGLIST creating, {each} th BODY adding")
                    self.telegram_msg["msg"].append(msg[each])
        return self.telegram_msg

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a xhsfeedbot, please send me a xhs link!")

def get_redirected_url(url: str) -> str:
    return unquote(requests.get(url).url.split("redirectPath=")[-1])

def get_clean_url(url: str) -> str:
    return urljoin(url, urlparse(url).path)

def get_xsec_token(redirectPath: str) -> str:
    parsed_url = urlparse(redirectPath)
    return parse_qs(parsed_url.query)['xsec_token'][0]

def get_time_emoji(timestamp: int) -> str:
    a=int(((timestamp/1000+8*3600)/900-3)/2%24)
    return f'{chr(128336+a//2+a%2*12)}'

def convert_timestamp_to_timestr(timestamp, timezone_name):
    utc_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    tz = pytz.timezone(timezone_name)
    local_dt = utc_dt.replace(tzinfo=pytz.utc).astimezone(tz)
    return local_dt.strftime('%Y-%m-%d %H:%M:%S %Z%z')

async def note2feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global webpage
    urls = re.findall(r"(https?://\S+)", update.message.text)

    if len(urls) == 0:
        logging.warning("NO URL NO URL")
        return
    xhslink = urls[0]
    keyboard = [
        [
            InlineKeyboardButton("Original Link", url=xhslink),
        ]
    ]
    redirectPath_ = get_redirected_url(xhslink)
    if len(re.findall(r"https?://(?:www.)?xhslink.com/m/[A-Za-z0-9]+", update.message.text)) > 0:
        logging.info("XHSLINK in message!")
        clean_ = get_clean_url(redirectPath_)
        parsed_url_ = urlparse(redirectPath_)
        try:
            xsec_token_ = parse_qs(parsed_url_.query)['xsec_token'][0]
        except:
            xsec_token_ = ''
        if 'xiaohongshu.com/404' not in redirectPath_:
            noteId_ = re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/discovery\/item\/([a-z0-9]+)", clean_)[0]
        else:
            noteId_ = re.findall(r"noteId=([a-z0-9]+)", redirectPath_)[0]
        typ = "discovery/item"
    elif len(re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/discovery\/item\/[0-9a-z]+", update.message.text)) > 0:
        logging.info("DISCOVERY/ITEM in message!")
        clean_ = get_clean_url(urls[0])
        noteId_ = re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/discovery\/item\/([a-z0-9]+)", clean_)[0]
        parsed_url_ = urlparse(urls[0])
        try:
            xsec_token_ = parse_qs(parsed_url_.query)['xsec_token'][0]
        except:
            xsec_token_ = ''
        typ = "discovery/item"
    elif len(re.findall(r"https?://(?:www.)?xiaohongshu.com/explore/[a-z0-9]+", update.message.text)) > 0:
        logging.info("EXPLORE in message!")
        clean_ = get_clean_url(urls[0])
        noteId_ = re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/explore\/([a-z0-9]+)", clean_)[0]
        parsed_url_ = urlparse(urls[0])
        try:
            xsec_token_ = parse_qs(parsed_url_.query)['xsec_token'][0]
        except:
            xsec_token_ = ''
        typ = "explore"
    else:
        logging.warning(f"NOTHING in message:\n{update.message.text}")
        logging.warning(f"explore: {re.findall(r"https?://(?:www.)?xiaohongshu.com/explore/[a-z0-9]+", update.message.text)}\n")
        logging.warning(f"discovery/item: {re.findall(r"https?://(?:www.)?.xiaohongshu.com/discovery/item/[a-z0-9]+", update.message.text)}\n")
        logging.warning(f"xhslink: {re.findall(r"https?://xhslink.com/m/[A-Za-z0-9]+", update.message.text)}")
        return
    logging.info(f'typ:{typ}\noriginal:{urls}\nredirectPath_:{redirectPath_}\nnoteId: {noteId_}\nxsec_token:{xsec_token_}\nparsed_url_:{parsed_url_}')
    keyboard[0].append(
        InlineKeyboardButton("Link with xsec_token", url=f"https://xiaohongshu.com/{typ}/{noteId_}?xsec_token={xsec_token_}"),
    )
    try:
        note = Note(noteId=noteId_, xsec_token=xsec_token_, webpage=webpage, typ=typ, xhslink=xhslink)
        keyboard[0].append(
            InlineKeyboardButton(
                "Author link with xsec_token", url=f"https://www.xiaohongshu.com/user/profile/{note.user["userId"]}?{note.user["xsecToken"]}"
            )
        )
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"Clean Url: https://xiaohongshu.com/{typ}/{noteId_}\nAuthor link: https://www.xiaohongshu.com/user/profile/{note.user["userId"]}", reply_markup=reply_markup)
        msg = note.note_to_telegram_msg()
        if len(msg["media"]) <= 10:
            await context.bot.send_media_group(
                chat_id=update.effective_chat.id, media=msg["media"],
                reply_to_message_id=update.message.message_id,
                caption=msg["msg"][0],
                parse_mode=ParseMode.HTML,
            )
        else:
            for i in range(len(msg["media"]) // 10 + 1):
                logging.info(f"MEDIA GOURP {i} SENDING!")
                if i < len(msg["media"]) // 10:
                    await context.bot.send_media_group(
                        chat_id=update.effective_chat.id, media=msg["media"][i * 10: (i + 1) * 10],
                        reply_to_message_id=update.message.message_id,
                    )
                else:
                    await context.bot.send_media_group(
                        chat_id=update.effective_chat.id, media=msg["media"][i * 10: (i + 1) * 10],
                        reply_to_message_id=update.message.message_id,
                        caption=msg["msg"][0],
                        parse_mode=ParseMode.HTML,
                    )
        logging.info(f"MSGLIST LEN: {len(msg["msg"])}")
        if len(msg["msg"]) > 1:
            logging.info(f"REMAINING MESSAGE SHOULD BE SENT")
            for each in range(1, len(msg["msg"])):
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,        
                    reply_to_message_id=update.message.message_id,
                    text=msg["msg"][each],
                    parse_mode=ParseMode.HTML
                )
    except Exception as e:
        logging.error(f'Error! {traceback.format_exc()}')
        await context.bot.send_message(
            chat_id=update.effective_chat.id,        
            reply_to_message_id=update.message.message_id,
            text=f"Error!\n{e}\nPlease try again.")

async def inline_note2feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    if not query:
        return
    urls = re.findall(r"(https?://\S+)", query)
    if len(urls) == 0:
        return
    results = []
    xhslink = urls[0]
    keyboard = [
        [
            InlineKeyboardButton("Original Link", url=xhslink),
        ]
    ]
    redirectPath_ = get_redirected_url(xhslink)
    if re.findall(r"https?://xhslink.com/m/[A-Za-z0-9]+", query):
        clean_ = get_clean_url(redirectPath_)
        parsed_url_ = urlparse(redirectPath_)
        try:
            xsec_token_ = parse_qs(parsed_url_.query)['xsec_token'][0]
        except:
            xsec_token_ = ''
        if 'xiaohongshu.com/404' not in redirectPath_:
            noteId_ = re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/discovery\/item\/([a-z0-9]+)", clean_)[0]
        else:
            noteId_ = re.findall(r"noteId=([a-z0-9]+)", redirectPath_)[0]
        typ = "discovery/item"
    elif re.findall(r"https?://(?:www.)?xiaohongshu.com/discovery/item/[0-9a-z]+", query):
        clean_ = get_clean_url(urls[0])
        noteId_ = re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/discovery/item\/([a-z0-9]+)", clean_)[0]
        parsed_url_ = urlparse(urls[0])
        try:
            xsec_token_ = parse_qs(parsed_url_.query)['xsec_token'][0]
        except:
            xsec_token_ = ''
        typ = "discovery/item"
    elif re.findall(r"https?://(?:www.)?xiaohongshu.com/explore/[a-z0-9]+", query):
        clean_ = get_clean_url(urls[0])
        noteId_ = re.findall(r"https?:\/\/(?:www.)?xiaohongshu.com\/explore\/([a-z0-9]+)", clean_)[0]
        parsed_url_ = urlparse(urls[0])
        try:
            xsec_token_ = parse_qs(parsed_url_.query)['xsec_token'][0]
        except:
            xsec_token_ = ''
        typ = "explore"
    else:
        logging.warning(f"NOTHING in message:\n{query}")
        logging.warning(f"explore: {re.findall(r"https?://(?:www.)?xiaohongshu.com/explore/[a-z0-9]+", query)}\n")
        logging.warning(f"discovery/item: {re.findall(r"https?://(?:www.)?.xiaohongshu.com/discovery/item/[a-z0-9]+", query)}\n")
        logging.warning(f"xhslink: {re.findall(r"https?://xhslink.com/m/[A-Za-z0-9]+", query)}")
        return
    logging.info(f'typ:{typ}\noriginal:{urls}\nredirectPath_:{redirectPath_}\nnoteId: {noteId_}\nxsec_token:{xsec_token_}\nparsed_url_:{parsed_url_}')
    keyboard[0].append(
        InlineKeyboardButton("Link with xsec_token", url=f"https://xiaohongshu.com/{typ}/{noteId_}?xsec_token={xsec_token_}"),
    )
    try:
        note = Note(noteId=noteId_, xsec_token=xsec_token_, webpage=webpage, typ=typ, xhslink=xhslink)
        keyboard.append([(
            InlineKeyboardButton(
                "Author link with xsec_token", url=f"https://www.xiaohongshu.com/user/profile/{note.user["userId"]}?{note.user["xsecToken"]}"
            )
        )])
        reply_markup = InlineKeyboardMarkup(keyboard)
        results.append(
            InlineQueryResultArticle(
                id=str(uuid4()),
                title="Clean URL",
                description=f"{note.title}",
                input_message_content=InputTextMessageContent(message_text=f"Clean Url: https://xiaohongshu.com/{typ}/{noteId_}\nAuthor link: https://www.xiaohongshu.com/user/profile/{note.user["userId"]}"),
                reply_markup=reply_markup
            )
        )
        msg = note.note_to_telegram_msg()
        results += msg["inline_media"]
        await context.bot.answer_inline_query(update.inline_query.id, results)
    except Exception as e:
        logging.error(f'Error! {traceback.format_exc()}')

def start_keep_cookie_thread(webpage: WebPage):
    t = threading.Thread(target=webpage.keep_cookie_alive, daemon=True)
    t.start()
    logging.info("Cookie keep-alive thread started.")

def main():
    start_keep_cookie_thread(webpage)

    application = ApplicationBuilder()\
        .token("Bot::Token")\
        .read_timeout(60)\
        .write_timeout(60)\
        .build()

    start_handler = CommandHandler("start", start)
    application.add_handler(start_handler)

    inline_note2feed_handler = InlineQueryHandler(inline_note2feed)
    application.add_handler(inline_note2feed_handler)

    note2feed_handler = MessageHandler(
        filters.TEXT,
        note2feed
    )
    application.add_handler(note2feed_handler)

    application.run_polling()

if __name__ == "__main__":
    webpage = WebPage()
    asyncio.run(main())
