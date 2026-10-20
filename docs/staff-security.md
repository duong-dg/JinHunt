# Đăng nhập quản trị JinHunt

## Đường dẫn và bảo vệ

- Người chơi dùng đăng nhập thường. Staff dùng **`/staff/login`**, nhập tên đăng nhập, mật khẩu và 6 số từ ứng dụng Authenticator. Bảng kiểm duyệt ở **`/staff`**.
- Đường dẫn không phải bí mật và không thay thế bảo vệ API. Tài khoản không có quyền hoặc staff chưa xác thực OTP không vào được công cụ duyệt, kể cả gọi API trực tiếp.
- Phiên staff là cookie **HttpOnly, SameSite=Strict, Secure**, thời hạn tuyệt đối **8 giờ**, không trả token ra JavaScript và không lưu phiên staff trong localStorage. Khóa tài khoản, đổi quyền hoặc đặt lại OTP thu hồi mọi phiên.
- API thay đổi dữ liệu bằng cookie yêu cầu header `X-JinHunt-Staff: 1`; trang staff gửi header này. CORS không mở cho website ngoài. Trang staff không được nhúng iframe, dùng CSP và `Cache-Control: no-store`.
- Mã TOTP chu kỳ 30 giây, chấp nhận lệch tối đa một chu kỳ. Mã đã dùng không được dùng lại, kể cả gửi đồng thời. OTP không chống được mọi hình thức phishing; không nhập mã trên tên miền lạ.

## Thiết lập lần đầu trên Ubuntu

1. Tạo một khóa Fernet ngẫu nhiên trên **server**, không gửi khóa vào chat:

```bash
python3 -c 'import os,base64; print("STAFF_TOTP_KEY="+base64.urlsafe_b64encode(os.urandom(32)).decode())'
```

2. Sao chép dòng đó vào `.env` thật, chỉ giữ một giá trị `STAFF_TOTP_KEY`. Giữ `STAFF_COOKIE_SECURE=1`, bảo vệ `.env`, không commit. Sao lưu khóa riêng khỏi database và giới hạn người được truy cập. Thiếu khóa không ảnh hưởng đăng nhập người chơi nhưng không thiết lập/đăng nhập staff được.

3. Cập nhật và chạy lại app:

```bash
git pull origin main
sudo docker compose up -d --build
```

4. Dùng tài khoản người lớn đang hoạt động đã đăng ký, cấp quyền và thêm OTP từ terminal tin cậy:

```bash
sudo docker compose exec api python -m app.manage_staff TEN_DANG_NHAP admin --setup-2fa
```

Lệnh hiện **setup key riêng tư** để nhập thủ công vào Google Authenticator, Microsoft Authenticator, Aegis hoặc ứng dụng TOTP tương thích. Chọn loại theo thời gian, nhập mã 6 số để xác nhận trên terminal. Không đưa key vào website tạo QR công khai, bình luận, ảnh chụp hoặc ticket hỗ trợ. Lệnh không ghi key thô vào database: key được mã hóa bằng Fernet; database lưu bộ đếm chống sử dụng lại mã. Sau khi thiết lập hãy chờ mã kế tiếp để đăng nhập.

Với kiểm duyệt viên thay `admin` bằng `moderator`. Muốn thu hồi quyền, chạy cùng lệnh với `user` (không thêm `--setup-2fa`). Không có admin hoặc mật khẩu mặc định.

5. Mở **`https://TEN_MIEN/staff/login`**. Nếu trước đó đang dùng phiên staff ở trang người chơi, phiên đó không còn đủ quyền; đăng nhập lại tại cổng riêng. Tài khoản staff không lấy được phiên bằng đăng nhập người chơi.

## HTTPS và reverse proxy

Production yêu cầu HTTPS. Đăng nhập staff qua HTTP bị từ chối, cookie Secure cũng không gửi qua HTTP. Reverse proxy cần chuyển đúng scheme HTTPS đến Uvicorn; chỉ tin forwarded headers từ IP proxy do bạn kiểm soát, không bật tin mọi IP trên cổng API public. Nếu mọi lượt bị coi là cùng IP proxy, cần sửa cấu hình proxy tin cậy thay vì bỏ giới hạn đăng nhập.

Chỉ để thử nghiệm trên máy cục bộ mới dùng `STAFF_COOKIE_SECURE=0`; không cấu hình này trên server Internet. Không đưa mật khẩu/OTP vào query string. Đồng bộ giờ server (NTP) và điện thoại để OTP hoạt động.

## Giới hạn thử đăng nhập

Áp dụng chung cổng thường và cổng staff, dùng bảng `login_buckets` nên chia sẻ giữa các worker và tồn tại qua lần restart:

- Tối đa **8 lần thử / định danh / cửa sổ 15 phút**.
- Tối đa **8 lần thử / tài khoản / cửa sổ 15 phút**, gộp cả khi đổi giữa username, email và số điện thoại.
- Tối đa **50 lần thử / IP / cửa sổ 15 phút**.

Đếm cả lượt thử thành công, không chỉ mật khẩu sai. Trả HTTP 429 kèm `Retry-After` khi vượt ngưỡng; hết cửa sổ có thể thử lại. Đây là cửa sổ cố định, không phải khóa vĩnh viễn. Không dùng `X-Forwarded-For` tùy ý từ request để lấy IP; địa chỉ là `request.client` do ASGI/proxy tin cậy xác định. Dữ liệu bucket dùng khóa băm và tự dọn các bucket cũ khi có lượt đăng nhập tiếp theo.

Cần theo dõi và bổ sung giới hạn mạng/WAF tại reverse proxy khi lượng truy cập tăng; ứng dụng không hứa ngăn mọi cuộc tấn công phân tán. Việc đạt giới hạn có thể tạm chặn cả người thật; không khôi phục bằng cách xóa database hoặc bỏ OTP.

## Mất điện thoại / đổi khóa

Khôi phục chỉ qua người có quyền vào terminal server:

```bash
sudo docker compose exec api python -m app.manage_staff TEN_DANG_NHAP admin --reset-2fa
```

Lệnh phát key mới, yêu cầu xác nhận mã mới và thu hồi phiên cũ. Không có API công khai tắt OTP, không có mã dự phòng mặc định. Vì vậy phải bảo vệ truy cập SSH và quy trình xác minh người đề nghị khôi phục. Nếu mất `STAFF_TOTP_KEY`, cần khôi phục bản sao hoặc cấp key mới và đặt lại OTP cho từng staff; không đơn thuần thay key mỗi lần deploy.

Các lần đăng nhập staff thành công, cấp/thu hồi quyền và thiết lập/đặt lại OTP được ghi vào `moderation_audits`. Không ghi mật khẩu hoặc mã OTP thô. Bộ đếm đăng nhập là dữ liệu vận hành, không thay thế hệ thống giám sát an ninh.

Tham khảo triển khai: [PyOTP: HTTPS, bảo vệ secret, chống dùng lại mã và giới hạn thử](https://pyauth.github.io/pyotp/), [Fernet](https://cryptography.io/en/latest/fernet/).
