# 公告

请不要魔改本项目多线程刷论坛，本项目的初衷只是为了给个人账号刷一下访问天数的，不是给号商养号用的。

# LinuxDo 每日签到（每日打卡）

## 项目描述

这个项目用于自动登录 [LinuxDo](https://linux.do/) 网站并随机读取几个帖子。它使用 Python 和 `DrissionPage`
模拟浏览器登录并浏览帖子，以达到自动签到的功能。

由于 `linux.do` 目前启用了更严格的 Cloudflare / 风控校验，**GitHub Actions 上的纯无状态登录已经不稳定**。  
现在更推荐把项目跑在 **VPS / NAS / 本地电脑 / 自建服务器 / 自托管 runner / 青龙** 上，并使用**持久化浏览器 profile**保存登录态。

## 功能

- 自动登录`LinuxDo`。
- 自动浏览帖子。
- 支持持久化浏览器 profile，适合自托管长期运行。
- 支持首次人工登录初始化，后续任务自动复用会话。
- 支持`青龙面板`、`cron`、`systemd timer`、自托管 runner 等方式运行。
- (可选)`Gotify`通知功能，推送获取签到结果。
- (可选)`Server酱³`通知功能，推送获取签到结果。
- (可选)`wxpush`通知功能，推送获取签到结果。
- (可选)`Telegram`通知功能，推送获取签到结果。

## 推荐运行方式

### 首选：自托管环境

推荐使用以下任一环境：

- 本地电脑 + `cron`
- VPS / NAS / 小主机
- 自托管 GitHub runner
- 青龙面板

这类环境的共同优势是：

- 浏览器 profile 可以持久化保存
- Cookie / 会话不会像 GitHub 托管 runner 一样每次重新开始
- 首次登录完成后，后续任务通常只需要复用本地浏览器状态

### 不再推荐：GitHub 托管 Actions

`linux.do` 当前会对无状态云环境触发额外挑战，导致：

- Cookie 一旦过期，自动回退账号密码登录可能失败
- `session/csrf` 等接口可能返回 `403` / `429`
- workflow 会出现“明明脚本没改，突然连续失败”的情况

如果你仍想继续使用 GitHub Actions，请尽量依赖最新 Cookie，且接受其不稳定性。
## 环境变量配置

### 登录方式

脚本现在会按以下顺序尝试登录：

1. 持久化浏览器 profile
2. `LINUXDO_COOKIES`
3. 本地 Cookie 快照文件
4. `LINUXDO_USERNAME` + `LINUXDO_PASSWORD`
5. 人工登录初始化（仅自托管、可见浏览器模式）

#### 方式一：持久化浏览器 profile（自托管推荐）

首次运行时，执行：

```bash
BROWSER_HEADLESS=false python3 main.py --init-session
```

脚本会打开一个可见浏览器，你手动完成登录和验证一次即可。成功后浏览器状态会保存在 `BROWSER_USER_DATA_DIR` 对应目录中，后续定时任务会自动复用。

#### 方式二：Cookie 登录

| 环境变量名称             | 描述                                         | 示例值                          |
|--------------------|--------------------------------------------|------------------------------|
| `LINUXDO_COOKIES`  | 从浏览器 DevTools 复制的 Cookie 字符串，设置后优先使用，无需账号密码 | `_t=xxx; _forum_session=yyy` |

> 获取方式：打开 [linux.do](https://linux.do/) 并登录 → 按 F12 → Application → Cookies → `https://linux.do` → 全选所有 Cookie 复制为字符串粘贴即可。

#### 方式三：账号密码登录

| 环境变量名称             | 描述                | 示例值                                |
|--------------------|-------------------|------------------------------------|
| `LINUXDO_USERNAME` | 你的 LinuxDo 用户名或邮箱 | `your_username` 或 `your@email.com` |
| `LINUXDO_PASSWORD` | 你的 LinuxDo 密码     | `your_password`                    |

> 若同时设置了 `LINUXDO_COOKIES` 和账号密码，仍然是 **Cookie 优先**。  
> 但在某些云环境里，账号密码回退登录可能会被 Cloudflare 拦截，因此不建议把它当成唯一方案。

~~之前的USERNAME和PASSWORD环境变量仍然可用，但建议使用新的环境变量~~

### 可选变量

| 环境变量名称                | 描述                   | 示例值                                    |
|----------------------|----------------------|----------------------------------------|
| `RUNTIME_DIR`        | 运行时目录，默认 `.runtime` | `/opt/linuxdo-checkin/runtime`         |
| `BROWSER_USER_DATA_DIR` | 浏览器 profile 目录，默认 `RUNTIME_DIR/browser-profile` | `/opt/linuxdo-checkin/browser-profile` |
| `BROWSER_PROFILE_NAME` | 浏览器 profile 名称，默认 `Default` | `Default` |
| `BROWSER_HEADLESS`   | 是否无头运行，默认 `true`    | `true` 或 `false`                      |
| `MANUAL_LOGIN_ENABLED` | 失败时是否允许人工登录回退，自托管推荐开启 | `true` 或 `false`                    |
| `MANUAL_LOGIN_TIMEOUT` | 人工登录等待秒数，默认 `300` | `300`                                  |
| `BROWSER_LOCAL_PORT` | 浏览器调试端口，默认自动分配     | `9222`                                 |
| `BROWSER_PATH`       | Chromium / Chrome 可执行文件路径 | `/usr/bin/chromium`               |
| `BROWSER_PROXY`      | 浏览器代理               | `http://127.0.0.1:7890`                |
| `TOPIC_COUNT`        | 每次随机浏览帖子数量，默认 `10` | `6`                                  |
| `GOTIFY_URL`         | Gotify 服务器地址         | `https://your.gotify.server:8080`      |
| `GOTIFY_TOKEN`       | Gotify 应用的 API Token | `your_application_token`               |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token   | `123456789:ABCdefghijklmnopqrstuvwxyz` |
| `TELEGRAM_CHAT_ID`   | Telegram 用户 ID       | `123456789`                            |
| `SC3_PUSH_KEY`       | Server酱³ SendKey     | `sctpxxxxt`                            |
| `WXPUSH_URL`         | wxpush 服务器地址         | `https://your.wxpush.server`           |
| `WXPUSH_TOKEN`       | wxpush 的 token       | `your_wxpush_token`                    |
| `BROWSE_ENABLED`     | 是否启用浏览帖子功能           | `true` 或 `false`，默认为 `true`           |

---

## 如何使用

### 自托管环境快速开始

#### 1. 安装依赖

最快的方式是直接跑引导脚本：

```bash
./scripts/bootstrap_self_hosted.sh
```

它会：

- 创建独立虚拟环境：`~/.cache/auto-check/venv`
- 安装 Python 依赖
- 创建持久化状态目录
- 生成环境配置文件：`~/.config/auto-check/auto-check.env`

如果你想手动安装，也可以继续按下面的方式执行。

#### 1.1 手动安装依赖

```bash
python3 -m pip install -r requirements.txt
```

Linux 机器还需要安装 Chromium，例如：

```bash
sudo apt update
sudo apt install -y chromium-browser
```

部分发行版包名可能是 `chromium`。

#### 2. 首次初始化登录态

在有桌面环境或可转发图形界面的机器上执行：

```bash
BROWSER_HEADLESS=false ./scripts/run_self_hosted.sh --init-session
```

说明：

- 会打开可见浏览器
- 你手动登录 `linux.do`
- 如遇 Cloudflare / Turnstile，请手动完成验证
- 成功后，会话保存在 `BROWSER_USER_DATA_DIR`
- 同时会写出本地 Cookie 快照，方便后续回退使用

#### 3. 手动执行一次正式任务

```bash
./scripts/run_self_hosted.sh
```

#### 4. 配置 cron

示例：

```cron
12 8,20 * * * cd /path/to/auto-check && ./scripts/run_self_hosted.sh >> ~/.cache/auto-check/runtime/cron.log 2>&1
```

这表示每天 `08:12` 和 `20:12` 执行一次。

### 自托管运行建议

- 如果是纯命令行服务器、没有图形界面，优先用 `LINUXDO_COOKIES`。
- 自托管脚本默认从 `~/.config/auto-check/auto-check.env` 读取配置，不会把敏感信息放进仓库工作区。
- 如果你能在桌面环境先执行一次 `--init-session`，后续把 `~/.cache/auto-check/browser-profile` 保留下来，稳定性通常更好。
- 建议把 `~/.cache/auto-check` 和 `~/.config/auto-check` 加入备份。
- 脚本现在带有锁文件，默认路径是 `~/.cache/auto-check/runtime/auto-check.lock`，可避免同一时间重复运行。

### 青龙面板使用

*注意：如果是 docker 容器创建的青龙，**请使用 `whyour/qinglong:debian` 镜像**，`latest`（alpine）版本可能无法安装部分依赖*

1. **依赖安装**
   - 安装 Python 依赖
     - 进入青龙面板 -> 依赖管理 -> 安装依赖
     - 依赖类型选择 `python3`
     - 自动拆分选择 `是`
     - 名称填写仓库 `requirements.txt` 的完整内容
   - 安装 Linux Chromium 依赖
     - 青龙面板 -> 依赖管理 -> 安装 Linux 依赖
     - 名称填 `chromium`

2. **添加仓库**
   - 进入青龙面板 -> 订阅管理 -> 创建订阅
   - 仓库地址填：`https://github.com/cxymds/auto-check.git`
   - 定时规则可按需设置

3. **配置环境变量**
   - 推荐至少配置：
     - `LINUXDO_COOKIES`
     - 或 `LINUXDO_USERNAME` + `LINUXDO_PASSWORD`
   - 如果青龙运行环境有桌面能力，也可以使用持久化 profile：
     - `BROWSER_USER_DATA_DIR`
     - `BROWSER_HEADLESS`
     - `MANUAL_LOGIN_ENABLED`

4. **运行**
   - 点击任务右侧“运行”按钮
   - 进入日志查看结果

### GitHub Actions 自动运行

仓库里的 workflow 现在已经改成 **self-hosted runner 版本**。  
也就是说，调度和日志仍在 GitHub，但脚本会在你自己的 Linux 机器上执行。

#### 配置步骤

1. **准备 self-hosted runner**
    - 在你的 Linux 机器上添加 GitHub self-hosted runner
    - 建议 runner 标签至少包含 `self-hosted` 和 `linux`
    - 在 runner 机器上提前安装：
      - `python3`
      - `pip`
      - `chromium` / `chromium-browser` / `google-chrome`

2. **在 runner 机器上执行一次引导**
    - 进入项目目录执行：
      ```bash
      ./scripts/bootstrap_self_hosted.sh
      ```

3. **首次初始化登录态**
    - 在 runner 所在机器上，进入项目目录执行：
      ```bash
      BROWSER_HEADLESS=false ./scripts/run_self_hosted.sh --init-session
      ```
    - 完成一次手动登录后，浏览器 profile 会保存在 runner 本机

4. **配置 GitHub Secrets / Variables**
    - 在 GitHub 仓库的 `Settings` -> `Secrets and variables` -> `Actions` 中添加以下变量：
        - （二选一）`LINUXDO_COOKIES`：从浏览器复制的 Cookie 字符串（**推荐，优先使用**）。
        - （二选一）`LINUXDO_USERNAME` + `LINUXDO_PASSWORD`：你的 LinuxDo 用户名/邮箱和密码。
        - (可选) `GOTIFY_URL` 和 `GOTIFY_TOKEN`。
        - (可选) `SC3_PUSH_KEY`。
        - (可选) `WXPUSH_URL` 和 `WXPUSH_TOKEN`。
        - (可选) `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`。
    - 可在 `Variables` 中配置：
      - `BROWSE_ENABLED`
      - `BROWSER_PATH`
      - `SELF_HOSTED_STATE_DIR`

5. **手动触发工作流**
    - 进入 GitHub 仓库的 `Actions` 选项卡
    - 选择 `Daily Check-in`
    - 点击 `Run workflow`

#### self-hosted workflow 行为说明

- workflow 会自动把运行时目录放到 runner 机器上的持久化路径中，而不是仓库工作区内。
- 默认持久化根目录是：`~/.cache/auto-check`
- 如果你希望改位置，可以在 GitHub Variables 里设置 `SELF_HOSTED_STATE_DIR`
- workflow 会自动尝试探测浏览器路径；如果探测不到，可以设置 `BROWSER_PATH`

### Gotify 通知

当配置了 `GOTIFY_URL` 和 `GOTIFY_TOKEN` 时，签到结果会通过 Gotify 推送通知。
具体 Gotify 配置方法请参考 [Gotify 官方文档](https://gotify.net/docs/).

### Server酱³ 通知

当配置了 `SC3_PUSH_KEY` 时，签到结果会通过 Server酱³ 推送通知。
获取 SendKey：请访问 [Server酱³ SendKey获取](https://sc3.ft07.com/sendkey) 获取你的推送密钥。

### wxpush 通知

当配置了 `WXPUSH_URL` 和 `WXPUSH_TOKEN` 时，签到结果会通过 wxpush 推送通知。
使用 POST 方式推送，请求地址为 `{WXPUSH_URL}/wxsend`。

### Telegram 通知

可选功能：配置 Telegram 通知，实时获取签到结果。

需要在 GitHub Secrets 中配置：
- `TELEGRAM_BOT_TOKEN`：Telegram Bot Token
- `TELEGRAM_CHAT_ID`：Telegram 用户 ID

获取方法：
1. Bot Token：与 [@BotFather](https://t.me/BotFather) 对话创建机器人获取
2. 用户 ID：与 [@userinfobot](https://t.me/userinfobot) 对话获取

未配置时将自动跳过通知功能，不影响签到。


## 自动更新

- **自托管**：推荐用 `git pull` 或你自己的发布方式控制更新节奏。
- **GitHub Actions**：如继续使用 fork，同步方式仍取决于你的 workflow 配置。
- **青龙面板**：更新频率由订阅定时规则决定。
