# Mã xác minh email

## Cấu hình

Luồng dùng SMTP đã cấu hình trong `.env` trên server, ví dụ tài khoản Zoho:

```dotenv
SMTP_HOST=smtppro.zoho.com
SMTP_PORT=465
SMTP_SECURITY=ssl
SMTP_FROM=JinHunt <jinhunt@jinhunt.io.vn>
SMTP_USER=jinhunt@jinhunt.io.vn
SMTP_PASSWORD=MAT_KHAU_SMTP_RIENG
PUBLIC_BASE_URL=https://TEN_MIEN_APP
```

Không đưa mật khẩu thật vào Git. Nếu Zoho bật 2FA, dùng mật khẩu ứng dụng theo cấu hình tài khoản Zoho. Máy chủ SMTP phụ thuộc gói/trung tâm dữ liệu; thông số nêu trên là cấu hình đã kiểm tra đăng nhập với tài khoản hiện tại, chưa phải kiểm chứng thư đi vào inbox của từng nhà cung cấp.

Có thể đặt thêm `EMAIL_CODE_KEY` là chuỗi ngẫu nhiên mạnh giữ riêng để bảo vệ mã trong database. Nếu để trống, app dùng `SMTP_PASSWORD` làm khóa HMAC. Thay khóa hoặc mật khẩu SMTP có thể khiến mã đang chờ hết hiệu lực; yêu cầu mã mới. Không dùng mã 6 số làm giá trị khóa. `.env` thật không được đưa lên Git và không tự thay đổi khi pull.

```bash
sudo docker compose up -d --build
```

## Người dùng

- Đăng ký người lớn bằng email: điền địa chỉ → **Gửi mã xác minh email** → chọn nhập 6 số hoặc mở liên kết trong thư → hoàn tất đăng ký. Liên kết chỉ được thêm khi `PUBLIC_BASE_URL` là địa chỉ HTTPS cố định, đúng tên miền app; nếu chưa cấu hình thì vẫn dùng mã. Không lấy domain từ Host header của request. Chưa xác minh thì backend chưa tạo tài khoản bằng email đó.
- Mã có hiệu lực **10 phút**, thử tối đa **5 lần**, chỉ dùng một lần. Chứng minh xác minh đăng ký bị ràng buộc đúng địa chỉ, có thời hạn và chỉ dùng một lần.
- Đổi email: nhập email mới trong Hồ sơ → gửi và xác minh mã. Địa chỉ cũ còn hiệu lực đến khi nhập đúng mã; xác minh thành công mới thay địa chỉ. Lưu hồ sơ bằng đường `PATCH /api/me` không bỏ qua được bước xác minh này.
- Email tài khoản cũ không tự được đánh dấu đã xác minh. Trong Hồ sơ có thể gửi mã cho địa chỉ hiện tại và xác minh mà không đổi địa chỉ.
- Tài khoản do phụ huynh quản lý tiếp tục dùng liên kết xác nhận người đại diện. Không tự đổi email quản lý qua OTP chung; gửi yêu cầu hỗ trợ để kiểm tra quyền quản lý.
- Đăng ký chỉ bằng số điện thoại vẫn là nhánh hiện có; chưa có SMS OTP và không được đánh dấu đã xác minh số điện thoại.
- Mã email dùng để xác minh quyền truy cập hộp thư; không phải đăng nhập không mật khẩu, đặt lại mật khẩu hay xác thực danh tính pháp lý. OTP quản trị vẫn là mã từ ứng dụng Authenticator, độc lập với luồng email.

## Giới hạn và bảo vệ

- Giao diện cho gửi lại sau 60 giây. Backend giới hạn một yêu cầu/địa chỉ/cửa sổ phút cố định, tối đa 5 yêu cầu/địa chỉ/cửa sổ giờ và 20 yêu cầu/IP/15 phút. Nhập mã giới hạn thêm 50 lượt/IP/15 phút, đồng thời mỗi mã chỉ có 5 lượt thử.
- Gửi lại thành công vô hiệu mã/bằng chứng cũ của cùng luồng. Gửi SMTP lỗi không đánh dấu email đã xác minh, không tạo tài khoản; lỗi vẫn có thể tiêu thụ hạn mức yêu cầu.
- Mã không lưu thô trong DB, chỉ lưu HMAC gắn với địa chỉ, mục đích và challenge. Token chứng minh đăng ký ngẫu nhiên chỉ lưu bản băm; token phía trình duyệt giữ trong bộ nhớ khi dùng mã. Với liên kết, trang xác minh lưu biên nhận ngắn hạn trong sessionStorage để tiếp tục đăng ký ở cùng tab, và thông báo cho tab đăng ký cùng trình duyệt qua BroadcastChannel; không đưa biên nhận vào URL hoặc localStorage. Backend vẫn kiểm tra thời hạn và dùng một lần.
- Mã đổi email gắn với phiên/tài khoản người yêu cầu, không dùng cho tài khoản khác hoặc đổi sang mục đích đăng ký. Thao tác nhập đúng mã và nhận bằng chứng được bảo vệ bằng cập nhật DB nguyên tử.
- Hết hạn mã không đồng nghĩa bản ghi đã xóa vật lý. Chưa có lịch tự xóa bảng `email_verifications`; vận hành phải đưa bản ghi này vào chính sách lưu trữ/xóa dữ liệu. Không ghi mã vào access log, phản hồi API hoặc ticket hỗ trợ.
- Các kiểm thử tự động dùng SMTP giả lập. Không tự gửi thư thử tới người dùng thật khi chạy test; kiểm tra thực tế gửi/nhận cần được thực hiện với hộp thư do người vận hành kiểm soát.

## Liên kết và trải nghiệm đăng ký

Liên kết xác minh chứa token ngẫu nhiên trong fragment, không phải query string. Trang xóa fragment khỏi URL và chỉ xác nhận khi người dùng bấm nút, tránh email scanner tải trang làm mất lượt dùng. Dùng mã hoặc liên kết đều vô hiệu cách còn lại. Email được xác minh chưa tự tạo tài khoản hay phiên đăng nhập; người dùng vẫn hoàn tất thông tin, mật khẩu và chủ động đồng ý chính sách ở form đăng ký.

Có thể quay lại tab đăng ký đang mở sau khi xác minh liên kết. Nếu không có tab đó, chọn Tiếp tục đăng ký trong cùng trình duyệt và điền thông tin; bằng chứng được xóa khi hoàn tất/reset form. Nếu mở liên kết trong trình duyệt khác thì dùng tiếp ở trình duyệt đó hoặc yêu cầu mã mới; không gửi mật khẩu giữa các tab hay thiết bị.

Sau khi tài khoản đã đồng ý phiên bản hiện tại, giao diện không tự mở lại form điều khoản và không bắt tick cam kết ảnh ở mỗi bài/avatar. Khi đăng/chọn ảnh, vẫn có lời nhắc trách nhiệm và backend kiểm tra tài khoản hợp lệ, lưu dấu hành động đăng ảnh theo điều khoản. Việc rút đồng ý, tài khoản chưa từng đồng ý hoặc cần xác nhận phiên bản mới vẫn xử lý theo cơ chế backend hiện có; không tự ghi đồng ý thay người dùng.
