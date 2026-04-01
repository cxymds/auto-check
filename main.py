"""
cron: 0 */6 * * *
new Env("Linux.Do 签到")
"""

import argparse
import functools
import os
import random
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests
from DrissionPage import Chromium, ChromiumOptions
from loguru import logger
from tabulate import tabulate

from notify import NotificationManager

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


def retry_decorator(retries=3, min_delay=5, max_delay=10):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == retries - 1:
                        logger.error(f"函数 {func.__name__} 最终执行失败: {str(e)}")
                    logger.warning(
                        f"函数 {func.__name__} 第 {attempt + 1}/{retries} 次尝试失败: {str(e)}"
                    )
                    if attempt < retries - 1:
                        sleep_s = random.uniform(min_delay, max_delay)
                        logger.info(
                            f"将在 {sleep_s:.2f}s 后重试 ({min_delay}-{max_delay}s 随机延迟)"
                        )
                        time.sleep(sleep_s)
            return None

        return wrapper

    return decorator


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"false", "0", "off", "no"}


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value.strip())
    except ValueError:
        logger.warning(f"环境变量 {name}={value!r} 不是整数，回退到默认值 {default}")
        return default


def resolve_path(raw_value: Optional[str], default: Path) -> Path:
    if raw_value and raw_value.strip():
        return Path(raw_value).expanduser().resolve()
    return default.expanduser().resolve()


class SingleInstanceLock:
    def __init__(self, path: Path):
        self.path = path
        self.file = None
        self.acquired = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("w")
        if fcntl is None:
            self.acquired = True
            self.file.write(str(os.getpid()))
            self.file.flush()
            return self

        try:
            fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.acquired = False
            return self

        self.file.seek(0)
        self.file.truncate()
        self.file.write(str(os.getpid()))
        self.file.flush()
        self.acquired = True
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self.file:
            return
        try:
            if self.acquired and fcntl is not None:
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        finally:
            self.file.close()

USERNAME = os.environ.get("LINUXDO_USERNAME") or os.environ.get("USERNAME")
PASSWORD = os.environ.get("LINUXDO_PASSWORD") or os.environ.get("PASSWORD")
COOKIES = os.environ.get("LINUXDO_COOKIES", "").strip()

HOME_URL = "https://linux.do/"
LOGIN_URL = "https://linux.do/login"
SESSION_URL = "https://linux.do/session"
CSRF_URL = "https://linux.do/session/csrf"

RUNNING_IN_GITHUB_ACTIONS = env_bool("GITHUB_ACTIONS", False)
BROWSE_ENABLED = env_bool("BROWSE_ENABLED", True)

RUNTIME_DIR = resolve_path(os.environ.get("RUNTIME_DIR"), Path(".runtime"))
BROWSER_USER_DATA_DIR = resolve_path(
    os.environ.get("BROWSER_USER_DATA_DIR"), RUNTIME_DIR / "browser-profile"
)
COOKIE_SNAPSHOT_PATH = resolve_path(
    os.environ.get("COOKIE_SNAPSHOT_PATH"), RUNTIME_DIR / "linuxdo-cookies.txt"
)
LOCK_FILE = resolve_path(os.environ.get("LOCK_FILE"), RUNTIME_DIR / "auto-check.lock")

BROWSER_PROFILE_NAME = os.environ.get("BROWSER_PROFILE_NAME", "Default").strip() or "Default"
BROWSER_HEADLESS = env_bool("BROWSER_HEADLESS", True)
BROWSER_NO_IMAGES = env_bool("BROWSER_NO_IMAGES", True)
BROWSER_NO_SANDBOX = env_bool("BROWSER_NO_SANDBOX", True)
MANUAL_LOGIN_ENABLED = env_bool("MANUAL_LOGIN_ENABLED", not RUNNING_IN_GITHUB_ACTIONS)
MANUAL_LOGIN_TIMEOUT = env_int("MANUAL_LOGIN_TIMEOUT", 300)
TOPIC_COUNT = max(env_int("TOPIC_COUNT", 10), 1)
BROWSE_SCROLL_ROUNDS = max(env_int("BROWSE_SCROLL_ROUNDS", 10), 1)
BROWSER_LOCAL_PORT = env_int("BROWSER_LOCAL_PORT", 0)
BROWSER_PATH = os.environ.get("BROWSER_PATH", "").strip()
BROWSER_PROXY = os.environ.get("BROWSER_PROXY", "").strip()
BROWSER_LOAD_MODE = os.environ.get("BROWSER_LOAD_MODE", "eager").strip().lower() or "eager"


class LinuxDoBrowser:
    def __init__(self, force_headless: Optional[bool] = None) -> None:
        from sys import platform

        self.last_failure_reason = None
        self.runtime_dir = RUNTIME_DIR
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir = self.runtime_dir / "downloads"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.force_headless = BROWSER_HEADLESS if force_headless is None else force_headless

        if platform == "linux" or platform == "linux2":
            platform_identifier = "X11; Linux x86_64"
        elif platform == "darwin":
            platform_identifier = "Macintosh; Intel Mac OS X 10_15_7"
        elif platform == "win32":
            platform_identifier = "Windows NT 10.0; Win64; x64"
        else:
            platform_identifier = "X11; Linux x86_64"

        self.browser_user_agent = (
            f"Mozilla/5.0 ({platform_identifier}) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        self.request_user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0"
        )

        co = ChromiumOptions(read_file=False)
        co.headless(self.force_headless)
        co.set_user_agent(self.browser_user_agent)
        co.set_user_data_path(str(BROWSER_USER_DATA_DIR))
        co.set_user(BROWSER_PROFILE_NAME)
        co.set_download_path(str(self.download_dir))
        co.set_timeouts(base=10, page_load=60, script=30)
        co.set_retry(times=2, interval=2)
        if BROWSER_LOAD_MODE in {"normal", "eager", "none"}:
            co.set_load_mode(BROWSER_LOAD_MODE)
        if BROWSER_NO_IMAGES:
            co.no_imgs(True)
        if BROWSER_PATH:
            co.set_browser_path(BROWSER_PATH)
        if BROWSER_PROXY:
            co.set_proxy(BROWSER_PROXY)
        if BROWSER_LOCAL_PORT > 0:
            co.set_local_port(BROWSER_LOCAL_PORT)
        else:
            co.auto_port()
        if platform.startswith("linux") and BROWSER_NO_SANDBOX:
            co.set_argument("--no-sandbox")
        co.set_argument("--disable-dev-shm-usage")

        self.browser = Chromium(co)
        self.page = self.browser.new_tab()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.request_user_agent,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )
        self.notifier = NotificationManager()

    def set_failure_reason(self, reason: str):
        self.last_failure_reason = reason
        logger.error(reason)

    @staticmethod
    def is_cloudflare_challenge_response(resp) -> bool:
        try:
            cf_mitigated = resp.headers.get("cf-mitigated", "")
            body = resp.text or ""
        except Exception:
            return False
        return (
            cf_mitigated == "challenge"
            or "Just a moment" in body
            or "cf-turnstile" in body
            or "/cdn-cgi/challenge-platform/" in body
        )

    @staticmethod
    def parse_cookie_string(cookie_str: str) -> list[dict]:
        cookies = []
        for part in cookie_str.strip().split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            name, _, value = part.partition("=")
            cookies.append(
                {
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": ".linux.do",
                    "path": "/",
                }
            )
        return cookies

    def load_cookie_snapshot(self) -> str:
        if not COOKIE_SNAPSHOT_PATH.exists():
            return ""
        try:
            content = COOKIE_SNAPSHOT_PATH.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.warning(f"读取本地 Cookie 快照失败: {e}")
            return ""
        return content

    def save_cookie_snapshot(self, cookies: Optional[list[dict]] = None):
        try:
            if cookies is None:
                cookies = list(self.browser.cookies(all_info=True))
            pairs = []
            for ck in cookies:
                domain = ck.get("domain", "")
                if "linux.do" not in domain:
                    continue
                name = ck.get("name")
                value = ck.get("value")
                if name and value:
                    pairs.append(f"{name}={value}")
            if pairs:
                COOKIE_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
                COOKIE_SNAPSHOT_PATH.write_text("; ".join(pairs), encoding="utf-8")
                logger.info(f"已更新本地 Cookie 快照: {COOKIE_SNAPSHOT_PATH}")
        except Exception as e:
            logger.warning(f"保存本地 Cookie 快照失败: {e}")

    def sync_browser_cookies_to_session(self):
        try:
            browser_cookies = list(self.browser.cookies(all_info=True))
        except Exception as e:
            logger.warning(f"同步浏览器 Cookie 失败: {e}")
            return

        self.session.cookies.clear()
        for ck in browser_cookies:
            name = ck.get("name")
            value = ck.get("value")
            domain = ck.get("domain") or "linux.do"
            path = ck.get("path") or "/"
            if not name or value is None:
                continue
            self.session.cookies.set(name, value, domain=domain, path=path)
        self.save_cookie_snapshot(browser_cookies)

    def open_home(self):
        self.page.get(HOME_URL)
        time.sleep(5)

    def is_login_or_challenge_page(self, page=None) -> bool:
        target = page or self.page
        try:
            current_url = target.url or ""
            html = target.html or ""
        except Exception:
            return True
        return (
            "/login" in current_url
            or "login-welcome__title" in html
            or "cf-turnstile" in html
            or "Just a moment" in html
            or "/cdn-cgi/challenge-platform/" in html
        )

    def is_logged_in(self, page=None) -> bool:
        target = page or self.page
        if self.is_login_or_challenge_page(target):
            return False
        try:
            user_ele = target.ele("@id=current-user")
        except Exception:
            user_ele = None
        if user_ele:
            return True
        try:
            return "avatar" in (target.html or "")
        except Exception:
            return False

    def try_login_with_browser_profile(self) -> bool:
        logger.info("尝试复用持久化浏览器会话...")
        self.open_home()
        if self.is_logged_in():
            logger.info("检测到有效的浏览器持久化会话")
            self.sync_browser_cookies_to_session()
            return True
        return False

    def login_with_cookies(self, cookie_str: str, source: str = "环境变量 Cookie") -> bool:
        logger.info(f"尝试使用{source}登录...")
        dp_cookies = self.parse_cookie_string(cookie_str)
        if not dp_cookies:
            self.set_failure_reason(f"{source} 解析失败或为空")
            return False

        for ck in dp_cookies:
            self.session.cookies.set(ck["name"], ck["value"], domain="linux.do")

        self.page.set.cookies(dp_cookies)
        self.open_home()
        if self.is_logged_in():
            logger.info(f"{source} 登录成功")
            self.sync_browser_cookies_to_session()
            return True

        self.set_failure_reason(f"{source} 登录失败，当前页面: {self.page.url}")
        return False

    def login(self) -> bool:
        logger.info("开始账号密码登录")
        headers = {
            "User-Agent": self.request_user_agent,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": LOGIN_URL,
        }
        resp_csrf = self.session.get(CSRF_URL, headers=headers, impersonate="firefox135")
        if resp_csrf.status_code != 200:
            if self.is_cloudflare_challenge_response(resp_csrf):
                self.set_failure_reason(
                    f"获取 CSRF token 失败: {resp_csrf.status_code}，疑似被 Cloudflare challenge 拦截"
                )
            else:
                self.set_failure_reason(f"获取 CSRF token 失败: {resp_csrf.status_code}")
            return False

        csrf_token = resp_csrf.json().get("csrf")
        if not csrf_token:
            self.set_failure_reason("CSRF token 为空，无法继续登录")
            return False

        headers.update(
            {
                "X-CSRF-Token": csrf_token,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": "https://linux.do",
            }
        )
        data = {
            "login": USERNAME,
            "password": PASSWORD,
            "second_factor_method": "1",
            "timezone": "Asia/Shanghai",
        }

        try:
            resp_login = self.session.post(
                SESSION_URL, data=data, impersonate="chrome136", headers=headers
            )
        except Exception as e:
            self.set_failure_reason(f"登录请求异常: {e}")
            return False

        if resp_login.status_code != 200:
            if self.is_cloudflare_challenge_response(resp_login):
                self.set_failure_reason(
                    f"登录失败，状态码: {resp_login.status_code}，疑似被 Cloudflare challenge 拦截"
                )
            else:
                self.set_failure_reason(f"登录失败，状态码: {resp_login.status_code}")
                logger.error(resp_login.text)
            return False

        response_json = resp_login.json()
        if response_json.get("error"):
            self.set_failure_reason(f"登录失败: {response_json.get('error')}")
            return False

        dp_cookies = [
            {
                "name": name,
                "value": value,
                "domain": ".linux.do",
                "path": "/",
            }
            for name, value in self.session.cookies.get_dict().items()
        ]

        self.page.set.cookies(dp_cookies)
        self.open_home()
        if self.is_logged_in():
            logger.info("账号密码登录成功")
            self.sync_browser_cookies_to_session()
            return True

        self.set_failure_reason(f"账号密码登录后仍未进入已登录态: {self.page.url}")
        return False

    def wait_for_manual_login(self, timeout_seconds: int) -> bool:
        if self.force_headless:
            self.set_failure_reason("当前是无头模式，无法执行人工登录初始化")
            return False

        logger.info(
            f"请在打开的浏览器中手动完成登录/Cloudflare 验证，等待 {timeout_seconds}s..."
        )
        self.page.get(LOGIN_URL)
        end_time = time.time() + timeout_seconds
        while time.time() < end_time:
            if self.is_logged_in():
                logger.info("检测到手动登录成功")
                self.sync_browser_cookies_to_session()
                return True
            time.sleep(3)

        self.set_failure_reason("等待人工登录超时")
        return False

    def authenticate(self, allow_manual_login: bool) -> bool:
        if self.try_login_with_browser_profile():
            return True

        if COOKIES and self.login_with_cookies(COOKIES, "环境变量 Cookie"):
            return True

        local_cookie_snapshot = self.load_cookie_snapshot()
        if local_cookie_snapshot and self.login_with_cookies(local_cookie_snapshot, "本地 Cookie 快照"):
            return True

        if USERNAME and PASSWORD and self.login():
            return True

        if allow_manual_login:
            return self.wait_for_manual_login(MANUAL_LOGIN_TIMEOUT)

        if not (USERNAME and PASSWORD) and not COOKIES and not local_cookie_snapshot:
            self.set_failure_reason(
                "没有可用的登录方式。请先运行 `python main.py --init-session` 初始化持久化会话，"
                "或配置 LINUXDO_COOKIES / LINUXDO_USERNAME / LINUXDO_PASSWORD。"
            )
        return False

    def init_session(self) -> bool:
        logger.info("开始初始化本地持久化会话")
        success = self.authenticate(allow_manual_login=True)
        if success:
            logger.info(f"持久化会话已就绪，浏览器数据目录: {BROWSER_USER_DATA_DIR}")
        return success

    def click_topic(self):
        try:
            list_area = self.page.ele("@id=list-area")
        except Exception:
            list_area = None
        if not list_area:
            self.set_failure_reason(
                f"未找到帖子列表区域，当前页面可能未登录或页面结构已变化: {self.page.url}"
            )
            return False

        topic_list = list_area.eles(".:title")
        if not topic_list:
            self.set_failure_reason(f"未找到主题帖，当前页面: {self.page.url}")
            return False

        sample_size = min(len(topic_list), TOPIC_COUNT)
        logger.info(f"发现 {len(topic_list)} 个主题帖，随机选择 {sample_size} 个")
        for topic in random.sample(topic_list, sample_size):
            topic_url = urljoin(HOME_URL, topic.attr("href"))
            self.click_one_topic(topic_url)
        return True

    @retry_decorator()
    def click_one_topic(self, topic_url):
        new_page = self.browser.new_tab()
        try:
            new_page.get(topic_url)
            if random.random() < 0.3:
                self.click_like(new_page)
            self.browse_post(new_page)
        finally:
            try:
                new_page.close()
            except Exception:
                pass

    def browse_post(self, page):
        prev_url = None
        for _ in range(BROWSE_SCROLL_ROUNDS):
            scroll_distance = random.randint(550, 650)
            logger.info(f"向下滚动 {scroll_distance} 像素...")
            page.run_js(f"window.scrollBy(0, {scroll_distance})")
            logger.info(f"已加载页面: {page.url}")

            if random.random() < 0.03:
                logger.success("随机退出浏览")
                break

            at_bottom = page.run_js(
                "window.scrollY + window.innerHeight >= document.body.scrollHeight"
            )
            current_url = page.url
            if current_url != prev_url:
                prev_url = current_url
            elif at_bottom and prev_url == current_url:
                logger.success("已到达页面底部，退出浏览")
                break

            wait_time = random.uniform(2, 4)
            logger.info(f"等待 {wait_time:.2f} 秒...")
            time.sleep(wait_time)

    def run(self):
        try:
            if not self.authenticate(allow_manual_login=MANUAL_LOGIN_ENABLED):
                reason = self.last_failure_reason or "登录验证失败"
                self.send_notifications(False, BROWSE_ENABLED, reason)
                return

            if BROWSE_ENABLED:
                click_topic_res = self.click_topic()
                if not click_topic_res:
                    reason = self.last_failure_reason or "点击主题失败，程序终止"
                    self.send_notifications(False, BROWSE_ENABLED, reason)
                    return
                logger.info("完成浏览任务")

            self.print_connect_info()
            self.send_notifications(True, BROWSE_ENABLED)
        finally:
            try:
                self.page.close()
            except Exception:
                pass
            try:
                self.browser.quit()
            except Exception:
                pass

    def click_like(self, page):
        try:
            like_button = page.ele(".discourse-reactions-reaction-button")
            if like_button:
                logger.info("找到未点赞的帖子，准备点赞")
                like_button.click()
                logger.info("点赞成功")
                time.sleep(random.uniform(1, 2))
            else:
                logger.info("帖子可能已经点过赞了")
        except Exception as e:
            logger.error(f"点赞失败: {str(e)}")

    def print_connect_info(self):
        logger.info("获取连接信息")
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        }
        try:
            self.sync_browser_cookies_to_session()
            resp = self.session.get(
                "https://connect.linux.do/", headers=headers, impersonate="chrome136"
            )
            if resp.status_code != 200:
                logger.warning(f"获取 connect 信息失败，状态码: {resp.status_code}")
                return

            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("table tr")
            info = []
            for row in rows:
                cells = row.select("td")
                if len(cells) >= 3:
                    project = cells[0].text.strip()
                    current = cells[1].text.strip() if cells[1].text.strip() else "0"
                    requirement = cells[2].text.strip() if cells[2].text.strip() else "0"
                    info.append([project, current, requirement])

            logger.info("--------------Connect Info-----------------")
            logger.info(
                "\n" + tabulate(info, headers=["项目", "当前", "要求"], tablefmt="pretty")
            )
        except Exception as e:
            logger.warning(f"获取 connect 信息异常: {e}")

    def send_notifications(self, success: bool, browse_enabled: bool, reason: str = ""):
        account_label = USERNAME or "cookie-user"
        if success:
            status_msg = f"✅每日登录成功: {account_label}"
            if browse_enabled:
                status_msg += " + 浏览任务完成"
        else:
            status_msg = f"❌每日登录失败: {account_label}"
            if reason:
                status_msg += f"\n原因: {reason}"
        self.notifier.send_all("LINUX DO", status_msg)


def parse_args():
    parser = argparse.ArgumentParser(description="Linux.do 自托管签到/刷帖脚本")
    parser.add_argument(
        "--init-session",
        action="store_true",
        help="以可见浏览器初始化持久化登录会话，适合首次在自托管环境上登录",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    with SingleInstanceLock(LOCK_FILE) as lock:
        if not lock.acquired:
            print(f"已有任务正在运行，锁文件: {LOCK_FILE}")
            raise SystemExit(1)

        browser = LinuxDoBrowser(force_headless=False if args.init_session else None)
        if args.init_session:
            if not browser.init_session():
                raise SystemExit(1)
            return

        browser.run()


if __name__ == "__main__":
    main()
