# Gold Signal Bot (XAUUSD)

Bot phân tích kỹ thuật XAUUSD đa khung thời gian, phát hiện tín hiệu BUY/SELL, gửi Telegram,
theo dõi TP/SL và tổng kết báo cáo cuối ngày.

> **Tất cả 10 Phase đã hoàn thành, kể cả xác nhận dữ liệu XAUUSD thật (Phase 2).** 224
> test pass, `mypy --strict` + `ruff` sạch trên toàn bộ code, toàn bộ pipeline (10
> phương pháp → Confluence → Entry/SL/TP → Signal State Machine → Telegram → Tracking →
> Reversal → Daily Report/Backtest) đã được nối thành các worker chạy nền thật qua
> APScheduler (`app/workers/`), khởi động cùng `docker compose up`. Bot hiện chạy với
> **`MARKET_DATA_PROVIDER=twelvedata`** — dữ liệu giá/nến XAUUSD **thật** từ
> [Twelve Data](https://twelvedata.com) (đã verify qua `/health` và `/market/candles`
> trên container thật). `MockProvider`, `TradingViewProvider`, `OANDAProvider` vẫn giữ
> nguyên và có test — chọn qua `MARKET_DATA_PROVIDER` mà không cần sửa logic phân tích.

## Yêu cầu

- Python 3.12+
- Docker & Docker Compose
- (Sau này) Telegram Bot Token — xem hướng dẫn ở Phase 6

## Cấu hình

```bash
cp .env.example .env
```

Chỉnh sửa `.env` theo nhu cầu. Không commit file `.env` (đã có trong `.gitignore`).

Biến quan trọng:

| Biến | Ý nghĩa |
|---|---|
| `SYMBOL` | Symbol giao dịch, mặc định `XAUUSD` |
| `DATABASE_URL` | Chuỗi kết nối PostgreSQL (async) |
| `REDIS_URL` | Chuỗi kết nối Redis |
| `MARKET_DATA_PROVIDER` | `mock` \| `tradingview` \| `broker` \| `twelvedata` |
| `PAPER_MODE` | `true` = chỉ phân tích/tín hiệu, không vào lệnh thật |

## Market Data Provider

Interface thống nhất `app/market_data/base.py::MarketDataProvider` với 4 cách lấy giá,
chọn qua `MARKET_DATA_PROVIDER`, không cần sửa logic phân tích khi đổi nguồn:

- **`mock`** — sinh nến OHLC hợp lệ bằng random walk, ổn định theo symbol, dùng để phát
  triển/test không cần mạng.
- **`tradingview`** — đọc dữ liệu do chính bạn đẩy vào qua TradingView Alert → Webhook,
  **không** scrape giao diện, không bypass đăng nhập/CAPTCHA.
- **`broker`** — gọi thẳng OANDA v20 REST/stream API (cần tài khoản **fxTrade**
  practice — lưu ý: một số entity OANDA, ví dụ "OANDA Global", chỉ cấp MetaTrader 5
  không có v20 REST API; nếu gặp trường hợp đó, dùng `twelvedata` thay thế).
- **`twelvedata`** (**đang dùng, mặc định hiện tại**) — gọi REST API của
  [Twelve Data](https://twelvedata.com), chỉ cần đăng ký email lấy API key miễn phí,
  **không cần mở tài khoản trading nào** — đây là dữ liệu giá **thật**.

### 0) Twelve Data (đang dùng — nhanh nhất, không cần tài khoản trading)

1. Đăng ký free tại https://twelvedata.com/pricing (gói Basic/Free), lấy **API Key**.
2. Điền vào `.env`:

   ```env
   MARKET_DATA_PROVIDER=twelvedata
   TWELVEDATA_API_KEY=<api key>
   TWELVEDATA_SYMBOL=XAU/USD
   ```

3. `docker compose up -d --build app` rồi kiểm tra `GET /health` và
   `GET /market/candles?timeframe=M15`.

Giới hạn free tier: 8 request/phút, 800 request/ngày (`app/market_data/twelvedata.py`).
Nến mới nhất chưa chắc đã đóng — provider tự loại bỏ bar chưa đủ thời gian đóng (cùng
nguyên tắc "no look-ahead bias" như `OANDAProvider`). Không có `/subscribe` stream ở gói
free nên `subscribe_ticks()` poll `get_current_price()` mỗi 5s (interface vẫn tương thích
100% — chỉ dùng trong test hiện tại, worker chính dùng `get_candles`/`get_current_price`
trực tiếp).

### 1) OANDA Broker (dữ liệu thật, cần đúng loại tài khoản fxTrade)

1. Tạo tài khoản practice (demo) miễn phí: https://www.oanda.com/demo-account/ —
   chọn/đảm bảo platform **"OANDA Trade" (fxTrade)**, không phải MetaTrader.
2. Đăng nhập https://trade.oanda.com/ → "My Account" → "Manage API Access" → tạo
   Personal Access Token, ghi lại Account ID (dạng `xxx-xxx-xxxxxxx-xxx`).
3. Điền vào `.env`:

   ```env
   MARKET_DATA_PROVIDER=broker
   OANDA_API_KEY=<token>
   OANDA_ACCOUNT_ID=<account id>
   OANDA_ENVIRONMENT=practice
   OANDA_INSTRUMENT=XAU_USD
   ```

4. `docker compose up -d --build app` rồi kiểm tra `GET /health` và
   `GET /market/candles?timeframe=M15`.

### 2) TradingView Webhook (cần gói TradingView có Webhook Alert, ví dụ Essential+)

1. Đặt `TRADINGVIEW_WEBHOOK_SECRET` trong `.env` (một chuỗi bí mật tự chọn).
2. Trong TradingView, tạo Alert trên chart XAUUSD, **Trigger: Once Per Bar Close**
   (bắt buộc — nếu không sẽ nhận nến chưa đóng, vi phạm nguyên tắc "no look-ahead bias").
3. Webhook URL: `https://<host-của-bạn>/webhook/tradingview?token=<TRADINGVIEW_WEBHOOK_SECRET>`
4. Message (Alert message), dán nguyên văn:

   ```json
   {"symbol": "{{ticker}}", "interval": "{{interval}}", "time": "{{timenow}}",
    "open": {{open}}, "high": {{high}}, "low": {{low}}, "close": {{close}}, "volume": {{volume}}}
   ```

5. Set `MARKET_DATA_PROVIDER=tradingview`, restart app. Kiểm tra `GET /market/price`.

### Kiểm tra thủ công

```bash
curl http://localhost:8000/market/price
curl "http://localhost:8000/market/candles?timeframe=M15&limit=20"
```

## Chạy bằng Docker (khuyến nghị)

```bash
cp .env.example .env
docker compose up -d --build
curl http://localhost:8000/health
```

Kết quả mong đợi:

```json
{
  "status": "healthy",
  "symbol": "XAUUSD",
  "environment": "development",
  "paperMode": true,
  "marketDataProvider": "mock",
  "database": "connected",
  "redis": "connected",
  "marketData": "connected",
  "lastPrice": 2649.2
}
```

Dừng stack:

```bash
docker compose down
```

## Chạy local (không Docker)

Cần PostgreSQL và Redis chạy sẵn (có thể chỉ chạy 2 service này qua Docker):

```bash
docker compose up -d postgres redis

python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# sửa DATABASE_URL / REDIS_URL trỏ về localhost thay vì postgres/redis
# lưu ý: Postgres của compose expose ra host ở cổng 5433 (không phải 5432) để
# tránh xung đột với một Postgres cài sẵn trên máy — dùng
# postgresql+asyncpg://gold:gold@localhost:5433/goldbot

uvicorn app.main:app --reload
```

> Trên macOS + Homebrew Python, nếu gặp lỗi `pyexpat` khi tạo venv, chạy với
> `DYLD_LIBRARY_PATH=$(brew --prefix expat)/lib` phía trước các lệnh `python`/`pip`.

## Test

```bash
source .venv/bin/activate
pytest -v
ruff check .
ruff format --check .
mypy app
```

## Database Migrations (Alembic)

```bash
DATABASE_URL="postgresql+asyncpg://gold:gold@localhost:5433/goldbot" alembic revision --autogenerate -m "mô tả thay đổi"
DATABASE_URL="postgresql+asyncpg://gold:gold@localhost:5433/goldbot" alembic upgrade head
```

Migration đầu tiên (`create candles table`) đã có sẵn trong `app/db/migrations/versions/`.

## 10 phương pháp phân tích kỹ thuật đã xây dựng — 4 quyết định hướng, 4 chỉ hỗ trợ entry/SL/TP (Phase 3)

Mỗi phương pháp là một hàm thuần `analyze_xxx(candles, timeframe, ...) -> AnalysisResult`
trong `app/analysis/`, trả về `direction` (BUY/SELL/NEUTRAL), `confidence` (0-1), `reason`,
`levels`, `metadata`. Không có phương pháp nào tự ý ra tín hiệu chỉ từ một chỉ báo đơn lẻ
(ví dụ RSI không bao giờ "RSI>70 => SELL" — luôn phải có phân kỳ hoặc structure đi kèm).

Cả 10 phương pháp đều đã viết và có test đầy đủ. Theo yêu cầu, chỉ **4 phương pháp** (Market
Structure, Support/Resistance, Liquidity/SMC, Price Action) được tính vào **confluence vote**
(`app/workers/analysis_worker.py::SINGLE_TIMEFRAME_METHODS` và
`app/backtest/engine.py::BACKTEST_METHODS`) — chỉ nhóm này quyết định hướng BUY/SELL và mức
đồng thuận. EMA Trend, MACD, Volatility (ATR/Bollinger) và Fibonacci **hoàn toàn thụ động** —
không vote, không chặn/veto tín hiệu — chỉ chạy để cấp dữ liệu thật (EMA20 pullback, Bollinger
band, ATR buffer, Fib extension) cho Entry/Risk/Target Engine (`STRUCTURAL_ONLY_METHODS`). RSI
Momentum và Multi-timeframe vẫn bị loại hoàn toàn, không tham gia bước nào.

| Method | File | Logic chính | Vai trò | Trọng số |
|---|---|---|---|---|
| `market_structure` | `market_structure.py` | Swing HH/HL/LH/LL (fractal, có phân biệt provisional/confirmed), BOS, CHoCH | 🗳️ vote (ưu tiên) | 1.30 |
| `liquidity_smc` | `liquidity_smc.py` | Equal high/low, liquidity sweep + displacement, Fair Value Gap, premium/discount | 🗳️ vote (ưu tiên) | 1.30 |
| `support_resistance` | `support_resistance.py` | Gom cụm swing gần nhau theo ATR thành zone, chấm điểm theo số lần chạm + độ mới | 🗳️ vote (ưu tiên) | 1.15 |
| `price_action` | `price_action.py` | Engulfing, pin bar, doji, inside/outside bar, morning/evening star, momentum candle; confidence phụ thuộc có đứng tại swing zone hay không | 🗳️ vote | 1.00 |
| `fibonacci` | `fibonacci.py` | Retracement/extension từ swing leg đủ lớn (>= 3×ATR), tín hiệu tại golden zone 50-61.8% | ⚙️ chỉ entry/SL/TP | 0.85 |
| `ema_trend` | `ema_trend.py` | EMA20/50/100/200 stack + slope + crossover | ⚙️ chỉ entry/SL/TP | 0.80 |
| `volatility` | `volatility.py` | ATR14 + Bollinger(20,2): squeeze, breakout, mean-reversion, ATR spike | ⚙️ chỉ entry/SL/TP | 0.70 |
| `macd` | `macd.py` | Crossover, histogram, vị trí zero-line | ⚙️ chỉ chạy, chưa có level nào dùng đến (xem lưu ý bên dưới) | 0.65 |
| `rsi_momentum` | `rsi_momentum.py` | RSI14 + regular/hidden divergence (so RSI tại 2 swing gần nhất) + momentum fallback | ⛔ đã loại | — |
| `multi_timeframe` | `multi_timeframe.py` | Gộp bias từng khung theo `TIMEFRAME_WEIGHTS`, H1/H4 có quyền veto khung nhỏ | ⛔ đã loại | 1.35 |

"vote (ưu tiên)" (`PRIORITY_STRATEGIES` trong `confluence.py`) = 3 phương pháp vote có trọng
số cao nhất — `market_structure`/`liquidity_smc`/`support_resistance` — chỉ cần **1** phương
pháp trong nhóm này đồng thuận là đủ điều kiện tín hiệu; `price_action` (vote nhưng trọng số
thấp nhất trong 4) cần **≥2** phương pháp cùng đồng thuận mới đủ (xem mục Confluence Engine
bên dưới). Trọng số ("cơ sở tính confidence") và ưu tiên ("cơ sở tính số lượng phiếu tối
thiểu") là **2 khái niệm độc lập**, gán riêng trong `PRIORITY_STRATEGIES`.

Lưu ý về `macd`: hiện **không có** hàm entry/risk/targets nào đọc `levels` của nó (chỉ
`support_resistance`/`ema_trend`/`volatility`/`liquidity_smc`/`fibonacci` mới có mức giá được
dùng) — nên với vai trò "thụ động" như hiện tại, `macd` được tính nhưng không ảnh hưởng gì đến
kết quả cuối cùng. Muốn nó thực sự "quản trị" entry/SL/TP, cần bổ sung logic đọc `levels` của
nó ở `app/engines/entry.py`/`risk.py`/`targets.py`.

Muốn bật lại một phương pháp vào confluence vote: thêm hàm `analyze_xxx` vào
`SINGLE_TIMEFRAME_METHODS` (và `BACKTEST_METHODS` nếu muốn backtest khớp) — không cần chỉnh
`MIN_METHOD_AGREEMENT`/`STRONG_METHOD_AGREEMENT` vì đây là ngưỡng theo **tỉ lệ**, không phải
số đếm tuyệt đối.

Chạy thử toàn bộ 10 phương pháp (kể cả các phương pháp không vote/đã loại) trên dữ liệu Mock:

```bash
python scripts/analysis_examples.py           # XAUUSD, M15
python scripts/analysis_examples.py XAUUSD H1  # đổi symbol/timeframe
```

Hạ tầng dùng chung: `app/analysis/indicators.py` (EMA/RSI/MACD/ATR/Bollinger tự viết bằng
pandas, không phụ thuộc TA-Lib/pandas-ta), `app/analysis/swings.py` (fractal swing detection
+ gom cụm theo giá, dùng chung cho S/R và liquidity).

## Confluence / Entry / Risk / Take-Profit Engine (Phase 4)

`app/engines/`:

- **`confluence.py`** — gộp `AnalysisResult` của **4 phương pháp vote**
  (`market_structure`/`support_resistance`/`liquidity_smc`/`price_action`) theo
  `STRATEGY_WEIGHTS` (configurable qua `Settings.strategy_weights`, mặc định theo Section 17).
  EMA Trend/MACD/Volatility/Fibonacci **không** được đưa vào hàm này — chúng thụ động, không
  vote, không veto. Điểm số là **trung bình có trọng số trong nhóm phương pháp đã ra hướng**
  (không bị pha loãng bởi các phương pháp NEUTRAL). Mức đồng thuận có **2 lớp gate độc lập**:
  1. **Tỉ lệ** trên số phương pháp thực sự ra hướng BUY/SELL (bỏ qua NEUTRAL khỏi cả tử số
     lẫn mẫu số) — ví dụ 2 BUY/0 SELL/2 NEUTRAL = tỉ lệ 2/2 = 100%. Cần **>50%** mới thành
     tín hiệu (`MIN_METHOD_AGREEMENT`), **>70%** mới đạt tier STRONG/VERY_STRONG
     (`STRONG_METHOD_AGREEMENT`, không đủ thì tự hạ xuống VALID).
  2. **Sàn số lượng tuyệt đối** (`PRIORITY_STRATEGIES` trong `confluence.py`) — sự cố thật
     GOLD-20260830-001 cho thấy tỉ lệ 100% vẫn lọt qua được dù chỉ **1 phương pháp duy nhất**
     lên tiếng (SL gần như dính ngay entry — lỗ hổng đó đã được vá riêng bằng
     `MIN_SL_ATR_MULT` trong `risk.py`, xem mục Entry/Risk/TP bên dưới). Từ đó thêm sàn số
     lượng: 3 trong 4 phương pháp vote có trọng số cao nhất (`market_structure`/
     `liquidity_smc`/`support_resistance`) được tin tưởng đủ để tự mang tín hiệu một mình
     (**≥1**); `price_action` (vote nhưng nhẹ ký nhất) cần **≥2** phương pháp cùng đồng ý mới
     đủ điều kiện. Trọng số dùng để tính confidence và sàn ưu tiên này là 2 cơ chế độc lập —
     `support_resistance` (phương pháp gây ra sự cố GOLD-20260830-001) nằm trong nhóm ưu tiên
     vì trọng số cao, không phải vì nó "an toàn" hơn; lớp bảo vệ thực sự cho trường hợp đó vẫn
     là sàn SL tối thiểu.

  Đúng nguyên tắc "chất lượng hơn số lượng". 5 tier: `NO_TRADE < WATCH < VALID < STRONG <
  VERY_STRONG`.
- **`entry.py`** — không bao giờ vào lệnh tại giá hiện tại nếu giá đã chạy quá xa; tìm vùng
  entry gần nhất theo support/resistance, Fib golden zone, EMA20, Bollinger band, liquidity
  level; đánh dấu `reachable=False` nếu khoảng cách vượt quá `MAX_CHASE_ATR_MULT × ATR`
  (`ENTRY_MAX_CHASE_ATR_MULT`, mặc định **1.3** — siết chặt hơn mặc định gốc 2.0 theo yêu cầu,
  để entry không lệch quá xa giá hiện tại lúc phát hiện tín hiệu). *(Đã thử đổi sang "market
  entry" — vào ngay giá hiện tại, không chờ pullback — vào 2026-09-01 nhưng đã revert lại logic
  chờ pullback ban đầu theo yêu cầu ngay sau đó; chỉ giữ lại việc siết `MAX_CHASE_ATR_MULT`.)*
- **`risk.py`** — Stop Loss đặt sau điểm vô hiệu hóa cấu trúc gần nhất (swing high/low từ
  market_structure, hoặc liquidity level, hoặc S/R zone) cộng buffer ATR — không đặt SL chỉ
  để đẹp R:R. Cũng có `reward_to_risk()` / `meets_minimum_rr()` (mặc định 1.5, theo `MIN_RR`).
- **`targets.py`** — TP1→TP5 tăng dần (BUY) / giảm dần (SELL), ưu tiên dùng level thật
  (resistance/support, Fib extension, liquidity level) nếu nó rơi **trong khoảng [80%, 130%]**
  của bậc R-multiple đó, nếu không thì fallback sang chiếu theo R-multiple từ ATR/risk. *(Sự
  cố thật GOLD-20260903-001, phát hiện 2026-09-03: điều kiện cũ chỉ có biên dưới — một mức giá
  thật cách xa tận 3.08R vẫn bị "vơ" vào đúng bậc TP1 (1.0R) vì nó thỏa mãn ≥80%, khiến
  TP2-TP5 hết level thật để dùng, rơi về chiếu R-multiple rồi bị logic "phải tăng dần" ép dồn
  cụm sát ngay sau TP1 thay vì giãn đều theo đúng bậc. Đã thêm biên trên 130% để mỗi mức giá
  thật chỉ được gán cho đúng bậc nó thực sự gần.)*

  **Thang R-multiple dùng `rr_ladder_for(min_rr)`, không phải hằng số cố định** — sự cố thật
  nghiêm trọng hơn, phát hiện 2026-09-08: `DEFAULT_RR_LADDER=(1.0, 1.5, 2.0, 3.0, 4.0)` có bậc
  đầu (TP1) là 1.0R, kết hợp biên trên 130% ở trên nghĩa là TP1 **không bao giờ** vượt quá
  1.3R. Với `MIN_RR` mặc định 1.5 > 1.3, gate `meets_minimum_rr(targets[0].rr, MIN_RR)`
  **luôn luôn False** — nghĩa là suốt từ lúc thêm biên trên (03/09) tới lúc phát hiện (08/09,
  **5 ngày liền**), không một tín hiệu nào có thể được tạo ra dù điều kiện đồng thuận/entry/SL
  hợp lệ đến đâu — không phải "thị trường yên ắng" như tưởng lúc đó. Đã sửa bằng
  `rr_ladder_for(min_rr) = tuple(min_rr * m for m in DEFAULT_RR_LADDER)` — TP1 giờ luôn bằng
  đúng `MIN_RR` (qua gate với dấu `=`), các bậc sau giãn theo đúng tỉ lệ gốc. Áp dụng ở cả
  `analysis_worker.py` và `backtest/engine.py`.

Chạy thử toàn bộ pipeline (4 phương pháp vote + 4 phương pháp entry/SL/TP → confluence → entry
→ SL → TP → gate R:R):

```bash
python scripts/signal_pipeline_example.py           # XAUUSD, M15
python scripts/signal_pipeline_example.py SEARCH72   # ví dụ đã biết ra tín hiệu BUY
```

Vì dữ liệu Mock là random walk độc lập giữa các phương pháp, phần lớn symbol sẽ ra
`NO_TRADE` (đúng thiết kế — bot không bị ép phải BUY/SELL). Script cũng minh họa trường hợp
tín hiệu bị **reject ở bước R:R cuối cùng** dù đã qua được confluence/entry/SL/TP.

## Signal State Machine (Phase 5)

`app/engines/signal.py` — domain thuần, immutable (mỗi transition trả về `Signal` mới):

```text
DETECTED/WAITING_ENTRY → ACTIVE → TP1_HIT → TP2_HIT → TP3_HIT → TP4_HIT → TP5_HIT (terminal)
                             ↓
                          STOPPED (terminal)
WAITING_ENTRY → CANCELLED / EXPIRED / MISSED_ENTRY (terminal)
Bất kỳ trạng thái chưa terminal → INVALIDATED / REVERSED (terminal)
```

- `build_signal()` tạo signal mới ở `WAITING_ENTRY`, ID dạng `GOLD-20260817-001`
  (`format_signal_id`), luôn kèm đúng 5 `TargetLevel` và event `SIGNAL_CREATED`.
- Mỗi hàm transition (`activate`, `hit_target`, `stop_out`, `cancel`, `invalidate`,
  `reverse`, `expire`, `mark_missed_entry`) tự kiểm tra trạng thái nguồn hợp lệ, raise
  `InvalidTransitionError` nếu sai (ví dụ không thể `hit_target(level=2)` trước TP1,
  không thể `cancel()` sau khi đã `activate()`).

Persistence: `app/db/models/signal.py` (bảng `signals`, `signal_targets`, `signal_events`,
`signal_sequences`) + `app/db/repositories/signal_repository.py`:

- `next_signal_id()` — atomic increment qua `INSERT ... ON CONFLICT DO UPDATE ... RETURNING`,
  không trùng ID dù nhiều worker tạo signal cùng lúc.
- `apply_transition()` — **conditional UPDATE** (`WHERE status = <trạng thái trước đó>`):
  nếu một worker khác đã transition trước, `rowcount=0` và hàm trả `False` thay vì ghi đè
  — đây là cách chống race condition ở Section 51 ("TP1 HIT" không bao giờ bị gửi Telegram 2 lần).

Xác minh với Postgres thật (không phải test giả lập, có kiểm tra race condition bằng 2
session chạy song song):

```bash
docker compose up -d postgres redis
DATABASE_URL="postgresql+asyncpg://gold:gold@localhost:5433/goldbot" \
  python scripts/verify_signal_repository.py
```

## Telegram (Phase 6)

`app/telegram/`:

- **`client.py`** — `TelegramClient` gọi Bot API thật, tự retry/backoff khi lỗi 5xx/mất
  kết nối, tôn trọng `retry_after` khi bị rate-limit (429), raise `TelegramError` ngay
  (không retry) với lỗi 4xx (Section 47).
- **`formatter.py`** — dựng đúng 6 loại tin nhắn theo Section 23-28: tín hiệu mới (BUY/SELL,
  ẩn/hiện metadata theo `TELEGRAM_SHOW_METADATA`), Entry Activated, TP hit (kèm "Còn lại"),
  Full TP, Stop Loss, Cancelled.
- **`notifier.py`** — gửi qua `client.py`, nhưng **reserve trước khi gửi** vào bảng
  `telegram_messages` (unique constraint trên `idempotency_key = "<signal_id>:<event>"`) —
  cùng một sự kiện của cùng một signal không bao giờ được gửi 2 lần dù có race condition.
- **`commands.py`** + **`dispatcher.py`** — admin command `/status /price /signal /analysis
  /report /pause /resume`, chỉ user trong `TELEGRAM_ADMIN_USER_IDS` mới dùng được.
  `/status` gọi trực tiếp market data provider + `market_structure` trên H4/H1/M15 để lấy
  bias thật (không phải số giả). `/pause`, `/resume` bật/tắt cờ trong Redis.

### Tạo Telegram Bot (miễn phí, không cần key bên ngoài)

1. Nhắn `@BotFather` trên Telegram → `/newbot` → đặt tên → nhận `TELEGRAM_BOT_TOKEN`.
2. Tạo một group/channel, thêm bot vào, hoặc nhắn trực tiếp cho bot rồi lấy `chat_id` qua
   `https://api.telegram.org/bot<TOKEN>/getUpdates`.
3. Điền vào `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=<token thật>
   TELEGRAM_CHAT_ID=<chat id thật>
   TELEGRAM_ADMIN_USER_IDS=<user id của bạn>
   ```

### Xác minh gửi tin nhắn thật + idempotency (không phải test giả lập)

```bash
docker compose up -d postgres redis
DATABASE_URL="postgresql+asyncpg://gold:gold@localhost:5433/goldbot" \
  python scripts/verify_telegram_message_repository.py   # race condition ở tầng DB
```

## Entry/TP/SL Tracking (Phase 7)

`app/tracking/`:

- **`signal_tracker.py`** — logic thuần, không đụng DB/mạng:
  - `evaluate_waiting_entry()`: giá chạm entry zone → `ACTIVE`; giá chạy quá xa
    (> `MAX_CHASE_ATR_MULT × ATR`) mà chưa từng chạm → `MISSED_ENTRY`; quá thời gian chờ
    (`DEFAULT_EXPIRY_MINUTES`, Section 32) → `EXPIRED`.
  - `evaluate_active_signal()`: giá chạm SL → `STOPPED`; giá chạm TP → `TPn_HIT`. Xử lý đúng
    Section 25 — nếu giá nhảy một lần qua nhiều mốc TP (ví dụ 4394→4400 vượt TP1,TP2,TP3),
    trả về **danh sách nhiều `TrackingStep` theo đúng thứ tự**, không bỏ sót mốc nào.
- **`event_processor.py`** — `process_symbol_tick()`: với mỗi bước tracker trả về, gọi
  `SignalRepository.apply_transition()` (conditional UPDATE) rồi **chỉ gửi Telegram nếu
  transition đó thật sự được áp dụng** — nếu một worker khác đã xử lý trước (`apply_transition`
  trả `False`), bỏ qua luôn, không gửi trùng (Section 51).

Verify end-to-end trên Postgres thật (tạo signal → giá vào entry → giá nhảy qua 3 TP cùng
lúc → tick trùng lặp không gửi lại → chạy tới TP5/FULL TP):

```bash
docker compose up -d postgres redis
DATABASE_URL="postgresql+asyncpg://gold:gold@localhost:5433/goldbot" \
  python scripts/verify_signal_tracking.py
```

## Invalidate / Cancel / Reversal (Phase 8)

`app/engines/reversal.py` — `evaluate_signal_health()`: so sánh confidence hiện tại của
signal đang chạy với confluence vừa tính lại. **Không bao giờ đảo chiều chỉ vì 1 cây M1
đỏ / RSI giảm nhẹ / MACD cross nhỏ** (Section 29) — phải qua 2 lớp điều kiện độc lập:

1. Confidence của chính hướng signal phải tụt dưới `INVALIDATION_CONFIDENCE_FLOOR`
   (mặc định **0.35**, hạ từ 0.55 theo yêu cầu 2026-09-03 để giữ lệnh lâu hơn khi chỉ suy yếu
   nhẹ chưa tới mức đáng lo) — nếu không, giữ nguyên (`KEEP`).
2. Chỉ khi (1) đã đúng, **và** confluence engine tự nó đã đổi hướng thắng sang phía đối
   lập, **và** confidence phía đối lập vượt `REVERSAL_SIGNAL_CONFIDENCE` (mặc định 0.82,
   ngưỡng cao hơn hẳn) → mới `REVERSE`. Nếu (1) đúng nhưng (2) chưa đủ → chỉ `CLOSE`
   (hủy/vô hiệu hóa), không tạo tín hiệu ngược.

> Sự cố thật (2026-09-03): `Settings.invalidation_confidence_floor`/`reversal_signal_confidence`
> (đọc từ `.env`) từng **không được truyền** vào `process_signal_health_check()` —
> `app/workers/analysis_worker.py` gọi hàm mà không set 2 tham số này, nên nó luôn dùng
> default cứng trong `reversal.py` (0.55/0.82) bất kể `.env` ghi gì. Đã sửa: giờ
> `run_analysis_cycle()` truyền đúng `settings.invalidation_confidence_floor`/
> `settings.reversal_signal_confidence` mỗi lần gọi.

`app/tracking/event_processor.py::process_signal_health_check()` áp dụng quyết định: signal
còn `WAITING_ENTRY` → `CANCELLED`; đang chạy → `INVALIDATED` hoặc `REVERSED`. Thông báo
Telegram khác nhau tuỳ trường hợp (đổi theo yêu cầu, 2026-09-03):

- **CLOSE thường** (`WAITING_ENTRY → CANCELLED` hoặc confidence suy yếu dần không có phe đối
  lập mạnh → `INVALIDATED`) — **không gửi thông báo** vào nhóm. Tín hiệu chỉ mang tính tham
  khảo, mỗi người tự quản lý lệnh riêng, và một tin nhắn "CANCELLED" cho một suy yếu nhẹ đọc
  như chỉ thị ("bạn nên huỷ") hơn là thông tin trung lập.
- **REVERSE** (thị trường đã thật sự đảo chiều mạnh, phe đối lập vượt `REVERSAL_SIGNAL_CONFIDENCE`,
  mặc định 0.82) — **vẫn gửi** thông báo "⚠️ CANCELLED" cho signal cũ, vì đây là một sự kiện
  thị trường rõ ràng đáng báo, không phải suy yếu mơ hồ. **Ngay trong cùng chu kỳ đó**
  (`app/workers/analysis_worker.py::run_analysis_cycle()`, đổi theo yêu cầu 2026-09-03), bot
  chạy tiếp đúng pipeline bình thường (Entry → Risk → Targets → `build_signal`) trên **cùng
  một lần đọc confluence** vừa kích hoạt REVERSE (đã nghiêng hẳn về phía đối lập) và gửi
  `SIGNAL_CREATED` cho tín hiệu mới ngay lập tức — không phải đợi tới chu kỳ 5 phút kế tiếp.
  Nếu entry/SL/TP/RR không đạt (ví dụ RR dưới `MIN_RR`), tín hiệu mới sẽ không được tạo dù
  signal cũ vẫn đã đóng — không có "code path riêng" nào đảm bảo chắc chắn có tín hiệu mới,
  vẫn phải qua đủ mọi gate như một tín hiệu bình thường.

Trạng thái luôn được cập nhật đầy đủ trong DB (`signal_events`, thống kê daily report) ở cả
hai trường hợp — chỉ riêng việc broadcast CLOSE-thường vào nhóm là bị tắt; thông báo
TP/SL/entry-activated không bị ảnh hưởng.

Verify end-to-end 3 kịch bản trên Postgres thật (KEEP không đổi gì, CLOSE khi không đủ mạnh
để đảo, REVERSE khi phía đối lập đủ mạnh, cộng kiểm tra idempotency khi check trùng lặp):

```bash
docker compose up -d postgres redis
DATABASE_URL="postgresql+asyncpg://gold:gold@localhost:5433/goldbot" \
  python scripts/verify_signal_reversal.py
```

## Daily Report / Statistics / Backtest (Phase 9)

`app/reports/statistics.py` — `compute_statistics()`: WIN nếu có ít nhất 1 TP đã hit (kể
cả sau đó bị SL — thắng một phần vẫn tính là Win, không tính Loss), SL nếu bị stop mà chưa
hit TP nào, còn lại (CANCELLED/INVALIDATED/REVERSED/EXPIRED/MISSED_ENTRY không có TP) tính
vào nhóm Cancelled. `realized_r()` trả `None` (không bịa số) cho các tín hiệu chưa từng được
fill — không có "kết quả" thật để báo cáo.

`app/reports/daily.py` — `format_daily_report()` dựng đúng format Section 38 (không có cấu
hình lot nên **không bao giờ hiện USD profit**, chỉ R-multiple/win-loss/TP-rate).
`build_daily_report()` gộp: tín hiệu đóng trong ngày (theo `REPORT_TIMEZONE`, mặc định
Asia/Ho_Chi_Minh) từ `SignalRepository`, bias thị trường thật từ `MarketDataProvider` +
`market_structure` (dùng chung code với lệnh `/status`, xem `app/analysis/bias.py`), và
**Bot Uptime thật** từ bảng `system_health` — mỗi lần gọi `/health` tự ghi 1 heartbeat, nếu
chưa có dữ liệu thì báo `N/A` thay vì bịa số.

`app/backtest/engine.py::run_backtest()` — chạy walk-forward, mỗi bước chỉ đưa
`candles[:i+1]` vào **chính 9 phương pháp phân tích + Confluence + Entry + Risk + Targets
đang chạy production** (Section 41 cấm viết chiến lược backtest riêng) — không có logic
chấm điểm nào khác. TP/SL trong từng bar mô phỏng bằng high/low (không chỉ close); nếu một
bar chạm cả TP lẫn SL, quy ước bảo thủ là tính SL trước (không thể biết thứ tự thật từ
OHLC). Bỏ qua `multi_timeframe` vì cần dữ liệu nhiều khung thời gian đồng bộ theo thời gian
thực mà backtest 1-khung không thể đảm bảo trung thực. `app/backtest/metrics.py` tính thêm
SL Rate, TP1-5 Rate, Expectancy, Max Consecutive Losses, Signals/Day.

> Lưu ý khi chạy backtest trên `MockProvider`: dữ liệu random walk gần như không bao giờ
> tạo ra sự đồng thuận cao giữa nhiều phương pháp cùng lúc, nên backtest thường ra **0 tín
> hiệu** trên dữ liệu Mock — đây là kết quả đúng (bot không bị ép phải giao dịch), không
> phải lỗi. Muốn backtest có ý nghĩa cần dữ liệu XAUUSD lịch sử thật (OANDA/TradingView).

```bash
python scripts/run_backtest_example.py XAUUSD M15 1500

docker compose up -d postgres redis
DATABASE_URL="postgresql+asyncpg://gold:gold@localhost:5433/goldbot" \
  python scripts/verify_daily_report.py
```

## Chạy Bot Live — Workers / Scheduler (Phase 10)

Trước Phase 10, tất cả các engine ở trên đã đúng và có test, nhưng **không có gì tự động
gọi chúng** — `app/workers/` từng rỗng. Phase 10 nối toàn bộ pipeline thành 3 job chạy nền
qua APScheduler (`AsyncIOScheduler`), khởi động trong `lifespan()` của `app/main.py` và tắt
gọn gàng khi app shutdown:

- **`app/workers/analysis_worker.py::run_analysis_cycle()`** — chạy mỗi
  `ANALYSIS_INTERVAL_SECONDS` giây. Nếu đang có tín hiệu mở, chạy lại đúng 4 phương pháp vote +
  Confluence rồi đưa cho `reversal engine` (Section 28/29) để quyết định KEEP/CLOSE/REVERSE —
  **không bao giờ mở lệnh thứ hai khi đã có lệnh đang chạy**. Nếu không có tín hiệu mở, kiểm
  tra `signal_generation_enabled`, trạng thái pause (`/pause` qua Telegram), cooldown
  (`SIGNAL_COOLDOWN_MINUTES`), giới hạn `MAX_SIGNALS_PER_HOUR`, và cổng rủi ro thị trường
  (`VolatilityMarketRiskProvider`, xem dưới) — chỉ khi tất cả đều "sạch" mới chạy phân tích
  đầy đủ → Confluence → Entry/SL/TP → tạo signal → gửi Telegram.
- **`app/workers/tracking_worker.py::run_tracking_cycle()`** — chạy mỗi
  `TRACKING_INTERVAL_SECONDS` giây, no-op nếu không có tín hiệu mở; nếu có, lấy giá/ATR mới
  nhất và gọi `process_symbol_tick()` (Phase 7) để phát hiện entry fill, TP hit, SL hit.
- **`app/workers/report_worker.py::run_daily_report_cycle()`** — chạy theo cron
  (`REPORT_HOUR`/`REPORT_TIMEZONE`), dựng và gửi daily report (Phase 9).
- **`app/workers/scheduler.py::start_workers()`** — wire cả 3 job trên vào một
  `AsyncIOScheduler` duy nhất, trả về `WorkerRuntime` (có `.shutdown()`). Nếu Telegram chưa
  cấu hình (`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` trống), trả về `None` và log giải thích
  thay vì raise lỗi — bot vẫn chạy được ở chế độ "phân tích only, không gửi thông báo".

Xác minh end-to-end (đã chạy thật, xem log job chạy không lỗi trong container Docker):

```bash
docker compose up -d postgres redis
DATABASE_URL="postgresql+asyncpg://gold:gold@localhost:5433/goldbot" \
  python scripts/verify_workers.py
```

### Execution Provider & Market Risk Provider (Section 50 / Section 34)

Hai interface được spec yêu cầu nhưng còn thiếu, bổ sung ở Phase 10:

- **`app/execution/base.py`** — `ExecutionProvider` (ABC: `open_trade`/`modify_trade`/
  `close_trade`) + `PaperExecutionProvider` (implementation ghi log, không gửi lệnh thật).
  **Chưa được gọi từ bất kỳ worker nào** — cố tình. Gọi nó cần một khối lượng giao dịch
  (`volume`/lot size), mà dự án không có cấu hình quản lý vốn/lot size nào cả; bịa một con số
  volume để "cho chạy được" sẽ vi phạm nguyên tắc "không bịa dữ liệu" xuyên suốt dự án. Khi
  nào có yêu cầu quản lý vốn rõ ràng, interface đã sẵn sàng để nối vào `analysis_worker.py`.
- **`app/market_data/risk.py`** — `MarketRiskProvider` (ABC) + `VolatilityMarketRiskProvider`,
  **đã được nối vào `analysis_worker.py`**, kiểm tra 2 chiều:
  1. **Spike** (biến động tăng đột biến): nếu true range của nến gần nhất vượt quá
     `ABNORMAL_VOLATILITY_MULT` (mặc định 3x) trung bình `ABNORMAL_VOLATILITY_LOOKBACK` nến
     gần nhất → `ABNORMAL_VOLATILITY`.
  2. **Biến động thấp bất thường** (thêm 2026-10-18, sự cố thật): khi thị trường đóng cửa
     (cuối tuần/lễ), TwelveDataProvider trả về nến gần như phẳng tuyệt đối thay vì khoảng
     trống thật — ATR(14) mà entry/risk/targets dựa vào đọc gần bằng 0, có thể khiến SL/entry
     bị tính sát một cách giả tạo ngay lúc thị trường mở cửa lại. Phát hiện bằng cách so sánh
     trung bình true range của `LOW_VOLATILITY_SHORT_PERIOD` (14) nến gần nhất với
     `ATR(LOW_VOLATILITY_LONG_PERIOD=200)` — nếu tỉ lệ dưới `LOW_VOLATILITY_RATIO` (15%) →
     cũng báo `ABNORMAL_VOLATILITY`. Worker tạm dừng tạo tín hiệu mới ở cả 2 trường hợp. Để hỗ
     trợ phép so sánh dài hạn này, `_recent_candles` trong `analysis_worker.py` lấy 250 nến
     thay vì 100 (cùng 1 request, không tốn thêm credit).

  Các trạng thái liên quan tin tức (`HIGH_IMPACT_NEWS_SOON`/`_ACTIVE`) trong Section 34
  **chưa** implement vì dự án chưa có nguồn lịch kinh tế thật — không giả lập.

## Triển khai Production

Checklist tối thiểu trước khi chạy thật với tiền thật (Section 53):

1. **Dữ liệu thị trường**: đổi `MARKET_DATA_PROVIDER` từ `mock` sang `oanda` hoặc
   `tradingview_webhook` với credentials thật (xem mục "Market Data Provider" ở trên) —
   **bắt buộc**, hệ thống hiện đang chạy Mock nên chưa nên dùng để ra quyết định giao dịch
   thật.
2. **`.env`**: không commit file `.env` thật (đã có trong `.gitignore`); dùng secret riêng cho
   `TELEGRAM_BOT_TOKEN`, `TRADINGVIEW_WEBHOOK_SECRET`, `DATABASE_URL`/`REDIS_URL` production.
3. **Restart policy**: `docker-compose.yml` nên chạy với `restart: unless-stopped` (đã cấu
   hình) để worker tự khởi động lại sau khi máy chủ reboot hoặc container crash.
4. **Giám sát**: `/health` ghi heartbeat thật vào bảng `system_health` mỗi lần được gọi — nên
   có external uptime check (cron/monitoring service) gọi endpoint này định kỳ để daily report
   hiện đúng Bot Uptime thay vì `N/A`.
5. **Execution vẫn là Paper/thủ công**: vì `ExecutionProvider` chưa được nối vào worker (xem
   trên), bot hiện chỉ **báo tín hiệu qua Telegram** — việc đặt lệnh thật vẫn do người dùng
   thực hiện thủ công dựa trên tín hiệu. Đừng kỳ vọng bot tự động khớp lệnh.
6. **Kiểm tra threshold/weight** (`STRATEGY_WEIGHTS`, `MIN_METHOD_AGREEMENT`,
   `STRONG_METHOD_AGREEMENT`, `MIN_RR`, ...) trong `.env` phù hợp khẩu vị rủi ro trước khi
   chạy dài hạn — giá trị mặc định trong `.env.example` là điểm khởi đầu hợp lý, không phải
   con số đã được tối ưu cho mọi trường hợp.

## Cấu trúc dự án

```text
app/
    main.py              FastAPI app factory + lifespan (khởi động workers)
    api/                 REST endpoints (health, signals, analysis, reports, webhook)
    core/                config, enums, logging, timeframes, time parsing
    market_data/         nguồn dữ liệu giá (Mock, TradingView-webhook, OANDA, Twelve Data) + risk (xong)
    analysis/             10 phương pháp phân tích kỹ thuật (6 đang dùng trong pipeline) + indicators/swings dùng chung
    engines/              confluence, entry, risk, targets, signal, reversal (xong)
    tracking/              signal_tracker, event_processor (xong)
    telegram/              client, formatter, notifier, admin commands (xong)
    reports/                statistics, daily report (xong)
    backtest/               engine + metrics, dùng chính analysis engine (xong)
    execution/               ExecutionProvider/PaperExecutionProvider (xong, chưa nối worker)
    db/                     models, repositories, alembic migrations
    workers/                analysis/tracking/report worker + scheduler (xong)
tests/
docker/
```

## Lộ trình Phase

- [x] Phase 1 — Project structure, FastAPI, Config, PostgreSQL, Redis, Docker, Health Check
- [x] Phase 2 — Market Data Provider (Mock/TradingView-webhook/OANDA/Twelve Data);
      dữ liệu XAUUSD thật đã xác nhận qua Twelve Data (`/health`, `/market/candles`
      trên container thật)
- [x] Phase 3 — 10 phương pháp phân tích kỹ thuật (xem mục bên dưới)
- [x] Phase 4 — Confluence / Entry / SL / TP / Risk Engine (xem mục bên dưới)
- [x] Phase 5 — Signal State Machine (xem mục bên dưới)
- [x] Phase 6 — Telegram (xem mục bên dưới; đã xác nhận gửi tin nhắn thật thành công)
- [x] Phase 7 — Entry/TP/SL Tracking (xem mục bên dưới)
- [x] Phase 8 — Invalidate / Cancel / Reversal (xem mục bên dưới)
- [x] Phase 9 — Daily Report, Statistics, Backtest (xem mục bên dưới)
- [x] Phase 10 — Workers/Scheduler live, ExecutionProvider + MarketRiskProvider, 224 test
      pass, `ruff` + `mypy --strict` sạch toàn bộ, verify end-to-end trên Docker thật
