# ESP32 Smart Home SCADA (VS Code)

Dự án gồm:
- `backend/main.py`: FastAPI chạy trên máy tính.
- `frontend/index.html`: Dashboard web AUTO/MANUAL.
- `esp32/main.py`: MicroPython chạy trên ESP32 DevKit V1.

## 1. Cài đặt trên máy tính

Cài Python 3.10+ và VS Code. Mở thư mục `SmartHome_SCADA_VSCode` trong VS Code.

Mở Terminal tại VS Code:

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
```

Chạy server:

```powershell
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Mở trình duyệt trên máy tính:
`http://127.0.0.1:8000`

## 2. Lấy địa chỉ IPv4 của máy tính

Mở CMD và chạy:

```powershell
ipconfig
```

Tìm `IPv4 Address` của card Wi-Fi, ví dụ `192.168.1.100`.

Nếu Windows Firewall hỏi quyền, cho phép Python/Uvicorn trên mạng Private.

## 3. Cấu hình ESP32

Mở `esp32/main.py`, sửa:

```python
WIFI_SSID = "YOUR_WIFI_NAME"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
SERVER_URL = "http://192.168.1.100:8000"
```

Thay IP ví dụ bằng IPv4 thật của máy tính. ESP32 và máy tính phải cùng mạng Wi-Fi.

Dùng Thonny hoặc công cụ MicroPython trong VS Code để chép `esp32/main.py` vào ESP32, đặt tên `main.py`, rồi khởi động lại board.

## 4. Thư viện MicroPython cần có trên ESP32

Cài/copy các module sau vào ESP32:
- `dht.py` (thường có sẵn trong firmware MicroPython).
- `ssd1306.py`.
- `mfrc522.py` tương thích MicroPython.
- `urequests.py` (một số firmware có thể dùng `requests`; code hiện tại gọi `urequests`).

Cần firmware MicroPython cho ESP32 có hỗ trợ `network`, `machine`, `ujson`.

## 5. Chân GPIO theo file Word

| Hệ thống | GPIO |
|---|---|
| Độ ẩm đất AO / relay bơm | 34 / 26 |
| RFID RC522 SS, RST, SCK, MISO, MOSI | 5, 22, 18, 19, 23 |
| Servo cửa | 13 |
| MQ-2 AO / buzzer | 35 / 25 |
| DHT22 DATA / relay quạt | 32 / 33 |
| OLED SDA / SCL | 14 / 17 |
| PIR OUT / LED | 36 / 16 |
| Rain DO / servo giàn phơi | 27 / 4 |

## 6. Hai chế độ

### AUTO
- Độ ẩm đất < 30%: bật bơm; ngược lại tắt bơm.
- Nhiệt độ >= 35°C: bật quạt; nhiệt độ <= 33°C: tắt quạt (vùng trễ).
- MQ-2 >= 1800: bật buzzer, ưu tiên an toàn ở cả AUTO và MANUAL.
- PIR phát hiện chuyển động: bật LED và giữ 3 giây sau lần phát hiện cuối.
- Có mưa: servo giàn phơi hướng 180°; hết mưa: về 0°.
- Cửa mở bằng thẻ RFID có UID `E4 9E 26 06`, giữ mở 3 giây rồi đóng.

### MANUAL
- Điều khiển bơm, quạt, LED, góc servo giàn phơi và yêu cầu mở cửa từ dashboard.
- Dữ liệu cảm biến vẫn được đọc và gửi lên web.
- Cảnh báo MQ-2 vẫn tự động hoạt động để ưu tiên an toàn.

## 7. Lưu ý trước khi cấp nguồn

1. Relay trong code đang giả định kích mức HIGH; nếu module relay của em kích LOW thì đảo `RELAY_ON` và `RELAY_OFF`.
2. Buzzer đang giả định kích LOW theo code MQ-2 gốc.
3. Không cấp nguồn servo hoặc bơm từ chân 3V3 của ESP32. Dùng nguồn ngoài phù hợp và nối GND chung.
4. Điện áp AO của MQ-2 đưa vào GPIO35 không được vượt giới hạn đầu vào ESP32 (3.3V).
5. Kiểm tra dòng tải relay, diode bảo vệ cho tải DC cảm ứng và nguồn riêng trước khi chạy.
6. Thử từng hệ thống riêng trước, sau đó mới chạy chương trình tổng.
7. `GPIO4` là chân được phân bổ cho servo giàn phơi theo file Word; kiểm tra trạng thái chân lúc khởi động.

## 8. Giới hạn phiên bản khởi đầu

Đây là bộ khung tích hợp để bắt đầu kiểm thử. Thư viện MFRC522 MicroPython có nhiều biến thể API; nếu thư viện em đang dùng khác API trong file Word, cần điều chỉnh phần khởi tạo/đọc thẻ tương ứng. Nên kiểm tra kết nối Wi-Fi và API trước khi cấp nguồn cho các tải công suất.
