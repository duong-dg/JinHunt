# Hồ sơ, kết nối và khôi phục tài khoản

## Khôi phục mật khẩu

Bấm Quên mật khẩu ở hộp đăng nhập, nhập email đã xác minh, nhận mã 6 số, đặt mật khẩu mới. Mã dùng một lần, có hiệu lực 10 phút, tối đa 5 lần thử. Dùng cùng SMTP và EMAIL_CODE_KEY đã cấu hình cho xác minh email. Sau khi đổi, mọi token đăng nhập cũ bị thu hồi; cần đăng nhập lại. Mã xác minh đăng ký không dùng để đổi mật khẩu và ngược lại.

Chỉ hỗ trợ email đã xác minh của tài khoản user đang hoạt động (bao gồm hộp thư quản lý đã xác minh của tài khoản do người đại diện quản lý). Không tự đánh dấu email cũ là đã xác minh, không khôi phục bằng số điện thoại. Tài khoản kiểm duyệt/admin không dùng luồng công khai này. Phản hồi yêu cầu gửi mã giống nhau cho email không tồn tại hoặc không đủ điều kiện; lỗi SMTP không tiết lộ email có tài khoản hay không và được ghi log không kèm email/mã. Giới hạn gửi mã dùng chung với đăng ký và đổi email: chờ 60 giây, tối đa 5 lần/email/giờ và 20 lần/IP/15 phút.

## Hồ sơ và theo dõi

Bấm avatar hoặc tên để xem hồ sơ và bài đã công khai, theo dõi/bỏ theo dõi, xem danh sách người theo dõi/đang theo dõi. Hồ sơ người khác không trả về email, điện thoại, ngày sinh hay thông tin đồng ý. Bài chờ duyệt/gỡ không xuất hiện. Chọn Đang theo dõi bên cạnh tìm kiếm để xem bảng tin của các tài khoản đã theo dõi. Theo dõi không cộng XP.

## Tìm kiếm và lưu bài

Tìm theo tiêu đề/gợi ý công khai, không tìm theo đáp án bí mật. Ký tự % và _ được coi là ký tự thường, không phải wildcard. Tìm kiếm hiện không hỗ trợ gõ không dấu để khớp chữ có dấu.

Bấm Lưu trên bài, vào Đã lưu để xem lại; bấm lần nữa để bỏ lưu. Danh sách lưu riêng theo tài khoản và không cộng điểm. Bài bị gỡ, tác giả dừng tài khoản hoặc bị chặn không hiển thị trong danh sách. Phân trang cho danh sách bài/hồ sơ/lưu và danh sách người.

## Chặn và báo cáo bình luận

Nút Chặn nằm trên hồ sơ người khác, có bước xác nhận. Danh sách và nút Bỏ chặn ở Chỉnh sửa hồ sơ → Tài khoản đã chặn. Chặn xóa quan hệ theo dõi hai chiều, ẩn bài, bình luận và thông báo từ người bị chặn; hai bên không mở hồ sơ hoặc tương tác bài của nhau trong các phiên đăng nhập. Bỏ chặn không tự theo dõi lại. Danh sách chặn chỉ chủ tài khoản thấy.

Chặn là công cụ trải nghiệm trong tài khoản; bài công khai vẫn có thể được xem khi đăng xuất. Chặn không thu hồi ảnh đã tải hay ngăn nhân sự có quyền kiểm duyệt xử lý nội dung.

Bình luận có nút Báo cáo. Báo cáo riêng cho người kiểm duyệt, không công khai người gửi. Trong /staff, kiểm duyệt viên có thể giữ bình luận/đóng báo cáo hoặc gỡ bình luận kèm lý do được ghi audit. Bình luận bị gỡ chỉ còn thông báo chung, không lộ nội dung đáp án kể cả người đã giải đúng hoặc chủ bài. Không tự gỡ chỉ vì có người báo cáo.

## Triển khai

Các bảng follows, user_blocks, bookmarks, comment_reports và cột comments.is_removed được tạo/thêm tự động khi khởi động phiên bản mới; không cần xóa dữ liệu. API trả Cache-Control: no-store vì có dữ liệu phụ thuộc tài khoản. Không thay đổi cơ chế xác nhận điều khoản, quyền quản trị hoặc luồng người đại diện.


## Thông báo theo dõi mới

Theo dõi tạo thông báo trong app cho người được theo dõi, không gửi email/push hệ điều hành. Những người theo dõi mới được gộp thành một nhóm, tên mới nhất đứng đầu; bấm nhóm mở hồ sơ người mới nhất, bấm tên/avatar cụ thể mở đúng hồ sơ đó. Trạng thái chưa đọc tính theo nhóm, đánh dấu đã đọc theo mốc đã xem. Theo dõi lặp, bỏ rồi theo dõi lại không tạo thông báo mới cho cùng cặp người dùng. Không tạo thông báo ngược cho lượt theo dõi đã có trước khi nâng cấp. Người bị chặn không xuất hiện trong nhóm.

notifications.case_id được đổi thành nullable để thông báo theo dõi không cần bài viết giả. PostgreSQL dùng ALTER COLUMN; SQLite chuyển bảng có bảo toàn ID, nội dung và trạng thái đã đọc rồi tạo lại index. Chạy lại migration không tạo bản sao thông báo.


## Cài đặt cá nhân

Mở icon bánh răng ở góc trên bên phải thẻ hồ sơ của mình. Menu có bảng tin Đang theo dõi, Đổi mật khẩu, Tài khoản đã chặn; công tắc Chế độ tối luôn ở cuối. Công tắc lưu chế độ sáng/tối trên trình duyệt, không đổi dữ liệu tài khoản. Trước khi chọn lần đầu, giao diện vẫn theo thiết bị.

Đổi mật khẩu khi đăng nhập yêu cầu mật khẩu hiện tại, mật khẩu mới tối thiểu 8 ký tự và nhập lại cho khớp. Sau khi đổi, thu hồi mọi token cũ và mã khôi phục chưa dùng. Quy trình tài khoản quản trị vẫn tách riêng. API POST /api/me/password không chấp nhận đổi mật khẩu bằng thông tin công khai.


## Giao diện mở rộng và thiết bị đăng nhập

Đang theo dõi hiển thị ngoài cài đặt, dưới thanh tìm kiếm. Bấm số Người theo dõi / Đang theo dõi trên hồ sơ để mở danh sách tương ứng, cả hồ sơ của mình và người khác.

Cài đặt chia ba nhóm: Giao diện, Bảo mật & quyền riêng tư, Quản lý thiết bị. Giao diện có công tắc tối, mẫu Biển xanh/Hồng/Chibi và phông mặc định/bo tròn/có chân. Chibi là kiểu pastel với góc bo và nền họa tiết; không tải ảnh hoặc phông từ bên thứ ba. Lưu lựa chọn bằng localStorage trên thiết bị, không tự đồng bộ qua tài khoản.

Thiết bị là từng phiên đăng nhập của trình duyệt, không phải định danh vật lý chắc chắn. Tên thiết bị suy ra từ User-Agent. Lưu thời điểm đăng nhập, hoạt động gần nhất (cập nhật tối đa mỗi 5 phút), IP và thời hạn phiên trong login_sessions. Không trả token/token_hash cho giao diện. Chủ tài khoản có thể đăng xuất từng phiên hoặc tất cả phiên khác. Phiên kết thúc vẫn hiện trong lịch sử; không tự xóa lịch sử trong bản này.

Vị trí hiện hiển thị IP và trạng thái mạng nội bộ/chưa xác định địa điểm. Không giả tên thành phố, không tự bật GPS và không gửi IP tới dịch vụ GeoIP bên ngoài. Khi có reverse proxy, địa chỉ ASGI phụ thuộc cấu hình tin cậy proxy của Uvicorn/hạ tầng; ứng dụng không tự tin X-Forwarded-For do client gửi. Nếu IP chỉ là IP Docker/proxy, cần cấu hình proxy tin cậy đúng với môi trường triển khai; không mở tin cậy mọi nguồn tùy tiện.

Phiên cũ được ghi nhận ở lần sử dụng sau nâng cấp, thời điểm đăng nhập để trống vì không có dữ liệu lịch sử; IP/thiết bị là thông tin quan sát lần đó. Không truy dựng nơi đăng nhập cũ. Các lần đăng nhập/đăng ký mới được ghi ngay khi cấp token. Bảng mới tạo tự động khi khởi động.


### Mở khóa giao diện theo cấp

Mặc định mọi tài khoản và khách chỉ dùng Biển xanh với phông mặc định, có thể bật/tắt tối. Từ Level 20, API tài khoản trả can_customize_appearance=true và mở các màu Hồng/Chibi cùng lựa chọn phông. Đây là tùy chỉnh hiển thị cục bộ, không phải cơ chế bảo vệ dữ liệu hay phần thưởng XP. Theme/font đã lưu không được áp dụng trước khi xác nhận cấp từ server; đăng xuất hoặc dùng tài khoản chưa đủ cấp sẽ trở về giao diện mặc định, vẫn giữ lựa chọn sáng/tối. Mốc mở khóa trả về ở appearance_unlock_level.


### IP public sau reverse proxy

Compose truyền `FORWARDED_ALLOW_IPS` cho Uvicorn để chỉ tin header từ proxy đã cấu hình. Trong `.env`, đặt IP nguồn của proxy mà container API thực sự nhìn thấy (có thể là gateway Docker); không đặt IP của người chơi và không dùng `*`. Có thể khai báo nhiều IP, phân cách dấu phẩy. Không tự mặc định tin toàn bộ mạng Docker.

Nếu Nginx chạy trực tiếp trên cùng Ubuntu và nhận kết nối từ người dùng, dùng `API_BIND_ADDRESS=127.0.0.1` để cổng 8000 chỉ phục vụ nội bộ. Trong location chuyển tiếp API:

```nginx
proxy_pass http://127.0.0.1:8000;
proxy_set_header Host $host;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
```

Nginx ghi đè X-Forwarded-For bằng địa chỉ kết nối thực, tránh nhận IP giả do khách tự gửi. Nếu có Cloudflare/CDN hoặc nhiều lớp proxy, cần cấu hình real_ip và danh sách IP tin cậy tương ứng trước; không áp dụng mẫu một lớp để suy ra IP người chơi qua CDN.

Sau khi cấu hình, chạy `sudo docker compose up -d --build`, đăng xuất rồi đăng nhập lại và kiểm tra Quản lý thiết bị. Bản ghi lịch sử đã lưu IP gateway giữ nguyên vì không thể khôi phục IP public cũ. IP public có thể dùng chung giữa nhiều thiết bị và không xác định chắc chắn địa chỉ nhà hay thành phố.
