import asyncio, logging, re, requests, json, time, pytz, threading, random, traceback
from telegram.ext import filters, MessageHandler, ApplicationBuilder, CommandHandler, ContextTypes, InlineQueryHandler
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent, MessageEntity, InputMediaPhoto, InputMediaVideo
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

class WebPage:
    def __init__(self):
        self.scroll_distance = 0
        try:
            with open('./cookie.json', 'r') as c:
                self.cookies = json.load(c)
                logging.info(f"cookie load FROM FILE:\n{self.cookies}")
                c.close()
            with open('./headers.json', 'r') as h:
                self.headers = json.load(h)
                logging.info(f"header load FROM FILE:\n{self.headers}")
                h.close()
        except:
            logging.error(f"no previous cache!\n{traceback.format_exc()}")
        options = webdriver.ChromeOptions()
        options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        options.add_argument("user-data-dir=selenium")
        self.driver = webdriver.Chrome(options)
        self.actions = ActionChains(self.driver)
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
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'priority': 'u=0, i',
            'sec-ch-ua': '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
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
        self.driver.find_element(By.XPATH, "//div[@class='close close-mask-dark']").click()
    
    def scroll_down_for_more_note(self):
        self.scroll_distance += random.randint(500, 800)
        self.driver.execute_script(f"window.scrollTo(0, {self.scroll_distance})")

    def keep_cookie_alive(self):
        while True:
            self.acts = [self.open_url, self.random_choose_note_to_view, self.scroll_down_for_more_note]
            try:
                time.sleep(6)
                with self.lock:
                    cs = self.get_cookie_from_webdriver()
                    if cs is not None:
                        self.cookies = cs
                    hs = self.get_headers_from_webdriver()
                    if hs is not None:
                        self.headers = hs
                with open('./cookie.json', 'wb+') as c:
                    c.write(
                        json.dumps(
                            self.cookies,
                            sort_keys=True,
                            indent=4,
                            separators=(',', ': '),
                            ensure_ascii=False
                    ).encode('utf8'))
                    c.close()
                with open('./headers.json', 'wb+') as h:
                    h.write(
                        json.dumps(
                            self.headers,
                            sort_keys=True,
                            indent=4,
                            separators=(',', ': '),
                            ensure_ascii=False
                    ).encode('utf8'))
                    h.close()
                for i in range(random.randint(2,10)):
                    random.choice(self.acts)()
                    time.sleep(random.randint(5, 30))
                    if random.random() <= 0.05:
                        time.sleep(random.randint(300, 500))
            except ElementNotInteractableException:
                logging.error('ElementNotInteractableException')
            except Exception as e:
                logging.error(f"Error refreshing cookie!\n{traceback.format_exc()}")
                time.sleep(random.randint(10, 20))

class Note:
    def __init__(self, noteId: str, xsec_token: str, webpage: WebPage):
        self.noteId = noteId
        self.data = self.get_note_data(xsec_token)
        with open(f'./note_data/{self.noteId}.json', 'wb+') as f:
            f.write(
                json.dumps(
                    self.data,
                    sort_keys=True,
                    indent=4,
                    separators=(',', ': '),
                    ensure_ascii=False
            ).encode('utf8')
        )
        self.type = self.data["type"] # normal, video
        self.user = self.data["user"]
        self.title = self.data["title"]
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
        self.url = f"https://www.xiaohongshu.com/explore/{self.noteId}?xsec_token={xsec_token}&xsec_source=pc_feed"
        self.webpage = webpage

    def get_note_data(self, xsec_token: str) -> dict:
        with webpage.lock:
            self.cookies = webpage.get_cookie_from_webdriver()
            self.headers = webpage.get_headers_from_webdriver()
            logging.info(f'get_cookies from webpage:\n{self.cookies}\nget_headers from webpage:\n{self.headers}')
        response = requests.get(
            f"https://www.xiaohongshu.com/explore/{self.noteId}?xsec_token={xsec_token}&xsec_source=pc_feed",
            cookies=self.cookies,
            headers=self.headers,
        ).text
        try:
            data = json.loads(BeautifulSoup(
                response,
                "html.parser"
            ).find_all("script")[-1].contents[0].replace("window.__INITIAL_STATE__=", '').replace("undefined", "\"undefined\"").replace("\"\"undefined\"\"", "\"undefined\""))["note"]["noteDetailMap"][self.noteId]["note"]
            return data
        except:
            with open(f'./note_data/error/{self.noteId}-JSONDecodeError.json', 'w+') as f:
                f.write(BeautifulSoup(
                response,
                "html.parser"
            ).find_all("script")[-1].contents[0].replace("window.__INITIAL_STATE__=", '').replace("undefined", "\"undefined\"").replace("\"\"undefined\"\"", "\"undefined\""))
            return {}

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
        if self.type == "normal":
            self.telegram_msg["media"] = []
            for img in self.imageListData:
                self.telegram_msg["media"].append(InputMediaPhoto(img["Data"]))
                if "livePhotoData" in img:
                    self.telegram_msg["media"].append(InputMediaVideo(requests.get(img["livePhotoData"]).content))
        if self.type == "video":
            self.telegram_msg["media"] = [InputMediaVideo(requests.get(v).content) for v in self.videoData]
        logging.info(self.url)
        self.telegram_msg["msg"] = f"""<a href="https://www.xiaohongshu.com/user/profile/{self.user["userId"]}?xsec_token={quote_plus(self.user["xsecToken"])}&xsec_source=app_share&xhsshare=CopyLink">{self.user["nickname"]}</a>: <a href="{self.url}">{self.title}</a>
<blockquote>{self.desc}</blockquote>
👍 {self.likedCount} | ⭐️ {self.collectedCount} | 💬 {self.commentCount}
📍 {self.ipLocation}
{get_time_emoji(self.time)} {convert_timestamp_to_timestr(self.time/1000, 'Asia/Shanghai')}
✏️ {convert_timestamp_to_timestr(self.lastUpdateTime/1000, 'Asia/Shanghai')}"""
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
        return
    redirectPath_ = get_redirected_url(urls[0])
    if re.findall(r"https?://www.xiaohongshu.com/discovery/item/[0-9a-z]+", update.message.text):
        clean_ = get_clean_url(urls[0])
        noteId_ = re.findall(r"https?:\/\/www.xiaohongshu.com\/discovery/item\/([a-z0-9]+)", clean_)[0]
        parsed_url_ = urlparse(urls[0])
        xsec_token_ = parse_qs(parsed_url_.query)['xsec_token'][0]
    elif re.findall(r"https?://xhslink.com/m/[A-Za-z0-9]+", update.message.text):
        clean_ = get_clean_url(redirectPath_)
        parsed_url_ = urlparse(redirectPath_)
        xsec_token_ = parse_qs(parsed_url_.query)['xsec_token'][0]
        noteId_ = re.findall(r"https?:\/\/www.xiaohongshu.com\/discovery\/item\/([a-z0-9]+)", clean_)[0]
    elif re.findall(r"https?://www.xiaohongshu.com/explore/[a-z0-9]+", update.message.text):
        clean_ = get_clean_url(urls[0])
        noteId_ = re.findall(r"https?:\/\/www.xiaohongshu.com\/explore\/([a-z0-9]+)", clean_)[0]
        parsed_url_ = urlparse(urls[0])
        xsec_token_ = parse_qs(parsed_url_.query)['xsec_token'][0]
    else:
        return
    logging.info(f'original:{urls}\nredirectPath_:{redirectPath_}\nnoteId: {noteId_}\nxsec_token:{xsec_token_}\nparsed_url_:{parsed_url_}')
    try:
        note = Note(noteId=noteId_, xsec_token=xsec_token_, webpage=webpage)
        msg = note.note_to_telegram_msg()
        if len(msg["media"]) <= 10:
            await context.bot.send_media_group(
                chat_id=update.effective_chat.id, media=msg["media"],
                reply_to_message_id=update.message.message_id,
                caption=msg["msg"],
                parse_mode=ParseMode.HTML
            )
        else:
            for i in range(len(msg["media"]) // 10 + 1):
                if i < len(msg["media"]) // 10:
                    await context.bot.send_media_group(
                        chat_id=update.effective_chat.id, media=msg["media"][i * 10: (i + 1) * 10],
                        reply_to_message_id=update.message.message_id,
                    )
                else:
                    await context.bot.send_media_group(
                        chat_id=update.effective_chat.id, media=msg["media"][i * 10: (i + 1) * 10],
                        reply_to_message_id=update.message.message_id,
                        caption=msg["msg"],
                        parse_mode=ParseMode.HTML
                    )
    except Exception as e:
        logging.error(f'Error! {traceback.format_exc()}')
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Error!\n{e}\nPlease try again.")

def start_keep_cookie_thread(webpage: WebPage):
    t = threading.Thread(target=webpage.keep_cookie_alive, daemon=True)
    t.start()
    logging.info("Cookie keep-alive thread started.")

def main():
    start_keep_cookie_thread(webpage)

    application = ApplicationBuilder().token("Bot::Token").build()
    start_handler = CommandHandler("start", start)
    application.add_handler(start_handler)

    note2feed_handler = MessageHandler(
        filters.TEXT & (
            filters.Entity(MessageEntity.URL) |
            filters.Entity(MessageEntity.TEXT_LINK)
        ),
        note2feed
    )
    application.add_handler(note2feed_handler)

    application.run_polling()

if __name__ == "__main__":
    webpage = WebPage()
    asyncio.run(main())
