# Dynamic Island cho Windows

Viên đảo nổi ở giữa mép trên màn hình: nhạc đang phát, thông báo Windows, đồng hồ và thông số máy.
Toàn bộ code chạy trên máy bạn — không tải exe lạ, không gọi mạng, không cài service.

| Thu gọn — đang phát | Thu gọn — rảnh rỗi |
|---|---|
| ![thu gọn](preview/compact.png) | ![rảnh](preview/idle.png) |

| Mở rộng — nhạc | Mở rộng — đồng hồ |
|---|---|
| ![mở rộng](preview/expanded.png) | ![đồng hồ](preview/expanded_idle.png) |

| Thông báo | Kệ file (kéo-thả) |
|---|---|
| ![thông báo](preview/notif.png) | ![kệ file](preview/shelf.png) |

## Thiết kế

Lấy cảm hứng từ mấy app notch kiểu macOS (Notchy, Nusa): nền **đen tuyền** thay vì xám, viền
sáng 1px, và **đôi mắt linh vật** — thứ làm nó sống hơn hẳn một widget thông thường.

- **Mắt**: chớp ngẫu nhiên 2–6 giây, nhìn theo con trỏ khi rê chuột lên, cong `^ ^` khi có nhạc,
  lim dim ngủ (kèm chữ `z` bay lên) sau ~35 giây không có gì.
- **Nền**: đen `#000` pha chút xanh ở đỉnh, cộng quầng sáng rất nhẹ lấy màu từ bìa album.
- **Chữ**: tên bài dài tự chạy ngang, mờ dần ở mép phải thay vì cắt cụt.
- **Bung/thu**: 360 ms `OutExpo` cho kích thước; nội dung trượt lên ~7 px và mờ dần vào.
- **Sóng nhạc**: 4 thanh mảnh, màu nhấn đổi theo bìa đĩa.
- **Nút điều khiển**: play tròn 42 px viền màu nhấn, sáng lên khi rê chuột; prev/next có quầng tròn.

## Cần gì

- Windows 10 1809+ hoặc Windows 11
- Python 3.11 trở lên (chỉ cần cho lần cài đầu)

## Cài

1. Chạy `setup.bat` — tạo `.venv` và cài thư viện (PySide6, psutil, winrt).
2. Chạy `start-island.vbs` — island hiện ra, không có cửa sổ đen.

Nếu bạn đã có sẵn một môi trường Python khác và không muốn tạo `.venv`, tạo file
`python-path.txt` ở thư mục gốc, dòng đầu ghi đường dẫn đầy đủ tới `pythonw.exe`.
`start-island.vbs` sẽ dùng nó khi không thấy `.venv`.

Muốn tự khởi động cùng Windows: chuột phải lên island → **Khởi động cùng Windows** (hoặc bật trong menu tray).

| Thao tác | Kết quả |
|---|---|
| Đưa chuột lên island | Bung ra: nhạc + thông số CPU/RAM/NET/PIN |
| Bấm chuột trái | Ghim mở rộng (bấm lần nữa để thu lại) |
| Kéo chuột | Di chuyển island, tự bám lại mép trên |
| Trượt/click lên thanh âm lượng | Chỉnh âm lượng hệ thống; click icon loa để tắt/bật tiếng |
| Kéo file vào island | Lưu tạm vào kệ file (SHELF) |
| Click file trên kệ | Mở file bằng ứng dụng mặc định |
| Kéo file trên kệ ra ngoài | Đẩy file sang app khác (Explorer, chat…) |
| Click dấu × trên kệ | Xoá file khỏi kệ |
| Chuột phải | Menu: ghim, kệ file, về giữa màn hình, gửi thông báo thử, thoát |
| Icon ở khay hệ thống | Menu đầy đủ: luôn trên cùng, chế độ tĩnh, tự động tĩnh, kệ file, khởi động cùng Windows |

Khi thu nhỏ:

- **Có nhạc** → bìa album + sóng nhạc + tên bài + đôi mắt ở cuối.
- **Không có nhạc** → đôi mắt + giờ + thứ/ngày.

Khi có thông báo Windows → island tự bung thành thẻ thông báo 6 giây rồi thu lại.
Nếu đang mở rộng thì chỉ hiện chấm đỏ ở góc, không cắt ngang việc bạn đang làm.

## Chế độ tĩnh & Tối ưu CPU

Đảo tự động **đông cứng** khi bạn chuyển sang làm việc ở ứng dụng khác — mắt ngừng chớp, sóng nhạc dừng, chỉ còn đồng hồ và hình dáng viên đảo. Điều này giúp CPU gần như không tốn tài nguyên khi bạn tập trung vào việc chính.

- **Tự động tĩnh khi dùng app khác** (mặc định BẬT): đảo phát hiện khi một cửa sổ ứng dụng thật chiếm foreground → tự động đứng yên. Quay lại desktop hoặc rê chuột lên đảo → hoạt cảnh tiếp tục.
- **Chế độ tĩnh thủ công** (mặc định TẮT): bật trong khay hệ thống để đảo luôn đứng yên, chỉ vẽ lại khi phút đổi hoặc bạn rê chuột vào.
- Nhịp vẽ tự thích ứng: 30 fps khi đang chớp mắt / chạy chữ / rê chuột, 15 fps khi chỉ có sóng nhạc, ~1 fps khi rảnh hoặc đông cứng.

## Thông báo Teams / Outlook / mail

Mọi thứ hiện thành **toast của Windows** đều vào island: Microsoft Teams, Outlook, Gmail trên
trình duyệt, Zalo, Discord, Telegram, Slack… Avatar tự lấy màu thương hiệu của app.

Muốn kiểm tra nhanh: chuột phải lên island → **Gửi thông báo thử**.

Nếu app đó không hiện trong island, kiểm tra theo thứ tự:

1. **Windows → Settings → System → Notifications**: app đó phải đang bật, và không ở chế độ
   "chỉ hiện banner" (nếu chỉ banner thì thông báo không vào Action Center nên không đọc được).
2. Đang bật **Focus Assist / Do Not Disturb** thì Windows không tạo toast → island không thấy gì.
3. App dùng cửa sổ thông báo tự vẽ (không phải toast) thì không đọc được — chỉ đọc được toast chuẩn.
4. Lần đầu chạy, Windows hỏi quyền truy cập thông báo → phải bấm **Đồng ý**.

## Cái gì hoạt động

- **Nhạc**: đọc Windows SMTC — Spotify, Apple Music, YouTube/Chrome/Edge/Brave, Media Player…
  bất kỳ app nào có trong bảng điều khiển media của Windows. Có play/pause, chuyển bài, thanh
  tiến trình, thời lượng, ảnh bìa, và **màu nhấn lấy từ ảnh bìa**.
- **Thông báo**: đọc toast của Windows qua `UserNotificationListener`.
- **Thông số**: CPU, RAM, tốc độ mạng xuống, phần trăm pin (kèm tia sét khi đang sạc).
- **Âm lượng hệ thống**: thanh trượt trong panel mở rộng, kéo để chỉnh master volume (qua
  `pycaw` / Core Audio), click icon loa để tắt/bật tiếng. Tự cập nhật nếu bạn chỉnh âm lượng
  ở nơi khác.
- **Kệ file kéo-thả (SHELF)**: kéo file từ Explorer hay bất kỳ đâu thả vào island để lưu tạm;
  click để mở bằng app mặc định, kéo ngược ra để đẩy file sang app khác, dấu × để xoá. Số lượng
  file đang lưu hiện thành huy hiệu nhỏ trên island khi thu gọn. Mở/đóng kệ qua chuột phải hoặc
  icon khay hệ thống.
- **Đồng hồ**: giờ ở trạng thái thu gọn, đồng hồ lớn + thứ/ngày khi mở rộng mà không có nhạc.

## Cấu hình

Lưu ở `%APPDATA%\DynamicIsland\config.json` (vị trí island, trạng thái ghim, luôn trên cùng).
Xoá file này để về mặc định.

## Gỡ

1. Chuột phải lên island → **Thoát**.
2. Tắt "Khởi động cùng Windows" trong menu tray.
3. Xoá thư mục này và `%APPDATA%\DynamicIsland`.

## Ghi chú kỹ thuật

- Cửa sổ là `QWidget` frameless + `WA_TranslucentBackground`, toàn bộ vẽ bằng `QPainter`
  (bo góc, gradient, bóng đổ blur, icon vector) nên không có file ảnh nào.
- Hoạt cảnh bung/thu là `QVariantAnimation` nội suy đồng thời kích thước và bán kính góc
  (360 ms, OutExpo).
- Nền + bóng đổ được render một lần rồi cache thành `QPixmap` theo kích thước/màu nhấn; mỗi
  khung hình chỉ blit lại, nên lúc phát nhạc CPU ~1–2% (một nhân).
- Nhịp vẽ tự thích ứng: 30 fps khi đang chớp mắt / chạy chữ / rê chuột, 15 fps khi chỉ có sóng
  nhạc, 1 fps khi rảnh.
- **Chế độ tĩnh / tối ưu foreground**: theo dõi cửa sổ đang chiếm foreground qua `GetClassNameW`
  (mỗi 400 ms). Nếu là ứng dụng thật (không phải desktop/traybar) → đông cứng, chỉ vẽ lại khi
  phút đổi hoặc rê chuột vào. Giúp CPU gần như 0% khi đang làm việc ở app khác.
- `media.py` và `notify.py` chạy trong `QThread` riêng, mỗi thread có asyncio loop cho WinRT;
  giao tiếp với UI qua `Signal`.
- Chạy `python main.py` để xem log; `python snapshot.py` để xuất ảnh từng trạng thái vào `preview/`.
- Cần soi kỹ sự kiện chuột / lệnh media / chuyển trạng thái: đặt `ISLAND_DEBUG=1` rồi chạy,
  log ghi vào `%APPDATA%\DynamicIsland\debug.log`.

## Giấy phép

MIT — xem [LICENSE](LICENSE).
