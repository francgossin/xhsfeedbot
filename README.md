# xhsfeedbot
[![Require: Python 3.13](https://img.shields.io/badge/Python-3.13-blue?logo=python)](https://www.python.org/)

[![Require: mitmproxy 12.1.2](https://img.shields.io/badge/mitmproxy-12.1.2-blue)](https://pypi.org/project/mitmproxy/)
[![Require: python-telegram-bot 22.4](https://img.shields.io/badge/python--telegram--bot-22.4-blue)](https://pypi.org/project/python-telegram-bot/)
[![Require: telegraph 2.2.0](https://img.shields.io/badge/telegraph-2.2.0-blue)](https://pypi.org/project/telegraph/)
[![Require: Flask 3.1.2](https://img.shields.io/badge/Flask-3.1.2-blue)](https://pypi.org/project/Flask/)
[![Require: pytz 2025.2](https://img.shields.io/badge/pytz-2025.2-blue)](https://pypi.org/project/pytz/)
[![Require: python-dotenv 1.1.1](https://img.shields.io/badge/python--dotenv-1.1.1-blue)](https://pypi.org/project/python-dotenv/)
[![Require: requests 2.32.5](https://img.shields.io/badge/requests-2.32.5-blue)](https://pypi.org/project/requests/)
[![Require: paramiko 4.0.0](https://img.shields.io/badge/paramiko-4.0.0-blue)](https://www.paramiko.org/)

[![Android](https://img.shields.io/badge/Android-3DDC84?logo=android&logoColor=white)](#)
[![iOS](https://img.shields.io/badge/iOS-000000?&logo=apple&logoColor=white)](#)

[![Linux](https://img.shields.io/badge/Linux-FCC624?logo=linux&logoColor=black)](#)
[![macOS](https://img.shields.io/badge/macOS-000000?logo=apple&logoColor=F0F0F0)](#)
[![Windows](https://custom-icon-badges.demolab.com/badge/Windows-0078D6?logo=windows11&logoColor=white)](#)

A bot that forward REDNote to Telegram Message or Telegraph

[![Telegram Channel](https://img.shields.io/badge/Telegram-Channel-green.svg?logo=telegram)](https://t.me/xhsfeed)
[![xhsfeed Bot](https://img.shields.io/badge/xhsfeed-Bot-green?logo=telegram)](https://t.me/xhsfeedbot)

## Requirements

1. Server side: Python 3.13 or newer on Linux, macOS or Windows.

2. Device side: A rooted Android device or emulator, or jailbroken iOS device, with REDNote app installed.

3. Both server and device must be in the same network, and server side should has stable access to Telegram and Telegraph server.

## How it works
![](./res/diagram.png)

## Deployment guide

### Server side
Download [platform-tools](https://developer.android.com/tools/releases/platform-tools) and add `adb` to `PATH` if you are using a Android device.

```bash
git clone https://github.com/francgossin/xhsfeedbot.git
cd xhsfeedbot
mkdir -p data
mkdir -p log
python3.13 -m venv .venv
```
Create a `.env` file with your own configuration.
```python
BOT_TOKEN='Telegram Bot Token'
ADMIN_ID='Bot Owner Telegram ID'

# 0: Android with root; 1: Jailbroken iOS
TARGET_DEVICE_TYPE=1

# ssh information neccessary if your target device type is jailbroken iOS
SSH_IP=127.0.0.1 # device IP address
SSH_PORT=22 # device ssh port, defaut 22
SSH_USERNAME=root
SSH_PASSWORD=alpine
# Default user name and password for jailbroken iOS. You may have to configure your own.
```
Open three terminal windows or use screen, start all three scripts.
```bash
source .venv/bin/activate
python xhsfeedbot.py
```

```bash
source .venv/bin/activate
python mitm_server.py
```

```bash
source .venv/bin/activate
python shared_server.py
```
### Device side

Start `mitm_server.py` and set device proxy on Wi-Fi settings.

Host: server side IP address.

Port: mitm server's port number.

Open [mitm.it](http://mitm.it) on device browser and follow the corresponding guide.

#### iOS devices

Check [ios.cfw.guide](https://ios.cfw.guide/) to jailbreak your iOS device. 

Then install `OpenSSH` through APT package manager for jailbroken iOS like Cydia or Sileo.

#### Android devices
Guide of [Android Emulator](https://docs.mitmproxy.org/stable/howto/install-system-trusted-ca-android/)

If you are not using an emulator, you need to root your device and then manually move CA certificate to system partition and reboot.