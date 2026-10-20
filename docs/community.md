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
