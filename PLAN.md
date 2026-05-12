# PLAN.md — Course Registration Automation Service

## 1. Mục tiêu dự án

Xây dựng một service Python chạy 24/7 trên server để hỗ trợ đăng ký học phần theo danh sách môn/lớp học phần đã cấu hình trước.

Dự án này nâng cấp từ script hiện tại đang dùng:

- `requests.Session()` để giữ session/cookie đăng nhập.
- `BeautifulSoup` để parse form login và các hidden inputs.
- Gửi request đăng ký học phần qua endpoint đăng ký.
- Retry trong vòng lặp cho đến khi đăng ký thành công hoặc người dùng dừng chương trình.
- Hardcode username, password và danh sách mã lớp học phần trong code.

Mục tiêu của bản nâng cấp là biến script thử nghiệm thành một service ổn định, dễ cấu hình, dễ quan sát, có logging, notification, retry/backoff, rate limit, dry-run mode, và có thể deploy bằng Docker/systemd.

## 2. Phạm vi

### 2.1. In scope

Service cần hỗ trợ:

1. Đọc danh sách học phần từ file cấu hình.
2. Đọc tài khoản/mật khẩu từ environment variables hoặc secret file, không hardcode trong source code.
3. Tạo session đăng nhập và tự refresh/relogin khi session hết hạn.
4. Truy cập trang đăng ký học phần để kiểm tra session hợp lệ.
5. Gửi request đăng ký học phần cho từng mã lớp học phần đã cấu hình.
6. Phân loại response rõ ràng:
   - đăng ký thành công,
   - đăng ký thất bại,
   - hết slot hoặc chưa mở đăng ký,
   - đã đăng ký trước đó,
   - cần đăng nhập lại,
   - portal lỗi,
   - response không hợp lệ.
7. Lưu trạng thái từng học phần vào SQLite.
8. Có dry-run mode để test login, parser và flow mà không gửi request đăng ký thật.
9. Có notification qua Telegram khi:
   - đăng nhập thành công/thất bại,
   - đăng ký thành công,
   - đăng ký thất bại nhiều lần,
   - session hết hạn,
   - portal trả lỗi bất thường,
   - service start/stop.
10. Có logging dạng structured log.
11. Có rate limit và retry/backoff để service ổn định, không bắn request vô hạn.
12. Có Dockerfile và docker-compose để chạy trên server.
13. Có healthcheck endpoint hoặc CLI command để kiểm tra service còn sống.
14. Có test unit cho parser, config, state machine và portal client bằng mock response.

### 2.2. Out of scope

Không triển khai các hành vi sau:

1. Bypass CAPTCHA, hàng chờ, rate limit, hoặc cơ chế bảo vệ của portal.
2. Giả lập nhiều tài khoản nếu không được phép.
3. Spam request không giới hạn.
4. Hardcode cookie/token lấy từ trình duyệt.
5. Lưu mật khẩu trong Git repository.
6. Tự động thay đổi logic portal bằng cách đoán field khi parser fail. Nếu parser fail thì log lỗi và dừng an toàn.

## 3. Assumption

Dự án giả định rằng:

1. Người dùng có quyền hợp lệ để đăng nhập portal.
2. Việc tự động hóa đăng ký học phần bằng tài khoản cá nhân được trường/đơn vị quản lý cho phép.
3. Portal hiện tại dùng luồng tương tự:
   - GET trang login,
   - parse hidden input,
   - POST form login,
   - giữ cookie auth trong session,
   - POST request AJAX đến trang đăng ký học phần với payload có `action` và `data`.
4. Portal có thể thay đổi HTML hoặc response format, nên code phải dễ sửa và có test parser.

## 4. Tech stack đề xuất

### 4.1. Runtime

- Python 3.12+
- Docker
- SQLite cho bản single-user
- PostgreSQL là optional nếu sau này muốn multi-user

### 4.2. Python libraries

Core:

```txt
httpx
beautifulsoup4
pydantic
pydantic-settings
PyYAML
tenacity
APScheduler
sqlmodel
alembic
python-dotenv
```

Observability:

```txt
structlog
rich
prometheus-client
sentry-sdk
```

Notification:

```txt
python-telegram-bot
```

Web dashboard/API optional:

```txt
fastapi
uvicorn
jinja2
```

Testing:

```txt
pytest
pytest-asyncio
respx
freezegun
```

Lint/format:

```txt
ruff
mypy
```

## 5. Kiến trúc tổng quan

```txt
course-registration-service/
  app/
    __init__.py
    main.py

    config.py
    logging_config.py

    domain/
      models.py
      statuses.py
      errors.py

    portal/
      client.py
      parser.py
      schemas.py

    services/
      registrar.py
      scheduler.py
      notifier.py
      rate_limiter.py
      state_store.py

    web/
      api.py
      templates/

  tests/
    test_config.py
    test_parser.py
    test_portal_client.py
    test_registrar.py
    fixtures/
      login_page.html
      register_success.json
      register_failed.json
      expired_session.html

  config.example.yaml
  .env.example
  Dockerfile
  docker-compose.yml
  pyproject.toml
  README.md
  PLAN.md
```

## 6. Module design

### 6.1. `app/config.py`

Nhiệm vụ:

- Load config từ:
  - `config.yaml`,
  - `.env`,
  - environment variables.
- Validate config bằng Pydantic.
- Không cho app chạy nếu thiếu username/password hoặc thiếu danh sách học phần.

Config đề xuất:

```yaml
portal:
  login_url: "https://portal.ctdb.hcmus.edu.vn/Login?returnurl=%2f"
  registration_url: "https://portal.ctdb.hcmus.edu.vn/dang-ky-hoc-phan/sinh-vien-clc"
  expected_registration_page_text: "Sinh viên CLC"

student:
  username_env: "PORTAL_USERNAME"
  password_env: "PORTAL_PASSWORD"

runtime:
  mode: "auto"
  dry_run: true
  relogin_after_seconds: 600
  request_timeout_seconds: 15
  normal_interval_seconds: 30
  hot_interval_seconds: 3
  max_requests_per_minute: 20
  stop_when_all_success: true

courses:
  - id: "6101"
    name: "Tên môn 1"
    priority: 1
    enabled: true
  - id: "6102"
    name: "Tên môn 2"
    priority: 2
    enabled: true

notification:
  telegram_enabled: true
  telegram_bot_token_env: "TELEGRAM_BOT_TOKEN"
  telegram_chat_id_env: "TELEGRAM_CHAT_ID"

database:
  url: "sqlite:///data/app.db"
```

### 6.2. `app/domain/statuses.py`

Định nghĩa enum thay cho string rời rạc.

```python
class RegistrationStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    FULL = "full"
    NOT_OPEN = "not_open"
    ALREADY_REGISTERED = "already_registered"
    NEED_RELOGIN = "need_relogin"
    RATE_LIMITED = "rate_limited"
    HTTP_ERROR = "http_error"
    PARSE_ERROR = "parse_error"
    UNKNOWN = "unknown"
```

### 6.3. `app/portal/client.py`

Class chính: `PortalClient`

Nhiệm vụ:

- Tạo HTTP client.
- Set headers mặc định.
- Login.
- Kiểm tra session hợp lệ.
- Gửi request đăng ký học phần.
- Tự relogin khi cần.
- Không chứa business logic lựa chọn môn; chỉ giao tiếp với portal.

Interface đề xuất:

```python
class PortalClient:
    def __init__(self, settings: Settings): ...

    async def login(self) -> LoginResult: ...

    async def ensure_logged_in(self) -> None: ...

    async def check_registration_page(self) -> bool: ...

    async def register_course(self, course_id: str) -> RegistrationResult: ...

    async def close(self) -> None: ...
```

Yêu cầu:

- Không log password.
- Không log full cookie.
- Không hardcode session/cookie lấy từ DevTools.
- Dùng timeout rõ ràng.
- Dùng typed result object thay vì trả về string.

### 6.4. `app/portal/parser.py`

Nhiệm vụ:

- Parse hidden inputs từ trang login.
- Parse response đăng ký.
- Map response về `RegistrationStatus`.

Interface đề xuất:

```python
def parse_login_form(html: str) -> dict[str, str]:
    ...

def parse_registration_response(status_code: int, body: str) -> RegistrationResult:
    ...
```

Parser phải có test fixture riêng.

### 6.5. `app/services/registrar.py`

Nhiệm vụ:

- Nhận danh sách môn từ config/database.
- Sắp xếp theo priority.
- Với từng môn:
  - check trạng thái,
  - gọi `PortalClient.register_course`,
  - lưu kết quả,
  - gửi notification nếu cần.
- Không remove item khỏi list trong lúc đang loop; dùng state store.

Logic đề xuất:

```txt
For each enabled course sorted by priority:
  if course.status == success:
    skip

  if dry_run:
    log what would be done
    continue

  result = portal.register_course(course.id)
  save_attempt(course.id, result)

  if result.status == success:
    mark course success
    notify success

  if result.status == need_relogin:
    portal.login()
    retry later

  if result.status == rate_limited:
    backoff

  if result.status in failed/full/not_open:
    keep watching
```

### 6.6. `app/services/rate_limiter.py`

Nhiệm vụ:

- Giới hạn request/phút.
- Giới hạn attempts/môn/phút.
- Có jitter để tránh request đều như máy.
- Khi portal trả lỗi 429 hoặc lỗi quá tải, tăng thời gian nghỉ.

Yêu cầu:

- Không có vòng lặp spam không giới hạn.
- Rate limit phải cấu hình được.
- Ghi log khi bị throttle.

### 6.7. `app/services/scheduler.py`

Nhiệm vụ:

- Chạy job đăng ký định kỳ.
- Hỗ trợ normal mode và hot mode.
- Có thể pause/resume.
- Có thể chạy một lần bằng CLI.

Jobs đề xuất:

```txt
registration_job
session_refresh_job
healthcheck_job
cleanup_old_attempts_job
```

### 6.8. `app/services/notifier.py`

Nhiệm vụ:

- Gửi Telegram message.
- Có fallback log nếu Telegram fail.
- Không làm crash service nếu notification lỗi.

Message templates:

```txt
✅ Đăng ký thành công
Môn: {course_name}
Mã lớp HP: {course_id}
Thời gian: {timestamp}
Số lần thử: {attempt_count}

⚠️ Cần đăng nhập lại
Lý do: {reason}
Thời gian: {timestamp}

❌ Đăng ký thất bại nhiều lần
Môn: {course_name}
Lỗi gần nhất: {message}
```

### 6.9. `app/services/state_store.py`

Dùng SQLite qua SQLModel.

Tables đề xuất:

#### `courses`

```txt
id
name
priority
enabled
status
created_at
updated_at
last_attempt_at
success_at
attempt_count
last_message
```

#### `attempts`

```txt
id
course_id
status
http_status
message
response_excerpt
created_at
duration_ms
```

#### `runtime_events`

```txt
id
level
event_type
message
created_at
metadata_json
```

### 6.10. `app/web/api.py`

Optional nhưng nên có cho bản chạy 24/7.

Endpoints:

```txt
GET  /health
GET  /courses
POST /courses
PATCH /courses/{id}
POST /courses/{id}/enable
POST /courses/{id}/disable
POST /run-once
POST /pause
POST /resume
GET  /attempts
GET  /events
```

## 7. Luồng chạy chính

### 7.1. Startup

```txt
1. Load config.
2. Validate env secrets.
3. Init logging.
4. Init database.
5. Load courses from config into database nếu chưa có.
6. Init PortalClient.
7. Init Notifier.
8. Start scheduler.
9. Gửi notification "service started".
```

### 7.2. Registration job

```txt
1. Ensure logged in.
2. Check registration page.
3. Load enabled courses that are not success.
4. Sort by priority.
5. For each course:
   a. Check rate limiter.
   b. If dry-run, log and skip POST.
   c. Submit registration request.
   d. Parse response.
   e. Save attempt.
   f. Update course status.
   g. Notify important status.
6. If all courses success and stop_when_all_success=true, stop scheduler gracefully.
```

### 7.3. Shutdown

```txt
1. Stop scheduler.
2. Close HTTP client.
3. Flush logs.
4. Send shutdown notification if possible.
```

## 8. Modes

### 8.1. Dry-run mode

Purpose:

- Test login flow.
- Test parser.
- Test config.
- Test notification.
- Không gửi request đăng ký thật.

Behavior:

```txt
dry_run=true:
  - login thật nếu cần,
  - check registration page thật,
  - không gọi action addMonDangKy,
  - log "would register course X".
```

### 8.2. Auto mode

Purpose:

- Service tự xử lý các môn enabled.
- Đăng ký theo priority.
- Stop khi tất cả môn success nếu config cho phép.

### 8.3. Manual approval mode

Optional.

Purpose:

- Bot phát hiện trạng thái sẵn sàng, sau đó gửi Telegram để user xác nhận trước khi gửi request đăng ký.
- Hữu ích trong giai đoạn đầu khi chưa tin parser 100%.

## 9. Error handling

### 9.1. Login fail

- Retry với backoff.
- Không retry liên tục.
- Notify nếu fail quá N lần.

### 9.2. Session expired

- Map về `NEED_RELOGIN`.
- Gọi `login()`.
- Retry job ở vòng tiếp theo.

### 9.3. HTTP timeout

- Retry bằng Tenacity.
- Ghi attempt với status `HTTP_ERROR`.
- Không crash service.

### 9.4. Response không phải JSON

- Nếu response giống trang login hoặc HTML redirect, map về `NEED_RELOGIN`.
- Nếu không nhận diện được, map về `PARSE_ERROR`.
- Lưu excerpt ngắn để debug.

### 9.5. Portal overload / 429 / 5xx

- Backoff.
- Notify nếu kéo dài.
- Giảm tần suất job tạm thời.

## 10. Logging

Dùng structured logging.

Mỗi event nên có fields:

```txt
timestamp
level
event
course_id
course_name
status
http_status
duration_ms
attempt_count
message
```

Không log:

```txt
password
full cookie
full auth token
full HTML page nếu chứa thông tin cá nhân
```

## 11. Security

Yêu cầu bắt buộc:

1. `.env` không commit.
2. Có `.env.example`.
3. Password chỉ đọc từ env/secret.
4. Không in cookie auth ra console.
5. Không lưu response đầy đủ nếu response chứa thông tin cá nhân.
6. Docker container chạy non-root nếu có thể.
7. File database và config mount vào volume riêng.
8. Git ignore:
   - `.env`
   - `data/`
   - `*.db`
   - logs
   - cookies/session dumps

## 12. Deployment

### 12.1. Docker Compose

`docker-compose.yml` cần có:

```yaml
services:
  course-bot:
    build: .
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./data:/app/data
    healthcheck:
      test: ["CMD", "python", "-m", "app.main", "healthcheck"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### 12.2. CLI commands

Service nên hỗ trợ:

```bash
python -m app.main run
python -m app.main run-once
python -m app.main dry-run
python -m app.main healthcheck
python -m app.main init-db
```

## 13. Testing plan

### 13.1. Unit tests

Test các phần sau:

1. Config loader:
   - thiếu env thì fail rõ ràng,
   - config hợp lệ thì load được.
2. Login parser:
   - parse được hidden inputs.
   - thiếu input quan trọng thì báo lỗi.
3. Registration response parser:
   - success JSON,
   - failed JSON,
   - unknown JSON,
   - HTML login page,
   - invalid JSON.
4. State store:
   - create course,
   - update status,
   - save attempt.
5. Rate limiter:
   - cho request khi dưới limit,
   - block khi vượt limit.

### 13.2. Integration tests

Dùng `respx` để mock HTTPX.

Test flow:

```txt
GET login page -> POST login -> GET registration page -> POST registration success
```

Test thêm:

```txt
- login fail,
- session expired,
- portal returns 500,
- response invalid JSON,
- dry-run does not POST registration request.
```

## 14. Implementation roadmap

### Phase 1 — Refactor nền tảng

Deliverables:

- Tạo project structure.
- Thêm `pyproject.toml`.
- Implement config bằng Pydantic.
- Implement logging.
- Implement domain models/status enum.
- Implement parser với unit tests.

Done khi:

- `pytest` pass.
- `ruff` pass.
- App load config được.
- Không còn hardcode username/password trong code.

### Phase 2 — Portal client

Deliverables:

- Implement `PortalClient` bằng HTTPX.
- Implement login flow.
- Implement check registration page.
- Implement register course.
- Implement typed result object.

Done khi:

- Mock integration tests pass.
- Dry-run login được.
- Không log sensitive values.

### Phase 3 — State store và registrar

Deliverables:

- SQLite state store.
- Course status table.
- Attempts table.
- Registrar service xử lý course priority.
- Không mutate list trong loop.

Done khi:

- Có thể chạy `run-once`.
- Course success được lưu vào database.
- Attempts được lưu đầy đủ.

### Phase 4 — Scheduler, retry, rate limit

Deliverables:

- APScheduler job.
- Tenacity retry/backoff.
- Rate limiter.
- Normal/hot interval config.
- Stop khi tất cả môn success nếu config bật.

Done khi:

- Service chạy liên tục bằng Docker.
- Không crash khi portal lỗi tạm thời.
- Có backoff khi lỗi.

### Phase 5 — Notification

Deliverables:

- Telegram notifier.
- Notification templates.
- Notify success/failure/service started.
- Fallback log khi Telegram lỗi.

Done khi:

- `test-notification` gửi được.
- Success event gửi Telegram.
- Notification lỗi không làm app crash.

### Phase 6 — Dashboard/API optional

Deliverables:

- FastAPI app.
- `/health`
- `/courses`
- `/attempts`
- `/run-once`
- `/pause`
- `/resume`

Done khi:

- Có thể xem trạng thái service qua HTTP.
- Healthcheck dùng được trong Docker Compose.

## 15. Acceptance criteria

Dự án được xem là hoàn thành MVP khi:

1. Chạy được bằng Docker Compose.
2. Không còn hardcode username/password trong source.
3. Đọc được danh sách môn từ `config.yaml`.
4. Dry-run mode chạy được.
5. Auto mode chạy được.
6. Login thành công và giữ session.
7. Khi session hết hạn, service relogin được.
8. Response được parse thành enum status rõ ràng.
9. Đăng ký thành công thì course được mark `success`.
10. Có SQLite lưu attempts.
11. Có Telegram notification cho đăng ký thành công.
12. Có rate limit và retry/backoff.
13. Có test cho parser và portal client.
14. Có README hướng dẫn setup.

## 16. Suggested README sections

README nên có:

```txt
# Course Registration Automation Service

## Features
## Requirements
## Setup
## Configuration
## Environment Variables
## Dry Run
## Run Once
## Run 24/7 with Docker Compose
## Telegram Notification
## Troubleshooting
## Security Notes
## Development
## Testing
```

## 17. Prompt ngắn cho Codex

Codex nên đọc `PLAN.md` này trước, sau đó implement theo thứ tự:

1. Tạo project skeleton.
2. Implement config + domain models + parser.
3. Viết tests cho parser.
4. Implement HTTPX PortalClient.
5. Implement SQLite state store.
6. Implement Registrar.
7. Implement scheduler/rate limiter/retry.
8. Implement Telegram notifier.
9. Thêm Dockerfile/docker-compose.
10. Viết README.

Không implement dashboard trước khi MVP CLI/service chạy ổn.
Không hardcode credential.
Không log cookie/token/password.
Luôn giữ dry-run mode.
