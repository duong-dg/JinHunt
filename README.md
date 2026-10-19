# JinHunt

Ứng dụng đoán địa điểm qua ảnh. MVP gồm FastAPI và giao diện web responsive tiếng Việt, dùng chung API cho client iOS/Android tương lai.

Trang chủ hiển thị feed ảnh lớn, thanh điều hướng bên trái và hồ sơ/XP/bảng xếp hạng ở bên phải trên desktop. Tablet thu gọn bố cục; điện thoại dùng thanh điều hướng dưới cùng. Mỗi bài có nút đoán địa điểm và mở phần trao đổi. Feed tải 12 bài mỗi lượt, có nút xem thêm. Chưa có tính năng theo dõi, thả tim hoặc nhắn tin.

Form đăng ảnh và dự đoán có nút **Lấy vị trí hiện tại**, không cần nhập vĩ độ/kinh độ. Trình duyệt chỉ xin quyền định vị sau khi bấm nút. Dùng vị trí máy khi đang ở đúng địa điểm trong ảnh; ảnh chụp nơi khác có thể chỉ dùng đáp án tên. Có thể bỏ vị trí, hủy đang lấy hoặc thử lại khi bị từ chối quyền/GPS kém. Sai số trên 150 m không được đính kèm. Vị trí chỉ gửi cùng thao tác đăng bài/dự đoán, không hiện trên feed. GPS trên web cần **HTTPS** (ngoại lệ localhost khi phát triển); HTTP qua IP server không dùng được định vị. Đây không phải bằng chứng chống giả GPS.

Cửa sổ có nút Đóng lớn, hỗ trợ Escape và bấm nền bên ngoài để đóng. Đóng cửa sổ không tự gửi hay lưu form; dữ liệu đang nhập được giữ trong cửa sổ của tab để có thể mở lại. Chữ ô nhập 16px; palette cyan–aqua với nền kem nhẹ.

Trong Hồ sơ, chọn ảnh đại diện để tải lên và lưu ngay, hoặc Xóa ảnh để trở về chữ cái mặc định. Avatar tối đa 8 MB, tự cắt vuông 512×512 và xóa metadata. Avatar xuất hiện trên feed, bình luận và bảng xếp hạng; tên hiển thị được ưu tiên, thiếu thì dùng username. API ảnh đại diện: `POST /api/me/avatar` (multipart `file`) và `DELETE /api/me/avatar`; đều yêu cầu token. Cột avatar được tự thêm vào database khi khởi động. Ảnh đã thay/xóa khỏi hồ sơ vẫn còn file trong storage; chưa có tác vụ dọn file không còn dùng.

Thông báo dùng Popover API để nổi trên cả cửa sổ modal, có nút đóng riêng. Lỗi màu cam đỏ giữ 12 giây, thông báo khác 7 giây; lỗi thao tác form còn hiển thị ngay trước nút gửi để đọc lại. Nút chính dùng gradient xanh ngọc–xanh biển, điểm XP vàng nhẹ.

## Chạy bằng Docker

```sh
git clone https://github.com/duong-dg/JinHunt.git
cd JinHunt
cp .env.example .env
# Đổi POSTGRES_PASSWORD trong .env thành chuỗi ngẫu nhiên chỉ gồm chữ và số.
docker compose up -d --build
```

PowerShell: dùng `Copy-Item .env.example .env` thay cho `cp` nếu cần.

Mở http://localhost:8000; tài liệu API: http://localhost:8000/docs.
Docker Compose tạo PostgreSQL mới và lưu ảnh trong volume riêng. Database không mở cổng ra ngoài.

## Chạy local không cần Docker

Python 3.12 trở lên:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Mặc định dùng SQLite (`jinhunt.db`), ảnh trong `uploads/`. Có thể đặt biến môi trường `DATABASE_URL` để chuyển PostgreSQL và `UPLOAD_DIR` để đổi thư mục ảnh.

## Luồng chơi

1. Đăng ký tài khoản (username không dấu 3–30 ký tự, mật khẩu ít nhất 8 ký tự, email hoặc số điện thoại). Đăng nhập bằng username/email/SĐT. Số Việt Nam bắt đầu bằng 0 được chuẩn hóa sang +84; số quốc tế cần mã quốc gia.
2. Tải ảnh, nhập tiêu đề, gợi ý và tên đáp án bí mật. Tọa độ là tùy chọn.
3. Người khác đoán bằng tên (không phân biệt hoa/thường và dấu tiếng Việt) hoặc tọa độ trong bán kính 150 m mặc định.
4. Đoán đúng nhận 50 XP một lần duy nhất. Người tạo không được tự giải. Mỗi 200 XP lên một level.
5. Bình luận công khai; bình luận có chứa đầy đủ tên đáp án được che, kể cả trong API. Các biến thể/cách nói gián tiếp chưa được nhận diện.

API không trả đáp án/tọa độ đích, kể cả sau khi đoán đúng. Không trả khoảng cách để tránh dò vị trí. Dự đoán giới hạn 10 lần/phút/tài khoản. Ảnh tối đa 8 MB, được mã hóa lại JPEG và bỏ metadata GPS. Token đăng nhập lưu dưới dạng hash phía server, hết hạn sau 7 ngày; web giữ token trong sessionStorage của tab.

## Kiểm thử

```sh
python -m pytest -q
node --check app/static/app.js
```

## Cấu trúc

```text
app/main.py       API, xác thực, xử lý ảnh và luật chơi
app/models.py     User, Token, Case, Solve, Comment, Attempt
app/database.py   SQLite/PostgreSQL và session
app/static/       Giao diện web HTML/CSS/JavaScript
tests/            Kiểm thử tích hợp
docker-compose.yml  API + PostgreSQL + volumes
```

## Phạm vi và triển khai

Đây là MVP web và API, chưa có binary iOS/Android hay bản đồ tương tác. Chưa triển khai lên máy chủ thật. Trước khi mở công khai, cần HTTPS qua reverse proxy, giới hạn request/body tại proxy, sao lưu DB/ảnh, kiểm duyệt/báo cáo nội dung, chống spam đăng ký/đăng ảnh/bình luận, quên mật khẩu và chính sách quyền riêng tư. Hiện chỉ cộng XP cho đoán đúng; điểm tương tác chưa bật để tránh khuyến khích spam.

Schema đã thay đổi so với bản check-in ban đầu. `create_all` chỉ tạo bảng mới, không migrate bảng cũ. Không dùng trực tiếp với database cũ: sao lưu và tạo database mới, hoặc viết migration trước khi nâng cấp. Compose dùng volume `postgres_data` mới và không xóa volume `jinhunt_postgres_data` trước đây.

Không commit `.env`, database, token hay ảnh người dùng. Giữ bản sao lưu riêng của các volume khi chuyển máy chủ.

## Hồ sơ và nâng cấp từ MVP

Nhấn tên tài khoản trên thanh đầu trang để sửa tên hiển thị, giới thiệu, email/SĐT hoặc đăng xuất. `GET /api/me` và `PATCH /api/me` yêu cầu token, chỉ trả thông tin liên hệ cho chính người dùng. Email/SĐT là duy nhất và chưa xác minh, không dùng để khôi phục mật khẩu hay tự động liên kết tài khoản xã hội. Đăng ký mới cần ít nhất một thông tin liên hệ; tài khoản cũ được giữ nguyên và bổ sung ở Hồ sơ.

Bản cập nhật này tự động thêm các cột hồ sơ và bảng `external_identities` khi khởi động, áp dụng cho schema MVP trong commit `8973c8a`, không xóa dữ liệu. Chạy nâng cấp khi chỉ có một tiến trình API (Compose mặc định). Sao lưu trước khi nâng cấp; không dùng `docker compose down -v`.

```sh
git pull --ff-only
docker compose up -d --build
docker compose logs --tail=100 api
```

Cấu trúc danh tính ngoài có khóa duy nhất `(provider, subject)` và `(user_id, provider)` để tích hợp Google/Facebook sau. Hiện chưa có OAuth, nút đăng nhập Google/Facebook, xác nhận email hay SMS OTP. Khi tích hợp cần cấu hình app/redirect URI từ nhà cung cấp, kiểm tra token/issuer/audience/nonce/state phía server và chỉ liên kết qua phiên người dùng đã xác thực; không tự ghép bằng email chưa xác minh.
